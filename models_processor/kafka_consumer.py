from __future__ import annotations

import json
import logging
import os
import time as time_module
from dataclasses import dataclass
from threading import Event
from typing import Dict, Iterable, Iterator, Optional


from confluent_kafka import Consumer, KafkaError

from dev_utils import get_kafka_group_id

logger = logging.getLogger("models_processor.kafka_consumer")


class ConsumerNotConfiguredError(RuntimeError):
    """Raised when a required Kafka consumer configuration value is missing."""


@dataclass(frozen=True)
class KafkaConsumerSettings:
    bootstrap_servers: str
    group_id: str = "models-processor"
    auto_offset_reset: str = "latest"
    enable_auto_commit: bool = False
    max_poll_interval_ms: int = 300000

    @classmethod
    def from_env(cls) -> "KafkaConsumerSettings":
        bootstrap_servers = os.getenv("BOOTSTRAP_SERVER")
        if not bootstrap_servers:
            raise ConsumerNotConfiguredError(
                "BOOTSTRAP_SERVER environment variable is not set"
            )

        group_id = get_kafka_group_id(os.getenv("KAFKA_GROUP_ID", "models-processor"))
        return cls(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
        )


def _create_consumer(settings: KafkaConsumerSettings) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": settings.bootstrap_servers,
            "group.id": settings.group_id,
            "auto.offset.reset": settings.auto_offset_reset,
            "enable.auto.commit": settings.enable_auto_commit,
            "max.poll.interval.ms": settings.max_poll_interval_ms,
        }
    )


def _extract_user_email(payload: Dict[str, object]) -> Optional[str]:
    user_email = payload.get("user_email")
    if isinstance(user_email, str):
        return user_email

    value_obj = payload.get("value")
    if isinstance(value_obj, dict):
        user_email = value_obj.get("user_email")
        if isinstance(user_email, str):
            return user_email

    if isinstance(value_obj, str):
        try:
            value_dict = json.loads(value_obj)
            user_email = value_dict.get("user_email")
            if isinstance(user_email, str):
                return user_email
        except json.JSONDecodeError:
            logger.debug("Failed to parse value field as JSON", exc_info=True)

    return None


def validate_user_data(
    payload: Dict[str, object], expected_user_email: Optional[str] = None
) -> bool:
    """Validate that the message belongs to the expected user."""

    try:
        message_user_email = _extract_user_email(payload)

        if not message_user_email:
            logger.warning("No user_email found in message")
            return False

        if expected_user_email and message_user_email != expected_user_email:
            logger.warning(
                "User email mismatch. Expected: %s, Got: %s",
                expected_user_email,
                message_user_email,
            )
            return False

        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error validating user data: %s", exc)
        return False


def consume_messages(
    topics: Iterable[str],
    settings: Optional[KafkaConsumerSettings] = None,
) -> Consumer:
    topics = list(topics)
    if not topics:
        raise ValueError("At least one topic must be provided for consumption")

    settings = settings or KafkaConsumerSettings.from_env()
    consumer = _create_consumer(settings)

    consumer.subscribe(topics)
    logger.info("Subscribed to topics: %s", topics)

    return consumer


def poll_messages(
    consumer: Consumer,
    timeout: float = 1.0,
    stop_event: Optional[Event] = None,
) -> Iterator[object]:
    while True:
        if stop_event and stop_event.is_set():
            break

        msg = consumer.poll(timeout)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                logger.info("End of partition reached for topic %s", msg.topic())
                continue
            if msg.error().code() == KafkaError.BROKER_NOT_AVAILABLE:
                logger.error("Broker not available. Retrying in 5 seconds...")
                time_module.sleep(5)
                continue
            if msg.error().code() == KafkaError.INVALID_MSG_SIZE:
                logger.error("Message too large: %s", msg.error())
                continue

            logger.error("Consumer error: %s", msg.error())
            continue

        yield msg
