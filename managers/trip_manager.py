"""Trip CRUD, ownership rules and status derivation."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from flask import current_app

from managers.base_manager import BaseManager, NotFoundError
from models.trip import Trip
from services import validation


class TripManager(BaseManager):
    """Full CRUD for trips, always scoped to the signed-in user."""

    table = "trips"
    primary_key = "trip_id"
    owner_column = "user_id"
    model = Trip
    writable_fields = ("trip_name", "start_date", "end_date", "description",
                       "budget", "budget_currency", "status")

    def _to_model(self, row: sqlite3.Row | None) -> Trip | None:
        return Trip.from_row(row) if row is not None else None

    # ----------------------------------------------------------- helpers ----
    @property
    def _rules(self) -> dict[str, Any]:
        return {
            "allowed_statuses": current_app.config["TRIP_STATUSES"],
            "max_days": current_app.config["MAX_TRIP_DAYS"],
            "supported_currencies": current_app.config["SUPPORTED_CURRENCIES"],
            "default_currency": current_app.config["CURRENCY_DEFAULT"],
        }

    def _validated(self, payload: dict[str, Any]) -> dict[str, Any]:
        return validation.validate_trip(payload, **self._rules)

    def _assert_dates_inside(self, trip_id: int, value: str | None,
                             field: str) -> None:
        """Block visit/activity dates that fall outside the trip window."""
        if not value:
            return
        trip = self.get_by_id(trip_id)
        if not trip.contains_date(value):
            raise validation.ValidationError(
                f"This date must fall between the trip dates "
                f"({trip.get('start_date')} and {trip.get('end_date')}).", field)

    # ------------------------------------------------------------- CRUD -----
    def create_trip(self, user_id: int, payload: dict[str, Any]) -> Trip:
        return self.create(self._validated(payload), user_id)

    def update_trip(self, trip_id: int, user_id: int, payload: dict[str, Any]) -> Trip:
        """Partial update: merge with the stored values then re-validate."""
        existing = self.get_by_id(trip_id, user_id)
        merged = {**existing.serialize(), **payload}
        return self.update(trip_id, self._validated(merged), user_id)

    def delete_trip(self, trip_id: int, user_id: int) -> bool:
        """Deleting a trip cascades to destinations, schedules, ..."""
        return self.delete(trip_id, user_id)

    # --------------------------------------------------------- listing ------
    def list_for_user(self, user_id: int, status: str | None = None,
                      search: str | None = None) -> list[Trip]:
        """Trips of one user, optionally filtered by status / free text."""
        clauses, params = ["user_id = ?"], [user_id]
        status = validation.optional_choice(status, self._rules["allowed_statuses"])
        if status:
            clauses.append("status = ?")
            params.append(status)
        search = validation.clean_optional(search)
        if search:
            clauses.append("(trip_name LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        rows = self.db.query_all(
            f"SELECT * FROM trips WHERE {' AND '.join(clauses)} "
            f"ORDER BY date(start_date) DESC, trip_id DESC", params)
        return self._to_models(rows)

    def paginate(self, user_id: int, page: int = 1, per_page: int = 12,
                 status: str | None = None, search: str | None = None
                 ) -> dict[str, Any]:
        """Simple offset pagination for the mobile-friendly trip list."""
        page = max(1, int(page))
        per_page = min(max(1, int(per_page)), 50)
        rows = self.list_for_user(user_id, status, search)
        total = len(rows)
        start = (page - 1) * per_page
        return {
            "items": rows[start:start + per_page],
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
            "has_next": start + per_page < total,
            "has_prev": page > 1,
        }
# ------------------------------------------------------- statistics ------
    def statistics(self, user_id: int) -> dict[str, Any]:
        """Aggregate trip counts for the dashboard (done in SQL, not in Python)."""
        today = date.today().isoformat()
        totals = self.db.query_one(
            """
            SELECT
                COUNT(*)                                                    AS total,
                SUM(CASE WHEN date(end_date) >= ? AND status <> 'cancelled'
                         THEN 1 ELSE 0 END)                                  AS upcoming,
                SUM(CASE WHEN date(end_date) < ? OR status = 'completed'
                         THEN 1 ELSE 0 END)                                  AS completed,
                SUM(CASE WHEN date(start_date) > ? THEN 1 ELSE 0 END)         AS future
            FROM trips WHERE user_id = ?
            """, [today, today, today, user_id])
        upcoming = self.db.query_all(
            """
            SELECT * FROM trips
            WHERE user_id = ? AND date(end_date) >= ? AND status <> 'cancelled'
            ORDER BY date(start_date) ASC LIMIT 5
            """, [user_id, today])
        return {
            "total_trips": int(totals["total"] or 0),
            "upcoming_trips": int(totals["upcoming"] or 0),
            "completed_trips": int(totals["completed"] or 0),
            "future_trips": int(totals["future"] or 0),
            "next_trip": self._to_model(upcoming[0]) if upcoming else None,
            "upcoming_preview": self._to_models(upcoming),
        }

    def trip_ids_for_user(self, user_id: int) -> list[int]:
        return self.ids_for_owner(user_id, order_by="trip_id")

    def next_sequence_for_destinations(self, trip_id: int) -> int:
        value = self.db.scalar(
            "SELECT COALESCE(MAX(sequence_number), 0) FROM trip_destinations "
            "WHERE trip_id = ?", [trip_id])
        return int(value) + 1

    def delete_with_dependents(self, trip_id: int, user_id: int) -> bool:
        """Explicit cascade - SQLite FK cascade handles it, this documents intent."""
        self.db.execute("DELETE FROM trips WHERE trip_id = ? AND user_id = ?",
                        [trip_id, user_id])
        return True