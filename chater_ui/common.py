import base64
import hashlib
import io
import logging
import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
import redis
import yaml
from flask import flash, jsonify, redirect, request, url_for
from PIL import Image
from user import get_user_language, update_user_activity

logger = logging.getLogger(__name__)
SECRET_KEY = str(os.getenv("EATER_SECRET_KEY"))
PROMPT_FILE = "eater/prompt.yaml"

# Redis client for rate limiting
redis_client = redis.StrictRedis(host=os.getenv("REDIS_ENDPOINT"), port=6379, db=0)

IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"
KEY_PREFIX = "_dev:" if IS_DEV else ""


def get_jwt_secret_key():
    """
    Get the JWT secret key, deriving a 256-bit key if the original is too short.
    This matches the logic used in the chater-auth service.
    """
    if not SECRET_KEY:
        raise ValueError("EATER_SECRET_KEY environment variable not set")

    secret_bytes = SECRET_KEY.encode("utf-8")

    # If the secret is already 32+ bytes, use it directly
    # Otherwise, derive a 256-bit key using SHA-256
    if len(secret_bytes) >= 32:
        return SECRET_KEY
    else:
        # Derive a 256-bit key from the secret using SHA-256
        hash_obj = hashlib.sha256(secret_bytes)
        derived_key = hash_obj.digest()
        logger.debug(
            "Secret key was too short (%d bits), derived 256-bit key using SHA-256",
            len(secret_bytes) * 8,
        )
        return derived_key


