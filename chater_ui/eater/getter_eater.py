import logging
from datetime import datetime, timezone

from common import create_multilingual_prompt, get_prompt, json_to_plain_text
from kafka_consumer_service import (get_message_response,
                                    get_user_message_response)
from kafka_producer import KafkaDispatchError, send_kafka_message

from .proto import (custom_date_food_pb2, food_health_level_pb2,
                    get_recomendation_pb2, today_food_pb2)

logger = logging.getLogger(__name__)


def eater_kafka_request(topic_send, topic_receive, payload, user_email, timeout_sec=30):
    try:
        message_id = send_kafka_message(
            topic_send,
            value={**payload, "user_email": user_email},
        )
        logger.info("Dispatching %s request for user %s", topic_send, user_email)
    except KafkaDispatchError as kafka_error:
        logger.error(
            "Failed to send Kafka message for topic %s user %s: %s",
            topic_send,
            user_email,
            kafka_error,
        )
        return None
    except Exception as exc:
        logger.exception(
            "Unexpected error while sending Kafka message for user %s on topic %s",
            user_email,
            topic_send,
        )
        return None

    logger.debug(
        "Awaiting response from topic %s for user %s (message_id=%s)",
        topic_receive,
        user_email,
        message_id,
    )

    # Get response from Redis using the background consumer service
    try:
        response = get_user_message_response(
            message_id, user_email, timeout=timeout_sec
        )
        if response is not None:
            logger.debug("Retrieved response for user %s", user_email)

            if response.get("error"):
                logger.error(
                    "Error in response for user %s: %s",
                    user_email,
                    response.get("error"),
                )
                return None

            return response
        else:
            logger.warning(
                "Timeout waiting for response for user %s (message_id=%s)",
                user_email,
                message_id,
            )
            return None
    except Exception as exc:
        logger.exception("Failed to get message response for user %s", user_email)
        return None


def eater_get_today_kafka(user_email):
    payload = {
        "date": datetime.now(timezone.utc).strftime("%d-%m-%Y"),
    }
    return eater_kafka_request(
        "get_today_data", "send_today_data", payload, user_email, timeout_sec=20
    )


def eater_get_custom_date_kafka(user_email, custom_date):
    payload = {
        "date": custom_date,
    }
    return eater_kafka_request(
        "get_today_data_custom", "send_today_data_custom", payload, user_email
    )


def eater_get_today(user_email):
    try:
        today_food = eater_get_today_kafka(user_email)
        if not today_food:
            logger.warning(
                "No data received from Kafka for user %s; returning 503",
                user_email,
            )
            return "Service temporarily unavailable", 503

        logger.debug("Today food payload for user %s: %s", user_email, today_food)
        proto_message = today_food_pb2.TodayFood()
        tf = today_food.get("dishes", {}).get("total_for_day", {})
        logger.debug(
            "Total_for_day content for user %s: %s",
            user_email,
            tf,
        )
        total_avg_weight = tf.get("total_avg_weight", 0)
        logger.debug("total_avg_weight for user %s: %s", user_email, total_avg_weight)
        proto_message.total_for_day.total_avg_weight = int(total_avg_weight)
        total_calories = tf.get("total_calories", 0)
        logger.debug("total_calories for user %s: %s", user_email, total_calories)
        proto_message.total_for_day.total_calories = total_calories
        contains_data = tf.get("contains", {})
        if isinstance(contains_data, list):
            logger.warning(
                "'contains' is a list instead of dict for user %s; defaulting to empty",
                user_email,
            )
            contains_data = {}
        elif not isinstance(contains_data, dict):
            logger.warning(
                "'contains' is neither dict nor list for user %s; defaulting to empty",
                user_email,
            )
            contains_data = {}

        proto_message.total_for_day.contains.carbohydrates = int(
            contains_data.get("carbohydrates", 0)
        )
        proto_message.total_for_day.contains.fats = int(contains_data.get("fats", 0))
        proto_message.total_for_day.contains.proteins = int(
            contains_data.get("proteins", 0)
        )
        proto_message.total_for_day.contains.sugar = int(contains_data.get("sugar", 0))

        # Handle both old and new weight field names for backward compatibility
        lw = today_food.get("dishes", {}).get("latest_weight", {})
        if not lw:
            lw = today_food.get("dishes", {}).get("closest_weight", {})

        logger.debug("Weight data for user %s: %s", user_email, lw)
        proto_message.person_weight = lw.get("weight", 0)

        dishes = today_food.get("dishes", {}).get("dishes_today", [])
        for dish in dishes:
            logger.debug("Processing dish for user %s: %s", user_email, dish)
            dish_proto = proto_message.dishes_today.add()
            dish_proto.time = dish.get("time", 0)
            dish_proto.dish_name = dish.get("dish_name", "")
            dish_proto.estimated_avg_calories = dish.get("estimated_avg_calories", 0)
            dish_proto.total_avg_weight = int(dish.get("total_avg_weight", 0))
            hr = dish.get("health_rating")
            dish_proto.health_rating = int(hr) if hr is not None else -1
            dish_proto.image_id = dish.get("image_id") or ""

            ingredients = dish.get("ingredients", [])
            logger.debug(
                "Raw ingredients for user %s dish %s: %s",
                user_email,
                dish.get("dish_name"),
                ingredients,
            )
            if not isinstance(ingredients, list):
                logger.warning(
                    "'ingredients' is not a list for user %s; defaulting to empty",
                    user_email,
                )
                ingredients = []
            dish_proto.ingredients.extend(ingredients)
            logger.debug("Processed dish proto for user %s: %s", user_email, dish_proto)

        proto_data = proto_message.SerializeToString()
        logger.debug("Successfully processed today message for user %s", user_email)
        return proto_data, 200, {"Content-Type": "application/protobuf"}

    except Exception as exc:
        logger.exception("Error in eater_get_today for user %s", user_email)
        return "Failed", 500


