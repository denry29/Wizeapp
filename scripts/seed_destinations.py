"""Seed the destination catalogue from data/asia_destinations.json.

Usage (from the project root):
    python scripts/seed_destinations.py                 # seed the main database
    python scripts/seed_destinations.py --db path.db   # seed another database
    python scripts/seed_destinations.py --check         # validate only, no writes
    python scripts/seed_destinations.py --min 300       # require N records

What the script guarantees
-------------------------
1. It loads and validates every record from the JSON file.
2. It refuses to invent rows - anything invalid is reported, never inserted.
3. It detects duplicates inside the file (normalised name + country + city).
4. It is idempotent: rows that already exist are skipped, so running it
   twice inserts nothing new.
5. It prints valid / inserted / skipped / rejected counts.
6. It verifies the listed shared catalogue contains exactly the required 300.

Exit code is 0 on success and 1 when the minimum is not met, so the script
can be used as a check in CI or a Makefile.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Allow running as `python scripts/seed_destinations.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DATASET_PATH, MIN_DESTINATIONS  # noqa: E402
from database.db import DatabaseManager  # noqa: E402
from models.destination import normalise_name  # noqa: E402

CATEGORY_ALLOWLIST = {
    "beach", "mountain", "historical_site", "temple", "museum", "cultural",
    "park", "natural_landmark", "architectural_landmark", "theme_park",
    "island", "lake", "waterfall", "market", "other",
}

INSERT_SQL = """
INSERT INTO destinations
    (name, name_key, country, city, category, description, image_url,
     estimated_entrance_fee, currency, is_custom, user_id, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, datetime('now'))
"""


class SeedReport:
    """Collects counters and problems so the summary is printed at the end."""

    def __init__(self) -> None:
        self.total_in_file = 0
        self.valid: list[dict] = []
        self.rejected: list[tuple[int, str, str]] = []   # index, name, reason
        self.duplicates: list[tuple[int, str, str]] = []
        self.inserted = 0
        self.skipped = 0

    def summary(self) -> str:
        return (f"Records in file : {self.total_in_file}\n"
                f"Valid records    : {len(self.valid)}\n"
                f"Inserted         : {self.inserted}\n"
                f"Already present  : {self.skipped}\n"
                f"Duplicate rows   : {len(self.duplicates)}\n"
                f"Rejected         : {len(self.rejected)}")


def validate_record(record: object, index: int) -> tuple[dict | None, str | None]:
    """Validate one dataset record. Returns ``(data, error_message)``."""
    if not isinstance(record, dict):
        return None, "record is not a JSON object"

    name = str(record.get("name") or "").strip()
    country = str(record.get("country") or "").strip()
    city = (str(record["city"]).strip() if record.get("city") else None)
    category = str(record.get("category") or "").strip()
    description = (str(record["description"]).strip()
                   if record.get("description") else None)

    if len(name) < 2:
        return None, "name is missing or too short"
    if not country:
        return None, "country is missing"
    if not city:
        return None, "city/locality is missing"
    if category not in CATEGORY_ALLOWLIST:
        return None, f"unknown category '{category}'"
    if not description or len(description) < 10:
        return None, "description is missing or too short"

    fee = record.get("estimated_entrance_fee")
    if fee is not None:
        try:
            fee = float(fee)
            if fee < 0:
                return None, "estimated_entrance_fee cannot be negative"
        except (TypeError, ValueError):
            return None, "estimated_entrance_fee is not a number"

    currency = record.get("currency")
    if currency is not None:
        currency = str(currency).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return None, f"currency '{currency}' is not a 3-letter code"

    image_url = record.get("image_url")
    if image_url is not None:
        image_url = str(image_url).strip()
        if image_url and not image_url.startswith("https://"):
            return None, "image_url must use HTTPS"
        image_url = image_url.replace(
            "https://thumb.wikimedia.org/",
            "https://upload.wikimedia.org/",
            1,
        )
        if image_url and urlsplit(image_url).hostname != "upload.wikimedia.org":
            return None, "image_url must be served by Wikimedia"
    elif country.casefold() != "philippines":
        return None, "destination needs a usable photo (except Philippine destinations)"

    image_fields = {
        "image_title": str(record.get("image_title") or "").strip(),
        "image_creator": str(record.get("image_creator") or "").strip(),
        "image_source_url": str(record.get("image_source_url") or "").strip(),
        "image_license": str(record.get("image_license") or "").strip(),
        "image_license_url": str(record.get("image_license_url") or "").strip(),
        "image_attribution": str(record.get("image_attribution") or "").strip(),
    }
    if image_url and not all(image_fields.values()):
        return None, "photo requires complete source, creator and licence attribution"
    if image_url and not image_fields["image_source_url"].startswith("https://"):
        return None, "image_source_url must use HTTPS"
    if image_url and not image_fields["image_license_url"].startswith("https://"):
        return None, "image_license_url must use HTTPS"

    latitude = record.get("latitude")
    longitude = record.get("longitude")
    try:
        latitude = float(latitude) if latitude is not None else None
        longitude = float(longitude) if longitude is not None else None
    except (TypeError, ValueError):
        return None, "coordinates must be numeric"
    if latitude is not None and not -90 <= latitude <= 90:
        return None, "latitude must be between -90 and 90"
    if longitude is not None and not -180 <= longitude <= 180:
        return None, "longitude must be between -180 and 180"

    return {
        "name": name,
        "name_key": normalise_name(name),
        "country": country,
        "city": city,
        "category": category,
        "description": description,
        "image_url": image_url or None,
        "estimated_entrance_fee": fee,
        "currency": currency,
        **image_fields,
        "best_time_to_visit": (str(record["best_time_to_visit"]).strip()
                               if record.get("best_time_to_visit") else None),
        "recommended_duration": (str(record["recommended_duration"]).strip()
                                 if record.get("recommended_duration") else None),
        "latitude": latitude,
        "longitude": longitude,
    }, None


def load_dataset(path: Path) -> list:
    """Read the JSON dataset with a helpful error message if it is broken."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Dataset must be a JSON array of destination objects.")
    return data
