"""Additional REST endpoints used by the Expo client."""

from __future__ import annotations

import json
import math
import re
from datetime import date
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from managers.base_manager import NotFoundError
from services import validation
from services.security import api_error, csrf_protect, current_user_id, login_required

mobile_bp = Blueprint("mobile", __name__)
FLIGHT_FIELDS = {
    "airline", "airline_code", "airline_logo_url",
    "airline_logo_attribution", "airline_logo_source_url",
    "airline_logo_license", "flight_number", "origin", "destination",
    "departure_at", "arrival_at", "duration", "stops", "segments", "provider",
}
HOTEL_FIELDS = {
    "hotel_id", "platform_listing_id", "location", "images", "image_url",
    "image_attribution", "image_source_url", "image_license", "description",
    "property_type", "star_rating", "rating", "rating_scale", "review_count",
    "review_summary", "amenities", "max_occupancy", "bedrooms", "bathrooms",
    "host", "room_type", "bed_type", "availability", "booking_url",
    "price_source",
    "price_per_night", "total_price", "taxes", "fees", "currency", "nights",
    "rooms", "dates", "search_criteria", "cancellation_policy", "cancellation", "payment_policy",
    "meal_plan", "provider",
}


def _payload() -> dict[str, Any]:
    return validation.get_request_payload(request)


def _owned_trip(trip_id: int):
    return current_app.extensions["managers"]["trips"].get_by_id(
        trip_id, current_user_id())


def _option(row) -> dict[str, Any]:
    return {
        "option_id": row["option_id"],
        "trip_id": row["trip_id"],
        "option_type": row["option_type"],
        "title": row["title"],
        "amount": row["amount"],
        "currency": row["currency"],
        "details": json.loads(row["details_json"]),
        "created_at": row["created_at"],
    }


def _has_payment_credentials(value: Any) -> bool:
    if isinstance(value, dict):
        forbidden = ("card", "cvv", "cvc", "bank", "iban", "swift",
                     "accountnumber", "paymentmethod")
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if any(token in normalized for token in forbidden):
                return True
            if _has_payment_credentials(nested):
                return True
    elif isinstance(value, list):
        return any(_has_payment_credentials(item) for item in value)
    return False


@mobile_bp.route("/api/favorites", methods=["GET"])
@login_required
def list_favorites():
    rows = current_app.extensions["wize_db"].query_all(
        """
        SELECT d.* FROM favorites f
        JOIN destinations d ON d.destination_id = f.destination_id
        WHERE f.user_id = ? AND d.is_custom = 0 AND d.is_listed = 1
        ORDER BY f.created_at DESC, d.name
        """, [current_user_id()])
    from models.destination import Destination
    return jsonify({"favorites": [Destination.from_row(row).serialize()
                                  for row in rows]})


@mobile_bp.route("/api/favorites/<int:destination_id>", methods=["POST"])
@login_required
@csrf_protect
def add_favorite(destination_id: int):
    try:
        destination = current_app.extensions["managers"]["destinations"] \
            .get_catalogue_destination(destination_id)
        current_app.extensions["wize_db"].execute(
            "INSERT OR IGNORE INTO favorites (user_id, destination_id) "
            "VALUES (?, ?)", [current_user_id(), destination_id])
    except Exception as error:
        return api_error(error)
    return jsonify({"message": "Destination saved to favorites.",
                    "destination": destination.serialize()}), 201


@mobile_bp.route("/api/favorites/<int:destination_id>", methods=["DELETE"])
@login_required
@csrf_protect
def remove_favorite(destination_id: int):
    current_app.extensions["wize_db"].execute(
        "DELETE FROM favorites WHERE user_id = ? AND destination_id = ?",
        [current_user_id(), destination_id])
    return jsonify({"message": "Favorite removed."})


