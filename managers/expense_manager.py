"""Expense tracking and currency-safe totals."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from flask import current_app

from managers.base_manager import BaseManager, NotFoundError
from models.expense import CATEGORY_LABELS, Expense
from services import validation


class ExpenseManager(BaseManager):
    """CRUD plus category/currency summaries for expenses.

    OOP - Encapsulation of the money rule
        ``totals_by_currency()`` never collapses different currencies into one
        number.  Because the project has no exchange-rate service, amounts are
        grouped per currency and returned as a dict, which is the only
        mathematically honest option.
    """

    table = "expenses"
    primary_key = "expense_id"
    owner_column = None
    model = Expense
    writable_fields = ("trip_id", "expense_name", "category", "amount",
                       "currency", "expense_date", "expense_kind", "notes")

    def _to_model(self, row: sqlite3.Row | None) -> Expense | None:
        return Expense.from_row(row) if row is not None else None

    # --------------------------------------------------------- ownership ----
    def _trip_row(self, trip_id: int, user_id: int) -> sqlite3.Row:
        """Load the trip, but only when it belongs to ``user_id``."""
        trip_id = validation.positive_int(trip_id, "trip_id")
        row = self.db.query_one(
            "SELECT trip_id, start_date, end_date, budget, budget_currency "
            "FROM trips WHERE trip_id = ? AND user_id = ?", [trip_id, user_id])
        if row is None:
            raise NotFoundError("Trip not found.", "trip")
        return row

    def _validated(self, payload: dict[str, Any]) -> dict[str, Any]:
        return validation.validate_expense(
            payload, current_app.config["EXPENSE_CATEGORIES"],
            current_app.config["SUPPORTED_CURRENCIES"],
            current_app.config["CURRENCY_DEFAULT"])

    # -------------------------------------------------------------- CRUD ----
    def add_expense(self, trip_id: int, user_id: int, payload: dict[str, Any]) -> Expense:
        trip = self._trip_row(trip_id, user_id)
        data = self._validated(payload)
        cursor = self.db.execute(
            "INSERT INTO expenses (trip_id, expense_name, category, amount, currency, "
            "expense_date, expense_kind, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [trip["trip_id"], data["expense_name"], data["category"], data["amount"],
             data["currency"], data["expense_date"], data["expense_kind"],
             data["notes"]])
        return self.get_by_id(cursor.lastrowid, user_id)

    def update_expense(self, expense_id: int, user_id: int,
                       payload: dict[str, Any]) -> Expense:
        existing = self.get_owned_expense(expense_id, user_id)
        merged = {**existing.serialize(), **payload}
        data = self._validated(merged)
        assignments = [c for c in self.writable_fields if c in data]
        self.db.execute(
            f"UPDATE expenses SET {', '.join(f'{c} = ?' for c in assignments)} "
            f"WHERE expense_id = ?",
            [data[c] for c in assignments] + [existing.expense_id])
        return self.get_owned_expense(expense_id, user_id)

    def remove_expense(self, expense_id: int, user_id: int) -> bool:
        """Delete an expense after verifying the caller owns its trip."""
        expense = self.get_owned_expense(expense_id, user_id)
        self.db.execute("DELETE FROM expenses WHERE expense_id = ?",
                        [expense.expense_id])
        return True

    def get_owned_expense(self, expense_id: int, user_id: int) -> Expense:
        expense = self.get_by_id(expense_id, user_id)
        self._trip_row(expense.get("trip_id"), user_id)
        return expense

    # ------------------------------------------------------------ listing ---
    def list_for_trip(self, trip_id: int, user_id: int, category: str | None = None
                      ) -> list[Expense]:
        self._trip_row(trip_id, user_id)
        params: list[Any] = [trip_id]
        clause = "trip_id = ?"
        category = validation.optional_choice(
            category, current_app.config["EXPENSE_CATEGORIES"])
        if category:
            clause += " AND category = ?"
            params.append(category)
        rows = self.db.query_all(
            f"SELECT * FROM expenses WHERE {clause} "
            f"ORDER BY expense_date DESC, expense_id DESC", params)
        return self._to_models(rows)

    # ---------------------------------------------------------- summaries ----
    def totals_by_currency(self, trip_id: int, user_id: int) -> dict[str, float]:
        """Total per currency - never merged into one figure."""
        self._trip_row(trip_id, user_id)
        rows = self.db.query_all(
            "SELECT currency, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS n "
            "FROM expenses WHERE trip_id = ? AND expense_kind = 'actual' "
            "GROUP BY currency ORDER BY currency",
            [trip_id])
        return {row["currency"]: round(float(row["total"]), 2) for row in rows}

    def totals_by_kind_and_currency(self, trip_id: int, user_id: int
                                    ) -> dict[str, dict[str, float]]:
        """Return planned and actual amounts separately by currency."""
        self._trip_row(trip_id, user_id)
        rows = self.db.query_all(
            "SELECT expense_kind, currency, SUM(amount) AS total FROM expenses "
            "WHERE trip_id = ? GROUP BY expense_kind, currency "
            "ORDER BY expense_kind, currency", [trip_id])
        result: dict[str, dict[str, float]] = {"planned": {}, "actual": {}}
        for row in rows:
            result[row["expense_kind"]][row["currency"]] = round(
                float(row["total"]), 2)
        return result

    def summary_by_category(self, trip_id: int, user_id: int) -> list[dict[str, Any]]:
        """Per-category breakdown (grouped per currency inside each row)."""
        self._trip_row(trip_id, user_id)
        rows = self.db.query_all(
            "SELECT category, currency, COALESCE(SUM(amount), 0) AS total, "
            "COUNT(*) AS entries FROM expenses WHERE trip_id = ? "
            "AND expense_kind = 'actual' "
            "GROUP BY category, currency ORDER BY category, currency", [trip_id])
        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = merged.setdefault(row["category"], {
                "category": row["category"],
                "label": CATEGORY_LABELS.get(row["category"], "Other"),
                "entries": 0,
                "totals": {},
            })
            entry["entries"] += int(row["entries"])
            entry["totals"][row["currency"]] = round(float(row["total"]), 2)
        return list(merged.values())

    def grand_total_display(self, trip_id: int, user_id: int) -> str:
        """Human-readable total that stays correct with mixed currencies."""
        totals = self.totals_by_currency(trip_id, user_id)
        if not totals:
            return "No expenses yet"
        if len(totals) == 1:
            currency, amount = next(iter(totals.items()))
            return f"{amount:,.2f} {currency}"
        return " | ".join(f"{amount:,.2f} {code}" for code, amount in totals.items())

    def user_totals_by_currency(self, user_id: int) -> dict[str, float]:
        """All trips of one user, grouped per currency (dashboard)."""
        rows = self.db.query_all(
            "SELECT e.currency, COALESCE(SUM(e.amount), 0) AS total "
            "FROM expenses e JOIN trips t ON t.trip_id = e.trip_id "
            "WHERE t.user_id = ? AND e.expense_kind = 'actual' "
            "GROUP BY e.currency ORDER BY e.currency", [user_id])
        return {row["currency"]: round(float(row["total"]), 2) for row in rows}

    def count_for_trip(self, trip_id: int, user_id: int) -> int:
        self._trip_row(trip_id, user_id)
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM expenses WHERE trip_id = ?", [trip_id]))

    # ------------------------------------------------------- budget --------
    def budget_status(self, trip_id: int, user_id: int) -> dict[str, Any]:
        """Remaining budget for a trip.

        A budget can only be compared with expenses recorded in the *same*
        currency - the app has no exchange-rate service, so spending in other
        currencies is reported separately rather than guessed at.
        """
        trip = self._trip_row(trip_id, user_id)
        budget = trip["budget"]
        budget_currency = trip["budget_currency"]

        totals = self.totals_by_currency(trip_id, user_id)
        if budget is None or not budget_currency:
            return {"budget": None, "budget_currency": None,
                    "spent_in_budget_currency": None, "remaining": None,
                    "is_over_budget": None, "totals_by_currency": totals}

        spent = round(totals.get(budget_currency, 0.0), 2)
        remaining = round(float(budget) - spent, 2)
        return {
            "budget": round(float(budget), 2),
            "budget_currency": budget_currency,
            "spent_in_budget_currency": spent,
            "remaining": remaining,
            "is_over_budget": remaining < 0,
            "totals_by_currency": totals,
            "other_currencies": {k: v for k, v in totals.items()
                                 if k != budget_currency},
        }
        rows = self.db.query_all(
            f"SELECT * FROM expenses WHERE {clause} "
            f"ORDER BY expense_date DESC, expense_id DESC", params)
        return self._to_models(rows)