"""Checklist and checklist-item routes."""

from __future__ import annotations

from typing import Any

from flask import (Blueprint, current_app, jsonify, redirect, render_template,
                   request, url_for)

from managers.base_manager import NotFoundError
from services import validation
from services.security import (api_error, csrf_protect, current_user_id,
                               login_required)

checklists_bp = Blueprint("checklists", __name__)


def _manager():
    return current_app.extensions["managers"]["checklists"]


def _payload() -> dict[str, Any]:
    return validation.get_request_payload(request)


# --------------------------------------------------------------- JSON API --
@checklists_bp.route("/api/trips/<int:trip_id>/checklists", methods=["GET"])
@login_required
def api_list(trip_id: int):
    """GET - all checklists of a trip including items and progress."""
    try:
        checklists = _manager().list_for_trip(trip_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({
        "checklists": [c.serialize() for c in checklists],
        "progress": _manager().trip_progress(trip_id, current_user_id()),
    })


@checklists_bp.route("/api/trips/<int:trip_id>/checklists", methods=["POST"])
@login_required
@csrf_protect
def api_create(trip_id: int):
    """POST - create a checklist for a trip."""
    try:
        checklist = _manager().create_checklist(trip_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Checklist created.",
                    "checklist": checklist.serialize()}), 201


@checklists_bp.route("/api/checklists/<int:checklist_id>", methods=["GET"])
@login_required
def api_detail(checklist_id: int):
    try:
        checklist = _manager().get_checklist_with_items(checklist_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"checklist": checklist.serialize()})


@checklists_bp.route("/api/checklists/<int:checklist_id>", methods=["PUT", "PATCH"])
@login_required
@csrf_protect
def api_update(checklist_id: int):
    """PUT/PATCH - rename a checklist."""
    try:
        checklist = _manager().update_checklist(checklist_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Checklist updated.", "checklist": checklist.serialize()})


@checklists_bp.route("/api/checklists/<int:checklist_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete(checklist_id: int):
    """DELETE - remove a checklist and all of its items."""
    try:
        _manager().delete_checklist(checklist_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Checklist deleted."})


@checklists_bp.route("/api/checklists/<int:checklist_id>/items", methods=["GET", "POST"])
@login_required
def api_items(checklist_id: int):
    """GET lists items, POST adds one."""
    user_id = current_user_id()
    try:
        if request.method == "GET":
            checklist = _manager().get_checklist_with_items(checklist_id, user_id)
            return jsonify({"items": [i.serialize() for i in checklist.items]})
        item = _manager().add_item(checklist_id, user_id, _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Item added.", "item": item.serialize()}), 201


@checklists_bp.route("/api/checklist-items/<int:item_id>", methods=["PUT", "PATCH"])
@login_required
@csrf_protect
def api_update_item(item_id: int):
    """PATCH - rename an item and/or set its completion state.

    Use ``POST /api/checklist-items/<id>/toggle`` to flip the state; this
    endpoint only applies the fields that were actually sent.
    """
    try:
        item = _manager().update_item(item_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Item updated.", "item": item.serialize()})


@checklists_bp.route("/api/checklist-items/<int:item_id>/toggle", methods=["POST"])
@login_required
@csrf_protect
def api_toggle_item(item_id: int):
    """POST - flip completed <-> pending for a single item."""
    try:
        item = _manager().toggle_item(item_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Item toggled.", "item": item.serialize()})


@checklists_bp.route("/api/checklist-items/<int:item_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete_item(item_id: int):
    """DELETE - remove one checklist item."""
    try:
        _manager().delete_item(item_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Item deleted."})


# ------------------------------------------------------------ HTML forms ----
@checklists_bp.route("/trips/<int:trip_id>/checklists/add", methods=["POST"])
@login_required
@csrf_protect
def add_checklist(trip_id: int):
    """HTML form handler: create a checklist for the trip."""
    try:
        _manager().create_checklist(trip_id, current_user_id(), _payload())
    except (validation.ValidationError, NotFoundError):
        pass
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@checklists_bp.route("/checklists/<int:checklist_id>/items/add", methods=["POST"])
@login_required
@csrf_protect
def add_item(checklist_id: int):
    """HTML form handler: add an item, remembering which trip to return to."""
    user_id = current_user_id()
    try:
        checklist = _manager().get_checklist_with_items(checklist_id, user_id)
        trip_id = checklist.get("trip_id")
        _manager().add_item(checklist_id, user_id, _payload())
    except NotFoundError:
        return render_template("errors/404.html", page_title="Checklist not found"), 404
    except validation.ValidationError:
        pass
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@checklists_bp.route("/checklist-items/<int:item_id>/toggle", methods=["POST"])
@login_required
@csrf_protect
def toggle_item(item_id: int):
    """HTML form handler: tick/untick an item."""
    user_id = current_user_id()
    manager = _manager()
    try:
        item = manager.get_item(item_id, user_id)
        trip_id = _trip_id_for_item(manager, item)
        manager.toggle_item(item_id, user_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Item not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


def _trip_id_for_item(manager, item) -> int:
    """Resolve the trip that owns the item's checklist (for the redirect)."""
    row = manager.db.query_one(
        "SELECT trip_id FROM checklists WHERE checklist_id = ?",
        [item.get("checklist_id")])
    return int(row["trip_id"]) if row else 0


@checklists_bp.route("/checklist-items/<int:item_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_item(item_id: int):
    user_id = current_user_id()
    manager = _manager()
    try:
        item = manager.get_item(item_id, user_id)
        trip_id = _trip_id_for_item(manager, item)
        manager.delete_item(item_id, user_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Item not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@checklists_bp.route("/checklists/<int:checklist_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_checklist(checklist_id: int):
    """HTML form handler: delete a whole checklist and return to its trip."""
    manager = _manager()
    user_id = current_user_id()
    try:
        checklist = manager.get_checklist_with_items(checklist_id, user_id)
        trip_id = checklist.get("trip_id")
        manager.delete_checklist(checklist_id, user_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Checklist not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))
