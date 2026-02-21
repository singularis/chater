import json
import uuid
import logging
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, url_for

logger = logging.getLogger(__name__)

def gempt(session, redis_client):
    if "logged_in" not in session:
        flash("You need to log in to view this page")
        return redirect(url_for("chater_login"))

    user_id = session.get("user_email", session.get("username", "anonymous_user"))
    redis_key = f"gempt_notes_{user_id}"

    if request.method == "POST":
        note_content = request.form.get("note")
        if note_content:
            note = {
                "id": str(uuid.uuid4()),
                "content": note_content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            notes_data = redis_client.get(redis_key)
            notes = json.loads(notes_data) if notes_data else []
            notes.insert(0, note)
            redis_client.setex(redis_key, 86400, json.dumps(notes))
        return redirect(url_for("gempt"))

    notes_data = redis_client.get(redis_key)
    notes = json.loads(notes_data) if notes_data else []

    # Filter notes to ensure they are strictly not older than 24 hours
    now = datetime.now()
    valid_notes = []

    for n in notes:
        try:
            ts = datetime.strptime(n.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
            if now - ts <= timedelta(hours=24):
                valid_notes.append(n)
        except Exception:
            pass

    if len(valid_notes) < len(notes):
        if valid_notes:
            redis_client.setex(redis_key, 86400, json.dumps(valid_notes))
        else:
            redis_client.delete(redis_key)

    return render_template("gempt.html", notes=valid_notes)


def gempt_clear(session, redis_client):
    if "logged_in" not in session:
        flash("You need to log in to perform this action")
        return redirect(url_for("chater_login"))

    user_id = session.get("user_email", session.get("username", "anonymous_user"))
    redis_key = f"gempt_notes_{user_id}"
    
    redis_client.delete(redis_key)
    return redirect(url_for("gempt"))
