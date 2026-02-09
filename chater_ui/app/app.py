import atexit
import logging
import os
import time

import context
import jwt
import redis
from common import (before_request, chater_clear, generate_session_secret,
                    get_jwt_secret_key, rate_limit_required, token_required)
from eater_admin import eater_admin_proxy, eater_admin_request
from flask import (Flask, Response, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from flask_cors import CORS
from flask_session import Session
from google_ops import create_google_blueprint, g_login
from gphoto import gphoto, gphoto_proxy
from kafka_consumer_service import (start_kafka_consumer_service,
                                    stop_kafka_consumer_service)
from logging_config import setup_logging
from login import login, logout
from minio_utils import get_minio_client
from werkzeug.middleware.proxy_fix import ProxyFix

from chater import chater as chater_ui
from eater.eater import (alcohol_latest, alcohol_range, delete_food_record,
                         eater_auth_request, eater_custom_date, eater_photo,
                         eater_today, food_health_level, get_photo_file,
                         get_recommendations, manual_weight_record,
                         modify_food_record_data, set_language)
from eater.feedback import submit_feedback_request
from eater.user_mgmt import (add_friend_request, get_friends_request,
                           share_food_request, update_user_nickname)

from .metrics import (metrics_endpoint, record_http_metrics,
                      track_eater_operation, track_operation)

setup_logging("app.log")
logger = logging.getLogger(__name__)

log_level = os.getenv("LOG_LEVEL", "INFO")

# Dev environment detection
IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"
URL_PREFIX = "/dev" if IS_DEV else ""

redis_client = redis.StrictRedis(host=os.getenv("REDIS_ENDPOINT"), port=6379, db=0)
static_url_path = f"{URL_PREFIX}/chater/static" if IS_DEV else "/chater/static"
app = Flask(__name__, static_url_path=static_url_path)

# Initialize shared MinIO client once at app startup
try:
    app.config["MINIO_CLIENT"] = get_minio_client()
except Exception as e:
    logger.error(f"Failed to initialize MinIO client: {e}")

# Personal development configuration - secure but with debug logging
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", generate_session_secret()),
    SESSION_TYPE="redis",
    SESSION_REDIS=redis_client,
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
    SESSION_KEY_PREFIX="_dev:chater_ui:" if IS_DEV else "chater_ui:",
    # Security headers for personal app
    SESSION_COOKIE_SECURE=(
        True if os.getenv("HTTPS_ENABLED", "false").lower() == "true" else False
    ),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Enable debug logging for personal development
    DEBUG=True if log_level == "DEBUG" else False,
)

Session(app)

picFolder = "/app/app/static/pics"
SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME"))
ALLOWED_EMAILS = os.getenv("ALLOWED_EMAILS", "").split(",")

