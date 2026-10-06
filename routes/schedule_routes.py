"""Schedule / itinerary routes."""

from __future__ import annotations

from typing import Any

from flask import (Blueprint, current_app, jsonify, redirect, render_template,
                   request, url_for)

from managers.base_manager import NotFoundError
from services import validation
from services.security import (api_error, csrf_protect, current_user_id,
                               login_required)

schedules_bp = Blueprint("schedules", __name__)


def _manager():
    return current_app.extensions["managers"]["schedules"]


def _payload() -> dict[str, Any]:
    return validation.get_request_payload(request)


# --------------------------------------------------------------- JSON API --
@schedules_bp.route("/api/trips/<int:trip_id>/schedules", methods=["GET"])
@login_required
def api_list(trip_id: int):
    """GET - itinerary for a trip, optionally filtered by ?day=YYYY-MM-DD."""
    try:
        activities = _manager().list_for_trip(
            trip_id, current_user_id(), request.args.get("day"))
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"schedules": [a.serialize() for a in activities]})


@schedules_bp.route("/api/trips/<int:trip_id>/schedules", methods=["POST"])
@login_required
@csrf_protect
def api_create(trip_id: int):
    """POST - add an activity to the trip itinerary."""
    try:
        activity = _manager().add_activity(trip_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Activity added.", "schedule": activity.serialize()}), 201


@schedules_bp.route("/api/schedules/<int:schedule_id>", methods=["GET"])
@login_required
def api_detail(schedule_id: int):
    try:
        activity = _manager().get_owned_activity(schedule_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"schedule": activity.serialize()})


@schedules_bp.route("/api/schedules/<int:schedule_id>", methods=["PUT", "PATCH"])
@login_required
@csrf_protect
def api_update(schedule_id: int):
    """PUT/PATCH - edit an activity."""
    try:
        activity = _manager().update_activity(schedule_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Activity updated.", "schedule": activity.serialize()})


@schedules_bp.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete(schedule_id: int):
    """DELETE - remove an activity."""
    try:
        _manager().remove_activity(schedule_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Activity deleted."})


# ------------------------------------------------------------ HTML forms ----
@schedules_bp.route("/trips/<int:trip_id>/schedules/add", methods=["POST"])
@login_required
@csrf_protect
def add_activity(trip_id: int):
    """HTML form handler: add an activity and return to the trip page."""
    errors: dict = {}
    try:
        _manager().add_activity(trip_id, current_user_id(), _payload())
    except validation.ValidationError as error:
        errors = {error.field or "form": error.message}
        trip = current_app.extensions["managers"]["trips"].find_by_id(
            trip_id, current_user_id())
        if trip is None:
            return render_template("errors/404.html", page_title="Trip not found"), 404
        managers = current_app.extensions["managers"]
        return render_template(
            "trips/detail.html", trip=trip,
            linked_destinations=managers["destinations"].list_for_trip(trip_id),
            itinerary=managers["schedules"].itinerary_by_day(trip_id, trip.user_id),
            expenses=managers["expenses"].list_for_trip(trip_id, trip.user_id),
            expense_totals=managers["expenses"].totals_by_currency(trip_id, trip.user_id),
            expense_summary=managers["expenses"].summary_by_category(trip_id, trip.user_id),
            checklists=managers["checklists"].list_for_trip(trip_id, trip.user_id),
            progress=managers["checklists"].trip_progress(trip_id, trip.user_id),
            statuses=current_app.config["TRIP_STATUSES"],
            destination_choices=managers["destinations"].search_catalogue(per_page=100)["items"],
            expense_categories=current_app.config["EXPENSE_CATEGORIES"],
            form_errors=errors, active_tab="itinerary",
            page_title=trip.trip_name), 400
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@schedules_bp.route("/schedules/<int:schedule_id>/edit", methods=["POST"])
@login_required
@csrf_protect
def edit_activity(schedule_id: int):
    try:
        activity = _manager().update_activity(schedule_id, current_user_id(), _payload())
    except validation.ValidationError:
        pass                       # silently fall back: re-render via redirect below
    except NotFoundError:
        return render_template("errors/404.html", page_title="Activity not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=activity.get("trip_id")))


@schedules_bp.route("/schedules/<int:schedule_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_activity(schedule_id: int):
    user_id = current_user_id()
    try:
        activity = _manager().get_owned_activity(schedule_id, user_id)
        trip_id = activity.get("trip_id")
        _manager().remove_activity(schedule_id, user_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Activity not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))