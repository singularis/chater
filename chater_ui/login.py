import logging
import os
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, url_for
from flask_dance.contrib.google import google
from flask_wtf import FlaskForm
from werkzeug.security import check_password_hash
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, InputRequired

USERNAME = os.getenv("USERNAME")
PASSWORD_HASH = os.getenv("PASSWORD_HASH")
LAST_FAILED_ATTEMPT_TIME = None


class ChaterLoginForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired()], render_kw={"autocomplete": "username"}
    )
    password = PasswordField("Password", validators=[InputRequired()])


logger = logging.getLogger(__name__)


def login(session):
    global LAST_FAILED_ATTEMPT_TIME
    if LAST_FAILED_ATTEMPT_TIME and (
        datetime.now() - LAST_FAILED_ATTEMPT_TIME
    ) < timedelta(seconds=30):
        logger.warning("Too many failed login attempts in cooldown window")
        flash("Too many failed attempts. Please try again later.")
        return redirect(url_for("chater_wait"))
    else:
        form = ChaterLoginForm()
        if form.validate_on_submit():
            if form.username.data == USERNAME and check_password_hash(
                PASSWORD_HASH, form.password.data
            ):
                logger.info("User %s successfully authenticated", form.username.data)
                session.permanent = True
                session["logged_in"] = True
                session["username"] = form.username.data
                return redirect(url_for("chamini"))
            else:
                LAST_FAILED_ATTEMPT_TIME = datetime.now()
                logger.warning("Failed login attempt for user %s", form.username.data)
            flash("Wrong password", "error")
        return render_template("login.html", form=form)


def logout(session):
    logger.info("User initiated logout")
    if google.authorized:
        try:
            response = google.post(
                "https://accounts.google.com/o/oauth2/revoke",
                params={"token": google.token["access_token"]},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert response.ok, "Failed to revoke token"
            session.pop("google_id", None)
            session.pop("user_email", None)
        except Exception as e:
            logger.error("Failed to revoke Google token: %s", e)
    session.pop("logged_in", None)
    return redirect(url_for("chater_login"))
