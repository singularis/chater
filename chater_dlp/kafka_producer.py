import json
import logging
import os

from confluent_kafka import Producer
from dev_utils import get_topic_name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conf = {
    "bootstrap.servers": os.getenv("BOOTSTRAP_SERVER"),
    "message.max.bytes": 10000000,
    "client.id": "python-producer",
    "acks": "all",
}

producer = Producer(conf)


def delivery_report(err, msg):
    if err is not None:
        logger.error("Message delivery failed: {}".format(err))
    else:
        logger.info("Message delivered to {} [{}]".format(msg.topic(), msg.partition()))


def produce_message(topic, message):
    topic = get_topic_name(topic)
    try:
        # Ensure message has a value field
        if "value" not in message:
            message["value"] = {}

        # Ensure user_email is present in the value
        if "user_email" not in message["value"]:
            logger.warning("No user_email found in message value")
            message["value"]["user_email"] = "unknown"

        producer.produce(
            topic,
            key=(message["key"]),
            value=json.dumps(message),
            callback=delivery_report,
        )
        producer.flush()
    except Exception as e:
        logger.error("Failed to produce message: {}".format(e))
