"""Database integrity, cascade behaviour and dashboard tests."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from database.db import DatabaseManager
from models.destination import CustomDestination, Destination
from tests.conftest import login, register, switch_user, trip_payload

JSON = {"Accept": "application/json"}
EXPECTED_TABLES = {"users", "trips", "destinations", "trip_destinations",
                   "schedules", "expenses", "checklists", "checklist_items"}


def make_trip(client, **overrides) -> int:
    response = client.post("/api/trips", json=dict(trip_payload(), **overrides),
                           headers=JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]["trip_id"]


# ----------------------------------------------------------- schema shape --
def test_all_tables_are_created(app, db):
    with app.app_context():
        assert EXPECTED_TABLES.issubset(set(db.table_names()))


def test_old_expense_check_constraint_migrates_without_losing_rows(app, db):
    with app.app_context():
        connection = db.get_connection()
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE expenses")
        connection.execute(
            """
            CREATE TABLE expenses (
                expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                expense_name TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN (
                    'food','transportation','accommodation','entrance_fees',
                    'shopping','activities','other')),
                amount REAL NOT NULL CHECK (amount > 0),
                expense_kind TEXT NOT NULL DEFAULT 'actual',
                source_option_id INTEGER REFERENCES saved_options(option_id)
                    ON DELETE CASCADE,
                currency TEXT NOT NULL DEFAULT 'USD',
                expense_date TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips (trip_id) ON DELETE CASCADE
            )
            """)
        connection.execute("PRAGMA foreign_keys = ON")
        db.execute(
            "INSERT INTO users (full_name, email, password_hash) "
            "VALUES (?, ?, ?)", ["Legacy owner", "legacy@wize.local", "hash"])
        user_id = db.scalar(
            "SELECT user_id FROM users WHERE email = ?", ["legacy@wize.local"])
        db.execute(
            "INSERT INTO trips (user_id, trip_name, start_date, end_date) "
            "VALUES (?, ?, ?, ?)",
            [user_id, "Legacy trip", "2030-01-01", "2030-01-05"])
        trip_id = db.scalar("SELECT trip_id FROM trips WHERE user_id = ?", [user_id])
        expense_date = "2030-01-02"
        db.execute(
            "INSERT INTO expenses (trip_id, expense_name, category, amount, "
            "currency, expense_date) VALUES (?, ?, ?, ?, ?, ?)",
            [trip_id, "Old transit ticket", "transportation", 25, "PHP",
             expense_date])

        db.create_tables()

        preserved = db.query_one(
            "SELECT * FROM expenses WHERE expense_name = ?",
            ["Old transit ticket"])
        assert preserved["category"] == "transportation"
        assert preserved["amount"] == 25
        db.execute(
            "INSERT INTO expenses (trip_id, expense_name, category, amount, "
            "currency, expense_date) VALUES (?, ?, ?, ?, ?, ?)",
            [trip_id, "New hotel", "hotels", 1200, "PHP", expense_date])
        assert db.scalar(
            "SELECT COUNT(*) FROM expenses WHERE category = 'hotels'") == 1


def test_foreign_keys_are_enforced(app, db):
    with app.app_context():
        assert db.scalar("PRAGMA foreign_keys") == 1


def test_foreign_key_violation_is_rejected(app, db):
    """A schedule without a real trip must be refused by SQLite."""
    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO schedules (trip_id, activity_name, activity_date) "
                "VALUES (?, ?, ?)", [999999, "Orphan", date.today().isoformat()])


def test_email_unique_constraint(app, db):
    with app.app_context():
        db.execute("INSERT INTO users (full_name, email, password_hash) "
                   "VALUES (?, ?, ?)", ["Alice", "dup@x.com", "h"])
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO users (full_name, email, password_hash) "
                       "VALUES (?, ?, ?)", ["Bob", "dup@x.com", "h"])


def test_invalid_status_is_blocked_by_check_constraint(app, db):
    with app.app_context():
        db.execute("INSERT INTO users (full_name, email, password_hash) "
                   "VALUES (?, ?, ?)", ["Carol", "chk@x.com", "h"])
        user_id = db.scalar("SELECT user_id FROM users WHERE email = ?", ["chk@x.com"])
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO trips (user_id, trip_name, start_date, end_date, "
                       "status) VALUES (?, ?, ?, ?, ?)",
                       [user_id, "Trip One", "2030-01-01", "2030-01-05", "nonsense"])


# ---------------------------------------------------------------- cascades --
def test_deleting_a_trip_removes_dependents(client, app, db):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses", json={
        "expense_name": "Lunch", "category": "food", "amount": 10,
        "currency": "USD"}, headers=JSON)
    client.post(f"/api/trips/{trip_id}/schedules", json={
        "activity_name": "Walk around", "activity_date": trip_payload()["start_date"],
    }, headers=JSON)

    client.delete(f"/api/trips/{trip_id}", headers=JSON)
    with app.app_context():
        assert db.scalar("SELECT COUNT(*) FROM expenses WHERE trip_id = ?",
                         [trip_id]) == 0
        assert db.scalar("SELECT COUNT(*) FROM schedules WHERE trip_id = ?",
                         [trip_id]) == 0


def test_deleting_a_user_removes_their_trips(app, db):
    with app.app_context():
        db.execute("INSERT INTO users (full_name, email, password_hash) "
                   "VALUES (?, ?, ?)", ["Del", "del@x.com", "h"])
        user_id = db.scalar("SELECT user_id FROM users WHERE email = ?", ["del@x.com"])
        db.execute("INSERT INTO trips (user_id, trip_name, start_date, end_date) "
                   "VALUES (?, ?, ?, ?)", [user_id, "Trip Two", "2030-01-01", "2030-01-05"])
        db.execute("DELETE FROM users WHERE user_id = ?", [user_id])
        assert db.scalar("SELECT COUNT(*) FROM trips WHERE user_id = ?", [user_id]) == 0
# ------------------------------------------------------ OOP / polymorphism --
def test_destination_factory_returns_custom_subclass(app, db):
    """Polymorphism: `Destination.from_row` picks the subclass from the row."""
    with app.app_context():
        db.execute("INSERT INTO users (full_name, email, password_hash) "
                   "VALUES (?, ?, ?)", ["Poly", "poly@x.com", "h"])
        user_id = db.scalar("SELECT user_id FROM users WHERE email = ?", ["poly@x.com"])
        db.execute(
            "INSERT INTO destinations (name, name_key, country, city, category, "
            "description, is_custom, user_id) "
            "VALUES ('My Spot', 'my spot', 'Japan', 'Kyoto', 'park', 'A local find.', 1, ?)",
            [user_id])
        inserted = db.query_one(
            "SELECT * FROM destinations WHERE name_key = ?", ["my spot"])
    catalogue_row = dict(inserted, is_custom=0, user_id=None)
    assert isinstance(Destination.from_row(inserted), CustomDestination)
    assert type(Destination.from_row(catalogue_row)) is Destination
    assert Destination.from_row(inserted).serialize()["origin"] == "custom"


def test_normalised_name_blocks_duplicate_destinations(app, db):
    """`name_key` makes spelling variants collide at the database level."""
    with app.app_context():
        db.execute("INSERT INTO destinations (name, name_key, country, city, category) "
                   "VALUES ('Test Shrine', 'test shrine', 'Japan', 'Nara', 'temple')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO destinations (name, name_key, country, city, "
                       "category) VALUES ('Test  Shrine', 'test shrine', 'Japan', "
                       "'Nara', 'temple')")


# ------------------------------------------------------------- dashboard ---
def test_dashboard_summary(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses", json={
        "expense_name": "Lunch", "category": "food", "amount": 20, "currency": "USD",
        "expense_date": trip_payload()["start_date"]}, headers=JSON)

    body = client.get("/api/dashboard", headers=JSON).get_json()
    assert body["trips"]["total"] == 1
    assert body["trips"]["upcoming"] == 1
    assert body["expenses"]["totals_by_currency"] == {"USD": 20.0}
    assert body["catalogue"]["total_destinations"] >= 1


def test_dashboard_shows_only_own_data(client):
    from tests.conftest import VALID_USER
    register(client)
    make_trip(client)
    switch_user(client, "other@wize.local")
    body = client.get("/api/dashboard", headers=JSON).get_json()
    assert body["trips"]["total"] == 0
    assert body["expenses"]["totals_by_currency"] == {}


def test_dashboard_html_renders(client):
    register(client)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Total trips" in response.data


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"