def eater_get_custom_date(request, user_email):
    try:
        proto_request = custom_date_food_pb2.CustomDateFoodRequest()
        proto_request.ParseFromString(request.data)

        custom_date = proto_request.date
        if not custom_date:
            logger.error(
                "No date provided in custom date request for user %s", user_email
            )
            return "No date provided", 400

        custom_food = eater_get_custom_date_kafka(user_email, custom_date)
        if not custom_food:
            raise ValueError(
                f"No data received from Kafka for user {user_email} and date {custom_date}"
            )

        logger.debug(
            "Custom food payload for user %s (%s): %s",
            user_email,
            custom_date,
            custom_food,
        )

        proto_message = custom_date_food_pb2.CustomDateFoodResponse()
        tf = custom_food.get("dishes", {}).get("total_for_day", {})
        logger.debug(
            "Total_for_day content for user %s (%s): %s",
            user_email,
            custom_date,
            tf,
        )

        total_avg_weight = tf.get("total_avg_weight", 0)
        logger.debug(
            "total_avg_weight for user %s (%s): %s",
            user_email,
            custom_date,
            total_avg_weight,
        )
        proto_message.total_for_day.total_avg_weight = int(total_avg_weight)

        total_calories = tf.get("total_calories", 0)
        logger.debug(
            "total_calories for user %s (%s): %s",
            user_email,
            custom_date,
            total_calories,
        )
        proto_message.total_for_day.total_calories = total_calories

        contains_data = tf.get("contains", {})
        if isinstance(contains_data, list):
            logger.warning(
                "'contains' is a list instead of dict for user %s; defaulting to empty",
                user_email,
            )
            contains_data = {}
        elif not isinstance(contains_data, dict):
            logger.warning(
                "'contains' is neither dict nor list for user %s; defaulting to empty",
                user_email,
            )
            contains_data = {}

        proto_message.total_for_day.contains.carbohydrates = int(
            contains_data.get("carbohydrates", 0)
        )
        proto_message.total_for_day.contains.fats = int(contains_data.get("fats", 0))
        proto_message.total_for_day.contains.proteins = int(
            contains_data.get("proteins", 0)
        )
        proto_message.total_for_day.contains.sugar = int(contains_data.get("sugar", 0))

        # Handle both old and new weight field names for backward compatibility
        lw = custom_food.get("dishes", {}).get("closest_weight", {})
        if not lw:
            lw = custom_food.get("dishes", {}).get("latest_weight", {})

        logger.debug(
            "Weight data for user %s (%s): %s",
            user_email,
            custom_date,
            lw,
        )
        proto_message.person_weight = lw.get("weight", 0)

        dishes = custom_food.get("dishes", {}).get("dishes_today", [])
        for dish in dishes:
            logger.debug(
                "Processing dish for user %s (%s): %s", user_email, custom_date, dish
            )
            dish_proto = proto_message.dishes_for_date.add()
            dish_proto.time = dish.get("time", 0)
            dish_proto.dish_name = dish.get("dish_name", "")
            dish_proto.estimated_avg_calories = dish.get("estimated_avg_calories", 0)
            dish_proto.total_avg_weight = int(dish.get("total_avg_weight", 0))
            hr = dish.get("health_rating")
            dish_proto.health_rating = int(hr) if hr is not None else -1
            dish_proto.image_id = dish.get("image_id") or ""

            ingredients = dish.get("ingredients", [])
            logger.debug(
                "Raw ingredients for user %s (%s) dish %s: %s",
                user_email,
                custom_date,
                dish.get("dish_name"),
                ingredients,
            )
            if not isinstance(ingredients, list):
                logger.warning(
                    "'ingredients' is not a list for user %s; defaulting to empty",
                    user_email,
                )
                ingredients = []
            dish_proto.ingredients.extend(ingredients)
            logger.debug(
                "Processed custom dish proto for user %s (%s): %s",
                user_email,
                custom_date,
                dish_proto,
            )

        proto_data = proto_message.SerializeToString()
        logger.debug(
            "Successfully processed custom date message for user %s (%s)",
            user_email,
            custom_date,
        )
        return proto_data, 200, {"Content-Type": "application/protobuf"}

    except Exception as exc:
        logger.exception(
            "Error in eater_get_custom_date for user %s (%s)", user_email, custom_date
        )
        return "Failed", 500


