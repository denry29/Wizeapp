"""Checklist and checklist-item management."""

from __future__ import annotations

import sqlite3
from typing import Any

from managers.base_manager import BaseManager, NotFoundError
from models.checklist import Checklist, ChecklistItem
from services import validation


class ChecklistManager(BaseManager):
    """Checklists per trip plus their items and progress."""

    table = "checklists"
    primary_key = "checklist_id"
    owner_column = None
    model = Checklist
    writable_fields = ("trip_id", "checklist_name")

    def _to_model(self, row: sqlite3.Row | None) -> Checklist | None:
        return Checklist.from_row(row) if row is not None else None

    # --------------------------------------------------------- ownership ----
    def _trip_row(self, trip_id: int, user_id: int) -> sqlite3.Row:
        trip_id = validation.positive_int(trip_id, "trip_id")
        row = self.db.query_one(
            "SELECT trip_id, start_date, end_date, trip_name FROM trips "
            "WHERE trip_id = ? AND user_id = ?", [trip_id, user_id])
        if row is None:
            raise NotFoundError("Trip not found.", "trip")
        return row

    def _checklist_row(self, checklist_id: int, user_id: int) -> sqlite3.Row:
        """Load a checklist and verify its trip belongs to the caller."""
        checklist_id = validation.positive_int(checklist_id, "checklist_id")
        row = self.db.query_one(
            "SELECT c.*, t.user_id FROM checklists c "
            "JOIN trips t ON t.trip_id = c.trip_id "
            "WHERE c.checklist_id = ?", [checklist_id])
        if row is None or row["user_id"] != user_id:
            raise NotFoundError("Checklist not found.", "checklist")
        return row

    # -------------------------------------------------------------- CRUD ----
    def create_checklist(self, trip_id: int, user_id: int,
                         payload: dict[str, Any]) -> Checklist:
        trip = self._trip_row(trip_id, user_id)
        data = validation.validate_checklist(payload)
        duplicate = self.db.query_one(
            "SELECT 1 FROM checklists WHERE trip_id = ? AND checklist_name = ? "
            "COLLATE NOCASE", [trip["trip_id"], data["checklist_name"]])
        if duplicate is not None:
            raise validation.ValidationError("This trip already has that checklist.",
                                             "checklist_name")
        cursor = self.db.execute(
            "INSERT INTO checklists (trip_id, checklist_name) VALUES (?, ?)",
            [trip["trip_id"], data["checklist_name"]])
        return self.get_checklist_with_items(cursor.lastrowid, user_id)

    def delete_checklist(self, checklist_id: int, user_id: int) -> bool:
        """Deleting a checklist cascades to its items."""
        self._checklist_row(checklist_id, user_id)
        self.db.execute("DELETE FROM checklists WHERE checklist_id = ?", [checklist_id])
        return True

    def update_checklist(self, checklist_id: int, user_id: int,
                         payload: dict[str, Any]) -> Checklist:
        self._checklist_row(checklist_id, user_id)
        data = validation.validate_checklist(payload)
        self.db.execute("UPDATE checklists SET checklist_name = ? WHERE checklist_id = ?",
                        [data["checklist_name"], checklist_id])
        return self.get_checklist_with_items(checklist_id, user_id)

    # ------------------------------------------------------------ listing ---
    def list_for_trip(self, trip_id: int, user_id: int) -> list[Checklist]:
        """Every checklist of a trip with its items already attached."""
        self._trip_row(trip_id, user_id)
        rows = self.db.query_all(
            "SELECT * FROM checklists WHERE trip_id = ? ORDER BY checklist_id", [trip_id])
        checklists = self._to_models(rows)
        for checklist in checklists:
            checklist._items = self._items_for(checklist.checklist_id)
        return checklists

    def get_checklist_with_items(self, checklist_id: int, user_id: int) -> Checklist:
        row = self._checklist_row(checklist_id, user_id)
        checklist = self._to_model(row)
        checklist._items = self._items_for(checklist_id)
        return checklist
