"""Blueprint for authentication.

HTML pages and the JSON API are deliberately **separate endpoints**:

* ``auth.register_page`` -> ``/auth/register``     (always HTML)
* ``auth.login_page``    -> ``/auth/login``        (always HTML)
* ``auth.logout_page``   -> ``/auth/logout``       (always redirect)
* ``auth.profile``       -> ``/auth/profile``     (always HTML)
* ``auth.register_api``  -> ``/api/auth/register`` (always JSON)
* ``auth.login_api``     -> ``/api/auth/login``    (always JSON)
* ``auth.logout_api``    -> ``/api/auth/logout``   (always JSON)
* ``auth.me``            -> ``/api/auth/me``       (always JSON)

Why they are split: registering *one* view under two URLs made
``url_for("auth.login")`` ambiguous - Werkzeug returns the first rule in its
sorted order, which was the ``/api/...`` one.  ``login_required`` therefore
redirected browsers to the API URL, and because the view decided its
content type by sniffing the path, a browser got a JSON error instead of a
login page.  One endpoint = one URL = a deterministic ``url_for``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (Blueprint, current_app, jsonify, redirect, render_template,
                   request, session, url_for)

from managers.base_manager import BaseManager
from services import validation
from services.email_service import EmailDeliveryError, send_email
from services.security import csrf_protect, login_required

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


def _auth_manager() -> BaseManager:
    return current_app.extensions["managers"]["auth"]


def _payload() -> dict:
    return validation.get_request_payload(request)


def _login_session(user_id: int) -> None:
    session.clear()
    session["user_id"] = user_id
    session.permanent = True


def _next_target() -> str:
    """Where to go after signing in (form body first, then query string)."""
    return (request.form.get("next") or request.args.get("next")
            or url_for("dashboard.index"))


def _safe_next(target: str) -> str:
    """Only allow redirects to our own pages (open-redirect protection)."""
    if target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard.index")


def _email_verification(user) -> None:
    manager = _auth_manager()
    code = manager.issue_email_verification(user.user_id)
    try:
        send_email(
            user.email,
            "Verify your Wize email address",
            f"Hi {user.full_name},\n\n"
            f"Your Wize verification code is: {code}\n\n"
            "This code expires in 10 minutes and can only be used once.\n"
            "If you did not request this, you can ignore this email.\n\n"
            "— Wize",
        )
    except EmailDeliveryError:
        manager.clear_email_verification(user.user_id)
        raise


def _login_device() -> tuple[str, str]:
    platform = (request.user_agent.platform or "").lower()
    device_type = {
        "android": "Android",
        "iphone": "iPhone",
        "ipad": "iPad",
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
    }.get(platform, "Unknown")
    client_name = (
        request.user_agent.browser.title()
        if request.user_agent.browser else "Wize app"
    )
    return device_type, client_name


def _send_login_notification(user, login_at: str, device_type: str,
                             client_name: str) -> bool:
    try:
        try:
            timezone_info = ZoneInfo(current_app.config["AUTH_EMAIL_TIMEZONE"])
        except (ZoneInfoNotFoundError, ValueError):
            timezone_info = timezone.utc
        local_time = datetime.fromisoformat(login_at).astimezone(timezone_info)
        formatted_time = local_time.strftime("%B %d, %Y at %I:%M %p %Z")
    except ValueError:
        formatted_time = login_at
    try:
        send_email(
            user.email,
            "New login to your Wize account",
            f"Hi {user.full_name},\n\n"
            "Your Wize account was just used to log in.\n\n"
            f"Date and time: {formatted_time}\n"
            f"Device: {device_type or 'Unknown'}\n"
            f"Browser/App: {client_name or 'Unknown'}\n\n"
            "We do not estimate your location. If this was you, no action is "
            "needed. If you do not recognize this login, secure your account "
            "and change your password.\n\n"
            "— Wize Security",
        )
        return True
    except EmailDeliveryError:
        logger.warning("Login security notification could not be delivered.")
        return False


def _login_rate_response(manager, email: str):
    retry_after = manager.login_retry_after(email, request.remote_addr)
    if not retry_after:
        return None
    return jsonify({
        "error": "Too many sign-in attempts. Please try again later.",
        "retry_after": retry_after,
        "code": "login_rate_limited",
    }), 429


def _record_authenticated_login(user) -> tuple[str, str, bool]:
    device_type, client_name = _login_device()
    login_at = _auth_manager().record_successful_login(
        user.user_id, device_type, client_name)
    sent = _send_login_notification(user, login_at, device_type, client_name)
    return device_type, client_name, sent


# ------------------------------------------------------------- HTML pages --
@auth_bp.route("/auth/register", methods=["GET", "POST"])
@csrf_protect
def register_page():
    """Create an account and send its owner to email verification."""
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    form: dict = {}
    errors: dict = {}
    if request.method == "POST":
        form = _payload()
        try:
            user = _auth_manager().register(form)
        except validation.ValidationError as error:
            errors = {error.field or "form": error.message}
        else:
            try:
                _email_verification(user)
            except EmailDeliveryError as error:
                return render_template(
                    "auth/verify_email.html", email=user.email,
                    errors={"form": str(error)}, page_title="Verify email")
            else:
                return redirect(url_for(
                    "auth.verify_email_page", email=user.email))

    return render_template("auth/register.html", form=form, errors=errors,
                           page_title="Create account")


@auth_bp.route("/auth/verify-email", methods=["GET", "POST"])
@csrf_protect
def verify_email_page():
    email = validation.clean(request.values.get("email")).lower()
    errors: dict = {}
    message = ""
    if request.method == "POST":
        try:
            user = _auth_manager().verify_email(
                email, validation.clean(request.form.get("code")))
        except validation.ValidationError as error:
            errors[error.field or "form"] = error.message
        else:
            return render_template(
                "auth/verify_email.html", email=user.email, errors={},
                message="Email verified. You can now sign in.",
                verified=True, page_title="Email verified")
    return render_template(
        "auth/verify_email.html", email=email, errors=errors, message=message,
        page_title="Verify email")


@auth_bp.route("/auth/resend-verification", methods=["POST"])
@csrf_protect
def resend_verification_page():
    email = validation.clean(request.form.get("email")).lower()
    user = _auth_manager().get_by_email(email)
    if user and not user.email_verified:
        wait = _auth_manager().resend_wait_seconds(user.user_id)
        if wait:
            return render_template(
                "auth/verify_email.html", email=email, errors={
                    "form": f"Please wait {wait} seconds before requesting another code."
                }, page_title="Verify email"), 429
        try:
            _email_verification(user)
        except EmailDeliveryError as error:
            return render_template(
                "auth/verify_email.html", email=email,
                errors={"form": str(error)}, page_title="Verify email"), 503
    return render_template(
        "auth/verify_email.html", email=email, errors={},
        message="If this address has a pending Wize account, a new code was sent.",
        page_title="Verify email")


@auth_bp.route("/auth/login", methods=["GET", "POST"])
@csrf_protect
def login_page():
    """Sign-in form.  On success the user is sent back to `next` (or home)."""
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    form: dict = {}
    errors: dict = {}
    if request.method == "POST":
        form = _payload()
        manager = _auth_manager()
        email = validation.clean(form.get("email")).lower()
        blocked = _login_rate_response(manager, email)
        user = None
        if blocked:
            errors = {
                "form": "Too many sign-in attempts. Please try again later.",
                "email": email,
            }
        else:
            user = manager.authenticate(email, form.get("password") or "")
            if user is None:
                manager.record_failed_login(email, request.remote_addr)
                errors = {"form": "Incorrect e-mail address or password."}
            elif not user.email_verified:
                manager.record_failed_login(email, request.remote_addr)
                errors = {
                    "form": "Please verify your e-mail address before signing in.",
                    "email": user.email,
                }
            else:
                manager.clear_failed_logins(email, request.remote_addr)
                _login_session(user.user_id)
                _, _, notification_sent = _record_authenticated_login(user)
                if not notification_sent:
                    errors = {
                        "form": "Signed in, but the security notification could not be sent."
                    }
                    return render_template(
                        "auth/login.html", form=form, errors=errors,
                        next_url=_safe_next(_next_target()),
                        page_title="Sign in")
                return redirect(_safe_next(_next_target()))

    return render_template("auth/login.html", form=form, errors=errors,
                           next_url=_safe_next(_next_target()),
                           page_title="Sign in")


@auth_bp.route("/auth/logout", methods=["POST"])
@login_required
def logout_page():
    """Sign out from the navigation bar and return to the login page."""
    session.clear()
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/auth/profile", methods=["GET", "POST"])
@login_required
def profile():
    """View and update the signed-in user's profile."""
    manager = _auth_manager()
    user = manager.get_by_id(session["user_id"])
    errors: dict = {}

    if request.method == "POST":
        email_changed = (
            bool(_payload().get("email"))
            and validation.clean(_payload().get("email")).lower() != user.email.lower()
        )
        try:
            user = manager.update_profile(user.user_id, _payload())
        except validation.ValidationError as error:
            errors = {error.field or "form": error.message}
        else:
            if email_changed:
                session.clear()
                try:
                    _email_verification(user)
                except EmailDeliveryError as error:
                    return render_template(
                        "auth/verify_email.html", email=user.email,
                        errors={"form": str(error)}, page_title="Verify email")
                else:
                    return redirect(url_for(
                        "auth.verify_email_page", email=user.email))
            else:
                return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", user=user, errors=errors,
                           page_title="My profile")


