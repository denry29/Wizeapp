"""Database connection management for Wize.

`DatabaseManager` encapsulates every interaction with SQLite so that no other
layer has to know how connections are opened, committed or closed.  It follows
the application factory pattern: one instance per Flask application, stored on
``app.extensions`` and reused through the request-scoped ``flask.g``.

All queries executed through this class are parameterised (``?`` placeholders).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

import click
from flask import Flask, current_app, g, has_app_context


class DatabaseManager:
    """Owns the SQLite connection lifecycle (encapsulation)."""

    def __init__(self, database_path: str | Path, schema_path: str | Path | None = None):
        self.database_path = Path(database_path)
        self.schema_path = Path(schema_path) if schema_path else None
        self._initialised = False
        self._standalone: sqlite3.Connection | None = None

    # ----------------------------------------------------------- lifecycle --
    def init_app(self, app: Flask) -> None:
        """Register the connection handlers on a Flask application."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        app.teardown_appcontext(self.close_connection)
        app.extensions["wize_db"] = self
        if self.schema_path and not self._initialised:
            # The connection lives on flask.g, so create it inside an app context.
            with app.app_context():
                self.create_tables()

    def get_connection(self) -> sqlite3.Connection:
        """Return the connection for the active request/app context.

        Falls back to a standalone connection when there is no Flask context
        (for example when a management script runs outside the web app).
        """
        if not has_app_context():
            if self._standalone is None:
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
                self._standalone = self._connect()
            return self._standalone
        if "db_connection" not in g:
            g.db_connection = self._connect()
        return g.db_connection

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=15,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")     # FK enforcement
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def close_connection(self, _exception: BaseException | None = None) -> None:
        connection = g.pop("db_connection", None)
        if connection is not None:
            connection.close()

    def close(self) -> None:
        """Close the standalone connection used outside a Flask context."""
        if self._standalone is not None:
            self._standalone.close()
            self._standalone = None

    # ------------------------------------------------------------ queries --
    def execute(self, query: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run a write statement and commit it."""
        connection = self.get_connection()
        cursor = connection.execute(query, tuple(params))
        connection.commit()
        return cursor

    def execute_many(self, query: str, seq_of_params: Iterable[Sequence[Any]]) -> None:
        connection = self.get_connection()
        connection.executemany(query, [tuple(p) for p in seq_of_params])
        connection.commit()

    def executemany_no_commit(self, query: str, seq_of_params: Iterable[Sequence[Any]]) -> sqlite3.Cursor:
        """Bulk insert used by the seeder (single transaction for speed)."""
        connection = self.get_connection()
        return connection.executemany(query, [tuple(p) for p in seq_of_params])

    def commit(self) -> None:
        self.get_connection().commit()

    def rollback(self) -> None:
        self.get_connection().rollback()

    def query_all(self, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.get_connection().execute(query, tuple(params)).fetchall()

    def query_one(self, query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.get_connection().execute(query, tuple(params)).fetchone()

    def scalar(self, query: str, params: Sequence[Any] = (), default: Any = 0) -> Any:
        row = self.query_one(query, params)
        return row[0] if row is not None and row[0] is not None else default
# ------------------------------------------------------------ schema --
    #: These Wikimedia photo-credit columns are also added to older databases
    #: here; see schema.sql for why a plain ALTER TABLE isn't enough.
    IMAGE_COLUMNS = ("image_title", "image_creator", "image_source_url",
                     "image_license", "image_license_url", "image_attribution")
    OPTIONAL_COLUMNS = {
        "destinations": {
            "is_listed": "INTEGER NOT NULL DEFAULT 1",
            "best_time_to_visit": "TEXT",
            "recommended_duration": "TEXT",
            "latitude": "REAL",
            "longitude": "REAL",
        },
        "expenses": {
            "expense_kind": "TEXT NOT NULL DEFAULT 'actual'",
            "source_option_id": (
                "INTEGER REFERENCES saved_options(option_id) ON DELETE CASCADE"
            ),
        },
        "users": {
            # Older local accounts didn't use email verification, so keep them
            # active. New accounts get an explicit unverified value instead.
            "email_verified": "INTEGER NOT NULL DEFAULT 1",
            "email_verified_at": "TEXT",
            "last_login_at": "TEXT",
        },
    }

    def create_tables(self) -> None:
        """Execute schema.sql (idempotent thanks to IF NOT EXISTS)."""
        if not self.schema_path or not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")
        connection = self.get_connection()
        connection.executescript(self.schema_path.read_text(encoding="utf-8"))
        self._ensure_image_columns(connection)
        self._ensure_optional_columns(connection)
        self._ensure_flight_hotel_expense_categories(connection)
        connection.commit()
        self._initialised = True

    def _ensure_image_columns(self, connection: sqlite3.Connection) -> None:
        """Add any missing image-attribution column to ``destinations``.

        ``PRAGMA table_info`` is consulted first so re-running this is a no-op;
        a bare ``ALTER TABLE ... ADD COLUMN`` would raise "duplicate column
        name" the second time, which would break ``create_tables``.
        """
        existing = {row["name"] for row in connection.execute(
            "PRAGMA table_info(destinations)")}
        if not existing:
            return                      # no destinations table yet - nothing to do
        for column in self.IMAGE_COLUMNS:
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE destinations ADD COLUMN {column} TEXT")

    def _ensure_optional_columns(self, connection: sqlite3.Connection) -> None:
        """Upgrade existing user databases without dropping their records."""
        for table, columns in self.OPTIONAL_COLUMNS.items():
            existing = {row["name"] for row in connection.execute(
                f"PRAGMA table_info({table})")}
            if not existing:
                continue
            for column, declaration in columns.items():
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _ensure_flight_hotel_expense_categories(
            connection: sqlite3.Connection) -> None:
        """Extend the expense CHECK constraint without losing existing rows."""
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name = 'expenses'").fetchone()
        schema = row["sql"] if row is not None else ""
        if "'flights'" in schema and "'hotels'" in schema:
            return

        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                CREATE TABLE expenses_with_travel_categories (
                    expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER NOT NULL,
                    expense_name TEXT NOT NULL CHECK (
                        length(trim(expense_name)) BETWEEN 2 AND 120),
                    category TEXT NOT NULL CHECK (category IN (
                        'flights','hotels','food','transportation',
                        'accommodation','entrance_fees','shopping',
                        'activities','other')),
                    amount REAL NOT NULL CHECK (amount > 0),
                    expense_kind TEXT NOT NULL DEFAULT 'actual'
                        CHECK (expense_kind IN ('planned','actual')),
                    source_option_id INTEGER REFERENCES saved_options(option_id)
                        ON DELETE CASCADE,
                    currency TEXT NOT NULL DEFAULT 'USD'
                        CHECK (length(currency) = 3),
                    expense_date TEXT NOT NULL CHECK (length(expense_date) = 10),
                    notes TEXT,
                    FOREIGN KEY (trip_id) REFERENCES trips (trip_id)
                        ON DELETE CASCADE
                )
                """)
            connection.execute(
                """
                INSERT INTO expenses_with_travel_categories (
                    expense_id, trip_id, expense_name, category, amount,
                    expense_kind, source_option_id, currency, expense_date, notes)
                SELECT expense_id, trip_id, expense_name, category, amount,
                       expense_kind, source_option_id, currency, expense_date, notes
                FROM expenses
                """)
            connection.execute("DROP TABLE expenses")
            connection.execute(
                "ALTER TABLE expenses_with_travel_categories RENAME TO expenses")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_exp_trip ON expenses (trip_id)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_exp_cat "
                "ON expenses (trip_id, category)")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def drop_tables(self) -> None:
        """Delete every Wize table - used by tests/CLI only."""
        connection = self.get_connection()
        connection.executescript(
            """
            PRAGMA foreign_keys = OFF;
            DROP TABLE IF EXISTS destination_images;
            DROP TABLE IF EXISTS favorites;
            DROP TABLE IF EXISTS trip_notes;
            DROP TABLE IF EXISTS saved_options;
            DROP TABLE IF EXISTS checklist_items;
            DROP TABLE IF EXISTS checklists;
            DROP TABLE IF EXISTS expenses;
            DROP TABLE IF EXISTS schedules;
            DROP TABLE IF EXISTS trip_destinations;
            DROP TABLE IF EXISTS destinations;
            DROP TABLE IF EXISTS trips;
            DROP TABLE IF EXISTS users;
            PRAGMA foreign_keys = ON;
            """
        )
        connection.commit()

    def table_names(self) -> list[str]:
        rows = self.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in rows]


def get_db() -> DatabaseManager:
    """Shortcut used by blueprints: fetch the shared DatabaseManager."""
    return current_app.extensions["wize_db"]


def register_cli(app: Flask) -> None:
    """Provide `flask init-db` and `flask reset-db` commands."""

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create the database file and all tables if they do not exist."""
        manager: DatabaseManager = app.extensions["wize_db"]
        manager.create_tables()
        click.echo(f"Database ready at {manager.database_path}")
        click.echo(f"Tables: {', '.join(manager.table_names())}")

    @app.cli.command("reset-db")
    def reset_db_command() -> None:
        """Drop every table (destructive - development helper only)."""
        manager: DatabaseManager = app.extensions["wize_db"]
        manager.drop_tables()
        manager.create_tables()
        click.echo("Database reset complete.")