google_bp = create_google_blueprint()
google_login_prefix = f"{URL_PREFIX}/google_login" if IS_DEV else "/google_login"
app.register_blueprint(google_bp, url_prefix=google_login_prefix)
CORS(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Log dev mode status
if IS_DEV:
    logger.info("Running in DEV environment - routes will be prefixed with /dev")

# Start the background Kafka consumer service
logger.info("Starting Kafka Consumer Service...")
try:
    start_kafka_consumer_service()
except Exception as exc:
    logger.critical("Failed to start Kafka Consumer Service: %s", exc)
    raise

# Register cleanup function for graceful shutdown
atexit.register(stop_kafka_consumer_service)


def dev_route(path):
    """Returns the route path with /dev prefix when running in dev environment."""
    if IS_DEV:
        return f"/dev{path}"
    return path


@app.route(dev_route("/favicon.ico"))
def favicon_redirect():
    return redirect(url_for("static", filename="images/favicon.ico"))


@app.before_request
def before():
    if request.path != "/metrics":
        g._http_request_start_time = time.time()
    return before_request(session=session, app=app, SESSION_LIFETIME=SESSION_LIFETIME)


@app.after_request
def metrics_after_request(response):
    try:
        if request.path != "/metrics":
            start_time = getattr(g, "_http_request_start_time", time.time())
            endpoint_label = (
                request.url_rule.rule
                if getattr(request, "url_rule", None)
                else request.path
            )
            record_http_metrics(
                start_time=start_time,
                endpoint=endpoint_label,
                status=response.status_code,
            )
    finally:
        return response


@app.teardown_request
def metrics_teardown_request(exc):
    if exc is not None and request and request.path != "/metrics":
        start_time = getattr(g, "_http_request_start_time", time.time())
        endpoint_label = (
            request.url_rule.rule
            if getattr(request, "url_rule", None)
            else request.path
        )
        record_http_metrics(start_time=start_time, endpoint=endpoint_label, status=500)


@app.route(dev_route("/chater_login"), methods=["GET", "POST"])
@track_operation("chater_login")
def chater_login():
    return login(session=session)


@app.route(dev_route("/google_login"))
@track_operation("google_login")
def google_login():
    return g_login(session=session, ALLOWED_EMAILS=ALLOWED_EMAILS)


@app.route(dev_route("/chater"), methods=["GET", "POST"])
@track_operation("chater")
def chater():
    return chater_ui(session, target="chater")


@app.route(dev_route("/chamini"), methods=["GET", "POST"])
@track_operation("chamini")
def chamini():
    return chater_ui(session, target="chamini")


@app.route(dev_route("/gempt"), methods=["GET", "POST"])
@track_operation("gempt")
def gempt():
    return chater_ui(session, target="gempt")


@app.route(dev_route("/chater_clear_responses"), methods=["GET"])
@track_operation("chater_clear_responses")
def chater_clear_responses():
    return chater_clear(session=session)


@app.route(dev_route("/chater_logout"))
@track_operation("chater_logout")
def chater_logout():
    return logout(session=session)


@app.route(dev_route("/chater_wait"))
@track_operation("chater_wait")
def chater_wait():
    logger.warning("Waiting for next chater_login attempt")
    return render_template("wait.html")


@app.route(dev_route("/gphoto"), methods=["GET"])
@track_operation("gphoto")
def gphoto_ui():
    return gphoto(session, picFolder)


@app.route(dev_route("/gphoto_proxy/<path:resource_path>"), methods=["GET"])
@track_operation("gphoto_proxy")
def gphoto_proxy_route(resource_path):
    return gphoto_proxy(resource_path)


@app.route(dev_route("/toggle-switch"), methods=["POST"])
@track_operation("toggle_switch")
def toggle_switch():
    return context.context_switch(session)


@app.route(dev_route("/get-switch-state"), methods=["GET"])
@track_operation("get_switch_state")
def get_switch_state():
    return context.use_switch_state(session)


@app.route(dev_route("/toggle-dev-mode"), methods=["POST"])
@track_operation("toggle_dev_mode")
def toggle_dev_mode():
    return context.dev_mode_switch(session)


@app.route(dev_route("/get-dev-mode-state"), methods=["GET"])
@track_operation("get_dev_mode_state")
def get_dev_mode_state():
    default_state = "on" if IS_DEV else "off"
    return context.get_dev_mode_state(session, default_state)


@app.route(dev_route("/eater_test"), methods=["GET"])
@token_required
def eater(user_email):
    return jsonify({"message": f"Eater endpoint granted for user: {user_email}!"})


@app.route(dev_route("/get_photo"), methods=["GET"])
@track_eater_operation("get_photo")
def get_photo_route():
    """
    Get photo from MinIO.
    Params: image_id (query param)
    """

    image_id = request.args.get("image_id")
    if not image_id:
        return jsonify({"error": "Missing image_id"}), 400

    # Optional Auth: Try to extract user_email from token if present
    # This enables the backend to fix missing prefixes (e.g. "uuid.jpg" -> "email/uuid.jpg")
    # for authenticated users, while still allowing public access to full paths.
    user_email = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            jwt_secret = get_jwt_secret_key()
            decoded_token = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            user_email = decoded_token.get("sub")
        except Exception:
            # Ignore token errors (expired, invalid) and proceed as public/anonymous
            pass

    data, content_type = get_photo_file(image_id, user_email)
    if not data:
        return jsonify({"error": "Photo not found or accessible"}), 404

    return send_file(data, mimetype=content_type)


@app.route(dev_route("/eater_receive_photo"), methods=["POST"])
@track_eater_operation("receive_photo")
@token_required
@rate_limit_required
def eater_receive_photo(user_email):
    return eater_photo(user_email=user_email)


@app.route(dev_route("/eater_get_today"), methods=["GET"])
@track_eater_operation("get_today")
@token_required
def eater_get_today(user_email):
    return eater_today(user_email=user_email)


@app.route(dev_route("/get_food_custom_date"), methods=["POST"])
@track_eater_operation("get_food_custom_date")
@token_required
def get_food_custom_date(user_email):
    return eater_custom_date(request=request, user_email=user_email)


@app.route(dev_route("/delete_food"), methods=["POST"])
@track_eater_operation("delete_food")
@token_required
def delete_food(user_email):
    return delete_food_record(request=request, user_email=user_email)


@app.route(dev_route("/modify_food_record"), methods=["POST"])
@track_eater_operation("modify_food_record")
@token_required
def modify_food(user_email):
    return modify_food_record_data(request=request, user_email=user_email)


@app.route(dev_route("/get_recommendation"), methods=["POST"])
@track_eater_operation("get_recommendation")
@token_required
@rate_limit_required
def recommendations(user_email):
    recommendation = get_recommendations(request=request, user_email=user_email)
    return recommendation


@app.route(dev_route("/eater_auth"), methods=["POST"])
@track_eater_operation("eater_auth")
def eater_auth():
    return eater_auth_request(request=request)


@app.route(dev_route("/manual_weight"), methods=["POST"])
@track_eater_operation("manual_weight")
@token_required
def manual_weight(user_email):
    return manual_weight_record(request=request, user_email=user_email)


@app.route(dev_route("/alcohol_latest"), methods=["GET"])
@track_eater_operation("alcohol_latest")
@token_required
def get_alcohol_latest_route(user_email):
    return alcohol_latest(user_email=user_email)


@app.route(dev_route("/alcohol_range"), methods=["POST"])
@track_eater_operation("alcohol_range")
@token_required
def get_alcohol_range_route(user_email):
    return alcohol_range(request=request, user_email=user_email)


@app.route(dev_route("/feedback"), methods=["POST"])
@track_eater_operation("submit_feedback")
@token_required
def submit_feedback(user_email):
    return submit_feedback_request(user_email=user_email)


@app.route(dev_route("/eater_admin"), methods=["GET", "POST"])
@track_operation("eater_admin")
def eater_admin():
    return eater_admin_request(session)


@app.route(dev_route("/eater_admin_proxy/<path:resource_path>"), methods=["GET"])
@track_operation("eater_admin_proxy")
def eater_admin_proxy_route(resource_path):
    return eater_admin_proxy(resource_path)


@app.route(dev_route("/set_language"), methods=["POST"])
@track_eater_operation("set_language")
@token_required
def set_language_route(user_email):
    return set_language(request=request, user_email=user_email)


@app.route(dev_route("/nickname_update"), methods=["POST"])
@track_eater_operation("nickname_update")
@token_required
def nickname_update(user_email):
    return update_user_nickname(request=request, user_email=user_email)


@app.route(dev_route("/food_health_level"), methods=["POST"])
@track_eater_operation("food_health_level")
@token_required
def get_food_health_level(user_email):
    return food_health_level(request=request, user_email=user_email)


@app.route(dev_route("/autocomplete/addfriend"), methods=["POST"])
@track_eater_operation("add_friend")
@token_required
def add_friend_route(user_email):
    return add_friend_request(request=request, user_email=user_email)


@app.route(dev_route("/autocomplete/getfriend"), methods=["GET"])
@track_eater_operation("get_friend")
@token_required
def get_friend_route(user_email):
    return get_friends_request(request=request, user_email=user_email)


@app.route(dev_route("/autocomplete/sharefood"), methods=["POST"])
@track_eater_operation("share_food")
@token_required
def share_food_route(user_email):
    return share_food_request(request=request, user_email=user_email)


@app.route(dev_route("/autocomplete"), methods=["GET"])
def autocomplete_info():
    """
    Returns WebSocket endpoint information.
    This endpoint is NOT the WebSocket itself - it provides connection details.
    """
    websocket_url = os.getenv(
        "EATER_USERS_WS_URL",
        "ws://192.168.0.118/autocomplete" if IS_DEV else "ws://eater-users-service/autocomplete"
    )
    return jsonify({
        "error": "WebSocket endpoint not available on this service",
        "message": "Please connect to the WebSocket at the eater-users service",
        "websocket_url": websocket_url,
        "note": "Use WebSocket protocol (ws://) not HTTP"
    }), 400


@app.route("/metrics")
@app.route(dev_route("/metrics"))
def metrics():
    return metrics_endpoint()


if __name__ == "__main__":
    # Local development with debug logging enabled
    logging.getLogger("werkzeug").setLevel(log_level)
    logging.getLogger().setLevel(log_level)
    if log_level == "DEBUG":
        app.run(host="0.0.0.0", debug=True)
    else:
        app.run(host="0.0.0.0")
