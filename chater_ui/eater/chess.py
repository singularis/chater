"""Chess endpoints via Kafka (app -> eater service)."""
import logging

from flask import jsonify, request
from kafka_consumer_service import get_user_message_response
from kafka_producer import KafkaDispatchError, send_kafka_message

logger = logging.getLogger(__name__)

RECORD_CHESS_GAME_TIMEOUT = 15
CHESS_READ_TIMEOUT = 10


def record_chess_game_request(user_email):
    """
    Parse request (JSON), send record_chess_game to Kafka, wait for response.
    Returns (response_body, status_code).
    """
    try:
        body = request.get_data()
        if not body:
            return jsonify({"success": False, "error": "Request body required"}), 400

        try:
            data = request.get_json(force=True, silent=True) or {}
        except Exception:
            data = {}

        player_email = (data.get("player_email") or "").strip()
        opponent_email = (data.get("opponent_email") or "").strip()
        result = (data.get("result") or "").strip()
        timestamp = int(data.get("timestamp") or 0)

        if not player_email or not opponent_email:
            return (
                jsonify({"success": False, "error": "player_email and opponent_email required"}),
                400,
            )
        if player_email != user_email:
            return jsonify({"success": False, "error": "Cannot record game for another user"}), 403
        if result not in ("win", "loss", "draw"):
            return (
                jsonify({"success": False, "error": "result must be win, loss, or draw"}),
                400,
            )

        message_id = send_kafka_message(
            "record_chess_game",
            value={
                "user_email": user_email,
                "player_email": player_email,
                "opponent_email": opponent_email,
                "result": result,
                "timestamp": timestamp,
            },
        )

        response = get_user_message_response(
            message_id, user_email, timeout=RECORD_CHESS_GAME_TIMEOUT
        )
        if response is None:
            return (
                jsonify({"success": False, "error": "Service temporarily unavailable"}),
                503,
            )
        if response.get("error"):
            return (
                jsonify({"success": False, "error": response.get("error", "Unknown error")}),
                400 if "Forbidden" in str(response.get("error")) else 500,
            )
        if not response.get("success"):
            return (
                jsonify({"success": False, "error": response.get("error", "Failed to record")}),
                500,
            )

        return jsonify({
            "success": True,
            "player_wins": response.get("player_wins", 0),
            "player_losses": response.get("player_losses", 0),
            "opponent_wins": response.get("opponent_wins", 0),
            "opponent_losses": response.get("opponent_losses", 0),
        }), 200
    except KafkaDispatchError as e:
        logger.error("Kafka error in record_chess_game for %s: %s", user_email, e)
        return jsonify({"success": False, "error": "Service unavailable"}), e.status_code
    except Exception as e:
        logger.exception("record_chess_game failed for %s: %s", user_email, e)
        return jsonify({"success": False, "error": "Internal server error"}), 500


def get_chess_stats_request(user_email):
    """
    Optional JSON body: {"opponent_email": "..."}. Send get_chess_stats to Kafka, wait for response.
    Returns (response_body, status_code).
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        opponent_email = (data.get("opponent_email") or "").strip() or None

        message_id = send_kafka_message(
            "get_chess_stats",
            value={"user_email": user_email, "opponent_email": opponent_email},
        )
        response = get_user_message_response(
            message_id, user_email, timeout=CHESS_READ_TIMEOUT
        )
        if response is None:
            return jsonify({"error": "Service temporarily unavailable"}), 503
        if response.get("error"):
            return jsonify({"error": response.get("error")}), 500
        return jsonify({
            "score": response.get("score", "0:0"),
            "opponent_name": response.get("opponent_name", ""),
            "last_game_date": response.get("last_game_date", ""),
        }), 200
    except KafkaDispatchError as e:
        logger.error("Kafka error in get_chess_stats for %s: %s", user_email, e)
        return jsonify({"error": "Service unavailable"}), e.status_code
    except Exception as e:
        logger.exception("get_chess_stats failed for %s: %s", user_email, e)
        return jsonify({"error": "Internal server error"}), 500


def get_all_chess_data_request(user_email):
    """Send get_all_chess_data to Kafka, wait for response. Returns (response_body, status_code)."""
    try:
        message_id = send_kafka_message(
            "get_all_chess_data",
            value={"user_email": user_email},
        )
        response = get_user_message_response(
            message_id, user_email, timeout=CHESS_READ_TIMEOUT
        )
        if response is None:
            return jsonify({"error": "Service temporarily unavailable"}), 503
        if response.get("error"):
            return jsonify({"error": response.get("error")}), 500
        return jsonify({
            "total_wins": response.get("total_wins", 0),
            "opponents": response.get("opponents", {}),
        }), 200
    except KafkaDispatchError as e:
        logger.error("Kafka error in get_all_chess_data for %s: %s", user_email, e)
        return jsonify({"error": "Service unavailable"}), e.status_code
    except Exception as e:
        logger.exception("get_all_chess_data failed for %s: %s", user_email, e)
        return jsonify({"error": "Internal server error"}), 500
