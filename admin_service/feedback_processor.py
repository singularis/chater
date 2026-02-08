import json
import logging

from kafka_consumer import consume_messages, create_consumer
from postgres import create_feedback_table, save_feedback_data
from dev_utils import get_topics_list, is_dev_environment

logger = logging.getLogger(__name__)


def process_feedback_messages():
    """Main processor to consume feedback messages and write to database."""
    logger.info("Starting feedback processor")

    try:
        create_feedback_table()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    topics = get_topics_list(["feedback"])
    if is_dev_environment():
        logger.info("Running in DEV environment - using _dev topic suffix")
    consumer = create_consumer(topics)

    try:
        while True:
            try:
                for message in consume_messages(consumer):
                    try:
                        value = message.value().decode("utf-8")
                        value_dict = json.loads(value)

                        admin_info = value_dict.get("value", {})
                        admin_time = admin_info.get("time")
                        user_email = admin_info.get("user_email")
                        admin_text = admin_info.get("feedback")

                        if not all([admin_time, user_email, admin_text]):
                            logger.warning(f"Incomplete feedback data: {value_dict}")
                            continue

                        feedback_id = save_feedback_data(
                            user_email, admin_text, admin_time
                        )
                        consumer.commit(message)

                    except Exception as e:
                        logger.error(f"Error processing feedback message: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error in feedback processor: {e}")
                import time

                time.sleep(5)
    finally:
        try:
            consumer.close()
        except Exception as e:
            logger.error(f"Error closing consumer: {e}")


if __name__ == "__main__":
    process_feedback_messages()
