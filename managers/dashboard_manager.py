"""Dashboard aggregation for the signed-in user.

OOP - Composition (reuses the other managers)
    ``DashboardManager`` owns no tables of its own.  It composes the existing
    managers so that every number shown on the dashboard goes through exactly
    the same ownership filter as the corresponding CRUD screen - a dashboard
    can therefore never leak another user's data.
"""

from __future__ import annotations

from typing import Any

from database.db import DatabaseManager
from managers.auth_manager import AuthManager
from managers.checklist_manager import ChecklistManager
from managers.destination_manager import DestinationManager
from managers.expense_manager import ExpenseManager
from managers.schedule_manager import ScheduleManager
from managers.trip_manager import TripManager


class DashboardManager:
    """Read-only overview: trips, schedules, expenses and checklists."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        # Reuse the existing managers here instead of writing the same SQL twice.
        self.trips = TripManager(db)
        self.schedules = ScheduleManager(db)
        self.expenses = ExpenseManager(db)
        self.checklists = ChecklistManager(db)
        self.destinations = DestinationManager(db)
        self.auth = AuthManager(db)

    def summary(self, user_id: int) -> dict[str, Any]:
        """Everything the dashboard needs, for one user only."""
        trip_stats = self.trips.statistics(user_id)
        upcoming = self.schedules.upcoming_for_user(user_id, limit=6)
        totals = self.expenses.user_totals_by_currency(user_id)
        pending_items = self.checklists.pending_items_for_user(user_id, limit=8)

        return {
            "user": self.auth.find_by_id(user_id).serialize() if self.auth.find_by_id(user_id) else None,
            "trips": {
                "total": trip_stats["total_trips"],
                "upcoming": trip_stats["upcoming_trips"],
                "completed": trip_stats["completed_trips"],
                "next_trip": (trip_stats["next_trip"].serialize()
                              if trip_stats["next_trip"] else None),
                "upcoming_preview": [t.serialize()
                                    for t in trip_stats["upcoming_preview"]],
            },
            "expenses": {
                "totals_by_currency": totals,
                "total_display": (" | ".join(f"{v:,.2f} {k}" for k, v in totals.items())
                                  if totals else "No expenses recorded yet"),
                "currency_count": len(totals),
            },
            "schedules": {
                "upcoming_count": int(self.db.scalar(
                    "SELECT COUNT(*) FROM schedules s JOIN trips t "
                    "ON t.trip_id = s.trip_id WHERE t.user_id = ? "
                    "AND s.activity_date >= date('now')", [user_id])),
                "upcoming": [a.serialize() for a in upcoming],
            },
            "checklists": {
                "pending_items": self.checklists.pending_count_for_user(user_id),
                "pending_preview": pending_items,
            },
            "catalogue": {
                "total_destinations": self.destinations.catalogue_total(),
                "countries": len(self.destinations.distinct_countries()),
            },
        }

    def trip_snapshot(self, trip_id: int, user_id: int) -> dict[str, Any]:
        """Compact statistics shown at the top of a trip detail page."""
        return {
            "destinations": self.destinations.count_for_trip(trip_id),
            "schedules": self.schedules.count_for_trip(trip_id, user_id),
            "expenses": self.expenses.count_for_trip(trip_id, user_id),
            "checklist": self.checklists.trip_progress(trip_id, user_id),
            "expense_totals": self.expenses.totals_by_currency(trip_id, user_id),
        }