"""Shared server-side validation helpers.

Every rule lives here so routes stay thin and the same validation is reused by
the manager layer, which keeps the business rules in one place.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Iterable, Mapping

# Reasonable e-mail shape check (RFC 5322 is far too permissive to be useful).
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


class ValidationError(ValueError):
    """Raised when user input violates a business rule."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.message, "field": self.field}


# --------------------------------------------------------------- helpers ---
def clean(value: Any) -> str:
    """Trim and collapse whitespace; ``None`` becomes an empty string."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def clean_optional(value: Any, max_length: int | None = None) -> str | None:
    text = clean(value)
    if not text:
        return None
    return text[:max_length] if max_length else text


def require_text(value: Any, field: str, min_len: int = 2, max_len: int = 120) -> str:
    text = clean(value)
    if len(text) < min_len:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required "
                              f"(minimum {min_len} characters).", field)
    if len(text) > max_len:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} must be at "
                              f"most {max_len} characters.", field)
    return text


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(clean(email)))


def is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(clean(value)[:10], DATE_FORMAT)
        return True
    except (TypeError, ValueError):
        return False


def is_iso_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False


def is_valid_time(value: str) -> bool:
    try:
        datetime.strptime(clean(value), TIME_FORMAT)
        return True
    except (TypeError, ValueError):
        return False


def parse_date(value: str) -> date:
    return datetime.strptime(clean(value)[:10], DATE_FORMAT).date()


def parse_time(value: str) -> time:
    return datetime.strptime(clean(value), TIME_FORMAT).time()
# --------------------------------------------------------------- passwords --
def validate_password(password: str, confirm: str | None = None,
                      min_length: int = 8) -> tuple[str, str]:
    """Return ``(password, confirmation)`` after checking the strength rules."""
    if not password:
        raise ValidationError("Password is required.", "password")
    if len(password) < min_length:
        raise ValidationError(f"Password must be at least {min_length} characters long.",
                              "password")
    if len(password) > 128:
        raise ValidationError("Password must be at most 128 characters long.", "password")
    if password.isdigit() or password.isalpha():
        raise ValidationError("Password must mix letters and numbers.", "password")
    if password.lower() in {"password", "12345678", "qwerty123", "letmein123"}:
        raise ValidationError("That password is too common - please choose another.",
                              "password")
    if confirm is not None and password != confirm:
        raise ValidationError("Passwords do not match.", "confirm_password")
    return password, (confirm or password)


def validate_registration(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a sign-up payload and return normalised values."""
    full_name = require_text(data.get("full_name"), "full_name", 2, 80)
    email = clean(data.get("email")).lower()
    if not email:
        raise ValidationError("E-mail address is required.", "email")
    if len(email) > 190:
        raise ValidationError("E-mail address is too long.", "email")
    if not is_valid_email(email):
        raise ValidationError("Enter a valid e-mail address.", "email")
    password, confirm = validate_password(data.get("password") or "",
                                          data.get("confirm_password"))
    return {"full_name": full_name, "email": email,
            "password": password, "confirm_password": confirm}


# ------------------------------------------------------------------- trips --
def validate_budget(data: Mapping[str, Any],
                    supported_currencies: Iterable[str],
                    default_currency: str = "USD") -> dict[str, Any]:
    """Validate the optional trip budget.

    A budget without a currency is meaningless, so when a budget amount is
    given the currency defaults to ``default_currency`` if omitted.
    """
    raw = clean(data.get("budget"))
    if not raw:
        return {"budget": None, "budget_currency": None}

    try:
        budget = float(raw)
    except ValueError:
        raise ValidationError("Budget must be a number.", "budget") from None
    if budget != budget or budget in (float("inf"), float("-inf")):
        raise ValidationError("Budget must be a valid number.", "budget")
    if budget < 0:
        raise ValidationError("Budget cannot be negative.", "budget")
    if budget > 1_000_000_000:
        raise ValidationError("Budget is unrealistically large.", "budget")

    currency = (clean(data.get("budget_currency")) or default_currency).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("Currency must be a 3-letter code (for example USD).",
                              "budget_currency")
    if currency not in supported_currencies:
        raise ValidationError(f"Currency '{currency}' is not supported.",
                              "budget_currency")
    return {"budget": round(budget, 2), "budget_currency": currency}


