import base64
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from common import get_prompt, get_respond_in_language, resize_image
from flask import current_app, jsonify, request
from kafka_consumer_service import get_user_message_response
from kafka_producer import KafkaDispatchError, send_kafka_message
from minio_utils import put_bytes

from .proto import eater_photo_pb2

logger = logging.getLogger(__name__)


def _upload_to_minio_background(
    minio_client, bucket_name, object_name, photo_bytes, user_email
):
    try:
        put_bytes(
            minio_client,
            bucket_name,
            object_name,
            photo_bytes,
            content_type="image/jpeg",
        )
        logger.info(
            "Photo uploaded to MinIO at %s/%s for user %s",
            bucket_name,
            object_name,
            user_email,
        )
    except Exception as exc:
        logger.exception(
            "Error uploading photo to MinIO for user %s: %s", user_email, exc
        )


def eater_get_photo(user_email, local_model_service):
    try:
        photo_message = eater_photo_pb2.PhotoMessage()
        photo_message.ParseFromString(request.data)

        # 1. Receive Past Timestamps
        timestamp_str = photo_message.time
        timestamp = None
        
        # Default to current UTC time if not provided
        current_dt = datetime.now(timezone.utc)
        
        if timestamp_str:
            try:
                 if 'T' in timestamp_str or '-' in timestamp_str:
                     clean_ts = timestamp_str.replace('Z', '+00:00')
                     provided_dt = datetime.fromisoformat(clean_ts)
                     if provided_dt.tzinfo is None:
                         provided_dt = provided_dt.replace(tzinfo=timezone.utc)
                     
                     provided_dt = provided_dt.astimezone(timezone.utc)
                     logger.info("Parsed ISO8601 timestamp to datetime: %s", provided_dt)
                     ts_float_sec = provided_dt.timestamp()
                 else:
                    ts_float = float(timestamp_str)
                    if ts_float > 100000000000:
                       ts_float_sec = ts_float / 1000.0
                    else:
                       ts_float_sec = ts_float
                    
                    provided_dt = datetime.fromtimestamp(ts_float_sec, tz=timezone.utc)
                    logger.info("Parsed UTC timestamp from millis: %s", provided_dt)

                 logger.info("Parsed UTC date (YYYY-MM-DD): %s", provided_dt.strftime('%Y-%m-%d'))
                 logger.info("Current UTC server time: %s", current_dt)
                 logger.info("Date difference: %s days", (current_dt.date() - provided_dt.date()).days)
                 if provided_dt > current_dt + timedelta(hours=24):
                     logger.warning("Rejected future timestamp %s for user %s", timestamp_str, user_email)
                     return jsonify({"error": "Time cannot be in the future"}), 400
                 
                 timestamp = str(int(provided_dt.timestamp() * 1000))
                 logger.info("Storing food for date: %s with timestamp: %s", provided_dt.strftime('%d-%m-%Y'), timestamp)
            except ValueError as e:
                logger.warning("Invalid timestamp format %s for user %s, using current time. Error: %s", timestamp_str, user_email, e)
                current_dt = datetime.now(timezone.utc)
                timestamp = str(int(current_dt.timestamp() * 1000))
                provided_dt = current_dt

        if not timestamp:
            logger.info("No timestamp provided, using current time")
            current_dt = datetime.now(timezone.utc)
            timestamp = str(int(current_dt.timestamp() * 1000))
            provided_dt = current_dt

        photo_data = photo_message.photo_data
        type_of_processing = photo_message.photoType
        logger.debug("Received photo metadata for user %s", user_email)
        logger.debug(
            "Raw photo payload size for user %s: %s bytes", user_email, len(photo_data)
        )
        logger.debug("Task type for user %s: %s", user_email, type_of_processing)
        resized_photo_data = resize_image(photo_data, max_size=(1024, 1024))
        logger.debug(
            "Resized photo payload size for user %s: %s bytes",
            user_email,
            len(resized_photo_data),
        )    
        upload_time_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        object_name = f"{user_email}/{upload_time_str}.jpg"

        message_id = str(uuid.uuid4())
        photo_base64 = base64.b64encode(resized_photo_data).decode("utf-8")
        
        # Fast-track water detection BEFORE AI to avoid 504 timeout
        if type_of_processing == "default_prompt":
            try:
                from PIL import Image
                import io
                import numpy as np
                
                # Quick pixel analysis
                image = Image.open(io.BytesIO(resized_photo_data)).convert('RGB')
                pixels = np.array(image)
                
                # Check if image is mostly transparent/light colored (potential water)
                # Water photos typically have high brightness and low color variance
                brightness = pixels.mean()
                color_std = pixels.std()
                
                logger.info(f"Quick water check for {user_email}: brightness={brightness:.1f}, std={color_std:.1f}")
                
                # If very bright (>180) and low variance (<40), likely water
                if brightness > 180 and color_std < 40:
                    logger.info(f"✅ Fast-track water detected for {user_email} - skipping AI")
                    water_response = {
                        "type": "food_processing",
                        "dish_name": "Water",
                        "estimated_avg_calories": 0,
                        "ingredients": ["Water"],
                        "total_avg_weight": 250,
                        "health_rating": 100,
                        "food_health_level": {
                            "title": "Pure Hydration 💧",
                            "description": "Perfect choice! Staying hydrated is essential for health and wellbeing.",
                            "health_summary": [{
                                "ingredients": "Water 💧",
                                "description": "Zero calories, pure hydration, essential for life",
                                "risk": "None",
                                "benefit": "Essential hydration"
                            }]
                        },
                        "contains": {
                            "proteins": 0,
                            "fats": 0,
                            "carbohydrates": 0,
                            "sugar": 0,
                            "is_alcohol": False
                        }
                    }
                    
                    # Upload to MinIO in background
                    threading.Thread(
                        target=_upload_to_minio_background,
                        args=(
                            current_app.config.get("MINIO_CLIENT"),
                            os.getenv("MINIO_BUCKET_EATER", "eater"),
                            object_name,
                            resized_photo_data,
                            user_email,
                        ),
                        daemon=True,
                    ).start()
                    
                    return jsonify(water_response)
            except Exception as e:
                logger.warning(f"Fast water check failed for {user_email}: {e} - continuing with AI")
        
        try:
            _dispatch_photo_message(
                photo_base64,
                type_of_processing,
                user_email,
                message_id,
                local_model_service,
                image_path=object_name,
                timestamp=timestamp,
                date=provided_dt.strftime('%d-%m-%Y')
            )
        except KafkaDispatchError as kafka_error:
            logger.error(
                "Failed to dispatch photo request for user %s: %s",
                user_email,
                kafka_error,
            )
            return (
                jsonify(
                    {"message": "Kafka dispatch failed", "error": str(kafka_error)}
                ),
                kafka_error.status_code,
            )

        logger.info(
            "Waiting for photo analysis response for user %s (message_id=%s)",
            user_email,
            message_id,
        )

        # Get response from Redis using the background consumer service
        try:
            response = get_user_message_response(message_id, user_email, timeout=60)
            if response is not None:
                logger.debug(
                    "Retrieved photo analysis response for user %s", user_email
                )

                if response.get("error"):
                    logger.error(
                        "Error in photo analysis response for user %s: %s",
                        user_email,
                        response.get("error"),
                    )
                    return jsonify({"error": response.get("error")}), 400
                else:
                    # Trigger MinIO upload in background; do not block the response
                    client = current_app.config.get("MINIO_CLIENT")
                    bucket_name = os.getenv("MINIO_BUCKET_EATER", "eater")
                    if client is None:
                        logger.error("MINIO client is not initialized; skipping upload")
                    else:
                        threading.Thread(
                            target=_upload_to_minio_background,
                            args=(
                                client,
                                bucket_name,
                                object_name,
                                resized_photo_data,
                                user_email,
                            ),
                            daemon=True,
                        ).start()
                    
                    return jsonify(response)
            else:
                logger.warning(
                    "Timeout waiting for photo analysis response for user %s (message_id=%s)",
                    user_email,
                    message_id,
                )
                return "Timeout", 408
        except Exception as exc:
            logger.exception(
                "Failed to get photo analysis response for user %s", user_email
            )
            return "Timeout", 408

    except Exception as exc:
        logger.exception("Error processing request for user %s", user_email)
        return (
            jsonify({"message": "Failed to process the request", "error": str(exc)}),
            400,
        )