def eater_auth_token(request):
    """Handle authentication token request"""
    logger.debug("Entering eater_auth_token")
    try:
        import json

        from flask import jsonify

        # Parse the request JSON
        request_data = request.get_json()
        if not request_data:
            logger.error("No JSON data in auth request")
            return (
                jsonify(
                    {"error": "invalid_request", "message": "No JSON data provided"}
                ),
                400,
            )

        # Extract required fields
        provider = request_data.get("provider")
        id_token = request_data.get("idToken")
        email = request_data.get("email")
        name = request_data.get("name")
        profile_picture_url = request_data.get("profilePictureURL")

        # Validate required fields
        if not provider or not id_token or not email:
            logger.error("Missing required fields in auth request")
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "message": "Missing required fields: provider, idToken, email",
                    }
                ),
                400,
            )

        if provider not in ["google", "apple"]:
            logger.error("Invalid provider: %s", provider)
            return (
                jsonify(
                    {
                        "error": "invalid_provider",
                        "message": "Provider must be google or apple",
                    }
                ),
                400,
            )

        # Create payload for Kafka message
        payload = {
            "provider": provider,
            "idToken": id_token,
            "email": email,
            "name": name,
            "profilePictureURL": profile_picture_url,
        }

        # Use the standard eater_kafka_request function like other endpoints
        logger.info("Dispatching auth request for %s", email)

        # Create a temporary user email since this is before authentication
        temp_user_email = email  # Use the email from the request as user identifier

        # Send to Kafka using the standard pattern
        try:
            message_id = send_kafka_message(
                "auth_requires_token",
                value={**payload, "user_email": temp_user_email},
            )
        except KafkaDispatchError as kafka_error:
            logger.error(
                "Failed to dispatch auth request for %s: %s",
                email,
                kafka_error,
            )
            return (
                jsonify(
                    {
                        "error": "service_unavailable",
                        "message": "Authentication backend unavailable",
                    }
                ),
                kafka_error.status_code,
            )
        except Exception as exc:
            logger.exception(
                "Unexpected error creating Kafka auth message for %s", email
            )
            return (
                jsonify(
                    {
                        "error": "internal_error",
                        "message": "Authentication backend error",
                    }
                ),
                500,
            )

        logger.debug("Awaiting auth response for %s (message_id=%s)", email, message_id)

        # Get response from Redis using the background consumer service
        try:
            response = get_message_response(message_id, timeout=30)
            if response is not None:
                logger.debug("Auth response for %s received", email)

                if response.get("error"):
                    logger.error(
                        f"Error in auth response for email {email}: {response.get('error')}"
                    )
                    return (
                        jsonify(
                            {
                                "error": response.get("error"),
                                "message": response.get(
                                    "message", "Authentication failed"
                                ),
                            }
                        ),
                        401,
                    )

                # Return successful response
                return (
                    jsonify(
                        {
                            "token": response.get("token"),
                            "expiresIn": response.get("expiresIn", 86400),
                            "userEmail": response.get("userEmail", email),
                            "userName": response.get("userName", name),
                            "profilePictureURL": response.get(
                                "profilePictureURL", profile_picture_url
                            ),
                        }
                    ),
                    200,
                )
            else:
                logger.warning(
                    "Timeout waiting for auth response (message_id=%s)",
                    message_id,
                )
                return (
                    jsonify(
                        {
                            "error": "timeout",
                            "message": "Authentication request timed out",
                        }
                    ),
                    500,
                )
        except Exception as exc:
            logger.exception("Failed to get auth message response for %s", email)
            return (
                jsonify(
                    {
                        "error": "internal_error",
                        "message": "Failed to process authentication request",
                    }
                ),
                500,
            )

    except Exception as exc:
        user_identifier = (
            request_data.get("email")
            if "request_data" in locals() and request_data
            else "<unknown>"
        )
        logger.exception("Unexpected error in eater_auth_token for %s", user_identifier)
        return (
            jsonify(
                {
                    "error": "internal_error",
                    "message": "Authentication service temporarily unavailable",
                }
            ),
            500,
        )


