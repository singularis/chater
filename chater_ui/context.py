import logging

from flask import jsonify, request

logger = logging.getLogger(__name__)


def context_switch(session):
    state = request.json.get("state", "off")
    session["switch_state"] = state
    logger.debug("Switch state updated to %s", state)
    return jsonify({"status": "success", "state": state})


def use_switch_state(session):
    # Retrieve the switch state from the session
    switch_state = session.get("switch_state", "off")
    logger.debug("Switch state read from session: %s", switch_state)
    return jsonify({"switch_state": switch_state})


def dev_mode_switch(session):
    state = request.json.get("state", "off")
    session["dev_mode"] = state
    logger.debug("Dev mode state updated to %s", state)
    return jsonify({"status": "success", "state": state})


def get_dev_mode_state(session, default_state="off"):
    # Retrieve the dev mode state from the session
    dev_mode = session.get("dev_mode", default_state)
    return jsonify({"dev_mode": dev_mode})
