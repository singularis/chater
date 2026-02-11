import json
import logging
import uuid

from common import remove_markdown_fence
from dev_utils import get_topics_list, get_topic_name, is_dev_environment
from kafka_consumer import consume_messages, validate_user_data
from kafka_producer import produce_message
from logging_config import setup_logging
from postgres import (AlcoholConsumption, AlcoholForDay, delete_food,
                      get_alcohol_events_in_range, get_custom_date_dishes,
                      get_all_chess_data_sync, get_chess_stats_sync, get_food_health_level,
                      get_today_dishes, modify_food, record_chess_game)
from process_gpt import get_recommendation, process_food, process_weight

logger = logging.getLogger(__name__)


def process_messages():
    base_topics = [
        "photo-analysis-response",
        "get_today_data",
        "get_today_data_custom",
        "delete_food",
        "modify_food_record",
        "get_recommendation",
        "manual_weight",
        "get_alcohol_latest",
        "get_alcohol_range",
        "get_food_health_level",
        "record_chess_game",
        "get_chess_stats",
        "get_all_chess_data",
    ]
    topics = get_topics_list(base_topics)
    if is_dev_environment():
        logger.info("Running in DEV environment - using _dev topic suffix")
    logger.info(f"Starting message processing with topics: {topics}")
    while True:
        for message, consumer in consume_messages(topics):
            try:
                value = message.value().decode("utf-8")
                value_dict = json.loads(value)

                # Extract user_email from the message
                user_email = value_dict.get("value", {}).get("user_email")
                if not user_email:
                    logger.warning("No user_email found in message, skipping")
                    continue

                # Validate user data
                if not validate_user_data(value_dict, user_email):
                    logger.warning(
                        f"Invalid user data in message for user {user_email}, skipping"
                    )
                    continue

                # Get message key for tracking
                message_key = value_dict.get("key")
                if not message_key:
                    logger.warning(
                        f"No message key found for user {user_email}, skipping"
                    )
                    continue

                consumer.commit(message)

                if message.topic() == get_topic_name("photo-analysis-response"):
                    gpt_response = value_dict.get("value", {})
                    if isinstance(gpt_response, str):
                        gpt_response = remove_markdown_fence(gpt_response)
                        json_response = json.loads(gpt_response)
                    else:
                        json_response = gpt_response

                    # Preserve image_id from original message before parsing nested analysis
                    original_image_id = json_response.get("image_id")

                    # Parse nested analysis if present
                    if "analysis" in json_response:
                        json_response = json.loads(json_response.get("analysis"))

                    # Check for errors after parsing
                    if json_response.get("error"):
                        logger.error(f"Error for user {user_email}: {json_response}")
                        produce_message(
                            topic="photo-analysis-response-check",
                            message={
                                "key": message_key,
                                "value": {
                                    "error": json_response.get("error"),
                                    "user_email": user_email,
                                },
                            },
                        )
                    else:
                        type_of_processing = json_response.get("type")
                        logger.debug(
                            f"Received food processing {type_of_processing} for user {user_email}"
                        )
                        if type_of_processing == "food_processing":
                            logger.debug(
                                f"Received food_process for user {user_email}: {json_response}"
                            )
                            # Ensure image_id is passed to process_food
                            # Use preserved original_image_id, or message_key as last fallback
                            if "image_id" not in json_response:
                                json_response["image_id"] = original_image_id or message_key
                            
                            # Inject timestamp and date if present in the message
                            timestamp = value_dict.get("value", {}).get("timestamp")
                            date_val = value_dict.get("value", {}).get("date")
                            image_id_val = value_dict.get("value", {}).get("image_id")
                            
                            if timestamp:
                                json_response["timestamp"] = timestamp
                            if date_val:
                                json_response["date"] = date_val
                            
                            # Prioritize image_id from message value (should be MinIO path), then analysis, then fallback
                            if image_id_val:
                                json_response["image_id"] = image_id_val
                            elif "image_id" not in json_response:
                                json_response["image_id"] = original_image_id or message_key

                            process_food(json_response, user_email)
                        elif type_of_processing == "weight_processing":
                            process_weight(json_response, user_email)
                        else:
                            produce_message(
                                topic="photo-analysis-response-check",
                                message={
                                    "key": message_key,
                                    "value": {
                                        "error": "unknown request",
                                        "user_email": user_email,
                                    },
                                },
                            )
                        produce_message(
                            topic="photo-analysis-response-check",
                            message={
                                "key": message_key,
                                "value": {
                                    "status": "Success",
                                    "user_email": user_email,
                                },
                            },
                        )
                elif message.topic() == get_topic_name("get_today_data"):
                    today_dishes = get_today_dishes(user_email)
                    logger.debug(f"Received request to get food for user {user_email}")
                    message = {
                        "key": message_key,
                        "value": {"dishes": today_dishes, "user_email": user_email},
                    }
                    produce_message(topic="send_today_data", message=message)
                elif message.topic() == get_topic_name("get_today_data_custom"):
                    custom_date = value_dict.get("value", {}).get("date")
                    if not custom_date:
                        logger.warning(
                            f"No date provided in custom date request for user {user_email}"
                        )
                        continue
                    custom_dishes = get_custom_date_dishes(custom_date, user_email)
                    logger.debug(
                        f"Received request to get food for {custom_date} for user {user_email}"
                    )
                    message = {
                        "key": message_key,
                        "value": {"dishes": custom_dishes, "user_email": user_email},
                    }
                    produce_message(topic="send_today_data_custom", message=message)
                elif message.topic() == get_topic_name("get_alcohol_latest"):
                    today_dishes = get_today_dishes(user_email)
                    alcohol = (today_dishes or {}).get("alcohol_for_day", {})
                    resp = {"alcohol": alcohol, "user_email": user_email}
                    produce_message(
                        topic="send_alcohol_latest",
                        message={"key": message_key, "value": resp},
                    )
                elif message.topic() == get_topic_name("get_alcohol_range"):
                    value = value_dict.get("value", {})
                    start_date = value.get("start_date")
                    end_date = value.get("end_date")
                    if not start_date or not end_date:
                        logger.warning(
                            f"Invalid date range in alcohol request for user {user_email}"
                        )
                        continue

                    events = get_alcohol_events_in_range(
                        start_date=start_date, end_date=end_date, user_email=user_email
                    )
                    produce_message(
                        topic="send_alcohol_range",
                        message={
                            "key": message_key,
                            "value": {"events": events, "user_email": user_email},
                        },
                    )
                elif message.topic() == get_topic_name("delete_food"):
                    delete_food(value_dict.get("value"), user_email)
                    # Send confirmation
                    produce_message(
                        topic="delete_food_response",
                        message={
                            "key": message_key,
                            "value": {"status": "Success", "user_email": user_email},
                        },
                    )
                elif message.topic() == get_topic_name("modify_food_record"):
                    modify_food(value_dict.get("value"), user_email)
                    # Send confirmation
                    produce_message(
                        topic="modify_food_record_response",
                        message={
                            "key": message_key,
                            "value": {"status": "Success", "user_email": user_email},
                        },
                    )
                elif message.topic() == get_topic_name("get_recommendation"):
                    get_recommendation(
                        message_key, value_dict.get("value"), value_dict, user_email
                    )
                elif message.topic() == get_topic_name("manual_weight"):
                    # Handle messages from manual_weight endpoint
                    response_data = value_dict.get("value", {})
                    message_type = response_data.get("type")

                    if message_type == "weight_processing":
                        logger.debug(
                            f"Received manual weight processing for user {user_email}: {response_data}"
                        )
                        process_weight(response_data, user_email)
                        logger.debug(
                            f"Successfully processed manual weight for user {user_email}"
                        )
                    else:
                        logger.warning(
                            f"Unknown message type '{message_type}' in manual_weight for user {user_email}"
                        )
                elif message.topic() == get_topic_name("get_food_health_level"):
                    request_data = value_dict.get("value", {})
                    time_value = request_data.get("time")
                    food_name = request_data.get("food_name")
                    logger.debug(
                        f"Received food health level request for user {user_email}: time={time_value}, food_name={food_name}"
                    )
                    food_health_level = get_food_health_level(
                        time_value=time_value, user_email=user_email
                    )
                    produce_message(
                        topic="send_food_health_level",
                        message={
                            "key": message_key,
                            "value": {
                                "food_health_level": food_health_level or {},
                                "user_email": user_email,
                            },
                        },
                    )
                elif message.topic() == "record_chess_game":
                    req = value_dict.get("value", {})
                    player_email = (req.get("player_email") or "").strip()
                    opponent_email = (req.get("opponent_email") or "").strip()
                    result = (req.get("result") or "").strip()
                    timestamp = int(req.get("timestamp") or 0)
                    if player_email != user_email:
                        logger.warning(
                            "record_chess_game: player_email %s != user_email %s",
                            player_email,
                            user_email,
                        )
                        produce_message(
                            topic="record_chess_game_response",
                            message={
                                "key": message_key,
                                "value": {
                                    "success": False,
                                    "error": "Forbidden",
                                    "user_email": user_email,
                                },
                            },
                        )
                    elif result not in ("win", "loss", "draw"):
                        produce_message(
                            topic="record_chess_game_response",
                            message={
                                "key": message_key,
                                "value": {
                                    "success": False,
                                    "error": "result must be win, loss, or draw",
                                    "user_email": user_email,
                                },
                            },
                        )
                    else:
                        ok = record_chess_game(
                            player_email, opponent_email, result, timestamp
                        )
                        if not ok:
                            produce_message(
                                topic="record_chess_game_response",
                                message={
                                    "key": message_key,
                                    "value": {
                                        "success": False,
                                        "error": "Failed to record game",
                                        "user_email": user_email,
                                    },
                                },
                            )
                        else:
                            player_stats = get_chess_stats_sync(
                                player_email, opponent_email
                            )
                            opponent_stats = get_chess_stats_sync(
                                opponent_email, player_email
                            )
                            produce_message(
                                topic="record_chess_game_response",
                                message={
                                    "key": message_key,
                                    "value": {
                                        "success": True,
                                        "user_email": user_email,
                                        "player_wins": (player_stats or {}).get(
                                            "wins", 0
                                        ),
                                        "player_losses": (player_stats or {}).get(
                                            "losses", 0
                                        ),
                                        "opponent_wins": (opponent_stats or {}).get(
                                            "wins", 0
                                        ),
                                        "opponent_losses": (opponent_stats or {}).get(
                                            "losses", 0
                                        ),
                                    },
                                },
                            )
                elif message.topic() == "get_chess_stats":
                    req = value_dict.get("value", {})
                    opponent_email = (req.get("opponent_email") or "").strip() or None
                    stats = get_chess_stats_sync(user_email, opponent_email)
                    produce_message(
                        topic="get_chess_stats_response",
                        message={
                            "key": message_key,
                            "value": {
                                "user_email": user_email,
                                "score": (stats or {}).get("score", "0:0"),
                                "opponent_name": (stats or {}).get("opponent_name", ""),
                                "last_game_date": (stats or {}).get("last_game_date", ""),
                            },
                        },
                    )
                elif message.topic() == "get_all_chess_data":
                    data = get_all_chess_data_sync(user_email)
                    produce_message(
                        topic="get_all_chess_data_response",
                        message={
                            "key": message_key,
                            "value": {
                                "user_email": user_email,
                                "total_wins": (data or {}).get("total_wins", 0),
                                "opponents": (data or {}).get("opponents", {}),
                            },
                        },
                    )
            except Exception as e:
                logger.error(
                    f"Failed to process message for user {user_email}: {e}, message {value_dict}"
                )
                # Send error response if we have a message key
                if message_key:
                    produce_message(
                        topic="error_response",
                        message={
                            "key": message_key,
                            "value": {"error": str(e), "user_email": user_email},
                        },
                    )


if __name__ == "__main__":
    setup_logging("eater.log")
    logger.info("Starting Eater processor")
    process_messages()
