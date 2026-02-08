import json
import logging
import os
import threading
import time

import redis
from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_config import setup_logging
from dev_utils import get_topics_list, get_kafka_group_id

setup_logging("kafka_consumer_service.log")
logger = logging.getLogger("kafka_consumer_service")

CONSUMER_RESTART_BACKOFF_SECONDS = 5
MAX_CONSUMER_ERROR_RETRIES = 5


class KafkaConsumerService:
    def __init__(self):
        self.redis_client = redis.StrictRedis(
            host=os.getenv("REDIS_ENDPOINT"), port=6379, db=0
        )
        self.consumers = {}
        self.is_running = False
        self.threads = []

        # Topics to consume from based on target configurations
        self.topic_configs = {
            "gpt-response": {"name": "gpt-response"},
            "gemini-response": {"name": "gemini-response"},
            "send_today_data": {"name": "send_today_data"},
            "send_today_data_custom": {"name": "send_today_data_custom"},
            "photo-analysis-response-check": {"name": "photo-analysis-response-check"},
            "delete_food_response": {"name": "delete_food_response"},
            "modify_food_record_response": {"name": "modify_food_record_response"},
            "add_auth_token": {"name": "add_auth_token"},
            "send_alcohol_latest": {"name": "send_alcohol_latest"},
            "send_alcohol_range": {"name": "send_alcohol_range"},
            "send_food_health_level": {"name": "send_food_health_level"},
        }

    def create_consumer(self, topics):
        """Create a Kafka consumer for specific topics"""
        if not isinstance(topics, list):
            logger.error("Expected list of topic unicode strings")
            raise TypeError("Expected list of topic unicode strings")

        bootstrap_servers = os.getenv("BOOTSTRAP_SERVER")
        if not bootstrap_servers:
            message = (
                "BOOTSTRAP_SERVER environment variable is required for Kafka consumer"
            )
            logger.error(message)
            raise RuntimeError(message)

        try:
            consumer = Consumer(
                {
                    "bootstrap.servers": bootstrap_servers,
                    "group.id": get_kafka_group_id("chater_background_service"),
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": True,
                    "max.poll.interval.ms": 300000,
                    "session.timeout.ms": 60000,
                    "heartbeat.interval.ms": 10000,
                    "socket.keepalive.enable": True,
                }
            )

            def on_assign(consumer, partitions):
                logger.info(f"Assigned partitions: {partitions}")

            def on_revoke(consumer, partitions):
                logger.info(f"Partitions revoked: {partitions}")

            topics = get_topics_list(topics)
            consumer.subscribe(topics, on_assign=on_assign, on_revoke=on_revoke)
            logger.info(f"Subscribed to topics: {topics}")
            return consumer
        except KafkaException as e:
            logger.error(f"Failed to create consumer: {str(e)}")
            raise

    def store_response_in_redis(self, message_uuid, response_data, user_email=None):
        """Store response in Redis with expiration"""
        try:
            # Store response for 10 minutes (600 seconds)
            self.redis_client.setex(
                f"kafka_response:{message_uuid}", 600, json.dumps(response_data)
            )

            # Also store with user-specific key if user_email is provided
            if user_email:
                self.redis_client.setex(
                    f"kafka_response_user:{user_email}:{message_uuid}",
                    600,
                    json.dumps(response_data),
                )

            logger.info(
                f"Stored response for message UUID: {message_uuid}"
                + (f" and user: {user_email}" if user_email else "")
            )
        except Exception as e:
            logger.error(f"Failed to store response in Redis: {str(e)}")

    def consume_topic_messages(self, topics):
        """Consume messages from specific topics continuously"""
        logger.info(f"Starting consumer worker for topics: {topics}")

        while self.is_running:
            consumer = None
            try:
                consumer = self.create_consumer(topics)
                self._consume_loop(consumer, topics)
            except Exception as e:
                if not self.is_running:
                    break

                logger.error(f"Error in consumer loop for topics {topics}: {str(e)}")
                logger.debug("Restarting consumer after error", exc_info=True)
                time.sleep(CONSUMER_RESTART_BACKOFF_SECONDS)
            finally:
                if consumer is not None:
                    try:
                        consumer.close()
                        logger.info(f"Consumer closed for topics: {topics}")
                    except Exception as close_error:
                        logger.warning(
                            f"Failed to close consumer cleanly for topics {topics}: {close_error}"
                        )

        logger.info(f"Stopping consumer worker for topics: {topics}")

    def _consume_loop(self, consumer, topics):
        consecutive_errors = 0

        while self.is_running:
            try:
                msg = consumer.poll(1.0)
            except KafkaException as e:
                error = e.args[0] if e.args else e
                consecutive_errors += 1
                if hasattr(error, "fatal") and error.fatal():
                    logger.error(
                        f"Fatal Kafka error encountered while polling topics {topics}: {error}"
                    )
                    raise

                logger.warning(
                    "Kafka error while polling topics %s: %s (attempt %d/%d)",
                    topics,
                    error,
                    consecutive_errors,
                    MAX_CONSUMER_ERROR_RETRIES,
                )

                if consecutive_errors >= MAX_CONSUMER_ERROR_RETRIES:
                    raise

                backoff = min(1 + consecutive_errors, CONSUMER_RESTART_BACKOFF_SECONDS)
                time.sleep(backoff)
                continue
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    "Unexpected error while polling topics %s: %s (attempt %d/%d)",
                    topics,
                    str(e),
                    consecutive_errors,
                    MAX_CONSUMER_ERROR_RETRIES,
                )
                logger.debug("Unexpected polling error details", exc_info=True)

                if consecutive_errors >= MAX_CONSUMER_ERROR_RETRIES:
                    raise

                backoff = min(1 + consecutive_errors, CONSUMER_RESTART_BACKOFF_SECONDS)
                time.sleep(backoff)
                continue

            if msg is None:
                continue

            consecutive_errors = 0

            if msg.error():
                error = msg.error()
                if error.code() == KafkaError._PARTITION_EOF:
                    logger.debug(
                        "End of partition reached for topic %s partition %s offset %s",
                        msg.topic(),
                        msg.partition(),
                        msg.offset(),
                    )
                    continue

                if error.fatal():
                    logger.error(
                        f"Fatal consumer error for topics {topics}: {error}. Restarting consumer"
                    )
                    raise KafkaException(error)

                if error.retriable():
                    logger.warning(
                        "Retriable consumer error for topics %s: %s", topics, error
                    )
                    time.sleep(1)
                    continue

                if error.code() == KafkaError.BROKER_NOT_AVAILABLE:
                    logger.error("Broker not available. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue

                if error.code() == KafkaError.INVALID_MSG_SIZE:
                    logger.error(f"Message too large: {error}")
                    continue

                logger.error(f"Consumer error: {error}")
                continue

            try:
                message_payload = msg.value()
                if message_payload is None:
                    logger.warning(
                        f"Received empty message payload on topic {msg.topic()}"
                    )
                    continue

                message_data = json.loads(message_payload.decode("utf-8"))
                logger.info(f"Received message on topic {msg.topic()}: {message_data}")

                # Extract message UUID from key or value
                message_uuid = msg.key().decode("utf-8") if msg.key() else None
                if not message_uuid and isinstance(message_data, dict):
                    message_uuid = message_data.get("key")

                if message_uuid:
                    # Store the response in Redis
                    response_value = (
                        message_data.get("value")
                        if isinstance(message_data, dict)
                        else message_data
                    )

                    # Extract user_email for user-specific storage
                    user_email = None
                    if isinstance(response_value, dict):
                        user_email = response_value.get("user_email")

                    self.store_response_in_redis(
                        message_uuid, response_value, user_email
                    )

                    logger.info(
                        f"Processed message UUID: {message_uuid} from topic: {msg.topic()}"
                        + (f" for user: {user_email}" if user_email else "")
                    )
                else:
                    logger.warning(f"No message UUID found in message: {message_data}")

                try:
                    consumer.commit(msg)
                except KafkaException as commit_error:
                    logger.error(
                        f"Commit failed for message {message_uuid} on topic {msg.topic()}: {commit_error}"
                    )
                    if commit_error.args and commit_error.args[0].fatal():
                        raise

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message as JSON: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                logger.debug("Processing error details", exc_info=True)

    def start_service(self):
        """Start the background consumer service"""
        if self.is_running:
            logger.warning("Service is already running")
            return

        self.is_running = True
        logger.info("Starting Kafka Consumer Service")

        # Start consumers for different topic groups
        all_topics = list(self.topic_configs.keys())

        # Create a single consumer thread for all response topics
        consumer_thread = threading.Thread(
            target=self.consume_topic_messages, args=(all_topics,), daemon=True
        )
        consumer_thread.start()
        self.threads.append(consumer_thread)

        logger.info("Kafka Consumer Service started successfully")

    def stop_service(self):
        """Stop the background consumer service"""
        logger.info("Stopping Kafka Consumer Service")
        self.is_running = False

        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5)

        self.threads.clear()
        logger.info("Kafka Consumer Service stopped")

    def get_response_from_redis(self, message_uuid, timeout=120):
        """Get response from Redis by message UUID"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response_data = self.redis_client.get(f"kafka_response:{message_uuid}")
                if response_data:
                    # Delete the response after retrieving it
                    self.redis_client.delete(f"kafka_response:{message_uuid}")
                    return json.loads(response_data.decode("utf-8"))
            except Exception as e:
                logger.error(f"Error retrieving response from Redis: {str(e)}")

            time.sleep(0.5)  # Poll every 500ms

        logger.warning(f"Timeout waiting for response for UUID: {message_uuid}")
        return None

    def get_user_response_from_redis(self, message_uuid, user_email, timeout=120):
        """Get response from Redis by message UUID for a specific user"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try user-specific key first
                response_data = self.redis_client.get(
                    f"kafka_response_user:{user_email}:{message_uuid}"
                )
                if response_data:
                    # Delete both user-specific and general keys
                    self.redis_client.delete(
                        f"kafka_response_user:{user_email}:{message_uuid}"
                    )
                    self.redis_client.delete(f"kafka_response:{message_uuid}")
                    return json.loads(response_data.decode("utf-8"))

                # Fallback to general key
                response_data = self.redis_client.get(f"kafka_response:{message_uuid}")
                if response_data:
                    parsed_data = json.loads(response_data.decode("utf-8"))
                    # Check if this response is for the correct user
                    if (
                        isinstance(parsed_data, dict)
                        and parsed_data.get("user_email") == user_email
                    ):
                        # Delete the response after retrieving it
                        self.redis_client.delete(f"kafka_response:{message_uuid}")
                        return parsed_data

            except Exception as e:
                logger.error(f"Error retrieving user response from Redis: {str(e)}")

            time.sleep(0.5)  # Poll every 500ms

        logger.warning(
            f"Timeout waiting for response for UUID: {message_uuid} and user: {user_email}"
        )
        return None


# Global service instance
kafka_service = KafkaConsumerService()


def start_kafka_consumer_service():
    """Start the global Kafka consumer service"""
    kafka_service.start_service()


def stop_kafka_consumer_service():
    """Stop the global Kafka consumer service"""
    kafka_service.stop_service()


def get_message_response(message_uuid, timeout=120):
    """Get message response from Redis"""
    return kafka_service.get_response_from_redis(message_uuid, timeout)


def get_user_message_response(message_uuid, user_email, timeout=120):
    """Get message response from Redis for a specific user"""
    return kafka_service.get_user_response_from_redis(message_uuid, user_email, timeout)
