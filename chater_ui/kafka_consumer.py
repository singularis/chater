import json
import logging
import os
import time

from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_config import setup_logging
from dev_utils import get_topics_list, get_kafka_group_id

setup_logging("kafka_consumer.log")
logger = logging.getLogger("kafka_consumer")

CONSUMER_POLL_TIMEOUT_SECONDS = 1.0
MAX_POLL_RETRIES = 5


def create_consumer(topics):
    if not isinstance(topics, list):
        logger.error("Expected list of topic unicode strings")
        raise TypeError("Expected list of topic unicode strings")

    bootstrap_servers = os.getenv("BOOTSTRAP_SERVER")
    if not bootstrap_servers:
        message = "BOOTSTRAP_SERVER environment variable is required for Kafka consumer"
        logger.error(message)
        raise RuntimeError(message)

    try:
        consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": get_kafka_group_id("chater"),
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
                "max.poll.interval.ms": 300000,
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


def consume_messages(consumer, expected_user_email=None):
    attempts = 0

    try:
        while True:
            try:
                msg = consumer.poll(CONSUMER_POLL_TIMEOUT_SECONDS)
            except KafkaException as e:
                error = e.args[0] if e.args else e
                attempts += 1
                if hasattr(error, "fatal") and error.fatal():
                    logger.error(
                        f"Fatal Kafka error while consuming: {error}"
                        " - stopping consumer"
                    )
                    raise

                if attempts > MAX_POLL_RETRIES:
                    logger.error(
                        "Exceeded maximum poll retries (%d) due to error: %s",
                        MAX_POLL_RETRIES,
                        error,
                    )
                    raise

                backoff = min(1 + attempts, 5)
                logger.warning(
                    "Kafka error while polling: %s. Retrying in %d seconds (attempt %d/%d)",
                    error,
                    backoff,
                    attempts,
                    MAX_POLL_RETRIES,
                )
                time.sleep(backoff)
                continue
            except Exception as e:
                attempts += 1
                if attempts > MAX_POLL_RETRIES:
                    logger.error(
                        "Exceeded maximum poll retries (%d) due to unexpected error: %s",
                        MAX_POLL_RETRIES,
                        e,
                    )
                    raise

                backoff = min(1 + attempts, 5)
                logger.error(
                    "Unexpected error while polling: %s. Retrying in %d seconds (attempt %d/%d)",
                    e,
                    backoff,
                    attempts,
                    MAX_POLL_RETRIES,
                )
                time.sleep(backoff)
                continue

            if msg is None:
                continue

            attempts = 0

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.info(
                        f"End of partition reached for topic {msg.topic()} partition {msg.partition()} offset {msg.offset()}"
                    )
                    continue
                if msg.error().fatal():
                    logger.error(f"Fatal consumer error: {msg.error()}")
                    raise KafkaException(msg.error())
                if msg.error().retriable():
                    logger.warning(
                        "Retriable consumer error: %s. Continuing to poll.", msg.error()
                    )
                    time.sleep(1)
                    continue
                if msg.error().code() == KafkaError.BROKER_NOT_AVAILABLE:
                    logger.error("Broker not available. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                if msg.error().code() == KafkaError.INVALID_MSG_SIZE:
                    logger.error(f"Message too large: {msg.error()}")
                    continue

                logger.error(f"Consumer error: {msg.error()}")
                continue

            try:
                message_data = json.loads(msg.value())
                value = message_data.get("value")
                user_email = (
                    value.get("user_email", "unknown")
                    if isinstance(value, dict)
                    else "unknown"
                )

                if expected_user_email and user_email != expected_user_email:
                    logger.debug(
                        "Skipping message for unexpected user %s when waiting for %s",
                        user_email,
                        expected_user_email,
                    )
                    continue

                logger.info(
                    f"Consumed message for user {user_email}: {msg.key()} - {msg.value()}"
                )
                yield msg
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message as JSON: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error processing message: {str(e)}")
                logger.debug("Processing error details", exc_info=True)

    except KafkaException as e:
        logger.error(f"Error while consuming messages: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise
    finally:
        consumer.close()
        logger.info("Consumer closed")
