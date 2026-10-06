"""Trip routes: HTML pages plus a REST-style JSON API under /api/trips."""

from __future__ import annotations

import json
from typing import Any

from flask import (Blueprint, current_app, jsonify, redirect, render_template,
                   request, url_for)

from managers.base_manager import NotFoundError
from services import validation
from services.security import (api_error, csrf_protect, current_user_id,
                               login_required)

trips_bp = Blueprint("trips", __name__)


def _manager():
    return current_app.extensions["managers"]["trips"]


def _payload() -> dict[str, Any]:
    return validation.get_request_payload(request)


def _serialise_trip(trip: Any) -> dict[str, Any]:
    return trip.serialize()


# --------------------------------------------------------------- JSON API --
@trips_bp.route("/api/trips", methods=["GET"])
@login_required
def api_list():
    """GET /api/trips?status=&search=&page= - the signed-in user's trips."""
    try:
        page = validation.positive_int(request.args.get("page", 1), "page")
        result = _manager().paginate(
            current_user_id(), page,
            current_app.config["ITEMS_PER_PAGE"],
            request.args.get("status"), request.args.get("search"))
    except Exception as error:                       # noqa: BLE001 - translated below
        return api_error(error)
    return jsonify({
        "trips": [_serialise_trip(t) for t in result["items"]],
        "pagination": {k: v for k, v in result.items() if k != "items"},
    })


@trips_bp.route("/api/trips", methods=["POST"])
@login_required
@csrf_protect
def api_create():
    """POST /api/trips - create a trip."""
    try:
        trip = _manager().create_trip(current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Trip created.", "trip": _serialise_trip(trip)}), 201


@trips_bp.route("/api/trips/<int:trip_id>", methods=["GET"])
@login_required
def api_detail(trip_id: int):
    """GET /api/trips/<id> - one trip owned by the caller."""
    try:
        trip = _manager().get_by_id(trip_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    snapshot = current_app.extensions["managers"]["dashboard"].trip_snapshot(
        trip_id, current_user_id())
    return jsonify({"trip": _serialise_trip(trip), "snapshot": snapshot})


@trips_bp.route("/api/trips/<int:trip_id>", methods=["PUT", "PATCH"])
@login_required
@csrf_protect
def api_update(trip_id: int):
    """PUT/PATCH /api/trips/<id> - partial update."""
    try:
        trip = _manager().update_trip(trip_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Trip updated.", "trip": _serialise_trip(trip)})


@trips_bp.route("/api/trips/<int:trip_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete(trip_id: int):
    """DELETE /api/trips/<id> - removes the trip and everything under it."""
    try:
        _manager().delete_trip(trip_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Trip deleted."})


# ------------------------------------------------------------ HTML pages ---
@trips_bp.route("/trips")
@login_required
def list_trips():
    manager = _manager()
    result = manager.paginate(current_user_id(),
                              validation.positive_int(request.args.get("page", 1), "page"),
                              current_app.config["ITEMS_PER_PAGE"],
                              request.args.get("status"), request.args.get("search"))
    return render_template("trips/list.html", trips=result["items"],
                           pagination=result, filters={
                               "status": request.args.get("status", ""),
                               "search": request.args.get("search", "")},
                           statuses=current_app.config["TRIP_STATUSES"],
                           page_title="My trips")


@trips_bp.route("/trips/new", methods=["GET", "POST"])
@login_required
@csrf_protect
def create_trip():
    """GET renders the form; POST creates the trip then redirects to it."""
    form: dict = {}
    errors: dict = {}
    if request.method == "POST":
        form = _payload()
        try:
            trip = _manager().create_trip(current_user_id(), form)
        except validation.ValidationError as error:
            errors = {error.field or "form": error.message}
        else:
            return redirect(url_for("trips.trip_detail", trip_id=trip.trip_id))

    return render_template("trips/form.html", form=form, errors=errors, trip=None,
                           statuses=current_app.config["TRIP_STATUSES"],
                           page_title="New trip")


@trips_bp.route("/trips/<int:trip_id>", methods=["GET"])
@login_required
def trip_detail(trip_id: int):
    """Trip overview with its destinations, itinerary, budget and checklists."""
    user_id = current_user_id()
    manager = _manager()
    try:
        trip = manager.get_by_id(trip_id, user_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Trip not found"), 404

    managers = current_app.extensions["managers"]
    db = current_app.extensions["wize_db"]
    saved_options = db.query_all(
        "SELECT * FROM saved_options WHERE trip_id = ? "
        "ORDER BY created_at DESC, option_id DESC", [trip_id])
    serialized_options = [
        {
            "option_id": row["option_id"],
            "trip_id": row["trip_id"],
            "option_type": row["option_type"],
            "title": row["title"],
            "amount": row["amount"],
            "currency": row["currency"],
            "details": json.loads(row["details_json"]),
            "created_at": row["created_at"],
        }
        for row in saved_options
    ]
    return render_template(
        "trips/detail.html",
        trip=trip,
        linked_destinations=managers["destinations"].list_for_trip(trip_id),
        itinerary=managers["schedules"].itinerary_by_day(trip_id, user_id),
        expenses=managers["expenses"].list_for_trip(trip_id, user_id),
        expense_totals=managers["expenses"].totals_by_currency(trip_id, user_id),
        trip_costs=managers["expenses"].totals_by_kind_and_currency(trip_id, user_id),
        expense_summary=managers["expenses"].summary_by_category(trip_id, user_id),
        saved_options=serialized_options,
        checklists=managers["checklists"].list_for_trip(trip_id, user_id),
        progress=managers["checklists"].trip_progress(trip_id, user_id),
        statuses=current_app.config["TRIP_STATUSES"],
        destination_choices=managers["destinations"].search_catalogue(per_page=100)["items"],
        expense_categories=current_app.config["EXPENSE_CATEGORIES"],
        page_title=trip.trip_name)


@trips_bp.route("/trips/<int:trip_id>/edit", methods=["GET", "POST"])
@login_required
@csrf_protect
def edit_trip(trip_id: int):
    manager = _manager()
    errors: dict = {}
    try:
        trip = manager.get_by_id(trip_id, current_user_id())
    except NotFoundError:
        return render_template("errors/404.html", page_title="Trip not found"), 404

    form = trip.serialize()
    if request.method == "POST":
        form = {**form, **_payload()}
        try:
            trip = manager.update_trip(trip_id, current_user_id(), form)
        except validation.ValidationError as error:
            errors = {error.field or "form": error.message}
        else:
            return redirect(url_for("trips.trip_detail", trip_id=trip_id))

    return render_template("trips/form.html", form=form, errors=errors, trip=trip,
                           statuses=current_app.config["TRIP_STATUSES"],
                           page_title=f"Edit {trip.trip_name}")


@trips_bp.route("/trips/<int:trip_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_trip(trip_id: int):
    """POST/redirect/delete pattern used by the HTML front-end."""
    try:
        _manager().delete_trip(trip_id, current_user_id())
    except NotFoundError:
        return render_template("errors/404.html", page_title="Trip not found"), 404
    return redirect(url_for("trips.list_trips"))
    errors: dict = {}
    if request.method == "POST":
        form = _payload()
        try:
            trip = _manager().create_trip(current_user_id(), form)
        except validation.ValidationError as error:
            errors = {error.field or "form": error.message}
        else:
            return redirect(url_for("trips.trip_detail", trip_id=trip.trip_id))
    return render_template("trips/form.html", form=form, errors=errors, trip=None,
                           statuses=current_app.config["TRIP_STATUSES"],
                           page_title="New trip")