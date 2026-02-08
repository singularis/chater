import json
import logging
import os
import time as time_module

from confluent_kafka import Consumer, KafkaError

from dev_utils import get_kafka_group_id

logger = logging.getLogger("kafka_consumer")


def validate_user_data(message_data, expected_user_email=None):
    """Validate that the message belongs to the expected user."""
    try:
        # If message_data is a string, try to parse it as JSON
        if isinstance(message_data, str):
            try:
                message_data = json.loads(message_data)
            except json.JSONDecodeError:
                logger.error("Failed to parse message as JSON")
                return False

        # Handle different message structures
        if isinstance(message_data, dict):
            # Get user_email from different possible locations
            message_user_email = None

            # Check root level
            if "user_email" in message_data:
                message_user_email = message_data.get("user_email")
            # Check value object
            elif "value" in message_data:
                value_obj = message_data.get("value", {})
                if isinstance(value_obj, dict):
                    message_user_email = value_obj.get("user_email")
                elif isinstance(value_obj, str):
                    try:
                        value_dict = json.loads(value_obj)
                        message_user_email = value_dict.get("user_email")
                    except json.JSONDecodeError:
                        pass

            if not message_user_email:
                logger.warning("No user_email found in message")
                return False

            if expected_user_email and message_user_email != expected_user_email:
                logger.warning(
                    f"User email mismatch. Expected: {expected_user_email}, Got: {message_user_email}"
                )
                return False

            return True
        else:
            logger.error(f"Unexpected message format: {type(message_data)}")
            return False
    except Exception as e:
        logger.error(f"Error validating user data: {str(e)}")
        return False


def consume_messages(topics, expected_user_email=None):
    logger.debug(
        f"Starting Kafka consumer with topics: {topics} for user: {expected_user_email}"
    )
    if not isinstance(topics, list):
        logger.error("Expected list of topic unicode strings")
        raise TypeError("Expected list of topic unicode strings")

    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv("BOOTSTRAP_SERVER"),
            "group.id": get_kafka_group_id("eater"),
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
            "max.poll.interval.ms": 300000,
        }
    )

    consumer.subscribe(topics)

    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                logger.debug(f"End of partition reached for topic {msg.topic()}")
                continue
            elif msg.error().code() == KafkaError.BROKER_NOT_AVAILABLE:
                logger.error("Broker not available. Retrying in 5 seconds...")
                time_module.sleep(5)
                continue
            elif msg.error().code() == KafkaError.INVALID_MSG_SIZE:
                logger.error(f"Message too large: {msg.error()}")
                continue
            else:
                logger.error(f"Consumer error: {msg.error()}")
                continue

        try:
            message_data = json.loads(msg.value())
            logger.debug(f"Received message: {message_data}")
            if not validate_user_data(message_data, expected_user_email):
                logger.warning(f"Skipping message for unexpected user: {message_data}")
                continue

            user_email = message_data.get("value", {}).get("user_email", "unknown")
            logger.info(
                f"Consumed message for user {user_email}: {msg.key()} - {msg.value()}"
            )
            yield msg, consumer
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message as JSON: {str(e)}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            continue
