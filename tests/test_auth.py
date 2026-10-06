"""Authentication, session and CSRF protection tests."""

from __future__ import annotations

from unittest.mock import Mock

from services.email_service import EmailDeliveryError
from tests.conftest import VALID_USER, login, logout, register, register_pending

JSON = {"Accept": "application/json"}


# ----------------------------------------------------------- registration --
def test_register_creates_account(client):
    response = client.post("/api/auth/register", json=VALID_USER, headers=JSON)
    assert response.status_code == 201
    body = response.get_json()
    assert body["user"]["email"] == VALID_USER["email"]
    assert body["user"]["user_id"] > 0
    assert body["user"]["email_verified"] is False
    assert client.get("/api/auth/me", headers=JSON).status_code == 401


def test_register_never_returns_password_hash(client):
    register(client)
    body = client.get("/api/auth/me", headers=JSON).get_data(as_text=True)
    assert "password_hash" not in body
    assert '"password"' not in body


def test_password_is_hashed_in_database(client, app, db):
    register(client)
    with app.app_context():
        stored = db.query_one("SELECT password_hash FROM users LIMIT 1")["password_hash"]
    assert stored != VALID_USER["password"]
    assert stored.startswith("pbkdf2:")


def test_duplicate_email_is_rejected(client):
    register(client)
    logout(client)
    response = client.post("/api/auth/register", json=VALID_USER, headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "email"


def test_duplicate_email_is_case_insensitive(client):
    register(client)
    logout(client)
    response = client.post("/api/auth/register",
                           json=dict(VALID_USER, email=VALID_USER["email"].upper()),
                           headers=JSON)
    assert response.status_code == 400


def test_invalid_email_is_rejected(client):
    response = client.post("/api/auth/register",
                           json=dict(VALID_USER, email="not-an-email"), headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "email"


def test_short_password_is_rejected(client):
    response = client.post("/api/auth/register",
                           json=dict(VALID_USER, password="abc", confirm_password="abc"),
                           headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "password"


def test_password_confirmation_must_match(client):
    response = client.post("/api/auth/register",
                           json=dict(VALID_USER, confirm_password="Different1"),
                           headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "confirm_password"


# ------------------------------------------------------------------ login --
def test_login_success(client):
    register(client)
    logout(client)
    assert login(client)["email"] == VALID_USER["email"]


def test_registration_verification_code_is_hashed_and_single_use(client, app, db):
    user, code = register_pending(client)
    with app.app_context():
        row = db.query_one(
            "SELECT code_hash FROM email_verifications WHERE user_id = ?",
            [user["user_id"]])
    assert row["code_hash"] != code
    verified = client.post(
        "/api/auth/verify-email",
        json={"email": user["email"], "code": code}, headers=JSON)
    assert verified.status_code == 200
    assert verified.get_json()["user"]["email_verified"] is True
    reused = client.post(
        "/api/auth/verify-email",
        json={"email": user["email"], "code": code}, headers=JSON)
    assert reused.status_code == 400


def test_unverified_login_is_rejected_without_login_email(client):
    user, _ = register_pending(client)
    response = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": VALID_USER["password"]},
        headers=JSON)
    assert response.status_code == 403
    assert response.get_json()["code"] == "email_not_verified"
    assert not any(
        item["subject"] == "New login to your Wize account"
        for item in client.application.extensions["test_email_outbox"])


def test_html_login_offers_verification_for_unverified_account(client):
    user, _ = register_pending(client)
    response = client.post(
        "/auth/login",
        data={"email": user["email"], "password": VALID_USER["password"]})
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Please verify your e-mail address" in body
    assert "/auth/verify-email" in body


def test_expired_verification_code_is_rejected(client, app, db):
    user, code = register_pending(client)
    with app.app_context():
        db.execute(
            "UPDATE email_verifications SET expires_at = ? WHERE user_id = ?",
            ["2000-01-01T00:00:00+00:00", user["user_id"]])
    response = client.post(
        "/api/auth/verify-email",
        json={"email": user["email"], "code": code}, headers=JSON)
    assert response.status_code == 400


def test_resend_invalidates_previous_code_and_enforces_cooldown(
        client, app, db, monkeypatch):
    values = iter((123, 456))

    def next_code(limit):
        assert limit == 1_000_000
        return next(values)

    monkeypatch.setattr("managers.auth_manager.secrets.randbelow",
                        next_code)
    user, old_code = register_pending(client)
    cooldown = client.post(
        "/api/auth/resend-verification",
        json={"email": user["email"]}, headers=JSON)
    assert cooldown.status_code == 429
    with app.app_context():
        db.execute(
            "UPDATE email_verifications SET sent_at = ? WHERE user_id = ?",
            ["2000-01-01T00:00:00+00:00", user["user_id"]])
    resent = client.post(
        "/api/auth/resend-verification",
        json={"email": user["email"]}, headers=JSON)
    assert resent.status_code == 202
    new_code = "000456"
    assert old_code == "000123"
    old_attempt = client.post(
        "/api/auth/verify-email",
        json={"email": user["email"], "code": old_code}, headers=JSON)
    assert old_attempt.status_code == 400
    assert client.post(
        "/api/auth/verify-email",
        json={"email": user["email"], "code": new_code}, headers=JSON
    ).status_code == 200


def test_successful_login_sends_security_email_and_records_login(client, app, db):
    user, code = register_pending(client)
    client.post("/api/auth/verify-email",
                json={"email": user["email"], "code": code}, headers=JSON)
    outbox = client.application.extensions["test_email_outbox"]
    outbox.clear()
    response = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": VALID_USER["password"]},
        headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["login"]["notification_sent"] is True
    assert [item["subject"] for item in outbox] == [
        "New login to your Wize account"]
    assert "Date and time:" in outbox[0]["body"]
    assert "Device: Unknown" in outbox[0]["body"]
    assert "Browser/App:" in outbox[0]["body"]
    assert "We do not estimate your location." in outbox[0]["body"]
    with app.app_context():
        history = db.query_one(
            "SELECT device_type, client_name FROM login_history WHERE user_id = ?",
            [user["user_id"]])
    assert history["device_type"] == "Unknown"
    assert history["client_name"]


def test_login_rate_limit_returns_html_without_unbound_variable(client, app):
    app.config["LOGIN_RATE_LIMIT_ATTEMPTS"] = 1
    payload = {"email": VALID_USER["email"], "password": "wrong"}
    first = client.post("/auth/login", data=payload)
    assert first.status_code == 200
    second = client.post("/auth/login", data=payload)
    assert second.status_code == 200
    assert "Too many sign-in attempts" in second.get_data(as_text=True)


def test_login_while_signed_in_returns_conflict(client):
    register(client)
    response = client.post("/api/auth/login",
                           json={"email": VALID_USER["email"],
                                 "password": VALID_USER["password"]}, headers=JSON)
    assert response.status_code == 409


def test_login_with_wrong_password_fails(client):
    register(client)
    logout(client)
    outbox = client.application.extensions["test_email_outbox"]
    outbox.clear()
    response = client.post("/api/auth/login",
                           json={"email": VALID_USER["email"], "password": "wrong"},
                           headers=JSON)
    assert response.status_code == 401
    assert "error" in response.get_json()
    assert outbox == []


def test_login_notification_delivery_failure_does_not_undo_login(
        client, monkeypatch):
    user, code = register_pending(client)
    client.post("/api/auth/verify-email",
                json={"email": user["email"], "code": code}, headers=JSON)

    monkeypatch.setattr(
        "routes.auth_routes.send_email",
        Mock(side_effect=EmailDeliveryError("SMTP unavailable")))
    response = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": VALID_USER["password"]},
        headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["login"]["notification_sent"] is False
    assert response.get_json()["notification_warning"]
    assert client.get("/api/auth/me", headers=JSON).status_code == 200
# ------------------------------------------------------------- protection --
def test_protected_endpoint_requires_authentication(client):
    response = client.get("/api/trips", headers=JSON)
    assert response.status_code == 401


def test_dashboard_requires_authentication(client):
    response = client.get("/api/dashboard", headers=JSON)
    assert response.status_code == 401


def test_logout_clears_session(client):
    register(client)
    assert client.get("/api/auth/me", headers=JSON).status_code == 200
    logout(client)
    assert client.get("/api/auth/me", headers=JSON).status_code == 401


# ------------------------------------------------------------------ CSRF --
def test_post_without_csrf_token_is_rejected(raw_client):
    """A state-changing JSON POST without the CSRF token must fail."""
    with raw_client.session_transaction() as session:
        session["_csrf_token"] = "expected-token"
    response = raw_client.post(
        "/api/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        headers=JSON)
    assert response.status_code == 400
    assert "CSRF" in response.get_json()["error"]


def test_post_with_wrong_csrf_token_is_rejected(raw_client):
    with raw_client.session_transaction() as session:
        session["_csrf_token"] = "expected-token"
    response = raw_client.post(
        "/api/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"],
              "csrf_token": "wrong-token"},
        headers=JSON)
    assert response.status_code == 400


def test_html_page_exposes_csrf_token(client):
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert 'name="csrf_token"' in response.get_data(as_text=True)


# ------------------------------------------------ HTML pages vs JSON API --
def test_anonymous_homepage_redirects_to_html_login_page(client):
    """Regression: / must never redirect a browser to the /api/ URL."""
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/login")
    assert "/api/" not in response.headers["Location"]


def test_login_page_renders_html_for_a_browser(client):
    response = client.get("/auth/login", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert 'name="password"' in body
    assert "Sign in" in body
    assert not body.lstrip().startswith("{")


def test_register_page_renders_html_for_a_browser(client):
    response = client.get("/auth/register", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert 'name="confirm_password"' in response.get_data(as_text=True)


def test_login_page_keeps_the_next_parameter(client):
    response = client.get("/auth/login?next=/trips", headers={"Accept": "text/html"})
    body = response.get_data(as_text=True)
    assert 'name="next" value="/trips"' in body


def test_api_login_endpoint_never_renders_the_html_form(client):
    """The API URL must never serve the login page.

    The API endpoint is POST-only, so a GET is a 405 (correct); a POST with
    bad credentials must return JSON, never the HTML form.
    """
    get_response = client.get("/api/auth/login", headers={"Accept": "text/html"})
    assert get_response.status_code == 405          # POST-only endpoint

    post_response = client.post("/api/auth/login",
                               json={"email": "nobody@wize.local",
                                     "password": "wrong"},
                               headers={"Accept": "text/html"})
    assert post_response.mimetype == "application/json"
    assert "<form" not in post_response.get_data(as_text=True)


def test_html_login_redirects_to_dashboard(client):
    """A successful HTML form sign-in lands on the dashboard."""
    register(client)
    logout(client)
    response = client.post("/auth/login", data=VALID_USER, headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"] in ("/", "/dashboard")
    assert client.get("/", headers={"Accept": "text/html"}).status_code == 200


def test_html_login_honours_safe_next(client):
    register(client)
    logout(client)
    response = client.post("/auth/login", data=dict(VALID_USER, next="/trips"),
                           headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/trips"


def test_html_login_rejects_offsite_next(client):
    """Open-redirect protection still applies to the login form."""
    register(client)
    logout(client)
    response = client.post("/auth/login",
                           data=dict(VALID_USER, next="https://evil.example.com"),
                           headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"] in ("/", "/dashboard")


def test_html_login_shows_error_and_stays_html(client):
    register(client)
    logout(client)
    response = client.post("/auth/login",
                           data={"email": VALID_USER["email"], "password": "wrong",
                                 "csrf_token": ""},
                           headers={"Accept": "text/html"})
    assert response.mimetype == "text/html"
    assert "Incorrect e-mail address or password." in response.get_data(as_text=True)


def test_html_registration_redirects_to_verification(client):
    response = client.post("/auth/register", data=VALID_USER,
                           headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/verify-email")
    verify_page = client.get(response.headers["Location"])
    assert verify_page.status_code == 200
    assert 'name="code"' in verify_page.get_data(as_text=True)


def test_html_logout_returns_to_login_page(client):
    register(client)
    response = client.post("/auth/logout", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/login"
    assert client.get("/", headers={"Accept": "text/html"}).status_code == 302


def test_navigation_sign_in_link_points_at_the_page(client):
    """The header link must not point at the API endpoint."""
    body = client.get("/auth/login", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert 'href="/auth/login"' in body
    assert 'href="/auth/register"' in body
    assert 'action="/api/auth/logout"' not in body



def test_login_with_unknown_email_fails(client):
    response = client.post("/api/auth/login",
                           json={"email": "nobody@wize.local", "password": "x"},
                           headers=JSON)
    assert response.status_code == 401


def test_login_error_does_not_reveal_which_field_failed(client):
    """Same generic message for unknown e-mail and wrong password."""
    register(client)
    logout(client)
    unknown = client.post("/api/auth/login",
                          json={"email": "nobody@wize.local", "password": "x"},
                          headers=JSON).get_json()["error"]
    wrong = client.post("/api/auth/login",
                        json={"email": VALID_USER["email"], "password": "x"},
                        headers=JSON).get_json()["error"]
    assert unknown == wrong