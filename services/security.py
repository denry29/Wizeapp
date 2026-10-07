"""Security helpers: CSRF tokens, authentication guards, response helpers.

Implemented without extra dependencies (no Flask-WTF) to keep the stack as
small as the project proposal requires.
"""

from __future__ import annotations

import hmac
import secrets
from functools import wraps
from typing import Any, Callable

from flask import (abort, current_app, jsonify, redirect, request, session,
                   url_for)

from managers.base_manager import (NotFoundError, PermissionDeniedError)
from services import validation

CSRF_SESSION_KEY = "_csrf_token"
CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


# ----------------------------------------------------------------- CSRF ----
def generate_csrf_token() -> str:
    """Return (and remember) the session's CSRF token."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _submitted_token() -> str:
    """Accept the token from the form body, the JSON body or a header."""
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict) and payload.get(CSRF_FIELD_NAME):
            return str(payload[CSRF_FIELD_NAME])
    token = request.form.get(CSRF_FIELD_NAME)
    if token:
        return token
    return request.headers.get(CSRF_HEADER_NAME, "")


def validate_csrf_token() -> bool:
    expected = session.get(CSRF_SESSION_KEY)
    supplied = _submitted_token()
    if not expected or not supplied:
        return False
    return hmac.compare_digest(str(expected), str(supplied))


def csrf_protect(view: Callable) -> Callable:
    """Reject state-changing requests that carry a missing/incorrect token."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        # Make sure the page has a CSRF token before its first login or signup.
        generate_csrf_token()
        if request.method not in SAFE_METHODS and not validate_csrf_token():
            if _wants_json():
                return jsonify({"error": "Invalid or missing CSRF token."}), 400
            abort(400, description="Invalid or missing CSRF token.")
        return view(*args, **kwargs)

    return wrapper


# ------------------------------------------------------- authentication ----
def login_required(view: Callable) -> Callable:
    """Protect a view so that only signed-in users can reach it.

    API requests get a 401 JSON body; browsers are redirected to the *HTML*
    login page (``auth.login_page``).  Using the page endpoint name - not
    ``auth.login`` - matters, because an endpoint registered under both
    ``/auth/login`` and ``/api/auth/login`` makes ``url_for`` ambiguous.
    """

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if not session.get("user_id"):
            if _wants_json():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("auth.login_page", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def current_user_id() -> int:
    """The signed-in user's id, or 0 when anonymous (never None in routes)."""
    return int(session.get("user_id") or 0)


def _wants_json() -> bool:
    return (request.is_json
            or request.path.startswith("/api/")
            or request.accept_mimetypes.best == "application/json")


def api_error(error: Exception):
    """Translate a domain exception into a proper HTTP response."""
    if isinstance(error, NotFoundError):
        return jsonify({"error": error.message, "resource": error.resource}), 404
    if isinstance(error, PermissionDeniedError):
        return jsonify({"error": error.message}), 403
    if isinstance(error, validation.ValidationError):
        return jsonify({"error": error.message, "field": error.field}), 400
    if isinstance(error, (ValueError, TypeError)):
        return jsonify({"error": "Invalid request data."}), 400
    current_app.logger.exception("Unhandled error: %s", error)
    return jsonify({"error": "Something went wrong. Please try again."}), 500


def json_ok(payload: Any, status: int = 200):
    return jsonify(payload), status