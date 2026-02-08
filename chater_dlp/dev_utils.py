import os
import logging

logger = logging.getLogger(__name__)

def is_dev_environment() -> bool:
    return os.getenv("IS_DEV", "false").lower() == "true"


def get_topic_name(base_topic: str) -> str:

    if is_dev_environment():
        return f"{base_topic}_dev"
    return base_topic


def get_topics_list(base_topics: list) -> list:
    return [get_topic_name(topic) for topic in base_topics]


def get_kafka_group_id(base_group_id: str) -> str:
    if is_dev_environment():
        return f"{base_group_id}-dev"
    return base_group_id