def validate_trip(data: Mapping[str, Any], allowed_statuses: Iterable[str],
                  max_days: int = 365,
                  supported_currencies: Iterable[str] = ("USD",),
                  default_currency: str = "USD") -> dict[str, Any]:
    """Validate trip input, including the start <= end date rule."""
    trip_name = require_text(data.get("trip_name"), "trip_name", 2, 100)
    start_raw, end_raw = clean(data.get("start_date")), clean(data.get("end_date"))

    if not start_raw:
        raise ValidationError("Start date is required.", "start_date")
    if not end_raw:
        raise ValidationError("End date is required.", "end_date")
    if not is_valid_date(start_raw):
        raise ValidationError("Start date must be a valid YYYY-MM-DD date.", "start_date")
    if not is_valid_date(end_raw):
        raise ValidationError("End date must be a valid YYYY-MM-DD date.", "end_date")

    start, end = parse_date(start_raw), parse_date(end_raw)
    if end < start:
        raise ValidationError("End date cannot be earlier than the start date.", "end_date")
    if (end - start).days + 1 > max_days:
        raise ValidationError(f"A trip cannot be longer than {max_days} days.", "end_date")

    status = clean(data.get("status")) or "planning"
    if status not in allowed_statuses:
        raise ValidationError("Unknown trip status.", "status")

    return {
        "trip_name": trip_name,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "description": clean_optional(data.get("description"), 1000),
        "status": status,
        **validate_budget(data, supported_currencies, default_currency),
    }


# -------------------------------------------------------------- schedules --
def validate_schedule(data: Mapping[str, Any], trip_start: str | None = None,
                      trip_end: str | None = None) -> dict[str, Any]:
    """Validate an itinerary activity against the owning trip's dates."""
    activity_name = require_text(data.get("activity_name"), "activity_name", 2, 120)
    activity_date = clean(data.get("activity_date"))
    if not activity_date:
        raise ValidationError("Activity date is required.", "activity_date")
    if not is_valid_date(activity_date):
        raise ValidationError("Activity date must be a valid YYYY-MM-DD date.", "activity_date")

    if trip_start and trip_end:
        if not (parse_date(trip_start) <= parse_date(activity_date) <= parse_date(trip_end)):
            raise ValidationError(
                f"Activity date must fall between the trip dates "
                f"({trip_start} and {trip_end}).", "activity_date")

    start_time, end_time = clean(data.get("start_time")), clean(data.get("end_time"))
    for label, value in (("Start time", start_time), ("End time", end_time)):
        if value and not is_valid_time(value):
            raise ValidationError(f"{label} must use the 24-hour HH:MM format.", "time")
    if start_time and end_time and parse_time(end_time) < parse_time(start_time):
        raise ValidationError("End time cannot be earlier than the start time.", "time")

    return {
        "activity_name": activity_name,
        "activity_date": activity_date,
        "start_time": start_time or None,
        "end_time": end_time or None,
        "notes": clean_optional(data.get("notes"), 500),
        "destination_id": _optional_int(data.get("destination_id"), "destination_id"),
    }


# --------------------------------------------------------------- expenses --
def validate_expense(data: Mapping[str, Any], categories: Iterable[str],
                     supported_currencies: Iterable[str],
                     default_currency: str = "USD") -> dict[str, Any]:
    """Validate an expense line. Amounts are always positive."""
    expense_name = require_text(data.get("expense_name"), "expense_name", 2, 120)

    category = clean(data.get("category")) or "other"
    if category not in categories:
        raise ValidationError("Choose a valid expense category.", "category")

    raw_amount = clean(data.get("amount"))
    if not raw_amount:
        raise ValidationError("Amount is required.", "amount")
    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        raise ValidationError("Amount must be a number.", "amount") from None
    if amount != amount or amount in (float("inf"), float("-inf")):
        raise ValidationError("Amount must be a valid number.", "amount")
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.", "amount")
    if amount > 1_000_000_000:
        raise ValidationError("Amount is unrealistically large.", "amount")
    amount = round(amount, 2)

    currency = (clean(data.get("currency")) or default_currency).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("Currency must be a 3-letter code (for example USD).", "currency")
    if currency not in supported_currencies:
        raise ValidationError(f"Currency '{currency}' is not supported.", "currency")

    expense_date = clean(data.get("expense_date")) or date.today().isoformat()
    if not is_valid_date(expense_date):
        raise ValidationError("Expense date must be a valid YYYY-MM-DD date.", "expense_date")

    expense_kind = clean(data.get("expense_kind") or "actual").lower()
    if expense_kind not in {"planned", "actual"}:
        raise ValidationError("Expense type must be planned or actual.", "expense_kind")

    return {
        "expense_name": expense_name, "category": category, "amount": amount,
        "currency": currency, "expense_date": expense_date,
        "expense_kind": expense_kind,
        "notes": clean_optional(data.get("notes"), 500),
    }