def before_request(session, app, SESSION_LIFETIME):
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=SESSION_LIFETIME)
    session.modified = True
    if "logged_in" in session:
        last_activity_str = session.get("last_activity", None)
        if last_activity_str:
            if isinstance(last_activity_str, datetime):
                last_activity_str = last_activity_str.strftime("%Y-%m-%d %H:%M:%S")
            last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now() - last_activity > timedelta(hours=SESSION_LIFETIME):
                session.pop("logged_in", None)
                logger.info("logged out due to inactivity: %s", last_activity_str)
                flash("You have been logged out due to inactivity.")
                return redirect(url_for("chater_login"))
        session["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def chater_clear(session):
    if "logged_in" in session:
        session["responses"] = []
        session["context"] = None
        flash("Responses cleared successfully")
        referrer = request.referrer
        if referrer:
            return redirect(referrer)
        else:
            return redirect(url_for("chater"))
    else:
        logger.warning("Unauthorized clear attempt")
        flash("You need to log in to perform this action")
        return redirect(url_for("chater_login"))


def token_required(f):
    @wraps(f)  # This preserves the original function's metadata
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.debug("Authorization header is missing")
            return jsonify({"message": "Token is missing"}), 401
        if not auth_header.startswith("Bearer "):
            logger.debug("Authorization header is invalid: %s", auth_header)
            return jsonify({"message": "Invalid token format"}), 401
        try:
            token = auth_header.split(" ")[1]
            jwt_secret = get_jwt_secret_key()
            decoded_token = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            logger.debug("Decoded token subject: %s", decoded_token.get("sub"))
            kwargs["user_email"] = decoded_token.get("sub")
            if kwargs["user_email"]:
                update_user_activity(kwargs["user_email"])
        except jwt.ExpiredSignatureError:
            logger.debug("Token has expired")
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            logger.debug("Invalid token: %s", str(e))
            return jsonify({"message": "Invalid token"}), 401

        return f(*args, **kwargs)

    return wrapper


def rate_limit_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Get user_email from kwargs (should be set by token_required decorator)
        user_email = kwargs.get("user_email")
        daily_limit = int(os.getenv("DAILY_REQUEST_LIMIT", "10"))
        if not user_email:
            logger.error("Rate limit check failed: no user_email found")
            return jsonify({"message": "Authentication required"}), 401

        # Check rate limit
        if not check_rate_limit(user_email):
            logger.warning("Rate limit exceeded for user %s", user_email)
            return (
                jsonify(
                    {
                        "error": f"Unfortuantly, you have reached your daily limit of {daily_limit} requests. Please try again tomorrow, be mingfull and eat healthy food."
                    }
                ),
                400,
            )

        return f(*args, **kwargs)

    return wrapper


def check_rate_limit(user_email):
    """Check if user has exceeded daily rate limit"""
    try:
        # Get daily limit from environment variable
        daily_limit = int(os.getenv("DAILY_REQUEST_LIMIT", "10"))

        if user_email == os.getenv("TEST_USER_EMAIL", ""):
            logger.debug("Rate limit check skipped for test user %s", user_email)
            return True
        # Get current UTC date as key
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        redis_key = f"{KEY_PREFIX}rate_limit:{user_email}:{current_date}"

        # Get current count
        current_count = redis_client.get(redis_key)
        if current_count is None:
            current_count = 0
        else:
            current_count = int(current_count)

        # Check if limit exceeded
        if current_count >= daily_limit:
            logger.warning(
                "Rate limit exceeded for user %s: %d/%d",
                user_email,
                current_count,
                daily_limit,
            )
            return False

        # Increment counter
        redis_client.incr(redis_key)

        next_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        expiry_seconds = int((next_day - datetime.now(timezone.utc)).total_seconds())
        redis_client.expire(redis_key, expiry_seconds)

        logger.debug(
            "Rate limit check passed for user %s: %d/%d",
            user_email,
            current_count + 1,
            daily_limit,
        )
        return True

    except Exception as e:
        logger.error("Error checking rate limit for user %s: %s", user_email, e)
        return True


def get_prompt(key):
    try:
        logger.debug("Attempting to open the file %s.", PROMPT_FILE)
        with open(PROMPT_FILE, "r") as file:
            data = yaml.safe_load(file)
            logger.info("Successfully loaded data from %s.", PROMPT_FILE)
        value = data.get(key)
        if value is not None:
            logger.info("Key '%s' found in the YAML file.", key)
            return value
        else:
            logger.error("Key '%s' is not defined in the YAML file.", key)
            raise ValueError(f"Key '{key}' is not defined in the YAML file.")
    except FileNotFoundError:
        logger.critical("The file %s was not found.", PROMPT_FILE)
        raise FileNotFoundError(f"Error: The file {PROMPT_FILE} was not found.")
    except yaml.YAMLError as e:
        logger.error("Error parsing YAML file: %s", e)
        raise ValueError(f"Error parsing YAML file: {e}")
    except Exception as e:
        logger.exception("An unexpected error occurred: %s", e)
        raise RuntimeError(f"An unexpected error occurred: {e}")


def get_respond_in_language(user_email: str) -> str:
    try:
        key = f"{KEY_PREFIX}user_language:{user_email}"
        cached = redis_client.get(key)
        if cached:
            return cached.decode("utf-8")
    except Exception:
        cached = None

    try:
        language = get_user_language(user_email) or "en"
        try:
            redis_client.setex(f"{KEY_PREFIX}user_language:{user_email}", 7 * 24 * 3600, language)
        except Exception:
            pass
        return language
    except Exception:
        return "en"


def create_multilingual_prompt(
    base_prompt_key: str, user_email: str, is_add_lang_instruction: bool = True
) -> str:
    """
    Create a multilingual prompt by combining a base prompt with language instructions.

    Args:
        base_prompt_key: The key for the base prompt in prompt.yaml
        user_email: User email to determine language preference

    Returns:
        Combined prompt with language instructions
    """
    try:
        base_prompt = get_prompt(base_prompt_key)
        lang_instruction = get_prompt("respond_in_language")
        user_lang = get_respond_in_language(user_email)

        # Combine prompts with language instruction
        if is_add_lang_instruction:
            combined_prompt = (
                f"{base_prompt}\n {lang_instruction}\n Target language: {user_lang} "
            )
        else:
            combined_prompt = base_prompt + f"\n respond_in_language: {user_lang} "
        return combined_prompt
    except Exception as e:
        logger.warning(
            "Failed to create multilingual prompt for %s: %s", base_prompt_key, e
        )
        # Fallback to base prompt only
        return get_prompt(base_prompt_key)


def resize_image(image_data, max_size=(1024, 1024)):
    try:
        image = Image.open(io.BytesIO(image_data))

        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save the resized image back to binary
        output = io.BytesIO()
        image.save(output, format=image.format)
        return output.getvalue()
    except Exception as e:
        logger.error("Failed to resize image: %s", e)
        raise


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


import json


def sanitize_data_for_logging(data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON string"}

    if not isinstance(data, dict):
        return {"error": "Data is not a dictionary"}

    sensitive_fields = {
        "user_email",
        "userEmail",
        "email",
        "key",
        "value",
        "type_of_processing",
        "days",
        "prompt",
        "internal_id",
        "session_id",
        "request_id",
        "timestamp",
        "created_at",
        "password",
        "token",
        "secret",
        "api_key",
        "auth_token",
    }

    sanitized = {}
    for key, value in data.items():
        if key not in sensitive_fields:
            if isinstance(value, dict):
                sanitized[key] = sanitize_data_for_logging(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    sanitize_data_for_logging(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

    return sanitized


def json_to_plain_text(json_data):
    if isinstance(json_data, str):
        cleaned_data = json_data.strip()
        if cleaned_data.startswith("```json"):
            cleaned_data = cleaned_data[len("```json") :].strip("`").strip()
        elif cleaned_data.startswith("json"):
            cleaned_data = cleaned_data[len("json") :].strip()

        try:
            json_data = json.loads(cleaned_data)
        except json.JSONDecodeError:
            return "Invalid JSON input."

    sensitive_fields = {
        "user_email",
        "userEmail",
        "email",
        "key",
        "value",
        "type_of_processing",
        "days",
        "prompt",
        "internal_id",
        "session_id",
        "request_id",
        "timestamp",
        "created_at",
    }

    json_data = {k: v for k, v in json_data.items() if k not in sensitive_fields}
    output_text = ""

    translation_keys = json_data.get("translation_keys", {})

    default_headers = {
        "foods_to_reduce_or_avoid": "Foods to Reduce or Avoid",
        "healthier_foods": "Healthier Food Options",
        "general_recommendations": "General Recommendations",
    }

    section_headers = {
        key: translation_keys.get(key, default)
        for key, default in default_headers.items()
    }

    def format_food_list(foods, header_key):
        if not foods or not isinstance(foods, list):
            return ""

        result = f"{section_headers[header_key]}:\n\n"
        for food in foods:
            if isinstance(food, dict):
                dish_name = food.get("dish_name", "Unnamed Dish")
                reason = food.get("reason", "")
                result += f"- {dish_name}: {reason}\n"
            else:
                result += f"- {food}\n"
        return result + "\n"

    def format_recommendations(recommendations):
        if not recommendations:
            return ""

        result = f"{section_headers['general_recommendations']}:\n\n"
        if isinstance(recommendations, dict):
            for value in recommendations.values():
                result += f"- {value}\n"
        elif isinstance(recommendations, list):
            for rec in recommendations:
                result += f"- {rec}\n"
        else:
            result += f"{recommendations}\n"
        return result + "\n"

    output_text += format_food_list(
        json_data.get("foods_to_reduce_or_avoid"), "foods_to_reduce_or_avoid"
    )
    output_text += format_food_list(json_data.get("healthier_foods"), "healthier_foods")
    output_text += format_recommendations(json_data.get("general_recommendations"))

    excluded_fields = {
        "general_recommendations",
        "healthier_foods",
        "foods_to_reduce_or_avoid",
        "translation_keys",
    }

    for key, value in json_data.items():
        if key in excluded_fields or key == "error":
            continue

        display_key = translation_keys.get(key, key.replace("_", " ").title())

        if isinstance(value, list):
            output_text += f"{display_key}:\n"
            for item in value:
                if isinstance(item, dict):
                    for sub_key, sub_value in item.items():
                        sub_display_key = translation_keys.get(
                            sub_key, sub_key.replace("_", " ").title()
                        )
                        output_text += f"  - {sub_display_key}: {sub_value}\n"
                else:
                    output_text += f"- {item}\n"
            output_text += "\n"
        elif isinstance(value, str):
            output_text += f"{display_key}:\n{value}\n\n"
        elif isinstance(value, dict):
            output_text += f"{display_key}:\n"
            for sub_key, sub_value in value.items():
                sub_display_key = translation_keys.get(
                    sub_key, sub_key.replace("_", " ").title()
                )
                output_text += f"- {sub_display_key}: {sub_value}\n"
            output_text += "\n"
        elif isinstance(value, (int, float)):
            output_text += f"{display_key}: {value}\n\n"

    return output_text


def generate_session_secret():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(30))


def sanitize_question(question):
    sanitized_question = re.sub(r"[^\w\s.,?!-]", "", question)
    sanitized_question = sanitized_question.strip()
    sanitized_question = re.sub(r"\s+", " ", sanitized_question)
    return sanitized_question
