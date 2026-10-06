"""Schedule (itinerary activity) domain model."""

from __future__ import annotations

import sqlite3
from datetime import date, time, datetime
from typing import Any, Mapping

from models.base import BaseModel, parse_date


class Schedule(BaseModel):
    """A single activity inside a trip's itinerary."""

    primary_key = "schedule_id"

    def __init__(self, schedule_id: int | None = None, trip_id: int | None = None,
                 destination_id: int | None = None, activity_name: str = "",
                 activity_date: str | None = None, start_time: str | None = None,
                 end_time: str | None = None, notes: str | None = None,
                 destination_name: str | None = None,
                 destination_city: str | None = None,
                 destination_country: str | None = None,
                 **extra: Any) -> None:
        super().__init__(
            schedule_id=schedule_id, trip_id=trip_id,
            destination_id=destination_id, activity_name=activity_name,
            activity_date=activity_date, start_time=start_time,
            end_time=end_time, notes=notes,
            destination_name=destination_name,
            destination_city=destination_city,
            destination_country=destination_country, **extra,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "Schedule":
        d = dict(row)
        return cls(
            schedule_id=d.get("schedule_id"), trip_id=d.get("trip_id"),
            destination_id=d.get("destination_id"),
            activity_name=d.get("activity_name", ""),
            activity_date=d.get("activity_date"),
            start_time=d.get("start_time"), end_time=d.get("end_time"),
            notes=d.get("notes"),
            destination_name=d.get("destination_name"),
            destination_city=d.get("destination_city"),
            destination_country=d.get("destination_country"),
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "schedule_id": self.get("schedule_id"),
            "trip_id": self.get("trip_id"),
            "destination_id": self.get("destination_id"),
            "activity_name": self.get("activity_name"),
            "activity_date": self.get("activity_date"),
            "start_time": self.get("start_time"),
            "end_time": self.get("end_time"),
            "notes": self.get("notes"),
            "destination_name": self.get("destination_name"),
            "location": ", ".join(
                p for p in [self.get("destination_city"), self.get("destination_country")] if p
            ) or None,
            "duration_minutes": self.duration_minutes(),
            "time_label": self.time_label(),
        }

    # ------------------------------------------------- encapsulation -------
    @property
    def schedule_id(self) -> int | None:
        return self.get("schedule_id")

    @property
    def activity_date(self) -> str | None:
        return self.get("activity_date")

    def _minutes(self, value: str | None) -> int | None:
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return None
        return parsed.hour * 60 + parsed.minute

    def duration_minutes(self) -> int | None:
        start, end = self._minutes(self.get("start_time")), self._minutes(self.get("end_time"))
        if start is None or end is None or end < start:
            return None
        return end - start

    def time_label(self) -> str:
        start, end = self.get("start_time"), self.get("end_time")
        if start and end:
            return f"{start} - {end}"
        return start or end or ""

    def is_past(self) -> bool:
        day = parse_date(self.get("activity_date"))
        if not day:
            return False
        if day < date.today():
            return True
        if day > date.today():
            return False
        start = self.get("start_time")
        if not start:
            return False
        try:
            return time.fromisoformat(start) < datetime.now().time()
        except ValueError:
            return False

    def day_number(self, trip_start: str | None) -> int | None:
        """Position of this activity inside the trip (day 1, 2, 3...)."""
        start, activity = parse_date(trip_start), parse_date(self.get("activity_date"))
        if not start or not activity:
            return None
        return (activity - start).days + 1