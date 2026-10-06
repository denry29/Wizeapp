"""Expense domain model."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from models.base import BaseModel, parse_date

CATEGORY_LABELS = {
    "flights": "Flights",
    "hotels": "Hotels",
    "food": "Food & Drinks",
    "transportation": "Transportation",
    "accommodation": "Accommodation",
    "entrance_fees": "Entrance Fees",
    "shopping": "Shopping",
    "activities": "Activities",
    "other": "Other",
}


class Expense(BaseModel):
    """A single expense line belonging to a trip.

    OOP note: an Expense always carries its own ``currency``.  Totals are
    never summed across different currencies (see ``ExpenseManager``), which is
    the correct behaviour for a travel planner without a conversion service.
    """

    primary_key = "expense_id"

    def __init__(self, expense_id: int | None = None, trip_id: int | None = None,
                 expense_name: str = "", category: str = "other",
                 amount: float = 0.0, currency: str = "USD",
                 expense_date: str | None = None, notes: str | None = None,
                 **extra: Any) -> None:
        super().__init__(
            expense_id=expense_id, trip_id=trip_id, expense_name=expense_name,
            category=category, amount=float(amount or 0.0), currency=currency,
            expense_date=expense_date, notes=notes, **extra,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "Expense":
        d = dict(row)
        return cls(
            expense_id=d.get("expense_id"), trip_id=d.get("trip_id"),
            expense_name=d.get("expense_name", ""),
            category=d.get("category", "other"), amount=d.get("amount", 0.0),
            currency=d.get("currency", "USD"),
            expense_date=d.get("expense_date"), notes=d.get("notes"),
            expense_kind=d.get("expense_kind", "actual"),
            source_option_id=d.get("source_option_id"),
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "expense_id": self.get("expense_id"),
            "trip_id": self.get("trip_id"),
            "expense_name": self.get("expense_name"),
            "category": self.get("category"),
            "category_label": CATEGORY_LABELS.get(self.get("category", "other"), "Other"),
            "amount": round(float(self.get("amount") or 0), 2),
            "currency": self.get("currency"),
            "expense_date": self.get("expense_date"),
            "expense_kind": self.get("expense_kind", "actual"),
            "source_option_id": self.get("source_option_id"),
            "notes": self.get("notes"),
            "formatted_amount": self.formatted_amount(),
        }

    # ------------------------------------------------- encapsulation -------
    @property
    def expense_id(self) -> int | None:
        return self.get("expense_id")

    @property
    def amount(self) -> float:
        return round(float(self.get("amount") or 0), 2)

    @property
    def currency(self) -> str:
        return self.get("currency", "USD")

    def formatted_amount(self) -> str:
        return f"{self.amount:,.2f} {self.currency}"

    def is_on_trip_date(self, start: str | None, end: str | None) -> bool | None:
        """Tri-state check: None when the trip window is unknown."""
        day, start_d, end_d = (parse_date(self.get("expense_date")),
                               parse_date(start), parse_date(end))
        if not (day and start_d and end_d):
            return None
        return start_d <= day <= end_d