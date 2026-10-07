"""Abstract base manager shared by every Wize manager.

OOP - Abstraction
    ``BaseManager`` is an abstract base class (ABC).  It declares the contract
    that every manager must provide (``create``/``get_by_id``/``list_owned``/
    ``update``/``delete``) and hides the SQL plumbing behind it.

OOP - Polymorphism
    Each concrete manager overrides the class attributes ``table``,
    ``primary_key``, ``owner_column`` and ``model``.  The inherited template
    methods then build the correct, fully parameterised SQL for that manager -
    one implementation, many behaviours.

OOP - Inheritance
    ``AuthManager``, ``TripManager``, ``DestinationManager``, ``ScheduleManager``,
    ``ExpenseManager``, ``ChecklistManager`` and ``DashboardManager`` all extend
    this class, which is why they share identical CRUD behaviour.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Iterable, Sequence

from database.db import DatabaseManager
from models.base import BaseModel
from services import validation


class NotFoundError(LookupError):
    """Raised when a record does not exist (or is not owned by the caller)."""

    def __init__(self, message: str = "Record not found.", resource: str = "record"):
        super().__init__(message)
        self.message = message
        self.resource = resource

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.message, "resource": self.resource}


class PermissionDeniedError(PermissionError):
    """Raised when a signed-in user touches somebody else's record."""

    def __init__(self, message: str = "You do not have permission to do that."):
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.message}


class BaseManager(ABC):
    """Generic, parameterised CRUD helper for a single table."""

    table: str = ""                       # overridden by every subclass
    primary_key: str = "id"
    owner_column: str | None = "user_id"  # None for the shared catalogue
    model: type[BaseModel]                # overridden by every subclass

    #: Only let clients write these columns, so they can't change protected fields.
    writable_fields: tuple[str, ...] = ()

    def __init__(self, db: DatabaseManager):
        self.db = db                      # Keep the database helper with this manager.

    # --------------------------------------------------------- abstraction --
    @abstractmethod
    def _to_model(self, row: sqlite3.Row | None) -> Any:
        """Turn a row into a model instance or ``None``."""

    def _to_models(self, rows: Iterable[sqlite3.Row]) -> list[Any]:
        return [self._to_model(row) for row in rows]