# -------------------------------------------------------------- JSON API --
@auth_bp.route("/api/auth/csrf", methods=["GET"])
def csrf_token_api():
    """Create/return the session's CSRF token for a separate Expo Web origin."""
    from services.security import generate_csrf_token
    return jsonify({"csrf_token": generate_csrf_token()})


@auth_bp.route("/api/auth/register", methods=["POST"])
@csrf_protect
def register_api():
    """POST /api/auth/register - create an unverified account."""
    if session.get("user_id"):
        return jsonify({"error": "You are already signed in."}), 409
    try:
        user = _auth_manager().register(_payload())
    except validation.ValidationError as error:
        return jsonify(error.to_dict()), 400
    try:
        _email_verification(user)
    except EmailDeliveryError as error:
        return jsonify({
            "error": str(error),
            "email": user.email,
            "code": "email_delivery_unavailable",
        }), 503
    return jsonify({
        "message": "Account created. Check your email for a verification code.",
        "email": user.email,
        "user": user.serialize(),
    }), 201


@auth_bp.route("/api/auth/verify-email", methods=["POST"])
@csrf_protect
def verify_email_api():
    payload = _payload()
    try:
        user = _auth_manager().verify_email(
            validation.clean(payload.get("email")),
            validation.clean(payload.get("code")))
    except validation.ValidationError as error:
        return jsonify(error.to_dict()), 400
    return jsonify({
        "message": "Email verified. You can now sign in.",
        "user": user.serialize(),
    })


