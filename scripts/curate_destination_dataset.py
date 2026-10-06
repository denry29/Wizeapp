"""Build the 300-record catalogue from the project's attributed photo library.

Run from the project root after the destination image fetcher has populated
``database/wize.db``:

    python scripts/curate_destination_dataset.py

The script only writes destinations with an HTTPS image, an attribution, and
a reusable licence. It balances the resulting catalogue across countries.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "database" / "wize.db"
DATASET_PATH = PROJECT_ROOT / "data" / "asia_destinations.json"
TARGET_COUNT = 300
ATTRIBUTION_FIELDS = (
    "image_title", "image_creator", "image_source_url", "image_license",
    "image_license_url", "image_attribution",
)


def build_dataset() -> list[dict]:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Image catalogue database not found: {DATABASE_PATH}")
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM destinations WHERE is_custom = 0 "
            "AND image_url IS NOT NULL AND trim(image_url) <> ''"
        ).fetchall()
    finally:
        connection.close()

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not all(row[field] for field in ATTRIBUTION_FIELDS):
            continue
        if not row["image_url"].startswith("https://"):
            continue
        if not any(term in row["image_license"].casefold()
                   for term in ("cc", "public domain", "pd-", "attribution",
                                "gfdl", "no restrictions")):
            continue
        record = {
            field: row[field]
            for field in ("name", "country", "city", "category", "description",
                          "estimated_entrance_fee", "currency")
        }
        record.update({
            "image_url": row["image_url"].replace(
                "https://thumb.wikimedia.org/",
                "https://upload.wikimedia.org/",
                1,
            ),
            "image_title": row["image_title"],
            "image_creator": row["image_creator"],
            "image_source_url": row["image_source_url"],
            "image_license": row["image_license"],
            "image_license_url": row["image_license_url"].replace(
                "http://creativecommons.org/", "https://creativecommons.org/"
            ).replace("http://www.gnu.org/", "https://www.gnu.org/"),
            "image_attribution": row["image_attribution"],
            "best_time_to_visit": None,
            "recommended_duration": None,
            "latitude": None,
            "longitude": None,
        })
        groups[row["country"]].append(record)

    for entries in groups.values():
        entries.sort(key=lambda item: item["name"].casefold())
    selected: list[dict] = []
    while len(selected) < TARGET_COUNT:
        added = False
        for country in sorted(groups):
            if groups[country]:
                selected.append(groups[country].pop(0))
                added = True
                if len(selected) == TARGET_COUNT:
                    break
        if not added:
            raise ValueError(
                f"Only {len(selected)} fully attributed destinations have photos; "
                f"{TARGET_COUNT} are required."
            )
    return selected


def main() -> int:
    records = build_dataset()
    temporary_path = DATASET_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(DATASET_PATH)
    print(f"Wrote {len(records)} photo-backed, attributed destinations to "
          f"{DATASET_PATH}")
    print(f"Countries represented: {len({item['country'] for item in records})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