# ------------------------------------------------------- checklists / dest --
def validate_checklist(data: Mapping[str, Any]) -> dict[str, Any]:
    return {"checklist_name": require_text(data.get("checklist_name"),
                                           "checklist_name", 2, 100)}


def validate_checklist_item(data: Mapping[str, Any]) -> dict[str, Any]:
    item_name = require_text(data.get("item_name"), "item_name", 2, 120)
    return {"item_name": item_name,
            "is_completed": 1 if _to_bool(data.get("is_completed")) else 0}


def validate_destination(data: Mapping[str, Any], categories: Iterable[str],
                         supported_currencies: Iterable[str]) -> dict[str, Any]:
    """Validate a user-created custom destination."""
    name = require_text(data.get("name"), "name", 2, 120)
    country = require_text(data.get("country"), "country", 2, 60)

    category = clean(data.get("category")) or "other"
    if category not in categories:
        raise ValidationError("Choose a valid destination category.", "category")

    currency = clean(data.get("currency")).upper() or None
    if currency and (len(currency) != 3 or not currency.isalpha()):
        raise ValidationError("Currency must be a 3-letter code (for example JPY).", "currency")
    if currency and currency not in supported_currencies:
        raise ValidationError(f"Currency '{currency}' is not supported.", "currency")

    raw_fee = clean(data.get("estimated_entrance_fee"))
    fee: float | None = None
    if raw_fee:
        try:
            fee = float(raw_fee)
        except ValueError:
            raise ValidationError("Entrance fee must be a number.", "estimated_entrance_fee") from None
        if fee < 0:
            raise ValidationError("Entrance fee cannot be negative.", "estimated_entrance_fee")
        fee = round(fee, 2)

    image_url = clean_optional(data.get("image_url"), 500)
    if image_url and not image_url.lower().startswith(("http://", "https://")):
        raise ValidationError("Image URL must start with http:// or https://.", "image_url")

    return {
        "name": name, "country": country,
        "city": clean_optional(data.get("city"), 60),
        "category": category,
        "description": clean_optional(data.get("description"), 1000),
        "image_url": image_url,
        "estimated_entrance_fee": fee,
        "currency": currency,
    }


# ------------------------------------------------------------- primitives ---
def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def _optional_int(value: Any, field: str) -> int | None:
    """Convert to a positive int or ``None``; empty values become ``None``."""
    text = clean(value)
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} must be a number.",
                              field) from None
    if number <= 0:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} must be positive.", field)
    return number


def positive_int(value: Any, field: str = "id", default: int | None = None) -> int:
    """Parse a URL id, raising a clear ValidationError for junk input."""
    text = clean(value)
    if not text:
        if default is not None:
            return default
        raise ValidationError("An identifier is required.", field)
    try:
        number = int(text)
    except ValueError:
        raise ValidationError("Identifier must be a whole number.", field) from None
    if number <= 0:
        raise ValidationError("Identifier must be positive.", field)
    return number


def optional_choice(value: Any, choices: Iterable[str]) -> str | None:
    """Sanitise a filter parameter: only allow known values through."""
    text = clean(value)
    return text if text in set(choices) else None


def get_request_payload(request, fallback_source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge JSON and form payloads so one route serves both front-ends."""
    payload: dict[str, Any] = {}
    if request.is_json:
        payload.update(request.get_json(silent=True) or {})
    if request.form:
        payload.update(request.form.to_dict())
    if request.args and request.method in {"GET", "DELETE"}:
        payload.update({k: v for k, v in request.args.items() if v != ""})
    if not payload and fallback_source:
        payload.update(dict(fallback_source))
    return payload