# -------------------------------------------------------------- CRUD ----
    def create(self, data: dict[str, Any], user_id: int | None = None) -> Any:
        """Insert a row and return the freshly created model.

        ``user_id`` is taken from the authenticated session only - it is never
        read from the request payload, so ownership cannot be spoofed.
        """
        payload = dict(data)
        if self.owner_column and user_id is not None:
            payload[self.owner_column] = user_id
        columns = self._columns_for_insert(payload)
        placeholders = ", ".join("?" for _ in columns)
        cursor = self.db.execute(
            f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[c] for c in columns],
        )
        return self.get_by_id(cursor.lastrowid, user_id)

    def get_by_id(self, record_id: int, user_id: int | None = None) -> Any:
        """Fetch one record, scoped to its owner. Raises NotFoundError."""
        record_id = validation.positive_int(record_id, self.primary_key)
        where, params = self._filter(user_id)
        clause = f"{where} AND {self.primary_key} = ?" if where else f"{self.primary_key} = ?"
        model = self._select_one(clause, [*params, record_id])
        if model is None:
            raise NotFoundError(f"{self.resource_label.capitalize()} not found.",
                                self.table)
        return model

    def find_by_id(self, record_id: int, user_id: int | None = None) -> Any:
        """Like ``get_by_id`` but returns ``None`` instead of raising."""
        try:
            return self.get_by_id(record_id, user_id)
        except NotFoundError:
            return None

    def exists_for_user(self, record_id: int, user_id: int | None = None) -> bool:
        return self.find_by_id(record_id, user_id) is not None

    def list_owned(self, user_id: int | None = None, order_by: str | None = None
                   ) -> list[Any]:
        where, params = self._where(user_id)
        rows = self.db.query_all(
            f"SELECT * FROM {self.table}{where} "
            f"ORDER BY {order_by or f'{self.primary_key} DESC'}", params)
        return self._to_models(rows)

    def count_owned(self, user_id: int | None = None) -> int:
        where, params = self._where(user_id)
        return int(self.db.scalar(f"SELECT COUNT(*) FROM {self.table}{where}", params))

    def update(self, record_id: int, data: dict[str, Any],
               user_id: int | None = None) -> Any:
        """Update the given fields and return the updated model."""
        existing = self.get_by_id(record_id, user_id)          # ownership check
        assignments = [c for c in self.writable_fields if c in data]
        if not assignments:
            return existing
        self.db.execute(
            f"UPDATE {self.table} SET {', '.join(f'{c} = ?' for c in assignments)} "
            f"WHERE {self.primary_key} = ?",
            [data[c] for c in assignments] + [existing.id],
        )
        return self.get_by_id(record_id, user_id)

    def delete(self, record_id: int, user_id: int | None = None) -> bool:
        """Delete a record owned by ``user_id``. Returns True when removed.

        SQLite's ``ON DELETE CASCADE`` removes dependent rows (and therefore
        ``user_id`` ownership is enforced by ``get_by_id`` above).
        """
        existing = self.get_by_id(record_id, user_id)          # ownership check
        self.db.execute(f"DELETE FROM {self.table} WHERE {self.primary_key} = ?",
                        [existing.id])
        return True

    # --------------------------------------------------------- aggregates ---
    def sum_column(self, column: str, user_id: int | None = None,
                   where_extra: str = "", params_extra: Sequence[Any] = ()) -> float:
        """Safe SUM() helper - returns 0.0 when no rows match."""
        where, params = self._where(user_id)
        clause = f"{where} AND {where_extra}" if where_extra else where
        return float(self.db.scalar(
            f"SELECT COALESCE(SUM({column}), 0) FROM {self.table}{clause}",
            [*params, *params_extra]))

    def distinct_values(self, column: str) -> list[str]:
        rows = self.db.query_all(
            f"SELECT DISTINCT {column} FROM {self.table} "
            f"WHERE {column} IS NOT NULL AND TRIM({column}) <> '' ORDER BY {column}")
        return [row[0] for row in rows]

    def ids_for_owner(self, user_id: int | None = None, order_by: str | None = None
                      ) -> list[int]:
        where, params = self._where(user_id)
        rows = self.db.query_all(
            f"SELECT {self.primary_key} FROM {self.table}{where} "
            f"ORDER BY {order_by or f'{self.primary_key} DESC'}", params)
        return [row[0] for row in rows]

    # ------------------------------------------------------------- helpers --
    @property
    def resource_label(self) -> str:
        return self.table[:-1].replace("_", " ") if self.table.endswith("s") else self.table

    # ------------------------------------------------------------ helpers --
    def _filter(self, user_id: int | None) -> tuple[str, list[Any]]:
        """Ownership condition *without* the WHERE keyword.

        Returns ``("", [])`` when the table has no owner column, so callers can
        safely write ``f"{condition} AND col = ?"``.
        """
        if self.owner_column and user_id is not None:
            return f"{self.owner_column} = ?", [user_id]
        return "", []

    def _where(self, user_id: int | None) -> tuple[str, list[Any]]:
        """Ownership condition *including* the WHERE keyword (for whole clauses)."""
        condition, params = self._filter(user_id)
        return (f" WHERE {condition}" if condition else ""), params

    def _columns_for_insert(self, data: dict[str, Any]) -> list[str]:
        """Writable columns for an INSERT.

        The owner column is always included when present, even though it is
        deliberately *not* listed in ``writable_fields`` - it may never be set
        by a client, only by the manager from the authenticated session.
        """
        columns = list(self.writable_fields)
        if self.owner_column and self.owner_column not in columns:
            columns.append(self.owner_column)
        return [column for column in columns if column in data]

    def _select_one(self, where_clause: str, params: Sequence[Any]) -> Any:
        return self._to_model(self.db.query_one(
            f"SELECT * FROM {self.table} WHERE {where_clause}", params))

    def _select_all(self, where_clause: str, params: Sequence[Any],
                    order_by: str) -> list[Any]:
        return self._to_models(self.db.query_all(
            f"SELECT * FROM {self.table} WHERE {where_clause} ORDER BY {order_by}", params))