@mobile_bp.route("/api/trips/<int:trip_id>/notes", methods=["GET", "POST"])
@login_required
def trip_notes(trip_id: int):
    try:
        _owned_trip(trip_id)
        db = current_app.extensions["wize_db"]
        if request.method == "GET":
            rows = db.query_all(
                "SELECT * FROM trip_notes WHERE trip_id = ? "
                "ORDER BY updated_at DESC, note_id DESC", [trip_id])
            return jsonify({"notes": [dict(row) for row in rows]})
        if not csrf_protect_valid():
            return jsonify({"error": "Invalid or missing CSRF token."}), 400
        payload = _payload()
        title = validation.require_text(payload.get("title"), "title", 1, 120)
        content = str(payload.get("content") or "").strip()
        if len(content) > 10000:
            raise validation.ValidationError("Notes must be 10,000 characters or fewer.",
                                             "content")
        cursor = db.execute(
            "INSERT INTO trip_notes (trip_id, title, content) VALUES (?, ?, ?)",
            [trip_id, title, content])
        note = db.query_one("SELECT * FROM trip_notes WHERE note_id = ?",
                            [cursor.lastrowid])
        return jsonify({"message": "Note saved.", "note": dict(note)}), 201
    except Exception as error:
        return api_error(error)


@mobile_bp.route("/api/notes/<int:note_id>", methods=["PUT", "PATCH", "DELETE"])
@login_required
@csrf_protect
def edit_note(note_id: int):
    db = current_app.extensions["wize_db"]
    row = db.query_one(
        "SELECT n.* FROM trip_notes n JOIN trips t ON t.trip_id = n.trip_id "
        "WHERE n.note_id = ? AND t.user_id = ?",
        [note_id, current_user_id()])
    if row is None:
        return api_error(NotFoundError("Note not found.", "note"))
    if request.method == "DELETE":
        db.execute("DELETE FROM trip_notes WHERE note_id = ?", [note_id])
        return jsonify({"message": "Note deleted."})
    try:
        payload = _payload()
        title = validation.require_text(payload.get("title", row["title"]),
                                        "title", 1, 120)
        content = str(payload.get("content", row["content"]) or "").strip()
        if len(content) > 10000:
            raise validation.ValidationError("Notes must be 10,000 characters or fewer.",
                                             "content")
        db.execute(
            "UPDATE trip_notes SET title = ?, content = ?, "
            "updated_at = datetime('now') WHERE note_id = ?",
            [title, content, note_id])
        updated = db.query_one("SELECT * FROM trip_notes WHERE note_id = ?",
                               [note_id])
        return jsonify({"message": "Note updated.", "note": dict(updated)})
    except Exception as error:
        return api_error(error)


def csrf_protect_valid() -> bool:
    """Validate CSRF for the POST branch of the combined notes endpoint."""
    from services.security import validate_csrf_token
    return validate_csrf_token()


@mobile_bp.route("/api/trips/<int:trip_id>/saved-options",
                 methods=["GET", "POST"])