def _dispatch_photo_message(
    photo_base64,
    type_of_processing,
    user_email,
    message_id,
    local_model_service,
    topic="eater-send-photo",
    image_path=None,
    timestamp=None,
    date=None
):
    photo_uuid = message_id or str(uuid.uuid4())
    clear_prompt = get_prompt(type_of_processing)
    try:
        lang_instruction = get_prompt("respond_in_language")
        user_lang = get_respond_in_language(user_email)
        prompt = f"{clear_prompt}\n {lang_instruction}\n Target language: {user_lang} "
    except Exception:
        pass

    # Use image_path (MinIO object name) as image_id if valid, else use uuid
    image_id_to_send = image_path if image_path else photo_uuid

    payload = {
        "prompt": prompt,
        "photo": photo_base64,
        "user_email": user_email,
        "image_id": image_id_to_send,
        "timestamp": timestamp,
        "date": date
    }
    logger.debug("Food image %s queued for user %s with timestamp %s and date %s", photo_uuid, user_email, timestamp, date)
    destination_topic = topic
    if type_of_processing == "weight_prompt":
        destination_topic = "chater-vision"
        payload = {
            "prompt": clear_prompt,
            "photo": photo_base64,
            "user_email": user_email,
            "timestamp": timestamp,
            "date": date
        }
        logger.debug(
            "Routing weight prompt for user %s to topic %s",
            user_email,
            destination_topic,
        )
    elif type_of_processing == "default_prompt":
        if local_model_service:
            destination_topic = local_model_service.get_user_kafka_topic(
                user_email, topic
            )
        else:
            logger.warning(
                "User model tier lookup unavailable; using default topic %s for user %s",
                destination_topic,
                user_email,
            )
    elif type_of_processing not in {"eater-send-photo", "weight_prompt"}:
        logger.error(
            "Invalid processing type %s for user %s; using default topic %s",
            type_of_processing,
            user_email,
            destination_topic,
        )

    send_kafka_message(
        destination_topic,
        value=payload,
        key=photo_uuid,
        ensure_user_email=True,
    )
