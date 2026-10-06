"""Initialise the Wize SQLite database.

Usage:
    python scripts/init_db.py              # create database/wize.db
    python scripts/init_db.py --reset      # drop everything first (destructive)
    python scripts/init_db.py --seed       # also load the destination catalogue

The script can be run independently of the Flask application: it only needs
the schema file and the standard library sqlite3 module.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DATABASE_PATH, SCHEMA_PATH          # noqa: E402
from database.db import DatabaseManager                # noqa: E402
from scripts.seed_destinations import main as seed_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the Wize database.")
    parser.add_argument("--db", default=str(DATABASE_PATH), help="Target SQLite file.")
    parser.add_argument("--schema", default=str(SCHEMA_PATH), help="Path to schema.sql.")
    parser.add_argument("--reset", action="store_true",
                        help="Drop all tables before creating them.")
    parser.add_argument("--seed", action="store_true",
                        help="Also seed the Asian destination catalogue.")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    db = DatabaseManager(db_path, Path(args.schema))
    db.get_connection()                     # creates the file
    if args.reset:
        db.drop_tables()
        print(f"Dropped all existing tables in {db_path}")
    db.create_tables()
    tables = db.table_names()
    db.close()                              # standalone connection (no Flask ctx)

    print("Database initialised successfully.")
    print(f"  File   : {db_path}")
    print(f"  Tables : {len(tables)} -> {', '.join(tables)}")

    if args.seed:
        print("\nSeeding destinations ...")
        return seed_main(["--db", str(db_path)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())