@login_required
def saved_options(trip_id: int):
    try:
        trip = _owned_trip(trip_id)
        db = current_app.extensions["wize_db"]
        if request.method == "GET":
            rows = db.query_all(
                "SELECT * FROM saved_options WHERE trip_id = ? "
                "ORDER BY created_at DESC, option_id DESC", [trip_id])
            return jsonify({"options": [_option(row) for row in rows]})
        if not csrf_protect_valid():
            return jsonify({"error": "Invalid or missing CSRF token."}), 400
        payload = _payload()
        option_type = payload.get("option_type")
        if option_type not in {"flight", "hotel"}:
            raise validation.ValidationError(
                "Option type must be flight or hotel.", "option_type")
        title = validation.require_text(payload.get("title"), "title", 1, 200)
        amount = payload.get("amount")
        currency = payload.get("currency")
        if amount is not None:
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                raise validation.ValidationError("Amount must be numeric.", "amount") from None
            if not math.isfinite(amount) or amount < 0 or amount > 1_000_000_000:
                raise validation.ValidationError("Amount is outside the supported range.",
                                                 "amount")
        if currency is not None:
            currency = str(currency).upper()
            if len(currency) != 3 or not currency.isalpha():
                raise validation.ValidationError(
                    "Currency must be a 3-letter code.", "currency")
        allowed = FLIGHT_FIELDS if option_type == "flight" else HOTEL_FIELDS
        details = payload.get("details")
        if not isinstance(details, dict):
            raise validation.ValidationError("Option details must be an object.",
                                             "details")
        if _has_payment_credentials(details):
            raise validation.ValidationError(
                "Payment, card, and bank information cannot be saved.", "details")
        details = {key: value for key, value in details.items() if key in allowed}
        if option_type == "hotel":
            dates = details.get("dates")
            if isinstance(dates, dict):
                trip = _owned_trip(trip_id)
                check_in = dates.get("check_in")
                check_out = dates.get("check_out")
                if (not isinstance(check_in, str) or not isinstance(check_out, str)
                        or not validation.is_iso_date(check_in)
                        or not validation.is_iso_date(check_out)
                        or check_in < trip.get("start_date")
                        or check_out > trip.get("end_date")
                        or check_out <= check_in):
                    raise validation.ValidationError(
                        "The trip dates must include the hotel stay.", "details")
        encoded = json.dumps(details, ensure_ascii=False)
        if len(encoded) > 12000:
            raise validation.ValidationError("Option details are too large.", "details")
        if (amount is None) != (currency is None):
            raise validation.ValidationError(
                "A listed price must include both amount and currency.", "amount")
        planned_expense = None
        if amount is not None and amount > 0:
            planned_expense = validation.validate_expense(
                {
                    "expense_name": f"Planned {option_type}: {title}"[:120],
                    "category": "flights" if option_type == "flight" else "hotels",
                    "amount": amount,
                    "currency": currency,
                    "expense_date": trip.get("start_date"),
                    "expense_kind": "planned",
                    "notes": "Listed API price; planning estimate only.",
                },
                current_app.config["EXPENSE_CATEGORIES"],
                current_app.config["SUPPORTED_CURRENCIES"],
                current_app.config["CURRENCY_DEFAULT"],
            )
        connection = db.get_connection()
        try:
            cursor = connection.execute(
                "INSERT INTO saved_options "
                "(trip_id, option_type, title, amount, currency, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [trip_id, option_type, title, amount, currency, encoded])
            option_id = cursor.lastrowid
            if planned_expense is not None:
                connection.execute(
                    "INSERT INTO expenses "
                    "(trip_id, expense_name, category, amount, expense_kind, "
                    "source_option_id, currency, expense_date, notes) "
                    "VALUES (?, ?, ?, ?, 'planned', ?, ?, ?, ?)",
                    [
                        trip_id, planned_expense["expense_name"],
                        planned_expense["category"], planned_expense["amount"],
                        option_id, planned_expense["currency"],
                        planned_expense["expense_date"], planned_expense["notes"],
                    ],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        row = db.query_one("SELECT * FROM saved_options WHERE option_id = ?",
                           [option_id])
        return jsonify({"message": "Saved to trip; no purchase was made.",
                        "option": _option(row)}), 201
    except Exception as error:
        return api_error(error)


@mobile_bp.route("/api/saved-options/<int:option_id>",
                  methods=["PATCH", "DELETE"])
@login_required
@csrf_protect
def delete_saved_option(option_id: int):
    db = current_app.extensions["wize_db"]
    row = db.query_one(
        "SELECT o.*, t.start_date AS trip_start_date, "
        "t.end_date AS trip_end_date "
        "FROM saved_options o JOIN trips t ON t.trip_id = o.trip_id "
        "WHERE o.option_id = ? AND t.user_id = ?",
        [option_id, current_user_id()])
    if row is None:
        return api_error(NotFoundError("Saved option not found.", "saved_option"))
    if request.method == "DELETE":
        db.execute("DELETE FROM saved_options WHERE option_id = ?", [option_id])
        return jsonify({"message": "Saved option removed."})

    if row["option_type"] != "hotel":
        return api_error(validation.ValidationError(
            "Only saved hotel dates can be changed.", "option_type"))
    payload = _payload()
    check_in = payload.get("check_in")
    check_out = payload.get("check_out")
    if (not isinstance(check_in, str) or not isinstance(check_out, str)
            or not validation.is_iso_date(check_in)
            or not validation.is_iso_date(check_out)
            or check_in < row["trip_start_date"]
            or check_out > row["trip_end_date"]
            or check_out <= check_in):
        return api_error(validation.ValidationError(
            "Choose valid hotel dates within the trip, with check-out after check-in.",
            "dates"))

    try:
        details = json.loads(row["details_json"])
    except json.JSONDecodeError:
        return api_error(validation.ValidationError(
            "Saved hotel details are invalid.", "details"))
    if not isinstance(details, dict):
        return api_error(validation.ValidationError(
            "Saved hotel details are invalid.", "details"))
    old_dates = details.get("dates")
    old_dates = old_dates if isinstance(old_dates, dict) else {}
    dates_changed = (
        old_dates.get("check_in") != check_in
        or old_dates.get("check_out") != check_out
    )
    nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    details["dates"] = {"check_in": check_in, "check_out": check_out}
    details["nights"] = nights

    amount = row["amount"]
    currency = row["currency"]
    if dates_changed:
        details["total_price"] = None
        nightly = details.get("price_per_night")
        try:
            nightly_amount = float(nightly)
        except (TypeError, ValueError, OverflowError):
            nightly_amount = None
        if (nightly_amount is not None and math.isfinite(nightly_amount)
                and 0 <= nightly_amount <= 1_000_000_000):
            amount = round(nightly_amount * nights, 2)
            currency = details.get("currency")
        else:
            amount = None
            currency = None

    planned_expense = None
    if amount is not None and currency is not None and amount > 0:
        planned_expense = validation.validate_expense(
            {
                "expense_name": f"Planned hotel: {row['title']}"[:120],
                "category": "hotels",
                "amount": amount,
                "currency": currency,
                "expense_date": check_in,
                "expense_kind": "planned",
                "notes": (
                    "Updated estimate from the provider nightly rate; "
                    "taxes and fees may be additional."
                    if dates_changed else
                    "Listed API price; planning estimate only."
                ),
            },
            current_app.config["EXPENSE_CATEGORIES"],
            current_app.config["SUPPORTED_CURRENCIES"],
            current_app.config["CURRENCY_DEFAULT"],
        )
        amount = planned_expense["amount"]
        currency = planned_expense["currency"]
    elif amount is None or currency is None:
        amount = None
        currency = None

    encoded = json.dumps(details, ensure_ascii=False)
    if len(encoded) > 12000:
        return api_error(validation.ValidationError(
            "Option details are too large.", "details"))

    connection = db.get_connection()
    try:
        connection.execute(
            "UPDATE saved_options SET amount = ?, currency = ?, details_json = ? "
            "WHERE option_id = ?",
            [amount, currency, encoded, option_id])
        expense = connection.execute(
            "SELECT expense_id FROM expenses WHERE source_option_id = ? "
            "AND expense_kind = 'planned'", [option_id]).fetchone()
        if planned_expense is not None:
            if expense is None:
                connection.execute(
                    "INSERT INTO expenses "
                    "(trip_id, expense_name, category, amount, expense_kind, "
                    "source_option_id, currency, expense_date, notes) "
                    "VALUES (?, ?, 'hotels', ?, 'planned', ?, ?, ?, ?)",
                    [
                        row["trip_id"], planned_expense["expense_name"], amount,
                        option_id, currency, check_in, planned_expense["notes"],
                    ],
                )
            else:
                connection.execute(
                    "UPDATE expenses SET expense_name = ?, amount = ?, currency = ?, "
                    "expense_date = ?, notes = ? WHERE expense_id = ?",
                    [
                        planned_expense["expense_name"], amount, currency, check_in,
                        planned_expense["notes"], expense["expense_id"],
                    ],
                )
        elif expense is not None:
            connection.execute(
                "DELETE FROM expenses WHERE expense_id = ?",
                [expense["expense_id"]],
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    updated = db.query_one(
        "SELECT * FROM saved_options WHERE option_id = ?", [option_id])
    return jsonify({
        "message": "Hotel dates and planning estimate updated.",
        "option": _option(updated),
    })
