import json
import uuid
import logging
import os
from datetime import datetime, timedelta

from flask import Response, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename
from minio_utils import get_minio_client, put_bytes

logger = logging.getLogger(__name__)

def gempt(session, redis_client):
    if "logged_in" not in session:
        flash("You need to log in to view this page")
        return redirect(url_for("chater_login"))

    user_id = session.get("user_email", session.get("username", "anonymous_user"))
    redis_key = f"gempt_notes_{user_id}"

    if request.method == "POST":
        note_content = request.form.get("note")
        file_obj = request.files.get("file")
        
        if note_content:
            note = {
                "id": str(uuid.uuid4()),
                "content": note_content,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Handle MinIO file upload if present
            if file_obj and file_obj.filename:
                try:
                    client = get_minio_client()
                    bucket_name = "gempt"
                    if not client.bucket_exists(bucket_name):
                        client.make_bucket(bucket_name)

                    safe_filename = secure_filename(file_obj.filename)
                    object_name = f"{uuid.uuid4()}_{safe_filename}"
                    file_bytes = file_obj.read()
                    
                    put_bytes(
                        client, 
                        bucket_name, 
                        object_name, 
                        file_bytes, 
                        content_type=file_obj.content_type
                    )
                    
                    note["filename"] = object_name
                    note["original_filename"] = safe_filename
                except Exception as e:
                    logger.error("Failed to upload file to minio: %s", e)
                    flash("Failed to upload the file attachment.")
            
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


def get_gempt_file(session, filename):
    if "logged_in" not in session:
        return Response("Unauthorized", status=401)
        
    client = get_minio_client()
    try:
        response = client.get_object("gempt", filename)
        return Response(
            response.read(), 
            mimetype=response.headers.get("Content-Type", "application/octet-stream")
        )
    except Exception as e:
        logger.error("Error fetching file %s: %s", filename, e)
        return Response("Not found", status=404)
    finally:
        if 'response' in locals():
            response.close()
            response.release_conn()
