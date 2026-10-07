"""Itinerary / schedule management."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Sequence

from managers.base_manager import BaseManager, NotFoundError
from models.schedule import Schedule
from services import validation

SELECT_WITH_DESTINATION = """
SELECT s.*, d.name AS destination_name, d.city AS destination_city,
       d.country AS destination_country
FROM schedules s
LEFT JOIN destinations d ON d.destination_id = s.destination_id
"""


class ScheduleManager(BaseManager):
    """CRUD for activities, always validated against the owning trip."""

    table = "schedules"
    primary_key = "schedule_id"
    owner_column = None          # ownership is enforced through the trips table
    model = Schedule
    writable_fields = ("trip_id", "destination_id", "activity_name",
                       "activity_date", "start_time", "end_time", "notes")

    def _to_model(self, row: sqlite3.Row | None) -> Schedule | None:
        return Schedule.from_row(row) if row is not None else None

    def _select_one(self, where_clause: str, params: Sequence[Any]) -> Schedule | None:
        """Join the destination so `destination_name` is always populated."""
        return self._to_model(self.db.query_one(
            f"{SELECT_WITH_DESTINATION} WHERE {where_clause}", params))

    def _select_all(self, where_clause: str, params: Sequence[Any],
                    order_by: str) -> list[Schedule]:
        return self._to_models(self.db.query_all(
            f"{SELECT_WITH_DESTINATION} WHERE {where_clause} ORDER BY {order_by}",
            params))

    # --------------------------------------------------------- ownership ----
    def _trip_row(self, trip_id: int, user_id: int) -> sqlite3.Row:
        """Fetch a trip, but only when it belongs to ``user_id`` (authorisation)."""
        trip_id = validation.positive_int(trip_id, "trip_id")
        row = self.db.query_one(
            "SELECT trip_id, user_id, start_date, end_date, trip_name FROM trips "
            "WHERE trip_id = ? AND user_id = ?", [trip_id, user_id])
        if row is None:
            # Give the same response for missing and other people's trips, so
            # nobody can use this endpoint to guess valid trip IDs.
            raise NotFoundError("Trip not found.", "trip")
        return row

    def _validated(self, payload: dict[str, Any], trip: sqlite3.Row) -> dict[str, Any]:
        data = validation.validate_schedule(
            payload, trip["start_date"], trip["end_date"])
        if data.get("destination_id"):
            row = self.db.query_one("SELECT 1 FROM destinations WHERE destination_id = ?",
                                    [data["destination_id"]])
            if row is None:
                raise validation.ValidationError("That destination does not exist.",
                                                 "destination_id")
        return data

    # -------------------------------------------------------------- CRUD ----
    def add_activity(self, trip_id: int, user_id: int,
                     payload: dict[str, Any]) -> Schedule:
        trip = self._trip_row(trip_id, user_id)
        data = self._validated(payload, trip)
        data["trip_id"] = trip["trip_id"]
        cursor = self.db.execute(
            "INSERT INTO schedules (trip_id, destination_id, activity_name, "
            "activity_date, start_time, end_time, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [data["trip_id"], data["destination_id"], data["activity_name"],
             data["activity_date"], data["start_time"], data["end_time"],
             data["notes"]])
        return self.get_by_id(cursor.lastrowid, user_id)

    def update_activity(self, schedule_id: int, user_id: int,
                        payload: dict[str, Any]) -> Schedule:
        """Load, merge with the stored values, then re-validate everything."""
        existing = self.get_owned_activity(schedule_id, user_id)
        trip = self._trip_row(existing.get("trip_id"), user_id)
        merged = {
            "activity_name": payload.get("activity_name", existing.get("activity_name")),
            "activity_date": payload.get("activity_date", existing.get("activity_date")),
            "start_time": payload.get("start_time", existing.get("start_time")),
            "end_time": payload.get("end_time", existing.get("end_time")),
            "notes": payload.get("notes", existing.get("notes")),
            "destination_id": payload.get("destination_id", existing.get("destination_id")),
        }
        data = self._validated(merged, trip)
        assignments = [c for c in self.writable_fields if c in data]
        self.db.execute(
            f"UPDATE schedules SET {', '.join(f'{c} = ?' for c in assignments)} "
            f"WHERE schedule_id = ?",
            [data[c] for c in assignments] + [existing.schedule_id])
        return self.get_owned_activity(schedule_id, user_id)

    def remove_activity(self, schedule_id: int, user_id: int) -> bool:
        """Delete an activity after verifying the caller owns its trip."""
        activity = self.get_owned_activity(schedule_id, user_id)
        self.db.execute("DELETE FROM schedules WHERE schedule_id = ?",
                        [activity.schedule_id])
        return True

    def get_owned_activity(self, schedule_id: int, user_id: int) -> Schedule:
        """Fetch an activity only when its trip belongs to the caller."""
        schedule = self.get_by_id(schedule_id, user_id)
        self._trip_row(schedule.get("trip_id"), user_id)
        return schedule

    # ------------------------------------------------------------ listing ---
    def list_for_trip(self, trip_id: int, user_id: int, day: str | None = None
                      ) -> list[Schedule]:
        self._trip_row(trip_id, user_id)
        params: list[Any] = [trip_id]
        clause = "s.trip_id = ?"
        if day:
            clause += " AND s.activity_date = ?"
            params.append(day)
        rows = self.db.query_all(
            f"{SELECT_WITH_DESTINATION} WHERE {clause} "
            f"ORDER BY s.activity_date, COALESCE(s.start_time, '99:99'), s.schedule_id",
            params)
        return self._to_models(rows)

    def itinerary_by_day(self, trip_id: int, user_id: int) -> dict[str, list[dict[str, Any]]]:
        """Group the itinerary per day for the schedule screen."""
        trip = self._trip_row(trip_id, user_id)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for activity in self.list_for_trip(trip_id, user_id):
            grouped.setdefault(activity.activity_date, []).append(
                activity.serialize()
                | {"day_number": activity.day_number(trip["start_date"])})
        return dict(sorted(grouped.items()))

    def upcoming_for_user(self, user_id: int, limit: int = 5) -> list[Schedule]:
        """Next activities across all of the user's trips (dashboard widget)."""
        today = date.today().isoformat()
        rows = self.db.query_all(
            f"""
            {SELECT_WITH_DESTINATION}
            JOIN trips t ON t.trip_id = s.trip_id
            WHERE t.user_id = ? AND s.activity_date >= ? AND date(t.end_date) >= ?
            ORDER BY s.activity_date, COALESCE(s.start_time, '99:99')
            LIMIT ?
            """, [user_id, today, today, int(limit)])
        return self._to_models(rows)

    def count_for_trip(self, trip_id: int, user_id: int) -> int:
        self._trip_row(trip_id, user_id)
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM schedules WHERE trip_id = ?", [trip_id]))