@auth_bp.route("/api/auth/resend-verification", methods=["POST"])
@csrf_protect
def resend_verification_api():
    payload = _payload()
    email = validation.clean(payload.get("email")).lower()
    manager = _auth_manager()
    user = manager.get_by_email(email)
    if user and not user.email_verified:
        wait = manager.resend_wait_seconds(user.user_id)
        if wait:
            return jsonify({
                "error": "Please wait before requesting another code.",
                "retry_after": wait,
                "code": "resend_cooldown",
            }), 429
        try:
            _email_verification(user)
        except EmailDeliveryError as error:
            return jsonify({"error": str(error)}), 503
    return jsonify({
        "message": "If this address has a pending Wize account, a new code was sent."
    }), 202


@auth_bp.route("/api/auth/login", methods=["POST"])
@csrf_protect
def login_api():
    """POST /api/auth/login - authenticate with e-mail and password."""
    if session.get("user_id"):
        return jsonify({"error": "You are already signed in."}), 409
    form = _payload()
    manager = _auth_manager()
    email = validation.clean(form.get("email")).lower()
    blocked = _login_rate_response(manager, email)
    if blocked:
        return blocked
    user = manager.authenticate(email, form.get("password") or "")
    if user is None:
        manager.record_failed_login(email, request.remote_addr)
        return jsonify({"error": "Incorrect e-mail address or password."}), 401
    if not user.email_verified:
        manager.record_failed_login(email, request.remote_addr)
        return jsonify({
            "error": "Please verify your email before logging in.",
            "code": "email_not_verified",
            "email": user.email,
        }), 403
    manager.clear_failed_logins(email, request.remote_addr)
    _login_session(user.user_id)
    device_type, client_name, notification_sent = _record_authenticated_login(user)
    response = {
        "message": "Signed in.",
        "user": user.serialize(),
        "login": {
            "device_type": device_type,
            "client_name": client_name,
            "notification_sent": notification_sent,
        },
    }
    if not notification_sent:
        response["notification_warning"] = (
            "Login succeeded, but the security notification could not be delivered.")
    return jsonify(response), 200


@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def logout_api():
    """POST /api/auth/logout - end the session."""
    session.clear()
    return jsonify({"message": "Signed out."}), 200


@auth_bp.route("/api/auth/me")
@login_required
def me():
    """GET /api/auth/me - the signed-in user's public profile."""
    user = current_app.extensions["managers"]["auth"].get_by_id(session["user_id"])
    return jsonify({"user": user.serialize()})