def get_recommendation(request, user_email, local_model_service):
    try:
        proto_request = get_recomendation_pb2.RecommendationRequest()
        proto_request.ParseFromString(request.data)

        days = proto_request.days
        # Use app language from request so recommendation matches UI language
        language_code = (getattr(proto_request, "language_code", "") or "").strip().lower()
        language_override = language_code if len(language_code) == 2 else None

        if local_model_service:
            processing_topic = local_model_service.get_user_kafka_topic(
                user_email, "gemini-send"
            )
            prompt = local_model_service.get_user_prompt(
                user_email, "get_recommendation"
            )
            if language_override:
                lang_instruction = get_prompt("respond_in_language")
                prompt = f"{prompt}\n {lang_instruction}\n Target language: {language_override} "
            logger.debug(
                "Routing recommendation for user %s to topic %s",
                user_email,
                processing_topic,
            )
        else:
            prompt = create_multilingual_prompt(
                "get_recommendation", user_email, language_override=language_override
            )
            processing_topic = "gemini-send"
            logger.warning(
                "User model tier unavailable; defaulting topic %s for user %s",
                processing_topic,
                user_email,
            )
        payload = {
            "days": days,
            "prompt": prompt,
            "type_of_processing": "get_recommendation",
            "model_topic": processing_topic,
        }
        recommendation_data = eater_kafka_request(
            "get_recommendation", "gemini-response", payload, user_email, timeout_sec=90
        )
        logger.debug("Recommendation data for user %s received", user_email)
        if recommendation_data is None:
            raise ValueError(
                f"No recommendation received from Kafka for user {user_email}"
            )
        plain_text = json_to_plain_text(recommendation_data)
        logger.debug("Recommendation plain text prepared for user %s", user_email)
        proto_response = get_recomendation_pb2.RecommendationResponse()
        proto_response.recommendation = plain_text
        response_data = proto_response.SerializeToString()
        return response_data, 200, {"Content-Type": "application/protobuf"}
    except Exception as exc:
        logger.exception("Recommendation generation failed for user %s", user_email)
        return "Failed", 500


def eater_get_food_health_level(request, user_email):
    """
    Get food health level for a specific food entry by time.
    Returns: FoodHealthLevelResponse proto with title, description, health_summary
    """
    try:
        proto_request = food_health_level_pb2.FoodHealthLevelRequest()
        proto_request.ParseFromString(request.data)

        time_value = proto_request.time
        food_name = proto_request.food_name

        logger.debug(
            "Food health level request for user %s: time=%s, food_name=%s",
            user_email,
            time_value,
            food_name,
        )

        # Request food health level from Kafka (via eater backend)
        payload = {
            "time": time_value,
            "food_name": food_name,
        }
        response_data = eater_kafka_request(
            "get_food_health_level",
            "send_food_health_level",
            payload,
            user_email,
            timeout_sec=30,
        )

        proto_response = food_health_level_pb2.FoodHealthLevelResponse()

        if response_data:
            health_level = response_data.get("food_health_level", {})
            proto_response.title = health_level.get("title", "")
            proto_response.description = health_level.get("description", "")
            summary = health_level.get("health_summary", "")
            if isinstance(summary, (list, dict)):
                import json

                proto_response.health_summary = json.dumps(summary)
            else:
                proto_response.health_summary = str(summary)
        else:
            logger.warning(
                "No food health level data received for user %s, time=%s",
                user_email,
                time_value,
            )
            proto_response.title = ""
            proto_response.description = ""
            proto_response.health_summary = ""

        return (
            proto_response.SerializeToString(),
            200,
            {"Content-Type": "application/protobuf"},
        )
    except Exception as exc:
        logger.exception("Food health level request failed for user %s", user_email)
        proto_response = food_health_level_pb2.FoodHealthLevelResponse()
        return (
            proto_response.SerializeToString(),
            500,
            {"Content-Type": "application/protobuf"},
        )
