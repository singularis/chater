import json
import logging
import os
import re
import uuid

from common import sanitize_question
from flask import flash, redirect, render_template, request, url_for
from kafka_consumer_service import get_message_response
from kafka_producer import KafkaDispatchError, send_kafka_message

logger = logging.getLogger(__name__)

# Dev environment detection
IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"

TARGET_CONFIG = {
    "chater": {
        "target": "chater",
        "send_topic": "gpt-send",
        "receive_topic": ["gpt-response"],
    },
    "chamini": {
        "target": "chamini",
        "send_topic": "gemini-send",
        "receive_topic": ["gemini-response"],
    },
}


def get_target_config(target):
    return TARGET_CONFIG.get(target)


def chater(session, target):
    if "logged_in" not in session:
        logger.warning("Unauthorized chater access attempt")
        flash("You need to log in to view this page")
        return redirect(url_for("chater_login"))

    if request.method == "POST":
        target_config = get_target_config(target)
        if not target_config:
            logger.error("Invalid target: %s", target)
            flash("Invalid target specified")
            return redirect(url_for("chater"))

        question = request.form["question"]
        question = sanitize_question(question=question)
        logger.debug("Queued question from UI; target=%s", target)
        
        # Resolve dev mode state
        dev_mode_str = session.get("dev_mode")
        is_dev_mode = (dev_mode_str == "on") if dev_mode_str is not None else IS_DEV
        
        def get_topic(base_name):
            return f"{base_name}_dev" if is_dev_mode else base_name

        send_topic = get_topic(target_config["send_topic"])
        receive_topics = [get_topic(t) for t in target_config["receive_topic"]]

        question_uuid = str(uuid.uuid4())
        message = {
            "key": question_uuid,
            "value": {
                "question": question,
                "send_topic": send_topic,
                "context": session.get("context", None),
                "think": True,
            },
        }
        logger.debug("Produced message payload for UUID %s (DevMode=%s)", question_uuid, is_dev_mode)
        try:
            send_kafka_message(
                "dlp-source",
                value=message["value"],
                key=question_uuid,
            )
        except KafkaDispatchError as kafka_error:
            logger.error(
                "Failed to dispatch chat question %s: %s",
                question_uuid,
                kafka_error,
            )
            flash("Chat backend unavailable. Please try again shortly.")
            return redirect(url_for(target_config["target"]))
        except Exception as exc:
            logger.exception(
                "Unexpected error producing chat question %s", question_uuid
            )
            flash("Chat backend unavailable. Please try again later.")
            return redirect(url_for(target_config["target"]))

        json_response = get_messages(
            question_uuid, topics=receive_topics
        )
        logger.debug("Received raw message response for UUID %s", question_uuid)
        try:
            json_response = json_response.get("response")
        except Exception as e:
            logger.error("Error normalising response for UUID %s: %s", question_uuid, e)
            json_response = json_response
        if session.get("switch_state", "off") == "on":
            session["context"] = (
                (session.get("context") or "") + question + json_response
            )
            logger.debug("Conversation context updated for session")
        else:
            session["context"] = None
        formatted_script = format_script(json_response)
        logger.debug("Formatted response ready for render")
        new_response = {
            "question": question,
            "response": formatted_script,
            "full": json_response,
        }

        session["responses"] = manage_session_responses(
            session.get("responses", []), new_response
        )
        return redirect(url_for(target_config["target"]))

    return render_template("chater.html", responses=session.get("responses", []))


def get_messages(message_uuid, topics):
    logger.debug("Awaiting response for UUID %s from topics %s", message_uuid, topics)

    # Get response from Redis using the background consumer service
    try:
        response = get_message_response(message_uuid, timeout=220)
        if response is not None:
            logger.debug("Retrieved response for UUID %s", message_uuid)
            return response
        else:
            logger.warning("Timeout waiting for response for UUID %s", message_uuid)
            return "Timeout: No response received within 30 seconds"
    except Exception as e:
        logger.error("Failed to get message response for UUID %s: %s", message_uuid, e)
        return "Error retrieving response"


def format_script(json_response):
    possible_keys = [
        "script",
        "code",
        "bash_script",
        "python_code",
        "javascript_code",
        "java_code",
        "csharp_code",
        "php_code",
        "ruby_code",
        "swift_code",
        "perl_code",
        "sql_code",
        "html_code",
        "css_code",
        "python_script",
        "javascript_script",
        "java_script",
        "csharp_script",
        "php_script",
        "ruby_script",
        "swift_script",
        "perl_script",
        "sql_script",
        "html_script",
        "css_script",
        "Python_Script",
    ]

    try:
        json_string = re.search(r"```json\n(.*?)\n```", json_response, re.DOTALL)
        if json_string:
            json_response = json_string.group(1)

        response_data = json.loads(json_response)
        script_content = next(
            (response_data[key] for key in possible_keys if key in response_data), None
        )
        if script_content is not None:
            return (
                "\n".join(script_content)
                if isinstance(script_content, list)
                else script_content
            )
        else:
            return json.dumps(response_data, indent=2)
    except (json.JSONDecodeError, TypeError) as e:
        return json_response


def manage_session_responses(existing_responses, new_response):
    existing_responses.insert(0, new_response)
    return existing_responses
