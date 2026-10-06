"""Create a demonstration account and sample trip data.

Usage:
    python scripts/create_demo_user.py                 # create 'demo@wize.local'
    python scripts/create_demo_user.py --with-samples  # also add a demo trip

The password is only for local demonstration. For any shared deployment set
WIZE_DEMO_PASSWORD in the environment instead of relying on the default,
and never reuse these credentials anywhere else.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app                              # noqa: E402
from config import DATABASE_PATH, SCHEMA_PATH       # noqa: E402
from database.db import DatabaseManager             # noqa: E402
from managers.auth_manager import AuthManager       # noqa: E402
from managers.checklist_manager import ChecklistManager  # noqa: E402
from managers.destination_manager import DestinationManager  # noqa: E402
from managers.expense_manager import ExpenseManager  # noqa: E402
from managers.schedule_manager import ScheduleManager  # noqa: E402
from managers.trip_manager import TripManager        # noqa: E402

DEMO_EMAIL = os.environ.get("WIZE_DEMO_EMAIL", "demo@wize.local")
DEMO_PASSWORD = os.environ.get("WIZE_DEMO_PASSWORD", "DemoPass123!")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Wize demo account.")
    parser.add_argument("--db", default=str(DATABASE_PATH))
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    parser.add_argument("--name", default="Demo Traveller")
    parser.add_argument("--with-samples", action="store_true",
                        help="Also create a sample trip with schedule, expenses, checklist.")
    args = parser.parse_args(argv)

    db = DatabaseManager(Path(args.db), PROJECT_ROOT / "database" / "schema.sql")

    # The managers read domain rules from ``current_app.config``, so the whole
    # script runs inside an application context created by the factory.
    app = create_app(database_path=db.database_path)
    with app.app_context():
        return _run(args, db)


def _run(args, db: DatabaseManager) -> int:
    db.get_connection()
    db.create_tables()

    auth = AuthManager(db)
    if auth.email_exists(args.email):
        print(f"Account {args.email} already exists - nothing to do.")
        db.close()
        return 0

    user = auth.register({
        "full_name": args.name,
        "email": args.email,
        "password": args.password,
        "confirm_password": args.password,
    })
    # This development-only seed account has no mailbox to verify.
    db.execute(
        "UPDATE users SET email_verified = 1, email_verified_at = datetime('now') "
        "WHERE user_id = ?", [user.user_id])
    print(f"Created user #{user.user_id}: {user.email}")

    if args.with_samples:
        trips = TripManager(db)
        today = date.today()
        trip = trips.create_trip(user.user_id, {
            "trip_name": "Sample Japan Trip",
            "start_date": (today + timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=37)).isoformat(),
            "description": "Demonstration trip created by create_demo_user.py.",
            "status": "planning",
        })
        print(f"Created trip #{trip.trip_id}: {trip.trip_name}")

        catalogue = DestinationManager(db)
        picks = catalogue.search_catalogue(country="Japan", per_page=3)["items"]
        for item in picks:
            catalogue.attach_to_trip(trip.trip_id, user.user_id,
                                     {"destination_id": item.destination_id})
            print(f"  + added destination {item.get('name')}")

        schedules = ScheduleManager(db)
        schedules.add_activity(trip.trip_id, user.user_id, {
            "activity_name": "Visit the main temple",
            "activity_date": (today + timedelta(days=31)).isoformat(),
            "start_time": "09:00", "end_time": "12:00",
            "notes": "Arrive early to beat the crowds.",
        })
        print("  + added a sample activity")

        expenses = ExpenseManager(db)
        expenses.add_expense(trip.trip_id, user.user_id, {
            "expense_name": "Entry tickets", "category": "entrance_fees",
            "amount": 45.0, "currency": "USD",
            "expense_date": (today + timedelta(days=30)).isoformat(),
        })
        expenses.add_expense(trip.trip_id, user.user_id, {
            "expense_name": "Lunch", "category": "food", "amount": 18.5,
            "currency": "USD", "expense_date": (today + timedelta(days=31)).isoformat(),
        })
        print("  + added two sample expenses")

        checklists = ChecklistManager(db)
        checklist = checklists.create_checklist(trip.trip_id, user.user_id,
                                                {"checklist_name": "Packing"})
        checklists.add_item(checklist.checklist_id, user.user_id,
                            {"item_name": "Passport"})
        checklists.add_item(checklist.checklist_id, user.user_id,
                            {"item_name": "Travel insurance"})
        print("  + created a checklist with two items")

    db.close()
    print("\nSign in with:")
    print(f"  email    : {args.email}")
    print(f"  password : {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())