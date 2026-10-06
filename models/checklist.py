"""Checklist and ChecklistItem domain models.

OOP - Inheritance
    ``ChecklistItem`` inherits from ``BaseModel`` just like the other
    entities, and both are composed inside ``Checklist``, which owns the
    progress calculation.  The composition keeps the database rows
    (checklists / checklist_items) separate while presenting one object to the
    routes and templates.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from models.base import BaseModel


class ChecklistItem(BaseModel):
    """One line of a packing / preparation checklist."""

    primary_key = "item_id"

    def __init__(self, item_id: int | None = None, checklist_id: int | None = None,
                 item_name: str = "", is_completed: int = 0,
                 created_at: str | None = None, **extra: Any) -> None:
        super().__init__(
            item_id=item_id, checklist_id=checklist_id, item_name=item_name,
            is_completed=int(is_completed or 0), created_at=created_at, **extra,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "ChecklistItem":
        d = dict(row)
        return cls(
            item_id=d.get("item_id"), checklist_id=d.get("checklist_id"),
            item_name=d.get("item_name", ""),
            is_completed=d.get("is_completed", 0),
            created_at=d.get("created_at"),
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "item_id": self.get("item_id"),
            "checklist_id": self.get("checklist_id"),
            "item_name": self.get("item_name"),
            "is_completed": bool(self.get("is_completed")),
            "created_at": self.get("created_at"),
        }

    # ------------------------------------------------- encapsulation -------
    @property
    def item_id(self) -> int | None:
        return self.get("item_id")

    def is_done(self) -> bool:
        return bool(self.get("is_completed"))

    def toggle(self) -> None:
        """Flip the completion flag (business rule kept off the routes)."""
        self._data["is_completed"] = 0 if self.is_done() else 1

    def __repr__(self) -> str:                      # pragma: no cover - debug
        mark = "x" if self.is_done() else " "
        return f"[{mark}] {self.get('item_name')}"


class Checklist(BaseModel):
    """A checklist attached to a trip, with its items."""

    primary_key = "checklist_id"

    def __init__(self, checklist_id: int | None = None, trip_id: int | None = None,
                 checklist_name: str = "", created_at: str | None = None,
                 items: list[ChecklistItem] | None = None, **extra: Any) -> None:
        super().__init__(
            checklist_id=checklist_id, trip_id=trip_id,
            checklist_name=checklist_name, created_at=created_at, **extra,
        )
        self._items: list[ChecklistItem] = list(items or [])

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "Checklist":
        d = dict(row)
        return cls(
            checklist_id=d.get("checklist_id"), trip_id=d.get("trip_id"),
            checklist_name=d.get("checklist_name", ""),
            created_at=d.get("created_at"),
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "checklist_id": self.get("checklist_id"),
            "trip_id": self.get("trip_id"),
            "checklist_name": self.get("checklist_name"),
            "created_at": self.get("created_at"),
            "items": [item.serialize() for item in self._items],
            "item_count": len(self._items),
            "completed_count": self.completed_count(),
            "pending_count": self.pending_count(),
            "progress_percent": self.progress_percent(),
            "is_complete": self.is_complete(),
        }

    # ------------------------------------------- composition + behaviour ----
    @property
    def checklist_id(self) -> int | None:
        return self.get("checklist_id")

    @property
    def items(self) -> list[ChecklistItem]:
        return self._items

    def add_item(self, item: ChecklistItem) -> None:
        self._items.append(item)

    def completed_count(self) -> int:
        return sum(1 for item in self._items if item.is_done())

    def pending_count(self) -> int:
        return len(self._items) - self.completed_count()

    def progress_percent(self) -> int:
        if not self._items:
            return 0
        return round(self.completed_count() / len(self._items) * 100)

    def is_complete(self) -> bool:
        return bool(self._items) and self.pending_count() == 0