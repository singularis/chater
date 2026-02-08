import json
import logging
import os

from dev_utils import get_topics_list, get_topic_name, is_dev_environment
from kafka_consumer import consume_messages
from kafka_producer import produce_message
from logging_config import setup_logging
from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL = os.getenv("MODEL")
VISION_MODEL = os.getenv("VISION_MODEL")
client = OpenAI()


def gpt_request(question, context=None, content=None) -> dict[str, str]:
    logger.debug(f"GPT Question: {question}")

    if MODEL == "o1-mini":
        messages = [{"role": "user", "content": question}]
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
    else:
        system_message = (
            content
            if content
            else (
                "You are a helpful assistant designed to output JSON. "
                "Oriented on software development, python, java, AWS, SRE."
            )
        )
        messages = [
            {
                "role": "system",
                "content": system_message,
            },
            {"role": "user", "content": question},
        ]
        if context:
            context_string = " ".join(
                [str(item) for item in context if item is not None]
            )
            messages.append({"role": "assistant", "content": context_string})

        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=messages,
        )

    response_content = response.choices[0].message.content
    logger.debug(f"GPT Answer: {response_content}")

    return response_content


def analyze_photo(prompt, photo_base64):
    try:
        logger.debug("Analyzing photo with prompt via ChatGPT.")
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": str(prompt),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{photo_base64}"
                            },
                        },
                    ],
                }
            ],
        )

        response_content = response.choices[0].message.content
        logger.debug(f"Photo analysis result: {response_content}")

        return response_content
    except Exception as e:
        logger.error(f"Failed to analyze photo: {e}")
        return None


def process_messages():
    base_topics = ["gpt-send", "eater-send-photo"]
    topics = get_topics_list(base_topics)
    if is_dev_environment():
        logger.info("Running in DEV environment - using _dev topic suffix")
    logger.info(f"Starting message processing with topics: {topics}")
    while True:
        for message, consumer in consume_messages(topics):
            try:
                topic = message.topic()
                key = message.key().decode("utf-8") if message.key() else None
                value = message.value().decode("utf-8")
                value_dict = json.loads(value)
                actual_value = value_dict["value"]

                if topic == get_topic_name("gpt-send"):
                    context = actual_value.get("context")
                    question = actual_value.get("question")
                    response_value = gpt_request(question, context)
                    kafka_message = {"key": key, "value": response_value}

                    produce_message("gpt-response", kafka_message)
                    logger.debug(
                        f"Processed GPT message and sent to Kafka: {kafka_message}"
                    )

                elif topic == get_topic_name("eater-send-photo"):
                    logger.debug("Received message on 'eater-send-photo'.")
                    prompt = actual_value.get("prompt")
                    photo_base64 = actual_value.get("photo")
                    user_email = actual_value.get("user_email")
                    image_id = actual_value.get("image_id")
                    if prompt and photo_base64:
                        timestamp = actual_value.get("timestamp")
                        date_val = actual_value.get("date")
                        
                        photo_analysis_result = analyze_photo(prompt, photo_base64)
                        
                        response_value = {
                            "analysis": photo_analysis_result,
                            "user_email": user_email,
                            "image_id": image_id,
                        }
                        if timestamp:
                            response_value["timestamp"] = timestamp
                        if date_val:
                            response_value["date"] = date_val

                        kafka_message = {
                            "key": key,
                            "value": response_value,
                        }
                        produce_message("photo-analysis-response", kafka_message)
                        logger.debug(
                            f"Photo analyzed and result sent to Kafka: {kafka_message}"
                        )
                    else:
                        logger.warning(
                            "Message on 'eater-send-photo' missing 'prompt' or 'photo'."
                        )

                consumer.commit(message)
            except Exception as e:
                logger.error(f"Failed to process message: {e}")


if __name__ == "__main__":
    setup_logging("gpt.log")
    logger.info("Starting GPT processing script")
    process_messages()
