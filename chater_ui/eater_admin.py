import logging
import os
from urllib.parse import urlparse

import requests
from flask import Response, flash, jsonify, redirect
from flask import session as flask_session
from flask import url_for

logger = logging.getLogger(__name__)


ADMIN_PAGE_URL = os.getenv("EATER_ADMIN_PAGE_URL", "http://192.168.0.113/statistics")
_parsed = urlparse(ADMIN_PAGE_URL)
ADMIN_ASSET_BASE = f"{_parsed.scheme}://{_parsed.netloc}"


IS_DEV = os.getenv("IS_DEV", "false").lower() == "true"
URL_PREFIX = "/dev" if IS_DEV else ""

def _rewrite_html_for_proxy(html_text: str) -> str:
    """Rewrite absolute resource URLs to go through our proxy endpoint."""
    if not html_text:
        return html_text

    replacements = [
        ('src="/', f'src="{URL_PREFIX}/eater_admin_proxy/'),
        ("src='/", f"src='{URL_PREFIX}/eater_admin_proxy/"),
        ('href="/', f'href="{URL_PREFIX}/eater_admin_proxy/'),
        ("href='/", f"href='{URL_PREFIX}/eater_admin_proxy/"),
        ('srcset="/', f'srcset="{URL_PREFIX}/eater_admin_proxy/'),
        ("srcset='/", f"srcset='{URL_PREFIX}/eater_admin_proxy/"),
        ("url(/", f"url({URL_PREFIX}/eater_admin_proxy/"),
    ]

    rewritten = html_text
    for src, dst in replacements:
        rewritten = rewritten.replace(src, dst)
    return rewritten


def eater_admin_request(session):
    """
    Handle eater admin requests - check session authentication and fetch statistics page content
    """
    # Check if user is logged in via session (not token required)
    if "logged_in" not in session:
        logger.warning("Unauthorized eater_admin access attempt")
        flash("You need to log in to view this page")
        return redirect(url_for("chater_login"))

    try:
        # Fetch content from the admin statistics page
        response = requests.get(ADMIN_PAGE_URL, timeout=10)
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


def eater_admin_proxy(resource_path):
    """Proxy assets for the eater admin page to the remote admin server."""
    if "logged_in" not in flask_session:
        return redirect(url_for("chater_login"))

    target_url = f"{ADMIN_ASSET_BASE.rstrip('/')}/{resource_path}"
    try:
        proxied = requests.get(target_url, stream=True, timeout=15)
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
