import json
import logging
import os

from confluent_kafka import Producer
from dev_utils import get_topic_name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conf = {
    "bootstrap.servers": os.getenv("BOOTSTRAP_SERVER"),
    "client.id": "python-producer",
    "acks": "all",
}

producer = Producer(conf)


def delivery_report(err, msg):
    if err is not None:
        logger.error("Message delivery failed: {}".format(err))
    else:
        logger.debug(
            "Message delivered to {} [{}]".format(msg.topic(), msg.partition())
        )


def produce_message(topic, message):
    """
    Produce a message to a Kafka topic.
    In dev environment (IS_DEV=true), automatically adds _dev suffix to topic name.
    """
    actual_topic = get_topic_name(topic)
    try:
        producer.produce(
            actual_topic,
            key=(message["key"]),
            value=json.dumps(message),
            callback=delivery_report,
        )
        producer.flush()
    except Exception as e:
        logger.error("Failed to produce message: {}".format(e))

