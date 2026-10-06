"""Authentication and user-account management."""

from __future__ import annotations

import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash
from flask import current_app

from database.db import DatabaseManager
from managers.base_manager import BaseManager
from models.user import User
from services import validation


class AuthManager(BaseManager):
    """Registration, login and profile lookups.

    OOP - Encapsulation
        ``password_hash`` is written only through ``_password_digest()`` and is
        never exposed by ``User.serialize()``.  Callers pass and receive plain
        passwords, never hashes, so no route can leak one by accident.
    """

    table = "users"
    primary_key = "user_id"
    owner_column = None          # users are not owned by another user
    model = User
    writable_fields = ("full_name", "email", "password_hash")

    # --------------------------------------------------- polymorphism -------
    def _to_model(self, row: sqlite3.Row | None) -> User | None:
        return User.from_row(row) if row is not None else None

    # ---------------------------------------------------------- passwords ---
    @staticmethod
    def _password_digest(password: str) -> str:
        """Hash with PBKDF2-SHA256 (Werkzeug's secure default)."""
        return AuthManager.hash_password(password)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash using the strength configured for the current environment."""
        method = current_app.config.get("PASSWORD_HASH_METHOD", "pbkdf2:sha256:260000")
        return generate_password_hash(password, method=method)

    def _verify(self, password: str, stored_hash: str) -> bool:
        """Constant-time comparison handled inside Werkzeug."""
        if not stored_hash:
            return False
        try:
            return check_password_hash(stored_hash, password)
        except (ValueError, TypeError):
            return False

    # --------------------------------------------------------- operations ---
    def register(self, payload: dict[str, Any]) -> User:
        """Create a new account. Raises ValidationError on bad input."""
        data = validation.validate_registration(payload)
        if self.email_exists(data["email"]):
            raise validation.ValidationError("An account with that e-mail already exists.",
                                             "email")
        try:
            self.db.execute(
                "INSERT INTO users "
                "(full_name, email, password_hash, email_verified) "
                "VALUES (?, ?, ?, 0)",
                [data["full_name"], data["email"],
                 self._password_digest(data["password"])],
            )
        except sqlite3.IntegrityError:
            raise validation.ValidationError(
                "An account with that e-mail already exists.", "email") from None
        return self.get_by_email(data["email"])

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _verification_digest(user_id: int, code: str) -> str:
        secret = current_app.config["SECRET_KEY"].encode("utf-8")
        message = f"email-verification:{user_id}:{code}".encode("utf-8")
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def issue_email_verification(self, user_id: int) -> str:
        """Store a short-lived HMAC of a fresh code; return the code for delivery."""
        user = self.get_by_id(user_id)
        if user.get("email_verified"):
            raise validation.ValidationError("This e-mail address is already verified.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._now()
        expires = now + timedelta(
            seconds=current_app.config["EMAIL_VERIFICATION_TTL_SECONDS"])
        self.db.execute(
            """
            INSERT INTO email_verifications
                (user_id, code_hash, expires_at, sent_at, attempts)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                code_hash = excluded.code_hash,
                expires_at = excluded.expires_at,
                sent_at = excluded.sent_at,
                attempts = 0
            """,
            [user_id, self._verification_digest(user_id, code),
             expires.isoformat(), now.isoformat()],
        )
        return code

    def clear_email_verification(self, user_id: int) -> None:
        self.db.execute(
            "DELETE FROM email_verifications WHERE user_id = ?", [user_id])

    def resend_wait_seconds(self, user_id: int) -> int:
        row = self.db.query_one(
            "SELECT sent_at FROM email_verifications WHERE user_id = ?",
            [user_id])
        if row is None:
            return 0
        sent_at = datetime.fromisoformat(row["sent_at"])
        available_at = sent_at + timedelta(
            seconds=current_app.config["EMAIL_VERIFICATION_RESEND_SECONDS"])
        return max(0, int((available_at - self._now()).total_seconds() + 0.999))

    def verify_email(self, email: str, code: str) -> User:
        """Verify one unexpired, single-use code with bounded attempts."""
        user = self.get_by_email(email)
        if user is None or user.get("email_verified"):
            raise validation.ValidationError(
                "The verification code is invalid or expired.", "code")
        if len(code) != 6 or not code.isdigit():
            raise validation.ValidationError(
                "Enter the 6-digit verification code.", "code")
        row = self.db.query_one(
            "SELECT code_hash, expires_at, attempts FROM email_verifications "
            "WHERE user_id = ?", [user.user_id])
        if row is None:
            raise validation.ValidationError(
                "The verification code is invalid or expired.", "code")
        now = self._now()
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= now:
            self.clear_email_verification(user.user_id)
            raise validation.ValidationError(
                "The verification code is invalid or expired. Request a new code.",
                "code")
        if int(row["attempts"]) >= current_app.config[
                "EMAIL_VERIFICATION_MAX_ATTEMPTS"]:
            self.clear_email_verification(user.user_id)
            raise validation.ValidationError(
                "Too many incorrect attempts. Request a new verification code.",
                "code")
        digest = self._verification_digest(user.user_id, code)
        if not hmac.compare_digest(row["code_hash"], digest):
            attempts = int(row["attempts"]) + 1
            if attempts >= current_app.config["EMAIL_VERIFICATION_MAX_ATTEMPTS"]:
                self.clear_email_verification(user.user_id)
                raise validation.ValidationError(
                    "Too many incorrect attempts. Request a new verification code.",
                    "code")
            self.db.execute(
                "UPDATE email_verifications SET attempts = ? WHERE user_id = ?",
                [attempts, user.user_id])
            raise validation.ValidationError(
                "The verification code is invalid or expired.", "code")
        connection = self.db.get_connection()
        connection.execute(
            "UPDATE users SET email_verified = 1, email_verified_at = ? "
            "WHERE user_id = ?",
            [now.isoformat(), user.user_id])
        connection.execute(
            "DELETE FROM email_verifications WHERE user_id = ?", [user.user_id])
        connection.commit()
        return self.get_by_id(user.user_id)

    # ------------------------------------------------- further operations --
    def authenticate(self, email: str, password: str) -> User | None:
        """Return the user for correct credentials; callers must check verification."""
        email = validation.clean(email).lower()
        if not email or not password:
            return None
        user = self.get_by_email(email)
        if user is None or not self._verify(password, user.password_hash):
            return None
        return user

    def _login_rate_key(self, email: str, ip_address: str | None) -> str:
        secret = current_app.config["SECRET_KEY"].encode("utf-8")
        identity = f"{email.lower()}|{ip_address or 'unknown'}".encode("utf-8")
        return hmac.new(secret, identity, hashlib.sha256).hexdigest()

    def login_retry_after(self, email: str, ip_address: str | None) -> int:
        key = self._login_rate_key(email, ip_address)
        row = self.db.query_one(
            "SELECT window_started_at, attempts FROM auth_rate_limits "
            "WHERE rate_key = ?", [key])
        if row is None:
            return 0
        started = datetime.fromisoformat(row["window_started_at"])
        expires = started + timedelta(
            seconds=current_app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"])
        if expires <= self._now():
            return 0
        if int(row["attempts"]) < current_app.config["LOGIN_RATE_LIMIT_ATTEMPTS"]:
            return 0
        return max(1, int((expires - self._now()).total_seconds() + 0.999))

    def record_failed_login(self, email: str, ip_address: str | None) -> None:
        key = self._login_rate_key(email, ip_address)
        now = self._now()
        cutoff = (now - timedelta(
            seconds=current_app.config["LOGIN_RATE_LIMIT_WINDOW_SECONDS"]
        )).isoformat()
        self.db.execute(
            """
            INSERT INTO auth_rate_limits (rate_key, window_started_at, attempts)
            VALUES (?, ?, 1)
            ON CONFLICT(rate_key) DO UPDATE SET
                attempts = CASE
                    WHEN window_started_at < ? THEN 1
                    ELSE attempts + 1
                END,
                window_started_at = CASE
                    WHEN window_started_at < ? THEN excluded.window_started_at
                    ELSE window_started_at
                END
            """, [key, now.isoformat(), cutoff, cutoff])

    def clear_failed_logins(self, email: str, ip_address: str | None) -> None:
        self.db.execute(
            "DELETE FROM auth_rate_limits WHERE rate_key = ?",
            [self._login_rate_key(email, ip_address)])

    def record_successful_login(self, user_id: int, device_type: str,
                                client_name: str) -> str:
        """Write minimal login metadata; do not persist IP/location."""
        now = self._now().isoformat()
        connection = self.db.get_connection()
        connection.execute(
            "UPDATE users SET last_login_at = ? WHERE user_id = ?",
            [now, user_id])
        connection.execute(
            "INSERT INTO login_history "
            "(user_id, login_at, device_type, client_name) VALUES (?, ?, ?, ?)",
            [user_id, now, device_type, client_name])
        connection.commit()
        return now

    def email_exists(self, email: str, exclude_user_id: int | None = None) -> bool:
        """E-mail uniqueness check (backed by the DB UNIQUE constraint too)."""
        email = validation.clean(email).lower()
        if not email:
            return False
        if exclude_user_id is not None:
            row = self.db.query_one(
                "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE AND user_id <> ?",
                [email, exclude_user_id])
        else:
            row = self.db.query_one(
                "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", [email])
        return row is not None

    def get_by_email(self, email: str) -> User | None:
        return self._to_model(self.db.query_one(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            [validation.clean(email).lower()]))

    def update_profile(self, user_id: int, payload: dict[str, Any]) -> User:
        """Update e-mail and/or full name; optionally change the password."""
        current = self.get_by_id(user_id)
        data: dict[str, Any] = {}

        if payload.get("full_name"):
            data["full_name"] = validation.require_text(payload["full_name"],
                                                        "full_name", 2, 80)
        email_changed = False
        if payload.get("email"):
            email = validation.clean(payload["email"]).lower()
            if not validation.is_valid_email(email):
                raise validation.ValidationError("Enter a valid e-mail address.", "email")
            if self.email_exists(email, exclude_user_id=user_id):
                raise validation.ValidationError(
                    "An account with that e-mail already exists.", "email")
            data["email"] = email
            email_changed = email != current.email.lower()
        if payload.get("password"):
            if payload.get("current_password") and not self._verify(
                    validation.clean(payload["current_password"]), current.password_hash):
                raise validation.ValidationError("Current password is incorrect.",
                                                 "current_password")
            password, _ = validation.validate_password(payload["password"],
                                                       payload.get("confirm_password"))
            data["password_hash"] = self._password_digest(password)
        if not data:
            raise validation.ValidationError("Nothing to update.")
        if email_changed:
            assignments = [f"{field} = ?" for field in data]
            values = list(data.values())
            assignments.extend(["email_verified = 0", "email_verified_at = NULL"])
            self.db.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE user_id = ?",
                values + [user_id])
            self.clear_email_verification(user_id)
            return self.get_by_id(user_id)
        return self.update(user_id, data)

    def change_password(self, user_id: int, current_password: str,
                        new_password: str) -> None:
        """Dedicated password change used by the profile screen."""
        user = self.get_by_id(user_id)
        if not self._verify(validation.clean(current_password), user.password_hash):
            raise validation.ValidationError("Current password is incorrect.",
                                             "current_password")
        password, _ = validation.validate_password(new_password, new_password)
        self.update(user_id, {"password_hash": self._password_digest(password)})

    def count_users(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM users"))