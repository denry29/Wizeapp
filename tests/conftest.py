"""Shared pytest fixtures.

Every test runs against an isolated SQLite file (``wize_test.db``) so the
main database is never touched.  A small fixture dataset (4 destinations) is
seeded instead of the full catalogue to keep the suite fast; the real dataset
is validated separately by ``test_dataset.py``.
"""

from __future__ import annotations

import shutil
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app                                    # noqa: E402
from database.db import DatabaseManager                       # noqa: E402
from managers.destination_manager import DestinationManager   # noqa: E402
from scripts.seed_destinations import INSERT_SQL               # noqa: E402

TEST_DB = PROJECT_ROOT / "database" / "wize_test.db"

#: A small set of destinations for the tests to use.
FIXTURE_DESTINATIONS = [
    {"name": "Kinkaku-ji", "name_key": "kinkaku ji", "country": "Japan",
     "city": "Kyoto", "category": "historical_site",
     "description": "Golden pavilion in Kyoto.", "image_url": None,
     "estimated_entrance_fee": 500, "currency": "JPY"},
    {"name": "Fushimi Inari Taisha", "name_key": "fushimi inari taisha",
     "country": "Japan", "city": "Kyoto", "category": "temple",
     "description": "Shrine with vermilion torii gates.", "image_url": None,
     "estimated_entrance_fee": None, "currency": "JPY"},
    {"name": "Angkor Wat", "name_key": "angkor wat", "country": "Cambodia",
     "city": "Siem Reap", "category": "temple",
     "description": "Largest religious monument on earth.", "image_url": None,
     "estimated_entrance_fee": 37.0, "currency": "USD"},
    {"name": "Maldives Beach", "name_key": "maldives beach", "country": "Maldives",
     "city": "Male", "category": "beach",
     "description": "Beach in the Maldives.", "image_url": None,
     "estimated_entrance_fee": None, "currency": "MVR"},
]

VALID_USER = {"full_name": "Test Traveller", "email": "test@wize.local",
              "password": "Str0ngPass!", "confirm_password": "Str0ngPass!"}


@pytest.fixture()
def db_path(tmp_path) -> Path:
    """A unique SQLite file per test.

    Each test gets its own file, so no fixture has to delete a database that
    another connection might still hold open (which breaks on Windows).
    """
    return tmp_path / "wize_test.db"


@pytest.fixture()
def app(db_path):
    """Flask app bound to a fresh, isolated test database."""
    application = create_app("testing", database_path=db_path)
    yield application


@pytest.fixture()
def db(app, db_path):
    """DatabaseManager seeded with the small destination fixture."""
    manager = DatabaseManager(db_path, PROJECT_ROOT / "database" / "schema.sql")
    with app.app_context():
        manager.get_connection()
        manager.create_tables()
        for record in FIXTURE_DESTINATIONS:
            manager.execute(INSERT_SQL, [
                record["name"], record["name_key"], record["country"], record["city"],
                record["category"], record["description"], record["image_url"],
                record["estimated_entrance_fee"], record["currency"],
            ])
    return manager


@pytest.fixture()
def client(app, db):
    """Test client that automatically supplies a valid CSRF token.

    Real browsers send the token as the ``X-CSRF-Token`` header (see
    ``static/js/app.js``); this wrapper does the same so individual tests do
    not have to repeat it.  Tests that specifically check CSRF rejection pass
    their own token in the body, which takes precedence.
    """
    return CsrfClient(app.test_client())


@pytest.fixture()
def raw_client(app, db):
    """Plain Flask test client that does NOT auto-attach a CSRF token.

    Used by the tests that assert CSRF protection actually rejects requests.
    """
    return app.test_client()


class CsrfClient:
    """Thin wrapper around Flask's test client that adds the CSRF header."""

    def __init__(self, inner):
        self._inner = inner

    def _token(self) -> str:
        """Read the session's CSRF token, creating a session if needed.

        The token is not cached: signing in clears the session (Flask rotates
        the CSRF token on privilege change), so it is re-read each time.
        """
        with self._inner.session_transaction() as session_data:
            token = session_data.get("_csrf_token")
        if token:
            return token
        self._inner.get("/auth/login")          # Visiting login sets up the session.
        with self._inner.session_transaction() as session_data:
            return session_data.get("_csrf_token", "")

    def _send(self, method: str, *args, **kwargs):
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("X-CSRF-Token", self._token())
            kwargs["headers"] = headers
        return self._inner.open(*args, method=method, **kwargs)

    def get(self, *args, **kwargs):
        return self._send("GET", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._send("POST", *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._send("PUT", *args, **kwargs)

    def patch(self, *args, **kwargs):
        return self._send("PATCH", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._send("DELETE", *args, **kwargs)

    def session_transaction(self):
        return self._inner.session_transaction()

    def __getattr__(self, name):                # Pass any other calls through as usual.
        return getattr(self._inner, name)


@pytest.fixture()
def managers(app, db):
    """Manager instances inside an application context."""
    with app.app_context():
        yield app.extensions["managers"]


def register_pending(client, **overrides) -> tuple[dict, str]:
    """Register an account and return its user payload and test mail code."""
    payload = dict(VALID_USER, **overrides)
    response = client.post("/api/auth/register", json=payload,
                           headers={"Accept": "application/json"})
    assert response.status_code == 201, response.get_json()
    message = client.application.extensions["test_email_outbox"][-1]
    match = re.search(r"\b(\d{6})\b", message["body"])
    assert match is not None
    return response.get_json()["user"], match.group(1)


def register(client, **overrides) -> dict:
    """Register, verify, and sign in a user for existing feature tests."""
    user, code = register_pending(client, **overrides)
    response = client.post(
        "/api/auth/verify-email",
        json={"email": user["email"], "code": code},
        headers={"Accept": "application/json"})
    assert response.status_code == 200, response.get_json()
    return login(client, email=user["email"],
                 password=overrides.get("password", VALID_USER["password"]))


def logout(client):
    """Sign out of the current session."""
    client.post("/api/auth/logout", headers={"Accept": "application/json"})


def switch_user(client, email: str, password: str | None = None):
    """Sign out and register a second user (who is then signed in)."""
    logout(client)
    register(client, email=email)
    if password:
        logout(client)
        login(client, email=email, password=password)


def login(client, email: str = VALID_USER["email"],
          password: str = VALID_USER["password"]):
    """Sign in and return the token header dict for JSON requests."""
    response = client.post("/api/auth/login",
                           json={"email": email, "password": password},
                           headers={"Accept": "application/json"})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["user"]


def trip_payload(**overrides) -> dict:
    """Valid trip input with dates relative to today (overridable)."""
    start = date.today() + timedelta(days=10)
    payload = {
        "trip_name": "Kyoto in Spring",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=7)).isoformat(),
        "description": "Temples and gardens.",
        "status": "planning",
    }
    payload.update(overrides)
    return payload