"""
Common utilities for dev environment support.
Provides functions to handle dev-specific configurations like Kafka topic suffixes.
"""
import os
import logging

logger = logging.getLogger(__name__)

def is_dev_environment() -> bool:
    """Check if running in dev environment based on IS_DEV env variable."""
    return os.getenv("IS_DEV", "false").lower() == "true"


def get_topic_name(base_topic: str) -> str:
    """
    Get the topic name with optional _dev suffix for dev environment.
    
    Args:
        base_topic: The base topic name (e.g., "gpt-send")
        
    Returns:
        Topic name with _dev suffix if IS_DEV=true, otherwise the base topic
    """
    if is_dev_environment():
        return f"{base_topic}_dev"
    return base_topic


def get_topics_list(base_topics: list) -> list:
    """
    Get a list of topic names with optional _dev suffix for dev environment.
    
    Args:
        base_topics: List of base topic names
        
    Returns:
        List of topic names with _dev suffix if IS_DEV=true
    """
    return [get_topic_name(topic) for topic in base_topics]


def get_db_name(base_db: str) -> str:
    """
    Get the database name with optional _dev suffix for dev environment.
    
    Args:
        base_db: The base database name (e.g., "eater")
        
    Returns:
        Database name with _dev suffix if IS_DEV=true, otherwise the base name
    """
    if is_dev_environment():
        return f"{base_db}_dev"
    return base_db


def get_kafka_group_id(base_group_id: str) -> str:
    """
    Get the Kafka group ID with optional -dev suffix for dev environment.
    
    Args:
        base_group_id: The base group ID (e.g., "eater")
        
    Returns:
        Group ID with -dev suffix if IS_DEV=true, otherwise the base group ID
    """
    if is_dev_environment():
        return f"{base_group_id}-dev"
    return base_group_id
