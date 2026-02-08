import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

from confluent_kafka import KafkaException, Producer
from logging_config import setup_logging
from dev_utils import get_topic_name

setup_logging("kafka_producer.log")
logger = logging.getLogger(__name__)

_producer_instance = None
_producer_lock = threading.Lock()

MAX_PRODUCE_RETRIES = 3
PRODUCE_BACKOFF_SECONDS = 0.5
FLUSH_TIMEOUT_SECONDS = 10


class KafkaDispatchError(Exception):
    """Represents a failure while enqueueing a Kafka message."""

    def __init__(self, message: str, *, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


def create_producer():
    """
    Returns a singleton Kafka producer instance.
    Creates the producer only once on first call and reuses it for subsequent calls.
    """
    global _producer_instance

    if _producer_instance is None:
        with _producer_lock:
            if _producer_instance is None:
                bootstrap_servers = os.getenv("BOOTSTRAP_SERVER")
                if not bootstrap_servers:
                    message = "BOOTSTRAP_SERVER environment variable is required for Kafka producer"
                    logger.error(message)
                    raise RuntimeError(message)

                try:
                    conf = {
                        "bootstrap.servers": bootstrap_servers,
                        "message.max.bytes": 10000000,
                        "client.id": "chater-ui-producer",
                        "acks": "all",
                        "socket.keepalive.enable": True,
                    }
                    _producer_instance = Producer(conf)
                    logger.info("Producer created successfully (singleton)")
                except KafkaException as e:
                    logger.error(f"Failed to create producer: {str(e)}")
                    raise
    else:
        logger.debug("Reusing existing producer instance")

    return _producer_instance


def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
        return

    try:
        message_data = json.loads(msg.value()) if msg.value() else {}
    except (json.JSONDecodeError, TypeError) as parse_error:
        logger.warning(f"Failed to decode delivered message payload: {parse_error}")
        message_data = {}

    user_email = message_data.get("value", {}).get("user_email", "unknown")
    logger.info(
        f"Message delivered to {msg.topic()} [{msg.partition()}] for user {user_email}"
    )


def produce_message(producer, topic, message, ensure_user_email=True):
    topic = get_topic_name(topic)
    if not isinstance(message, dict):
        raise TypeError("message must be a dictionary")

    try:
        # Ensure message has a value field
        if "value" not in message or not isinstance(message["value"], dict):
            message["value"] = {}

        # Debug logging for auth topic
        if topic in ("auth_requires_token", "auth_requires_token_dev"):
            logger.info(f"AUTH DEBUG - Message before user_email check: {message}")
            logger.info(
                f"AUTH DEBUG - Message value keys: {list(message.get('value', {}).keys())}"
            )
            logger.info(
                f"AUTH DEBUG - user_email in value: {'user_email' in message.get('value', {})}"
            )

        # Add user_email to the message if not present
        if ensure_user_email and "user_email" not in message["value"]:
            logger.warning(f"No user_email found in message value for topic {topic}")
            logger.warning(f"Message structure: {message}")
            message["value"]["user_email"] = "unknown"

        payload = json.dumps(message)

        attempts = 0
        while True:
            try:
                producer.produce(
                    topic,
                    key=message.get("key"),
                    value=payload,
                    callback=delivery_report,
                )
                producer.poll(0)
                break
            except BufferError as buffer_err:
                attempts += 1
                if attempts > MAX_PRODUCE_RETRIES:
                    logger.error("Local producer queue is full and retry limit reached")
                    raise

                sleep_time = min(PRODUCE_BACKOFF_SECONDS * attempts, 5)
                logger.warning(
                    "Producer queue is full; backing off for %.2f seconds before retry",
                    sleep_time,
                )
                producer.poll(0)
                time.sleep(sleep_time)
            except KafkaException as e:
                error = e.args[0] if e.args else e
                retriable = getattr(error, "retriable", lambda: False)()
                attempts += 1
                if retriable and attempts <= MAX_PRODUCE_RETRIES:
                    backoff = min(PRODUCE_BACKOFF_SECONDS * (2 ** (attempts - 1)), 10)
                    logger.warning(
                        "Retriable Kafka error while producing to %s: %s. Retrying in %.2f seconds (attempt %d/%d)",
                        topic,
                        error,
                        backoff,
                        attempts,
                        MAX_PRODUCE_RETRIES,
                    )
                    time.sleep(backoff)
                    continue

                logger.error(f"Failed to produce message: {str(e)}")
                raise

        outstanding = producer.flush(FLUSH_TIMEOUT_SECONDS)
        if outstanding > 0:
            logger.warning(
                "Producer flush timed out with %d message(s) still pending delivery",
                outstanding,
            )

        logger.info(
            f"Message produced to topic {topic} for user {message['value']['user_email']}"
        )
    except KafkaException as e:
        logger.error(f"Failed to produce message: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise


def send_kafka_message(
    topic: str,
    value: Dict[str, Any],
    *,
    key: Optional[str] = None,
    ensure_user_email: bool = True,
) -> str:
    if not isinstance(value, dict):
        raise TypeError("value must be a dictionary")

    message_key = key or str(uuid.uuid4())
    message = {"key": message_key, "value": dict(value)}

    try:
        producer = create_producer()
        produce_message(
            producer,
            topic,
            message,
            ensure_user_email=ensure_user_email,
        )
    except KafkaException as exc:
        logger.error("Kafka error while sending topic %s: %s", topic, exc)
        raise KafkaDispatchError("Kafka dispatch failed", status_code=503) from exc
    except Exception as exc:
        logger.error("Unexpected error while sending topic %s: %s", topic, exc)
        raise KafkaDispatchError("Kafka dispatch failed", status_code=500) from exc

    return message_key
