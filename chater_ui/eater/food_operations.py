import logging
import uuid

import base64
import os

from flask import current_app, jsonify
from kafka_consumer_service import get_user_message_response
from kafka_producer import KafkaDispatchError, send_kafka_message

from local_models_helper import LocalModelService

from .proto import (alcohol_pb2, delete_food_pb2, manual_weight_pb2,
                    modify_food_record_pb2)
from .process_photo import _dispatch_photo_message

logger = logging.getLogger(__name__)


def _dispatch_kafka_request(topic, payload, user_email, proto_error=None):
    try:
        message_id = send_kafka_message(
            topic,
            value=payload,
            key=str(uuid.uuid4()),
            ensure_user_email=True,
        )
    except KafkaDispatchError as error:
        logger.error(
            "Failed to dispatch topic %s for user %s: %s",
            topic,
            user_email,
            error,
        )
        return None, (error.status_code, str(error))

    return message_id, None


def _await_user_response(message_id, user_email, timeout, proto_response):
    try:
        response = get_user_message_response(message_id, user_email, timeout=timeout)
    except Exception:
        logger.exception(
            "Failed to get response for user %s (message_id=%s)", user_email, message_id
        )
        proto_response.success = False
        return proto_response.SerializeToString(), 500

    if response is None:
        logger.warning(
            "Timeout waiting for response for user %s (message_id=%s)",
            user_email,
            message_id,
        )
        proto_response.success = False
        return proto_response.SerializeToString(), 500

    if response.get("error"):
        logger.error(
            "Error in response for user %s (message_id=%s): %s",
            user_email,
            message_id,
            response.get("error"),
        )
        proto_response.success = False
        return proto_response.SerializeToString(), 500

    proto_response.success = True
    return proto_response.SerializeToString(), 200


def _proto_error_response(proto_message, status, error):
    proto_message.success = False
    return (
        proto_message.SerializeToString(),
        status,
        {"Content-Type": "application/grpc+proto"},
    )


def _json_error(status, message):
    return jsonify({"success": False, "error": message}), status


