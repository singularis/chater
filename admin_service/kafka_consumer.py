import json
import logging
import os
import time

from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_config import setup_logging
from dev_utils import get_kafka_group_id

setup_logging("kafka_consumer.log")
logger = logging.getLogger("kafka_consumer")


def create_consumer(topics):
    """Create a Kafka consumer for specified topics."""
    if not isinstance(topics, list):
        logger.error("Expected list of topic unicode strings")
        raise TypeError("Expected list of topic unicode strings")

    try:
        consumer = Consumer(
            {
                "bootstrap.servers": os.getenv("BOOTSTRAP_SERVER"),
                "group.id": get_kafka_group_id("chater"),
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
                "max.poll.interval.ms": 300000,
            }
        )

        def on_assign(consumer, partitions):
            logger.debug(f"Assigned partitions: {partitions}")

        def on_revoke(consumer, partitions):
            logger.debug(f"Partitions revoked: {partitions}")

        consumer.subscribe(topics, on_assign=on_assign, on_revoke=on_revoke)
        return consumer
    except KafkaException as e:
        logger.error(f"Failed to create consumer: {str(e)}")
        raise


def consume_messages(consumer, expected_user_email=None):
    """Consume messages from Kafka topics."""
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                elif msg.error().code() == KafkaError.BROKER_NOT_AVAILABLE:
                    logger.error("Broker not available. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                elif msg.error().code() == KafkaError.INVALID_MSG_SIZE:
                    logger.error(f"Message too large: {msg.error()}")
                    continue
                else:
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
                yield msg
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message as JSON: {str(e)}")
                continue

    except KafkaException as e:
        logger.error(f"Error while consuming messages: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise
    finally:
        consumer.close()
