"""Abstract base model shared by every Wize entity.

OOP - Abstraction
    ``BaseModel`` is an ABC.  Subclasses must implement ``from_row`` and
    ``serialize``.  Managers therefore only ever talk to this interface, which
    is what makes the design swappable.

OOP - Encapsulation
    Subclasses keep their fields in ``__slots``-like private attributes and
    expose read-only ``@property`` accessors instead of raw attributes.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Mapping


class BaseModel(ABC):
    """Common behaviour for all domain entities."""

    #: primary key column name - overridden by each subclass
    primary_key: str = "id"

    def __init__(self, **fields: Any) -> None:
        self._data: dict[str, Any] = dict(fields)

    # --------------------------------------------------------- factories ----
    @classmethod
    @abstractmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "BaseModel":
        """Build an instance from a database row (polymorphic factory)."""

    @abstractmethod
    def serialize(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the entity."""

    # ------------------------------------------------------- encapsulation --
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:                      # pragma: no cover - debug
        return f"<{type(self).__name__} {self.primary_key}={self._data.get(self.primary_key)}>"

    # ---------------------------------------------------- polymorphism ------
    def to_dict(self) -> dict[str, Any]:
        """Alias kept for callers that prefer the ``to_*`` naming."""
        return self.serialize()

    @property
    def id(self) -> Any:
        """Generic primary-key accessor.

        Managers use this instead of knowing each model's attribute name
        (``trip_id``, ``user_id``, ``checklist_id``, ...).
        """
        return self._data.get(self.primary_key)


def parse_date(value: str | date | None) -> date | None:
    """Safely convert an ISO date string to ``datetime.date``."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def json_safe(value: Any) -> Any:
    """Convert DB values into something ``json.dumps`` accepts."""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 2)
    return value