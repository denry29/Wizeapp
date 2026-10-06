"""Hotel search pages and authenticated StayingAPI proxy endpoints."""

from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
from typing import Any

from flask import (Blueprint, current_app, jsonify, redirect, render_template,
                   request, url_for)

from services import validation
from services.security import csrf_protect, current_user_id, login_required
from services.stayingapi import ASIAN_COUNTRIES, StayingAPIClient, StayingAPIError

hotels_bp = Blueprint("hotels", __name__)


def _client() -> StayingAPIClient:
    return StayingAPIClient(current_app.config["STAYING_API_KEY"])


def _integer_arg(name: str, default: int, minimum: int,
                 maximum: int) -> int:
    value = request.args.get(name, str(default))
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise validation.ValidationError(
            f"{name.replace('_', ' ').capitalize()} must be a whole number.",
            name) from None
    if not minimum <= number <= maximum:
        raise validation.ValidationError(
            f"{name.replace('_', ' ').capitalize()} must be between "
            f"{minimum} and {maximum}.", name)
    return number


def _validated_search() -> dict[str, Any]:
    city = validation.require_text(request.args.get("city"), "city", 2, 80)
    country_code = validation.clean(request.args.get("country")).upper()
    if country_code not in ASIAN_COUNTRIES:
        raise validation.ValidationError(
            "Choose a destination country in Asia.", "country")

    check_in = validation.clean(request.args.get("check_in"))
    check_out = validation.clean(request.args.get("check_out"))
    if (len(check_in) != 10 or len(check_out) != 10
            or not validation.is_valid_date(check_in)
            or not validation.is_valid_date(check_out)):
        raise validation.ValidationError(
            "Enter valid check-in and check-out dates (YYYY-MM-DD).", "check_in")
    start, end = validation.parse_date(check_in), validation.parse_date(check_out)
    if start < date.today() or end <= start or (end - start).days > 365:
        raise validation.ValidationError(
            "Choose future dates with check-out after check-in (maximum one year).",
            "check_out")

    adults = _integer_arg("adults", 2, 1, 20)
    rooms = _integer_arg("rooms", 1, 1, 10)
    children = _integer_arg("children", 0, 0, 10)
    raw_ages = validation.clean(request.args.get("child_ages"))
    child_ages: list[int] = []
    if raw_ages:
        try:
            child_ages = [int(part.strip()) for part in raw_ages.split(",")]
        except ValueError:
            raise validation.ValidationError(
                "Enter child ages as comma-separated whole numbers.", "child_ages") from None
    if len(child_ages) != children or any(age < 0 or age > 17 for age in child_ages):
        if children or child_ages:
            raise validation.ValidationError(
                "Provide one child age (0-17) for each child.", "child_ages")

    currency = validation.clean(
        request.args.get("currency") or current_app.config["CURRENCY_DEFAULT"]
    ).upper()
    if currency not in current_app.config["SUPPORTED_CURRENCIES"]:
        raise validation.ValidationError("Choose a supported currency.", "currency")

    return {
        "city": city,
        "country_code": country_code,
        "check_in": start.isoformat(),
        "check_out": end.isoformat(),
        "adults": adults,
        "rooms": rooms,
        "children": children,
        "child_ages": child_ages,
        "currency": currency,
    }


@hotels_bp.route("/hotels")
@login_required
def search_page():
    trips = current_app.extensions["managers"]["trips"].list_for_user(
        current_user_id())
    return render_template(
        "hotels/search.html",
        countries=ASIAN_COUNTRIES,
        currencies=sorted(current_app.config["SUPPORTED_CURRENCIES"]),
        trips=[trip.serialize() for trip in trips],
        default_currency=current_app.config["CURRENCY_DEFAULT"],
        page_title="Hotel search",
    )


@hotels_bp.route("/api/hotels/search")
@login_required
def search_hotels():
    try:
        params = _validated_search()
        result = _client().search_hotels(**params)
    except validation.ValidationError as error:
        return jsonify(error.to_dict()), 400
    except StayingAPIError as error:
        return jsonify({"error": str(error), "provider": "StayingAPI"}), 503
    return jsonify({
        "provider": "StayingAPI",
        "hotels": result["hotels"],
        "meta": result["meta"],
        "searched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "live_search": True,
        "booking_enabled": False,
    })


@hotels_bp.route("/api/hotels/reviews")
@login_required
def hotel_reviews():
    platform = validation.clean(request.args.get("platform")).lower()
    listing_id = validation.clean(request.args.get("listing_id"))
    if platform not in {"booking", "google"}:
        return jsonify({"error": "Choose a supported hotel provider."}), 400
    if not listing_id or len(listing_id) > 200:
        return jsonify({"error": "A valid hotel listing ID is required."}), 400
    try:
        result = _client().get_reviews(platform, listing_id)
    except StayingAPIError as error:
        return jsonify({"error": str(error), "provider": "StayingAPI"}), 503
    reviews = result["data"]
    if isinstance(reviews, dict):
        reviews = reviews.get("reviews", [])
    if not isinstance(reviews, list):
        reviews = []
    return jsonify({"reviews": reviews, "meta": result["meta"]})


@hotels_bp.route("/trips/<int:trip_id>/saved-options/<int:option_id>/delete",
                 methods=["POST"])
@login_required
@csrf_protect
def delete_saved_option(trip_id: int, option_id: int):
    db = current_app.extensions["wize_db"]
    trip = db.query_one(
        "SELECT trip_id FROM trips WHERE trip_id = ? AND user_id = ?",
        [trip_id, current_user_id()])
    if trip is None:
        return render_template("errors/404.html",
                               page_title="Trip not found"), 404
    option = db.query_one(
        "SELECT option_id FROM saved_options WHERE option_id = ? AND trip_id = ?",
        [option_id, trip_id])
    if option is None:
        return render_template("errors/404.html",
                               page_title="Saved item not found"), 404
    db.execute("DELETE FROM saved_options WHERE option_id = ?", [option_id])
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))
