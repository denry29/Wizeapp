"""Trip domain model."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any, Mapping

from models.base import BaseModel, parse_date


class Trip(BaseModel):
    """A personal trip owned by exactly one user."""

    primary_key = "trip_id"

    def __init__(self, trip_id: int | None = None, user_id: int | None = None,
                 trip_name: str = "", start_date: str | None = None,
                 end_date: str | None = None, description: str | None = None,
                 budget: float | None = None, budget_currency: str | None = None,
                 status: str = "planning", created_at: str | None = None,
                 **extra: Any) -> None:
        super().__init__(
            trip_id=trip_id, user_id=user_id, trip_name=trip_name,
            start_date=start_date, end_date=end_date, description=description,
            budget=budget, budget_currency=budget_currency,
            status=status, created_at=created_at, **extra,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "Trip":
        d = dict(row)
        return cls(
            trip_id=d.get("trip_id"), user_id=d.get("user_id"),
            trip_name=d.get("trip_name", ""), start_date=d.get("start_date"),
            end_date=d.get("end_date"), description=d.get("description"),
            budget=d.get("budget"), budget_currency=d.get("budget_currency"),
            status=d.get("status", "planning"), created_at=d.get("created_at"),
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "trip_id": self.get("trip_id"),
            "user_id": self.get("user_id"),
            "trip_name": self.get("trip_name"),
            "start_date": self.get("start_date"),
            "end_date": self.get("end_date"),
            "description": self.get("description"),
            "budget": self.get("budget"),
            "budget_currency": self.get("budget_currency"),
            "status": self.get("status"),
            "created_at": self.get("created_at"),
            "duration_days": self.duration_days(),
            "is_upcoming": self.is_upcoming(),
            "is_completed": self.is_completed(),
        }

    # ------------------------------------------------- encapsulation -------
    @property
    def trip_id(self) -> int | None:
        return self.get("trip_id")

    @property
    def trip_name(self) -> str:
        return self.get("trip_name", "")

    @property
    def user_id(self) -> int | None:
        return self.get("user_id")

    @property
    def status(self) -> str:
        return self.get("status", "planning")

    def duration_days(self) -> int:
        """Number of days covered by the trip (inclusive of both ends)."""
        start, end = parse_date(self.get("start_date")), parse_date(self.get("end_date"))
        if not start or not end:
            return 0
        return (end - start).days + 1

    def days_until_start(self) -> int | None:
        start = parse_date(self.get("start_date"))
        return None if start is None else (start - date.today()).days

    def is_upcoming(self) -> bool:
        end = parse_date(self.get("end_date"))
        return bool(end and end >= date.today() and self.status != "cancelled")

    def is_completed(self) -> bool:
        end = parse_date(self.get("end_date"))
        return bool(end and end < date.today()) or self.status == "completed"

    def contains_date(self, value: str | date) -> bool:
        """True when ``value`` falls inside the trip window."""
        target, start, end = parse_date(value), parse_date(self.get("start_date")), parse_date(self.get("end_date"))
        if not (target and start and end):
            return False
        return start <= target <= end

    def date_range(self) -> list[str]:
        """Every date of the trip - handy for itinerary rendering."""
        start, end = parse_date(self.get("start_date")), parse_date(self.get("end_date"))
        if not start or not end:
            return []
        days = (end - start).days + 1
        return [(start + timedelta(days=i)).isoformat() for i in range(days)]