def delete_food(request, user_email):
    delete_food_response = delete_food_pb2.DeleteFoodResponse()
    delete_food_request = delete_food_pb2.DeleteFoodRequest()
    try:
        proto_data = request.data
        if not proto_data:
            logger.error(
                "No Protobuf data found in the request from user %s", user_email
            )
            return jsonify({"success": False, "error": "Invalid Protobuf data"}), 400

        delete_food_request.ParseFromString(proto_data)
        time = delete_food_request.time
        logger.debug("Extracted time from Protobuf for user %s: %s", user_email, time)

        payload = {"time": time, "user_email": user_email}
        message_id, error = _dispatch_kafka_request(
            topic="delete_food", payload=payload, user_email=user_email
        )
        if error:
            status, message = error
            return _json_error(status, message)
        logger.debug(
            "Delete request dispatched for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        logger.debug(
            "Waiting for delete confirmation for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        # Get response from Redis using the background consumer service
        response_data, status = _await_user_response(
            message_id, user_email, timeout=30, proto_response=delete_food_response
        )
        return response_data, status, {"Content-Type": "application/grpc+proto"}

    except Exception as exc:
        logger.exception("Error in delete_food for user %s", user_email)
        delete_food_response.success = False
        response_data = delete_food_response.SerializeToString()
        return response_data, 500, {"Content-Type": "application/grpc+proto"}


def modify_food_record(request, user_email):
    modify_food_response = modify_food_record_pb2.ModifyFoodRecordResponse()
    modify_food_request = modify_food_record_pb2.ModifyFoodRecordRequest()
    try:
        proto_data = request.data
        if not proto_data:
            logger.error(
                "No Protobuf data found in the request from user %s", user_email
            )
            return jsonify({"success": False, "error": "Invalid Protobuf data"}), 400

        modify_food_request.ParseFromString(proto_data)
        time = modify_food_request.time
        percentage = modify_food_request.percentage
        is_try_again = modify_food_request.is_try_again
        image_id = modify_food_request.image_id
        added_sugar_tsp = modify_food_request.added_sugar_tsp
        manual_food_name = modify_food_request.manual_food_name
        manual_insight = modify_food_request.manual_insight
        manual_components = list(modify_food_request.manual_components)
        
        logger.debug(
            "Extracted modify payload for user %s: time=%s percentage=%s is_try_again=%s added_sugar_tsp=%s",
            user_email,
            time,
            percentage,
            is_try_again,
            added_sugar_tsp,
        )

        payload = {
            "time": time,
            "user_email": user_email,
            "percentage": percentage,
            "is_try_again": is_try_again,
            "image_id": image_id,
            "added_sugar_tsp": added_sugar_tsp,
            "manual_food_name": manual_food_name,
            "manual_insight": manual_insight,
            "manual_components": manual_components,
        }

        # If user is manually correcting the dish and wants a recalculation,
        # rerun photo analysis using the existing image_id and overwrite the existing record.
        if is_try_again and image_id:
            client = current_app.config.get("MINIO_CLIENT")
            if client is None:
                return _json_error(500, "MinIO client not available for try-again")

            bucket_name = os.getenv("MINIO_BUCKET_EATER", "eater")
            target_image_id = image_id if "/" in image_id else f"{user_email}/{image_id}"

            try:
                obj = client.get_object(bucket_name, target_image_id)
                photo_bytes = obj.read()
                try:
                    obj.close()
                except Exception:
                    pass
            except Exception:
                logger.exception("Failed to fetch image %s for user %s", target_image_id, user_email)
                return _json_error(500, "Failed to fetch image for try-again")

            photo_base64 = base64.b64encode(photo_bytes).decode("utf-8")
            message_id = str(uuid.uuid4())
            local_model_service = LocalModelService()

            suffix = None
            if manual_food_name:
                suffix = (
                    "IMPORTANT: The user corrected the dish name. "
                    f"Use exactly this value as dish_name: {manual_food_name!r}. "
                    "Do NOT guess another name."
                )

            try:
                _dispatch_photo_message(
                    photo_base64=photo_base64,
                    type_of_processing="default_prompt",
                    user_email=user_email,
                    message_id=message_id,
                    local_model_service=local_model_service,
                    image_path=image_id,
                    timestamp=str(time),
                    date=None,
                    prompt_suffix=suffix,
                )
            except KafkaDispatchError as error:
                return _json_error(error.status_code, str(error))

            # Wait for completion signal (same mechanism as eater_receive_photo)
            response = get_user_message_response(message_id, user_email, timeout=60)
            if not response or response.get("error"):
                modify_food_response.success = False
                return (
                    modify_food_response.SerializeToString(),
                    500,
                    {"Content-Type": "application/grpc+proto"},
                )

            modify_food_response.success = True
            return (
                modify_food_response.SerializeToString(),
                200,
                {"Content-Type": "application/grpc+proto"},
            )

        message_id, error = _dispatch_kafka_request(
            topic="modify_food_record",
            payload=payload,
            user_email=user_email,
        )
        if error:
            status, message = error
            return _json_error(status, message)
        logger.debug(
            "Modify request dispatched for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        logger.debug(
            "Waiting for modify confirmation for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        # Get response from Redis using the background consumer service
        try:
            response = get_user_message_response(message_id, user_email, timeout=30)
            if response is not None:
                logger.debug("Retrieved modify confirmation for user %s", user_email)

                if response.get("error"):
                    logger.error(
                        "Error in modify response for user %s: %s",
                        user_email,
                        response.get("error"),
                    )
                    modify_food_response.success = False
                    response_data = modify_food_response.SerializeToString()
                    return (
                        response_data,
                        500,
                        {"Content-Type": "application/grpc+proto"},
                    )

                modify_food_response.success = True
                response_data = modify_food_response.SerializeToString()
                return (
                    response_data,
                    200,
                    {"Content-Type": "application/grpc+proto"},
                )
            else:
                logger.warning(
                    "Timeout waiting for modify confirmation for user %s (message_id=%s)",
                    user_email,
                    message_id,
                )
                modify_food_response.success = False
                response_data = modify_food_response.SerializeToString()
                return (
                    response_data,
                    500,
                    {"Content-Type": "application/grpc+proto"},
                )
        except Exception as exc:
            logger.exception(
                "Failed to get modify confirmation for user %s", user_email
            )
            modify_food_response.success = False
            response_data = modify_food_response.SerializeToString()
            return (
                response_data,
                500,
                {"Content-Type": "application/grpc+proto"},
            )

    except Exception as exc:
        logger.exception("Error in modify_food_record for user %s", user_email)
        modify_food_response.success = False
        response_data = modify_food_response.SerializeToString()
        return response_data, 500, {"Content-Type": "application/grpc+proto"}


def modify_food_manual(request, user_email):
    """
    Lightweight JSON endpoint to allow manual dish name correction without
    going through protobuf on the UI side.
    Expects JSON body: { "time": int, "manual_food_name": str }

    This request can take several seconds (Kafka + eater service). Clients should
    show a loading state between "Save" and the success message. Chater UI provides
    a ready-made overlay: include static/css/loading-overlay.css and
    static/js/loading-overlay.js, then call loadingOverlay.show() before the
    request and loadingOverlay.hide() in a finally() block.
    """
    try:
        data = request.get_json(silent=False) or {}
    except Exception:
        logger.exception("Failed to parse JSON body for modify_food_manual (user %s)", user_email)
        return _json_error(400, "Invalid JSON body")

    time_value = data.get("time")
    manual_food_name = data.get("manual_food_name") or data.get("dish_name")

    if not time_value or not isinstance(time_value, (int, float)):
        return _json_error(400, "Missing or invalid 'time'")
    if not manual_food_name or not isinstance(manual_food_name, str):
        return _json_error(400, "Missing or invalid 'manual_food_name'")

    payload = {
        "time": int(time_value),
        "user_email": user_email,
        # Keep percentage at 100 so only name changes (no rescaling)
        "percentage": 100,
        "manual_food_name": manual_food_name,
    }

    message_id, error = _dispatch_kafka_request(
        topic="modify_food_record", payload=payload, user_email=user_email
    )
    if error:
        status, message = error
        return _json_error(status, message)

    logger.debug(
        "Manual food rename dispatched for user %s (message_id=%s, time=%s, new_name=%s)",
        user_email,
        message_id,
        time_value,
        manual_food_name,
    )

    # Wait for confirmation from background consumer service
    modify_food_response = modify_food_record_pb2.ModifyFoodRecordResponse()
    response_data, status = _await_user_response(
        message_id, user_email, timeout=30, proto_response=modify_food_response
    )

    # For JSON clients, translate proto-style response into JSON
    success = status == 200 and modify_food_response.success
    return jsonify({"success": success}), (200 if success else 500)


def manual_weight(request, user_email):
    manual_weight_response = manual_weight_pb2.ManualWeightResponse()
    manual_weight_request = manual_weight_pb2.ManualWeightRequest()
    try:
        proto_data = request.data
        if not proto_data:
            logger.error(
                f"No Protobuf data found in the request from user: {user_email}"
            )
            return jsonify({"success": False, "error": "Invalid Protobuf data"}), 400

        manual_weight_request.ParseFromString(proto_data)
        weight = manual_weight_request.weight
        user_email_from_proto = manual_weight_request.user_email
        logger.debug(
            "Extracted manual weight request for user %s: weight=%s",
            user_email,
            weight,
        )

        payload = {
            "user_email": user_email_from_proto,
            "weight": weight,
            "type": "weight_processing",
        }
        message_id, error = _dispatch_kafka_request(
            topic="manual_weight",
            payload=payload,
            user_email=user_email,
        )
        if error:
            status, _message = error
            manual_weight_response.success = False
            response_data = manual_weight_response.SerializeToString()
            return response_data, status, {"Content-Type": "application/grpc+proto"}
        logger.debug(
            "Manual weight request dispatched for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        # Return success immediately after sending the message
        manual_weight_response.success = True
        response_data = manual_weight_response.SerializeToString()
        return (
            response_data,
            200,
            {"Content-Type": "application/grpc+proto"},
        )

    except Exception as exc:
        logger.exception("Error in manual_weight for user %s", user_email)
        manual_weight_response.success = False
        response_data = manual_weight_response.SerializeToString()
        return response_data, 500, {"Content-Type": "application/grpc+proto"}


def get_alcohol_latest(user_email):
    response = alcohol_pb2.GetAlcoholLatestResponse()
    try:
        payload = {"user_email": user_email}
        message_id, error = _dispatch_kafka_request(
            topic="get_alcohol_latest",
            payload=payload,
            user_email=user_email,
        )
        if error:
            status, _message = error
            return (
                response.SerializeToString(),
                status,
                {"Content-Type": "application/grpc+proto"},
            )

        logger.debug(
            "Requested latest alcohol summary for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        # Wait for response
        kafka_response = get_user_message_response(message_id, user_email, timeout=30)
        if not kafka_response:
            logger.warning(
                "No alcohol summary received within timeout for user %s (message_id=%s)",
                user_email,
                message_id,
            )
            return (
                response.SerializeToString(),
                500,
                {"Content-Type": "application/grpc+proto"},
            )

        alcohol = kafka_response.get("alcohol", {}) or {}
        response.today_summary.total_drinks = int(alcohol.get("total_drinks", 0))
        response.today_summary.total_calories = int(alcohol.get("total_calories", 0))
        for drink in alcohol.get("drinks_of_day", []) or []:
            response.today_summary.drinks_of_day.append(drink)
        logger.debug(
            "Alcohol latest response for user %s: %s", user_email, kafka_response
        )
        return (
            response.SerializeToString(),
            200,
            {"Content-Type": "application/grpc+proto"},
        )
    except Exception as exc:
        logger.exception("Error in get_alcohol_latest for user %s", user_email)
        return (
            response.SerializeToString(),
            500,
            {"Content-Type": "application/grpc+proto"},
        )


def get_alcohol_range(request, user_email):
    response = alcohol_pb2.GetAlcoholRangeResponse()
    req = alcohol_pb2.GetAlcoholRangeRequest()
    try:
        req.ParseFromString(request.data)
        start_date = req.start_date
        end_date = req.end_date

        payload = {
            "user_email": user_email,
            "start_date": start_date,
            "end_date": end_date,
        }
        message_id, error = _dispatch_kafka_request(
            topic="get_alcohol_range",
            payload=payload,
            user_email=user_email,
        )
        if error:
            status, _message = error
            return (
                response.SerializeToString(),
                status,
                {"Content-Type": "application/grpc+proto"},
            )

        logger.debug(
            "Requested alcohol range for user %s (message_id=%s) from %s to %s",
            user_email,
            message_id,
            start_date,
            end_date,
        )

        kafka_response = get_user_message_response(message_id, user_email, timeout=30)
        if not kafka_response:
            logger.warning(
                "No alcohol range response within timeout for user %s (message_id=%s)",
                user_email,
                message_id,
            )
            return (
                response.SerializeToString(),
                500,
                {"Content-Type": "application/grpc+proto"},
            )

        # alcohol range proto only has repeated events
        for event in kafka_response.get("events", []) or []:
            proto_event = response.events.add()
            proto_event.time = int(event.get("time", 0))
            proto_event.date = event.get("date", "")
            proto_event.drink_name = event.get("drink_name", "")
            proto_event.calories = int(event.get("calories", 0))
            proto_event.quantity = int(event.get("quantity", 0))

        logger.debug(
            "Alcohol range response for user %s: %s", user_email, kafka_response
        )
        return (
            response.SerializeToString(),
            200,
            {"Content-Type": "application/grpc+proto"},
        )
    except Exception as e:
        logger.error(f"Error in get_alcohol_range for user {user_email}: {e}")
        return (
            response.SerializeToString(),
            500,
            {"Content-Type": "application/grpc+proto"},
        )
