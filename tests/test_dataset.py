"""Dataset integrity tests: the 300-destination requirement.

These tests read the real ``data/asia_destinations.json`` file and run the
seeder against a temporary database, so the main database is never touched.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from config import DATASET_PATH, MIN_DESTINATIONS
from models.destination import normalise_name
from scripts import seed_destinations

REQUIRED_KEYS = {"name", "country", "city", "category", "description",
                 "image_url", "estimated_entrance_fee", "currency"}


@pytest.fixture(scope="module")
def raw_records():
    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def validated(raw_records):
    """Every record that passes the seeder's own validation."""
    return [seed_destinations.validate_record(record, index)[0]
            for index, record in enumerate(raw_records, start=1)
            if seed_destinations.validate_record(record, index)[1] is None]


# ------------------------------------------------------------- file shape --
def test_dataset_is_a_json_array(raw_records):
    assert isinstance(raw_records, list)
    assert len(raw_records) == MIN_DESTINATIONS


def test_every_record_has_the_expected_keys(raw_records):
    for record in raw_records:
        assert REQUIRED_KEYS.issubset(record.keys()), record


def test_all_records_pass_validation(raw_records):
    problems = [seed_destinations.validate_record(record, index)[1]
                for index, record in enumerate(raw_records, start=1)]
    problems = [p for p in problems if p is not None]
    assert problems == [], f"invalid records: {problems[:5]}"


# --------------------------------------------------------- data quality ---
def test_no_duplicate_attractions(validated):
    keys = [(r["name_key"], r["country"].lower(), r["city"].lower()) for r in validated]
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert duplicates == set(), f"duplicate attractions: {duplicates}"


def test_alternate_spellings_are_detected_as_duplicates():
    """The normaliser collapses spelling variants to the same key."""
    assert normalise_name("Kinkaku-ji") == normalise_name("Kinkaku Ji")
    assert normalise_name("Hōkoku Shrine") == normalise_name("Hokoku Shrine")
    assert normalise_name("Angkor Wat") == normalise_name(" angkor   wat ")


def test_multiple_countries_are_present(validated):
    countries = {r["country"] for r in validated}
    assert len(countries) >= 10, countries


def test_category_variety(validated):
    categories = {r["category"] for r in validated}
    assert len(categories) >= 8, categories


def test_every_destination_has_a_description(validated):
    assert all(len(r["description"]) >= 10 for r in validated)


def test_destination_photos_use_absolute_https_urls_when_present(validated):
    for destination in validated:
        image_url = destination["image_url"]
        if image_url is None:
            continue
        parsed = urlsplit(image_url)
        assert parsed.scheme == "https", destination["name"]
        assert parsed.hostname == "upload.wikimedia.org", destination["name"]


def test_destination_photos_link_to_wikimedia_commons(validated):
    for destination in validated:
        if destination["image_url"] is not None:
            assert urlsplit(destination["image_source_url"]).hostname == \
                "commons.wikimedia.org", destination["name"]


def test_non_philippine_destinations_have_attributed_photos(validated):
    required = ("image_url", "image_title", "image_creator", "image_source_url",
                "image_license", "image_license_url", "image_attribution")
    for destination in validated:
        if destination["country"] != "Philippines":
            assert all(destination[field] for field in required), destination["name"]
            assert destination["image_url"].startswith("https://")


def test_photo_less_philippine_destination_is_allowed(raw_records):
    record = deepcopy(next(row for row in raw_records
                           if row["country"] == "Philippines"))
    for key in ("image_url", "image_title", "image_creator",
                "image_source_url", "image_license", "image_license_url",
                "image_attribution"):
        record.pop(key, None)
    validated_record, error = seed_destinations.validate_record(record, 1)
    assert error is None
    assert validated_record["image_url"] is None


def test_photo_less_non_philippine_destination_is_rejected(raw_records):
    record = deepcopy(next(row for row in raw_records
                           if row["country"] != "Philippines"))
    for key in ("image_url", "image_title", "image_creator",
                "image_source_url", "image_license", "image_license_url",
                "image_attribution"):
        record.pop(key, None)
    validated_record, error = seed_destinations.validate_record(record, 1)
    assert validated_record is None
    assert error == "destination needs a usable photo (except Philippine destinations)"


def test_exactly_300_unique_destinations(validated):
    assert len(validated) == MIN_DESTINATIONS


# ------------------------------------------------------------- the seeder --
def test_seeder_is_idempotent(tmp_path, raw_records):
    """Running the seeder twice must not create duplicates."""
    database = tmp_path / "seed_test.db"
    assert seed_destinations.main(
        ["--db", str(database), "--dataset", str(DATASET_PATH)]) == 0
    first = _catalogue_count(database)
    assert first == MIN_DESTINATIONS

    assert seed_destinations.main(
        ["--db", str(database), "--dataset", str(DATASET_PATH)]) == 0
    assert _catalogue_count(database) == first


def test_seeder_check_mode_does_not_write(tmp_path):
    database = tmp_path / "check_only.db"
    result = seed_destinations.main(
        ["--db", str(database), "--check", "--dataset", str(DATASET_PATH)])
    assert result == 0
    assert not database.exists()


def test_seeder_fails_when_minimum_not_reached(tmp_path):
    result = seed_destinations.main(
        ["--db", str(tmp_path / "x.db"), "--min", "100000",
         "--dataset", str(DATASET_PATH)])
    assert result == 1


def test_seeded_rows_are_asia_only(tmp_path):
    """Every seeded country must be in the known Asian country list."""
    database = tmp_path / "asia.db"
    seed_destinations.main(["--db", str(database), "--dataset", str(DATASET_PATH)])
    connection = sqlite3.connect(database)
    try:
        countries = [row[0] for row in
                     connection.execute("SELECT DISTINCT country FROM destinations")]
    finally:
        connection.close()
    assert set(countries) <= ASIAN_COUNTRIES, set(countries) - ASIAN_COUNTRIES


def _catalogue_count(database: Path) -> int:
    connection = sqlite3.connect(database)
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM destinations "
            "WHERE is_custom = 0 AND is_listed = 1").fetchone()[0]
    finally:
        connection.close()


#: Use this list to check that the dataset only includes Asian countries.
ASIAN_COUNTRIES = {
    "Bangladesh", "Bahrain", "Bhutan", "Cambodia", "China", "Hong Kong",
    "India", "Indonesia", "Iran", "Iraq", "Israel", "Japan", "Jordan",
    "Kazakhstan", "Kuwait", "Kyrgyzstan", "Laos", "Lebanon", "Macau",
    "Malaysia", "Maldives", "Mongolia", "Myanmar", "Nepal", "Oman",
    "Pakistan", "Philippines", "Qatar", "Saudi Arabia", "Singapore",
    "South Korea", "Sri Lanka", "Taiwan", "Tajikistan", "Thailand",
    "Turkey", "United Arab Emirates", "Uzbekistan", "Vietnam",
}