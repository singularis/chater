from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict

from confluent_kafka import KafkaException, Producer

logger = logging.getLogger("models_processor.kafka_producer")


class ProducerNotConfiguredError(RuntimeError):
    """Raised when the Kafka bootstrap server configuration is missing."""


def _delivery_report(err, msg) -> None:  # pragma: no cover - callback path
    if err is not None:
        logger.error("Message delivery failed: %s", err)
    else:
        logger.info("Message delivered to %s [%s]", msg.topic(), msg.partition())


@lru_cache(maxsize=1)
def _create_producer() -> Producer:
    bootstrap_servers = os.getenv("BOOTSTRAP_SERVER")
    if not bootstrap_servers:
        raise ProducerNotConfiguredError(
            "BOOTSTRAP_SERVER environment variable is not set"
        )

    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "models-processor-producer",
            "acks": "all",
        }
    )


from dev_utils import get_topic_name


def produce_message(topic: str, message: Dict[str, Any]) -> None:
    producer = _create_producer()
    topic = get_topic_name(topic)

    try:
        producer.produce(
            topic,
            key=message.get("key"),
            value=json.dumps(message),
            callback=_delivery_report,
        )
        producer.poll(0)
    except KafkaException as exc:
        logger.error("Failed to produce message: %s", exc)
    except Exception as exc:  # pragma: no cover - unexpected error path
        logger.exception("Unexpected error producing message: %s", exc)
