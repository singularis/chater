import logging
import os

import requests
from flask import Response, flash, jsonify, redirect
from flask import session as flask_session
from flask import url_for

logger = logging.getLogger(__name__)


BASE_GPHOTO_URL = os.getenv("GPHOTO_BASE_URL", "http://192.168.0.10:30500")


IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"
URL_PREFIX = "/dev" if IS_DEV else ""

def _rewrite_html_for_proxy(html_text: str) -> str:
    """
    Rewrite common resource URLs in HTML to go through our proxy endpoint so the
    browser doesn't try to fetch them from our Flask app root.
    """
    if not html_text:
        return html_text

    replacements = [
        ('src="/', f'src="{URL_PREFIX}/gphoto_proxy/'),
        ("src='/", f"src='{URL_PREFIX}/gphoto_proxy/"),
        ('href="/', f'href="{URL_PREFIX}/gphoto_proxy/'),
        ("href='/", f"href='{URL_PREFIX}/gphoto_proxy/"),
        ('srcset="/', f'srcset="{URL_PREFIX}/gphoto_proxy/'),
        ("srcset='/", f"srcset='{URL_PREFIX}/gphoto_proxy/"),
        ("url(/", f"url({URL_PREFIX}/gphoto_proxy/"),  # CSS url() refs
    ]

    rewritten = html_text
    for src, dst in replacements:
        rewritten = rewritten.replace(src, dst)
    return rewritten


def gphoto(session, _pic_folder=None):
    """
    Handle eater admin requests - check session authentication and fetch statistics page content
    """
    # Check if user is logged in via session (not token required)
    if "logged_in" not in session:
        logger.warning("Unauthorized eater_admin access attempt")
        flash("You need to log in to view this page")
        return redirect(url_for("chater_login"))

    try:
        response = requests.get(BASE_GPHOTO_URL, timeout=10)
        response.raise_for_status()
        # Rewrite HTML so asset requests go through our proxy endpoint
        html_text = _rewrite_html_for_proxy(response.text)
        return (
            html_text,
            response.status_code,
            {"Content-Type": response.headers.get("Content-Type", "text/html")},
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching statistics page: {e}")
        return (
            jsonify({"error": "Failed to fetch statistics data", "details": str(e)}),
            500,
        )


def gphoto_proxy(resource_path):
    """
    Proxy assets and sub-resources for the gphoto page to the remote server so the
    browser can load images, CSS, JS without cross-origin or missing-route issues.
    """
    # Ensure session is authenticated just like the main page
    if "logged_in" not in flask_session:
        return redirect(url_for("chater_login"))

    target_url = f"{BASE_GPHOTO_URL.rstrip('/')}/{resource_path}"
    try:
        proxied = requests.get(target_url, stream=True, timeout=15)
        # Build a passthrough response preserving important headers
        headers = {}
        content_type = proxied.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        cache_control = proxied.headers.get("Cache-Control")
        if cache_control:
            headers["Cache-Control"] = cache_control
        return Response(proxied.content, status=proxied.status_code, headers=headers)
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy error fetching {target_url}: {e}")
        return Response(status=502)
