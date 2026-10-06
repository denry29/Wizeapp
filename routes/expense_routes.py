"""Expense routes with currency-safe totals."""

from __future__ import annotations

from typing import Any

from flask import (Blueprint, current_app, jsonify, redirect, render_template,
                   request, url_for)

from managers.base_manager import NotFoundError
from services import validation
from services.security import (api_error, csrf_protect, current_user_id,
                               login_required)

expenses_bp = Blueprint("expenses", __name__)


def _manager():
    return current_app.extensions["managers"]["expenses"]


def _payload() -> dict[str, Any]:
    return validation.get_request_payload(request)


# --------------------------------------------------------------- JSON API --
@expenses_bp.route("/api/trips/<int:trip_id>/expenses", methods=["GET"])
@login_required
def api_list(trip_id: int):
    """GET - expenses of a trip, optionally filtered by ?category=."""
    try:
        expenses = _manager().list_for_trip(trip_id, current_user_id(),
                                            request.args.get("category"))
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"expenses": [e.serialize() for e in expenses]})


@expenses_bp.route("/api/trips/<int:trip_id>/expenses", methods=["POST"])
@login_required
@csrf_protect
def api_create(trip_id: int):
    """POST - record an expense."""
    try:
        expense = _manager().add_expense(trip_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Expense recorded.", "expense": expense.serialize()}), 201


@expenses_bp.route("/api/trips/<int:trip_id>/expenses/summary", methods=["GET"])
@login_required
def api_summary(trip_id: int):
    """Totals per currency and per category for one trip."""
    user_id = current_user_id()
    try:
        manager = _manager()
        kind_totals = manager.totals_by_kind_and_currency(trip_id, user_id)
        currencies = set(kind_totals["planned"]) | set(kind_totals["actual"])
        return jsonify({
            "totals_by_currency": manager.totals_by_currency(trip_id, user_id),
            "totals_by_kind_and_currency": kind_totals,
            "variance_by_currency": {
                currency: round(
                    kind_totals["actual"].get(currency, 0)
                    - kind_totals["planned"].get(currency, 0), 2)
                for currency in sorted(currencies)
            },
            "by_category": manager.summary_by_category(trip_id, user_id),
            "grand_total_display": manager.grand_total_display(trip_id, user_id),
            "budget": manager.budget_status(trip_id, user_id),
            "note": "Amounts in different currencies are never added together.",
        })
    except Exception as error:                       # noqa: BLE001
        return api_error(error)


@expenses_bp.route("/api/expenses/<int:expense_id>", methods=["GET"])
@login_required
def api_detail(expense_id: int):
    try:
        expense = _manager().get_owned_expense(expense_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"expense": expense.serialize()})


@expenses_bp.route("/api/expenses/<int:expense_id>", methods=["PUT", "PATCH"])
@login_required
@csrf_protect
def api_update(expense_id: int):
    """PUT/PATCH - edit an expense."""
    try:
        expense = _manager().update_expense(expense_id, current_user_id(), _payload())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Expense updated.", "expense": expense.serialize()})


@expenses_bp.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@login_required
@csrf_protect
def api_delete(expense_id: int):
    """DELETE - remove an expense."""
    try:
        _manager().remove_expense(expense_id, current_user_id())
    except Exception as error:                       # noqa: BLE001
        return api_error(error)
    return jsonify({"message": "Expense deleted."})


# ------------------------------------------------------------ HTML forms ----
@expenses_bp.route("/trips/<int:trip_id>/expenses/add", methods=["POST"])
@login_required
@csrf_protect
def add_expense(trip_id: int):
    """HTML form handler: record an expense, then return to the trip page."""
    try:
        _manager().add_expense(trip_id, current_user_id(), _payload())
    except (validation.ValidationError, NotFoundError):
        pass                       # the trip page re-renders with the error flash
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@expenses_bp.route("/expenses/<int:expense_id>/edit", methods=["POST"])
@login_required
@csrf_protect
def edit_expense(expense_id: int):
    user_id = current_user_id()
    try:
        existing = _manager().get_owned_expense(expense_id, user_id)
        trip_id = existing.get("trip_id")
        _manager().update_expense(expense_id, user_id, _payload())
    except NotFoundError:
        return render_template("errors/404.html", page_title="Expense not found"), 404
    except validation.ValidationError:
        pass
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))


@expenses_bp.route("/expenses/<int:expense_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_expense(expense_id: int):
    user_id = current_user_id()
    try:
        expense = _manager().get_owned_expense(expense_id, user_id)
        trip_id = expense.get("trip_id")
        _manager().remove_expense(expense_id, user_id)
    except NotFoundError:
        return render_template("errors/404.html", page_title="Expense not found"), 404
    return redirect(url_for("trips.trip_detail", trip_id=trip_id))