# ---------------------------------------------------------- checklist items --
    def add_item(self, checklist_id: int, user_id: int,
                 payload: dict[str, Any]) -> ChecklistItem:
        self._checklist_row(checklist_id, user_id)
        data = validation.validate_checklist_item(payload)
        cursor = self.db.execute(
            "INSERT INTO checklist_items (checklist_id, item_name, is_completed) "
            "VALUES (?, ?, ?)",
            [checklist_id, data["item_name"], data["is_completed"]])
        return self.get_item(cursor.lastrowid, user_id)

    def get_item(self, item_id: int, user_id: int) -> ChecklistItem:
        """Load an item, verifying its parent checklist is owned by the caller."""
        item_id = validation.positive_int(item_id, "item_id")
        row = self.db.query_one(
            "SELECT i.* FROM checklist_items i "
            "JOIN checklists c ON c.checklist_id = i.checklist_id "
            "JOIN trips t ON t.trip_id = c.trip_id "
            "WHERE i.item_id = ? AND t.user_id = ?", [item_id, user_id])
        if row is None:
            raise NotFoundError("Checklist item not found.", "item")
        return ChecklistItem.from_row(row)

    def update_item(self, item_id: int, user_id: int, payload: dict[str, Any]
                    ) -> ChecklistItem:
        existing = self.get_item(item_id, user_id)
        item_name = validation.require_text(
            payload.get("item_name", existing.get("item_name")), "item_name", 2, 120)
        if "is_completed" in payload:
            is_completed = 1 if validation._to_bool(payload.get("is_completed")) else 0
        else:
            is_completed = int(existing.get("is_completed") or 0)
        self.db.execute(
            "UPDATE checklist_items SET item_name = ?, is_completed = ? WHERE item_id = ?",
            [item_name, is_completed, existing.item_id])
        return self.get_item(item_id, user_id)

    def toggle_item(self, item_id: int, user_id: int) -> ChecklistItem:
        """Flip completed <-> pending."""
        item = self.get_item(item_id, user_id)
        item.toggle()
        self.db.execute("UPDATE checklist_items SET is_completed = ? WHERE item_id = ?",
                        [item.get("is_completed"), item.item_id])
        return self.get_item(item_id, user_id)

    def delete_item(self, item_id: int, user_id: int) -> bool:
        item = self.get_item(item_id, user_id)
        self.db.execute("DELETE FROM checklist_items WHERE item_id = ?", [item.item_id])
        return True

    # ------------------------------------------------------------ progress --
    def trip_progress(self, trip_id: int, user_id: int) -> dict[str, Any]:
        """Aggregate checklist progress for one trip."""
        self._trip_row(trip_id, user_id)
        row = self.db.query_one(
            """
            SELECT COUNT(i.item_id) AS total,
                   COALESCE(SUM(i.is_completed), 0) AS done
            FROM checklist_items i
            JOIN checklists c ON c.checklist_id = i.checklist_id
            WHERE c.trip_id = ?
            """, [trip_id])
        total = int(row["total"] or 0)
        done = int(row["done"] or 0)
        return {
            "total_items": total,
            "completed_items": done,
            "pending_items": total - done,
            "progress_percent": round(done / total * 100) if total else 0,
            "checklists": int(self.db.scalar(
                "SELECT COUNT(*) FROM checklists WHERE trip_id = ?", [trip_id])),
        }

    def pending_items_for_user(self, user_id: int, limit: int = 8) -> list[dict[str, Any]]:
        """Open items across every trip - powers the dashboard widget."""
        rows = self.db.query_all(
            """
            SELECT i.item_id, i.item_name, c.checklist_name, t.trip_name,
                   t.trip_id, c.checklist_id
            FROM checklist_items i
            JOIN checklists c ON c.checklist_id = i.checklist_id
            JOIN trips t ON t.trip_id = c.trip_id
            WHERE t.user_id = ? AND i.is_completed = 0
            ORDER BY date(t.start_date), i.item_id
            LIMIT ?
            """, [user_id, int(limit)])
        return [dict(row) for row in rows]

    def pending_count_for_user(self, user_id: int) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM checklist_items i "
            "JOIN checklists c ON c.checklist_id = i.checklist_id "
            "JOIN trips t ON t.trip_id = c.trip_id "
            "WHERE t.user_id = ? AND i.is_completed = 0", [user_id]))

    def _items_for(self, checklist_id: int) -> list[ChecklistItem]:
        rows = self.db.query_all(
            "SELECT * FROM checklist_items WHERE checklist_id = ? "
            "ORDER BY is_completed, item_id", [checklist_id])
        return [ChecklistItem.from_row(row) for row in rows]