def seed_database(db: DatabaseManager, records: list[dict]) -> int:
    """Publish exactly the curated set while retaining legacy trip references."""
    inserted = 0
    db.execute("UPDATE destinations SET is_listed = 0 WHERE is_custom = 0")
    for record in records:
        existing = db.query_one(
            "SELECT destination_id FROM destinations WHERE is_custom = 0 "
            "AND name_key = ? AND country = ? COLLATE NOCASE AND city IS ?",
            [record["name_key"], record["country"], record["city"]])
        if existing is not None:
            destination_id = existing["destination_id"]
        else:
            cursor = db.execute(INSERT_SQL, [
                record["name"], record["name_key"], record["country"], record["city"],
                record["category"], record["description"], record["image_url"],
                record["estimated_entrance_fee"], record["currency"],
            ])
            destination_id = cursor.lastrowid
            inserted += 1
        db.execute(
            """
            UPDATE destinations
               SET is_listed = 1, image_url = ?,
                   image_title = ?, image_creator = ?, image_source_url = ?,
                   image_license = ?, image_license_url = ?, image_attribution = ?,
                   best_time_to_visit = ?, recommended_duration = ?,
                   latitude = ?, longitude = ?
             WHERE destination_id = ? AND is_custom = 0
            """,
            [record["image_url"], record["image_title"], record["image_creator"],
             record["image_source_url"], record["image_license"],
             record["image_license_url"], record["image_attribution"],
             record["best_time_to_visit"], record["recommended_duration"],
             record["latitude"], record["longitude"], destination_id])
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the Asian destination catalogue.")
    parser.add_argument("--db", default=None,
                        help="Path to the SQLite file (defaults to the main database).")
    parser.add_argument("--dataset", default=str(DATASET_PATH),
                        help="Path to the JSON dataset.")
    parser.add_argument("--min", type=int, default=MIN_DESTINATIONS,
                        help=f"Minimum unique destinations required "
                             f"(default {MIN_DESTINATIONS}).")
    parser.add_argument("--exact", type=int, default=MIN_DESTINATIONS,
                        help=f"Require exactly N records (default {MIN_DESTINATIONS}).")
    parser.add_argument("--check", action="store_true",
                        help="Validate the dataset only; do not write to the database.")
    args = parser.parse_args(argv)

    # ---------------------------------------------------- 1. load + validate
    try:
        raw_records = load_dataset(Path(args.dataset))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1

    report = SeedReport()
    report.total_in_file = len(raw_records)
    seen: dict[tuple, int] = {}

    for index, record in enumerate(raw_records, start=1):
        data, error = validate_record(record, index)
        if error:
            report.rejected.append((index, str(record.get("name", "?")), error))
            continue
        key = (data["name_key"], data["country"].lower(), (data["city"] or "").lower())
        if key in seen:                                # duplicate inside the file
            report.duplicates.append((index, data["name"], f"same as entry #{seen[key]}"))
            continue
        seen[key] = index
        report.valid.append(data)

    print("=" * 66)
    print("Wize - destination seeding report")
    print("=" * 66)
    for index, name, reason in report.rejected:
        print(f"  REJECTED  entry #{index} '{name}': {reason}")
    for index, name, reason in report.duplicates:
        print(f"  DUPLICATE entry #{index} '{name}': {reason}")
    if not report.rejected and not report.duplicates:
        print("  All records passed validation; no duplicates found.")
    print("-" * 66)

    if len(report.valid) != args.exact:
        print(f"FAILED: exactly {args.exact} valid destinations are required, "
              f"but {len(report.valid)} were verified.")
        return 1

    # ------------------------------------------- 2. insert missing records --
    if args.check:
        print("Check-only mode: the database was not modified.")
        in_db = 0
    else:
        db_path = Path(args.db) if args.db else PROJECT_ROOT / "database" / "wize.db"
        db = DatabaseManager(db_path, PROJECT_ROOT / "database" / "schema.sql")
        db.get_connection()                           # create the file if missing
        db.create_tables()                            # safe to call repeatedly
        report.inserted = seed_database(db, report.valid)
        report.skipped = len(report.valid) - report.inserted
        in_db = int(db.scalar(
            "SELECT COUNT(*) FROM destinations "
            "WHERE is_custom = 0 AND is_listed = 1"))
        db.close()
        print(f"  Database : {db_path}")
        print(f"  Catalogue rows in database: {in_db}")
        if in_db != args.exact:
            print(f"FAILED: expected exactly {args.exact} listed catalogue rows, "
                  f"found {in_db}.")
            return 1

    print("-" * 66)
    print(report.summary())
    print("-" * 66)

    # ------------------------------------------------------ 3. verify count --
    unique_valid = len(report.valid)
    print(f"Unique valid destinations in dataset : {unique_valid}")
    if unique_valid < args.min:
        print(f"FAILED: the dataset must contain at least {args.min} valid destinations, "
              f"but only {unique_valid} are verified.")
        print("No placeholder records were generated - please add real entries.")
        return 1
    if report.rejected or report.duplicates:
        print(f"NOTE: {len(report.rejected)} record(s) rejected and "
              f"{len(report.duplicates)} duplicate(s) skipped.")
    print(f"SUCCESS: exactly {args.exact} unique Asian destinations verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())