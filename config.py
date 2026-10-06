"""Application configuration for Wize.

The secret key is never hard-coded. It is read from the environment variable
``WIZE_SECRET_KEY`` or generated once and stored in ``.secret_key``
(git-ignored).  Every setting can also be overridden by an environment
variable so the app can be deployed safely.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATA_DIR = BASE_DIR / "data"


def _load_env_file() -> None:
    """Load backend-only settings without making Expo read server secrets."""
    path = BASE_DIR / ".backend.env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


_load_env_file()

MIN_DESTINATIONS = 300          # dataset requirement enforced by seed + tests

# Module-level paths (mirrored by the config classes below) so scripts can
# `from config import DATABASE_PATH, SCHEMA_PATH, DATASET_PATH` directly.
DATABASE_PATH = DATABASE_DIR / "wize.db"
SCHEMA_PATH = DATABASE_DIR / "schema.sql"
DATASET_PATH = DATA_DIR / "asia_destinations.json"


def _load_or_create_secret_key() -> str:
    """Return the application secret key, creating a local one if needed."""
    env_key = os.environ.get("WIZE_SECRET_KEY")
    if env_key:
        return env_key.strip()

    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        stored = key_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    generated = secrets.token_hex(32)
    key_file.write_text(generated, encoding="utf-8")
    try:                                    # never leave the key world readable
        os.chmod(key_file, 0o600)
    except OSError:                         # pragma: no cover - Windows
        pass
    return generated


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = _load_or_create_secret_key()

    DATABASE_PATH = DATABASE_DIR / "wize.db"
    SCHEMA_PATH = DATABASE_DIR / "schema.sql"
    DATASET_PATH = DATA_DIR / "asia_destinations.json"

    # --- security ---------------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False          # True behind HTTPS in production
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 14   # 14 days
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    # --- domain rules -----------------------------------------------------
    MIN_PASSWORD_LENGTH = 8
    MAX_TRIP_DAYS = 365
    CURRENCY_DEFAULT = "USD"
    SUPPORTED_CURRENCIES = {
        # Asia
        "AED", "BDT", "BHD", "BTN", "CNY", "HKD", "IDR", "ILS", "INR", "JOD",
        "JPY", "KHR", "KGS", "KRW", "KZT", "LAK", "LKR", "MMK", "MNT", "MOP",
        "MVR", "MYR", "NPR", "OMR", "PHP", "PKR", "QAR", "SAR", "SGD", "THB",
        "TJS", "TRY", "TWD", "UZS", "VND",
        # Elsewhere
        "AUD", "BGN", "CAD", "CHF", "EUR", "GBP", "USD",
    }
    TRIP_STATUSES = ("planning", "upcoming", "ongoing", "completed", "cancelled")
    EXPENSE_CATEGORIES = (
        "flights", "hotels", "activities", "transportation", "food",
        "other", "accommodation", "entrance_fees", "shopping",
    )
    DESTINATION_CATEGORIES = (
        "beach", "mountain", "historical_site", "temple", "museum", "cultural",
        "park", "natural_landmark", "architectural_landmark", "theme_park",
        "island", "lake", "waterfall", "market", "other",
    )

    # --- behaviour --------------------------------------------------------
    ITEMS_PER_PAGE = 12
    JSON_SORT_KEYS = False
    EXPO_WEB_ORIGINS = tuple(
        origin.strip()
        for origin in os.environ.get(
            "EXPO_WEB_ORIGINS",
            "http://localhost:8081,http://127.0.0.1:8081,"
            "http://localhost:19006,http://127.0.0.1:19006",
        ).split(",")
        if origin.strip()
    )
    STAYING_API_KEY = os.environ.get("STAYING_API_KEY", "")
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USERNAME = os.environ.get("EMAIL_USERNAME", "")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in {
        "1", "true", "yes", "on"
    }
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() in {
        "1", "true", "yes", "on"
    }
    EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "15"))
    AUTH_EMAIL_TIMEZONE = os.environ.get("AUTH_EMAIL_TIMEZONE", "UTC")
    EMAIL_VERIFICATION_TTL_SECONDS = 600
    EMAIL_VERIFICATION_RESEND_SECONDS = 60
    EMAIL_VERIFICATION_MAX_ATTEMPTS = 6
    LOGIN_RATE_LIMIT_ATTEMPTS = 8
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = 900

    @staticmethod
    def init_app(app) -> None:
        """Hook for per-environment initialisation."""
        app.json.sort_keys = BaseConfig.JSON_SORT_KEYS


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True


class TestingConfig(BaseConfig):
    """Used by the automated test-suite - never touches the main database."""

    DEBUG = False
    TESTING = True
    SECRET_KEY = "wize-test-key-not-for-production"
    DATABASE_PATH = DATABASE_DIR / "wize_test.db"
    #: A cheaper PBKDF2 round count keeps the suite fast.  Production keeps the
    #: strong default (260000) - never lower it outside tests.
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"
    MIN_DESTINATIONS = 1                     # tests seed a tiny fixture dataset


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    """Return a config class from its name (defaults to ``FLASK_ENV``/dev)."""
    key = (name or os.environ.get("WIZE_ENV")
           or os.environ.get("FLASK_ENV") or "development").lower()
    return CONFIG_MAP.get(key, DevelopmentConfig)