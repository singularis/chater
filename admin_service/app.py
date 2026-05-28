import logging
import os
import threading
from datetime import datetime

from feedback_processor import process_feedback_messages
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from logging_config import setup_logging
from postgres import (create_feedback_table, get_all_feedback_data,
                      get_feedback_data_by_user, get_user_statistics)

# Configure logging
setup_logging("admin_service.log")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialize database
try:
    create_feedback_table()
    logger.info("Database initialized successfully")
    logger.info("Testing GitOps deployment!")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")


@app.route("/")
def index():
    """Home page with admin interface."""
    try:
        statistics = get_user_statistics()
        return render_template("index.html", statistics=statistics)
    except Exception as e:
        logger.error(f"Error getting statistics for home page: {e}")
        default_stats = {
            "total_users": 0,
            "active_users_7_days": 0,
            "active_users_30_days": 0,
            "constantly_active_7_days": 0,
            "constantly_active_7_days_emails": [],
            "constantly_active_30_days": 0,
            "constantly_active_30_days_emails": [],
            "total_dishes_scanned": 0,
            "total_feedback_records": 0,
            "avg_dishes_per_user": 0,
        }
        return render_template("index.html", statistics=default_stats)


@app.route("/feedbacks")
def feedbacks():
    """Show feedback data."""
    try:
        feedback_data = get_all_feedback_data()
        return render_template(
            "feedbacks.html",
            feedback_data=feedback_data,
            total_count=len(feedback_data),
        )
    except Exception as e:
        logger.error(f"Error displaying feedback data: {e}")
        return f"Error loading feedback data: {str(e)}", 500


@app.route("/api/admin")
def api_admin():
    """API endpoint to get all admin data as JSON."""
    try:
        feedback_data = get_all_feedback_data()
        return jsonify(
            {
                "success": True,
                "count": len(feedback_data),
                "feedback_data": feedback_data,
            }
        )
    except Exception as e:
        logger.error(f"Error getting feedback data via API: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/<user_email>")
def api_user_admin(user_email):
    """API endpoint to get admin data for a specific user."""
    try:
        feedback_data = get_feedback_data_by_user(user_email)
        return jsonify(
            {
                "success": True,
                "user_email": user_email,
                "count": len(feedback_data),
                "feedback_data": feedback_data,
            }
        )
    except Exception as e:
        logger.error(f"Error getting feedback data for user {user_email}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/statistics")
def user_statistics():
    """User statistics page."""
    try:
        statistics = get_user_statistics()
        return render_template("user_statistics.html", statistics=statistics)
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        default_stats = {
            "total_users": 0,
            "active_users_7_days": 0,
            "active_users_30_days": 0,
            "constantly_active_7_days": 0,
            "constantly_active_7_days_emails": [],
            "constantly_active_30_days": 0,
            "constantly_active_30_days_emails": [],
            "total_dishes_scanned": 0,
            "total_feedback_records": 0,
            "avg_dishes_per_user": 0,
        }
        return render_template("user_statistics.html", statistics=default_stats)


@app.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "admin-service",
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Start the feedback processor in a background thread
    processor_thread = threading.Thread(target=process_feedback_messages, daemon=True)
    processor_thread.start()
    logger.info("Feedback processor started in background thread")

    logger.info(f"Starting Admin Service on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
