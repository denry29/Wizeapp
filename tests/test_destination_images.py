"""Tests for the Wikimedia Commons destination-image feature.

No test in this file touches the network: ``CommonsClient`` accepts an
``opener`` callable, and every test injects a fake that returns a canned JSON
payload (or raises a canned error).  All database work runs against
``tmp_path``, so the real ``wize.db`` is never modified.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import urllib.error
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.db import DatabaseManager                       # noqa: E402
from models.destination import normalise_name                 # noqa: E402
from scripts import fetch_destination_images as fetcher       # noqa: E402
from services import commons                                  # noqa: E402

SCHEMA = PROJECT_ROOT / "database" / "schema.sql"


# --------------------------------------------------------------- fixtures --
def _page(title: str, *, url: str | None = None,
          licence: str = "CC BY-SA 4.0",
          artist: str = "<a href='//commons.wikimedia.org/wiki/User:T'>A Photographer</a>",
          width: int = 1200, height: int = 800,
          license_url: str = "https://creativecommons.org/licenses/by-sa/4.0",
          description: str = "") -> dict:
    """One ``query.pages`` entry shaped like the real Commons response."""
    return {
        "pageid": abs(hash(title)) % 100000,
        "ns": 6,
        "title": title,
        "imageinfo": [{
            "url": url or f"https://upload.wikimedia.org/{title}",
            "thumburl": url or f"https://upload.wikimedia.org/thumb/{title}",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{title[5:]}",
            "thumbwidth": width, "thumbheight": height,
            "extmetadata": {
                "Artist": {"value": artist, "source": "commons-desc-page"},
                "LicenseShortName": {"value": licence,
                                     "source": "commons-desc-page"},
                "LicenseUrl": {"value": license_url,
                               "source": "commons-desc-page"},
                "ImageDescription": {"value": description,
                                     "source": "commons-desc-page"},
            },
        }],
    }


def _payload(*pages: dict) -> str:
    return json.dumps({"batchcomplete": "",
                       "query": {"pages": {str(p["pageid"]): p for p in pages}}})


class FakeOpener:
    """Stands in for ``urllib.request.urlopen``.

    ``responses`` maps a substring of the query to a JSON string or to an
    Exception instance to raise.  A list value is consumed one entry per call,
    which is how the retry behaviour is exercised.
    """

    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, request, timeout):                 # noqa: ANN001
        url = request.full_url
        self.calls.append(url)
        for needle, value in self.responses.items():
            if needle in url:
                if isinstance(value, list):
                    value = value.pop(0) if len(value) > 1 else value[0]
                if isinstance(value, Exception):
                    raise value
                return value
        return json.dumps({"query": {}})


def make_client(responses: dict, **kwargs) -> commons.CommonsClient:
    """A client wired to a fake opener and a no-op sleeper (tests stay fast)."""
    opener = FakeOpener(responses)
    client = commons.CommonsClient(
        opener=opener, sleeper=lambda _s: None, min_interval=0.0, **kwargs)
    client.fake = opener                                   # type: ignore[attr-defined]
    return client


@pytest.fixture()
def ledger_db(tmp_path):
    """An empty database with the Wize schema applied."""
    manager = DatabaseManager(tmp_path / "images_test.db", SCHEMA)
    manager.get_connection()
    manager.create_tables()
    yield manager
    manager.close()


def add_destination(connection, name="Fushimi Inari Taisha", city="Kyoto",
                    country="Japan", image_url=None, is_custom=0):
    """Insert one destination and return its id.

    ``connection`` is any ``DatabaseManager`` - the isolated ``ledger_db``
    fixture for unit tests, or the shared app-bound ``db`` fixture when the
    rendered page is being asserted on.  ``name``/``city`` are varied by the
    caller so the UNIQUE(name_key, country, city) constraint is respected.
    """
    connection.execute(
        "INSERT INTO destinations (name, name_key, country, city, category, "
        "description, image_url, is_custom, user_id) "
        "VALUES (?, ?, ?, ?, 'temple', 'A test attraction.', ?, ?, NULL)",
        [name, normalise_name(name), country, city, image_url, is_custom])
    return int(connection.scalar("SELECT MAX(destination_id) FROM destinations"))


# ------------------------------------------------------- text + scoring -----
def test_strip_html_removes_markup_and_unescapes():
    assert commons.strip_html(
        '<a href="//x" title="y">Basile Morin</a>') == "Basile Morin"
    assert commons.strip_html("<span>Tom &amp; Jerry</span>") == "Tom & Jerry"
    assert commons.strip_html(None) == ""
    assert commons.strip_html("") == ""


def test_build_query_uses_name_city_and_country():
    assert commons.build_query("Angkor Wat", "Siem Reap", "Cambodia") == \
        "Angkor Wat Siem Reap Cambodia"
    assert commons.build_query("Petra", None, "Jordan") == "Petra Jordan"
    # Keep the extra words in parentheses; they help find the right place.
    assert "Golden Pavilion" in commons.build_query(
        "Kinkaku-ji (Golden Pavilion)", "Kyoto", "Japan")


def test_score_is_zero_for_a_clearly_unrelated_title():
    assert commons.score_candidate("Fushimi Inari Taisha", "Kyoto", "Japan",
                                    "File:Ramen Noodles Tokyo Street.jpg") == 0.0


def test_score_rewards_name_city_and_country():
    exact = commons.score_candidate("Fushimi Inari Taisha", "Kyoto", "Japan",
                                     "File:Fushimi Inari Taisha Kyoto Japan.jpg")
    assert exact > 0.8, exact


def test_partial_overlap_scores_below_a_full_match():
    partial = commons.score_candidate("Fushimi Inari Taisha", "Kyoto", "Japan",
                                       "File:Inari Taisha Kyoto.jpg")
    exact = commons.score_candidate("Fushimi Inari Taisha", "Kyoto", "Japan",
                                     "File:Fushimi Inari Taisha Kyoto.jpg")
    assert 0.0 < partial < exact


def test_wrong_city_lowers_the_confidence():
    right = commons.score_candidate("Fushimi Inari Taisha", "Kyoto", "Japan",
                                     "File:Fushimi Inari Taisha Kyoto.jpg")
    wrong = commons.score_candidate("Fushimi Inari Taisha", "Kyoto", "Japan",
                                     "File:Fushimi Inari Taisha Osaka.jpg")
    assert wrong < right


def test_only_free_licences_are_accepted():
    assert commons._is_allowed_licence("CC BY-SA 4.0")
    assert commons._is_allowed_licence("Public domain")
    assert not commons._is_allowed_licence("Fair use")
    assert not commons._is_allowed_licence("All rights reserved")
    assert not commons._is_allowed_licence("")


def test_attribution_string_names_author_licence_and_source():
    candidate = commons.ImageCandidate(
        title="File:Kinkaku-ji.jpg", url="https://example.test/a.jpg",
        source_page_url="https://commons.wikimedia.org/wiki/File:Kinkaku-ji.jpg",
        creator="Basile Morin", license_name="CC BY-SA 4.0",
        license_url="", width=800, height=600)
    assert commons.build_attribution(candidate) == (
        "Kinkaku-ji.jpg by Basile Morin, CC BY-SA 4.0, via Wikimedia Commons")


# --------------------------------------------------------- API parsing ----
def test_search_returns_ranked_candidates():
    payload = _payload(
        _page("File:Unrelated Noodles Tokyo.jpg"),
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg", width=2000, height=1000))
    client = make_client({"Fushimi": payload})
    result = client.search("Fushimi Inari Taisha", "Kyoto", "Japan")

    assert result.ok and result.error is None
    assert result.query == "Fushimi Inari Taisha Kyoto Japan"
    # The unrelated file is dropped entirely, not merely ranked lower.
    assert len(result.candidates) == 1
    best = result.best
    assert best.title.startswith("File:Fushimi Inari Taisha")
    assert best.creator == "A Photographer"          # HTML stripped to text
    assert best.license_name == "CC BY-SA 4.0"
    assert best.source_page_url.startswith("https://commons.wikimedia.org/wiki/")


def test_search_sends_a_descriptive_user_agent():
    client = make_client({})
    seen: list[dict] = []

    def capture(request, timeout):                     # noqa: ANN001
        seen.append(dict(request.headers))
        return json.dumps({"query": {}})

    client._opener = capture
    client.search("Angkor Wat", "Siem Reap", "Cambodia")
    agent = {k.lower(): v for k, v in seen[0].items()}["user-agent"]
    assert "Wize" in agent


def test_search_reports_no_results_without_error():
    client = make_client({})                          # empty payload
    result = client.search("Nowhere Place", "Nowhere", "Nowhere")
    assert result.ok
    assert result.candidates == []
    assert result.best is None


def test_non_free_candidates_are_discarded():
    client = make_client({"Angkor": _payload(
        _page("File:Angkor Wat.jpg", licence="Fair use"))})
    assert client.search("Angkor Wat", "Siem Reap", "Cambodia").candidates == []


def test_svg_and_pdf_files_are_discarded():
    client = make_client({"Petra": _payload(_page("File:Petra map.svg"),
                                           _page("File:Petra plan.pdf"))})
    assert client.search("Petra", None, "Jordan").candidates == []


# ------------------------------------------------------- error handling ----
def test_network_failure_is_reported_not_raised():
    client = make_client({"Angkor": urllib.error.URLError("refused")}, retries=2)
    result = client.search("Angkor Wat", "Siem Reap", "Cambodia")
    assert not result.ok
    assert "network error" in result.error
    assert len(client.fake.calls) == 2                # it retried


def test_rate_limit_429_is_retried_then_reported():
    throttled = urllib.error.HTTPError("u", 429, "Too Many Requests", None, None)
    client = make_client({"Angkor": [throttled, throttled]}, retries=2)
    result = client.search("Angkor Wat", "Siem Reap", "Cambodia")
    assert not result.ok and "429" in result.error


def test_client_error_404_is_not_retried():
    missing = urllib.error.HTTPError("u", 404, "Not Found", None, None)
    client = make_client({"Angkor": missing}, retries=3)
    result = client.search("Angkor Wat", "Siem Reap", "Cambodia")
    assert not result.ok and "404" in result.error
    assert len(client.fake.calls) == 1                # permanent error


def test_transient_503_then_success_is_retried():
    unavailable = urllib.error.HTTPError("u", 503, "Unavailable", None, None)
    client = make_client({"Angkor": [unavailable,
                                     _payload(_page("File:Angkor Wat.jpg"))]},
                         retries=3)
    result = client.search("Angkor Wat", "Siem Reap", "Cambodia")
    assert result.ok and result.best is not None


def test_malformed_json_is_reported_as_an_error():
    client = make_client({"Angkor": "this is not json"}, retries=2)
    result = client.search("Angkor Wat", "Siem Reap", "Cambodia")
    assert not result.ok and "malformed JSON" in result.error


# ------------------------------------------------- writing to the database --
def test_matched_image_and_attribution_are_stored(ledger_db):
    destination_id = add_destination(ledger_db)
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.matched == 1 and report.review == 0
    row = ledger_db.query_one(
        "SELECT image_url, image_title, image_creator, image_source_url, "
        "image_license, image_license_url, image_attribution "
        "FROM destinations WHERE destination_id = ?", [destination_id])
    assert row["image_url"].startswith("https://upload.wikimedia.org/thumb/")
    assert row["image_title"] == "File:Fushimi Inari Taisha Kyoto Japan.jpg"
    assert row["image_creator"] == "A Photographer"
    assert row["image_source_url"].startswith("https://commons.wikimedia.org/")
    assert row["image_license"] == "CC BY-SA 4.0"
    assert row["image_license_url"] == \
        "https://creativecommons.org/licenses/by-sa/4.0"
    assert "via Wikimedia Commons" in row["image_attribution"]


def test_unrelated_results_leave_the_destination_untouched(ledger_db):
    destination_id = add_destination(ledger_db)
    client = make_client({"Fushimi": _payload(_page("File:Sushi Menu Tokyo.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.matched == 0
    row = ledger_db.query_one("SELECT image_url, image_title FROM destinations "
                       "WHERE destination_id = ?", [destination_id])
    assert row["image_url"] is None      # placeholder stays visible
    assert row["image_title"] is None


def test_low_confidence_match_goes_to_review_not_the_image(ledger_db):
    destination_id = add_destination(ledger_db, name="Petra", city=None, country="Jordan")
    client = make_client({"Petra": _payload(_page("File:Petra Treasury.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.review == 1 and report.matched == 0
    assert ledger_db.query_one("SELECT image_url FROM destinations "
                        "WHERE destination_id = ?",
                        [destination_id])["image_url"] is None
    ledger = ledger_db.query_one("SELECT status, confidence FROM destination_images "
                          "WHERE destination_id = ?", [destination_id])
    assert ledger["status"] == "review"
    assert 0 < ledger["confidence"] < fetcher.DEFAULT_MIN_SCORE


def test_existing_image_is_never_overwritten(ledger_db):
    existing = "https://example.test/hand-picked.jpg"
    destination_id = add_destination(ledger_db, image_url=existing)
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.skipped_has_image == 1 and report.matched == 0
    assert ledger_db.query_one("SELECT image_url FROM destinations "
                        "WHERE destination_id = ?",
                        [destination_id])["image_url"] == existing
    assert client.fake.calls == []        # not even searched


def test_placeholder_image_url_is_treated_as_no_image(ledger_db):
    destination_id = add_destination(ledger_db, image_url="placeholder")
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.matched == 1
    assert ledger_db.query_one("SELECT image_url FROM destinations "
                        "WHERE destination_id = ?",
                        [destination_id])["image_url"].startswith("https://")


def test_duplicate_images_are_avoided(ledger_db):
    """Two destinations must never end up sharing one Commons file.

    The second row is in a different city so the UNIQUE(name_key, country,
    city) constraint is satisfied.  Because the available file titles name
    "Kyoto" rather than "Osaka", the second row legitimately falls short of
    the confidence threshold and is sent to review instead of being given a
    duplicate image - which is exactly the behaviour being asserted here.
    """
    first = add_destination(ledger_db, name="Fushimi Inari Taisha", city="Kyoto")
    second = add_destination(ledger_db, name="Fushimi Inari Taisha", city="Osaka")
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"),
        _page("File:Fushimi Inari Gates Kyoto Japan.jpg"))})

    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.matched == 1
    # The Osaka row was not given the already-used Kyoto photo.
    assert ledger_db.query_one(
        "SELECT image_url FROM destinations WHERE destination_id=?",
        [second])["image_url"] is None
    assert ledger_db.query_one(
        "SELECT status FROM destination_images WHERE destination_id=?",
        [second])["status"] == "review"
    pages = [row[0] for row in ledger_db.query_all(
        "SELECT source_page_url FROM destination_images "
        "WHERE status = 'matched'")]
    assert len(pages) == len(set(pages)) == 1


def test_runner_up_is_used_when_the_best_file_is_already_taken(ledger_db):
    """If the top hit is already taken, the next distinct candidate is used."""
    # "Kyoto-2" tokenises to "kyoto", so both destinations rank the candidates
    # identically and the second row really does compete for the same top file.
    first = add_destination(ledger_db, name="Fushimi Inari Taisha", city="Kyoto")
    second = add_destination(ledger_db, name="Fushimi Inari Taisha", city="Kyoto-2")

    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"),
        _page("File:Fushimi Inari Taisha Kyoto Japan 2.jpg"))})
    fetcher.fetch_images(ledger_db, client, verbose=False)

    pages = [row[0] for row in ledger_db.query_all(
        "SELECT source_page_url FROM destination_images "
        "WHERE status = 'matched' ORDER BY destination_id")]
    assert len(pages) == 2, "the second destination should fall back to a runner-up"
    assert pages[0] != pages[1], "the already-used file was reused"


# ------------------------------------------------------------- resumable --
def test_second_run_skips_already_processed_destinations(ledger_db):
    add_destination(ledger_db)
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})

    assert fetcher.fetch_images(ledger_db, client, verbose=False).matched == 1
    calls_after_first = len(client.fake.calls)

    second = fetcher.fetch_images(ledger_db, client, verbose=False)
    assert second.total == 0 and second.matched == 0
    assert len(client.fake.calls) == calls_after_first   # no new API calls


def test_errors_are_retried_only_with_the_retry_flag(ledger_db):
    add_destination(ledger_db)
    failing = make_client({"Fushimi": urllib.error.URLError("boom")}, retries=1)
    assert fetcher.fetch_images(ledger_db, failing, verbose=False).errors == 1
    assert ledger_db.query_one("SELECT status FROM destination_images")["status"] == "error"

    # A plain re-run does not retry an errored row.
    assert fetcher.fetch_images(ledger_db, make_client({"Fushimi": _payload()}),
                                verbose=False).total == 0

    # --retry-errors picks it up again.
    good = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    retried = fetcher.fetch_images(ledger_db, good, retry_errors=True, verbose=False)
    assert retried.total == 1 and retried.matched == 1
    assert len(good.fake.calls) == 1


def test_review_rows_are_not_reprocessed_by_default(ledger_db):
    add_destination(ledger_db, name="Petra", city=None, country="Jordan")
    client = make_client({"Petra": _payload(_page("File:Petra Treasury.jpg"))})
    fetcher.fetch_images(ledger_db, client, verbose=False)
    assert ledger_db.query_one("SELECT status FROM destination_images")["status"] == "review"
    # This needs a person to review, so a normal rerun should leave it alone.
    assert fetcher.fetch_images(ledger_db, client, verbose=False).total == 0


def test_no_result_is_recorded_as_processed(ledger_db):
    add_destination(ledger_db)
    client = make_client({})
    assert fetcher.fetch_images(ledger_db, client, verbose=False).no_result == 1
    assert ledger_db.query_one("SELECT status FROM destination_images")["status"] == "no_result"
    assert fetcher.fetch_images(ledger_db, client, verbose=False).total == 0


def test_dry_run_writes_nothing(ledger_db):
    destination_id = add_destination(ledger_db)
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, dry_run=True, verbose=False)

    assert report.matched == 1 and report.dry_run
    assert ledger_db.query_one("SELECT image_url FROM destinations WHERE destination_id=?",
                        [destination_id])["image_url"] is None
    assert ledger_db.query_one("SELECT COUNT(*) AS n FROM destination_images")["n"] == 0
    assert "dry run" in report.summary()


def test_limit_caps_the_number_of_destinations(ledger_db):
    for index in range(4):
        add_destination(ledger_db, name="Fushimi Inari Taisha",
                        city=f"Kyoto{index}")
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    assert fetcher.fetch_images(ledger_db, client, limit=2, verbose=False).total == 2


def test_custom_user_destinations_are_left_alone(ledger_db):
    add_destination(ledger_db, is_custom=1, name="My Secret Spot")
    client = make_client({"Secret": _payload(_page("File:Secret Spot.jpg"))})
    assert fetcher.fetch_images(ledger_db, client, verbose=False).total == 0
    assert client.fake.calls == []


def test_unrelated_destination_data_is_never_modified(ledger_db):
    destination_id = add_destination(ledger_db)
    before = dict(ledger_db.query_one("SELECT * FROM destinations WHERE destination_id=?",
                               [destination_id]))
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    fetcher.fetch_images(ledger_db, client, verbose=False)
    after = dict(ledger_db.query_one("SELECT * FROM destinations WHERE destination_id=?",
                              [destination_id]))

    changed = {k for k in before if before[k] != after[k]}
    assert changed <= {"image_url", "image_title", "image_creator",
                       "image_source_url", "image_license", "image_license_url",
                       "image_attribution"}, changed
    for key in ("name", "country", "city", "category", "description",
                "estimated_entrance_fee", "currency", "is_custom"):
        assert before[key] == after[key]


# -------------------------------------------------------- schema + report --
def test_schema_upgrade_adds_columns_and_is_idempotent(tmp_path):
    """An older database gains the new columns without losing data.

    The legacy table deliberately omits only the six image columns that this
    feature adds; everything else matches the real pre-feature schema, so the
    test reflects an actual upgrade rather than a stripped-down imitation.
    """
    legacy = tmp_path / "legacy.db"
    connection = sqlite3.connect(legacy)
    connection.executescript(
        "CREATE TABLE destinations ("
        "  destination_id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        "  name_key TEXT NOT NULL, country TEXT NOT NULL, city TEXT,"
        "  category TEXT NOT NULL, description TEXT, image_url TEXT,"
        "  estimated_entrance_fee REAL, currency TEXT,"
        "  is_custom INTEGER NOT NULL DEFAULT 0, user_id INTEGER,"
        "  created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "  UNIQUE (name_key, country, city));"
        "INSERT INTO destinations (name, name_key, country, city, category)"
        " VALUES ('Old Row', 'old row', 'Japan', 'Tokyo', 'temple');")
    connection.commit()
    connection.close()

    manager = DatabaseManager(legacy, SCHEMA)
    manager.get_connection()
    manager.create_tables()
    manager.create_tables()          # idempotent: must not raise

    columns = {row["name"] for row in
               manager.query_all("PRAGMA table_info(destinations)")}
    for column in DatabaseManager.IMAGE_COLUMNS:
        assert column in columns, column
    # The pre-existing row survived, and the ledger table was created.
    assert manager.scalar("SELECT COUNT(*) FROM destinations") == 1
    assert "destination_images" in manager.table_names()
    manager.close()


def test_reset_db_drops_the_ledger_table(ledger_db):
    ledger_db.drop_tables()
    assert "destination_images" not in ledger_db.table_names()


def test_report_counts_add_up(ledger_db):
    add_destination(ledger_db, name="Fushimi Inari Taisha")
    add_destination(ledger_db, name="Petra", city=None, country="Jordan")
    add_destination(ledger_db, name="Nowhere Place", city="Nowhere", country="Nowhere")
    client = make_client({
        "Fushimi": _payload(_page("File:Fushimi Inari Taisha Kyoto Japan.jpg")),
        "Petra": _payload(_page("File:Petra Treasury Jordan.jpg")),
        "Nowhere": _payload(),
    })
    report = fetcher.fetch_images(ledger_db, client, verbose=False)

    assert report.total == 3
    assert report.matched == 1
    assert report.review == 1
    assert report.no_result == 1
    text = report.summary()
    assert "Images matched" in text
    assert "Needs manual review" in text
    assert "No result found" in text


def test_report_only_runs_without_network(ledger_db, capsys):
    add_destination(ledger_db)
    assert fetcher.main(["--db", str(ledger_db.database_path), "--report-only"]) == 0
    assert "destination image report" in capsys.readouterr().out


# ------------------------------------------------------------- rendering ---
def test_browse_page_shows_the_placeholder_without_an_image(client):
    body = client.get("/destinations",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "dest-placeholder" in body


def test_browse_page_renders_image_and_attribution(app, db, client):
    with app.app_context():
        # A name not present in the conftest fixture dataset, so the
        # UNIQUE(name_key, country, city) constraint is not violated.
        destination_id = add_destination(db, name="Attribution Test Shrine",
                                         city="Nara")
        db.execute(
            "UPDATE destinations SET"
            " image_url = 'https://upload.wikimedia.org/x.jpg',"
            " image_creator = 'A Photographer', image_license = 'CC BY-SA 4.0',"
            " image_source_url = 'https://commons.wikimedia.org/wiki/File:X.jpg',"
            " image_license_url = 'https://creativecommons.org/licenses/by-sa/4.0'"
            " WHERE destination_id = ?", [destination_id])
    body = client.get("/destinations",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "https://upload.wikimedia.org/x.jpg" in body
    assert "A Photographer" in body
    assert "CC BY-SA 4.0" in body
    assert "https://commons.wikimedia.org/wiki/File:X.jpg" in body


def test_detail_page_shows_attribution_and_a_fallback(app, db, client):
    with app.app_context():
        with_image = add_destination(db, name="Credit Test Pavilion",
                                     city="Nara")
        without_image = add_destination(db, name="Placeholder Test Ruins",
                                        city="Nara")
        db.execute(
            "UPDATE destinations SET"
            " image_url = 'https://upload.wikimedia.org/k.jpg',"
            " image_creator = 'A Photographer', image_license = 'CC0',"
            " image_source_url = 'https://commons.wikimedia.org/wiki/File:K.jpg'"
            " WHERE destination_id = ?", [with_image])

    body = client.get(f"/destinations/{with_image}",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "A Photographer" in body and "CC0" in body

    body = client.get(f"/destinations/{without_image}",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "dest-placeholder" in body
    assert "No photograph available" in body


def test_api_exposes_attribution_fields(client):
    first = client.get("/api/destinations").get_json()["destinations"][0]
    for key in ("image_license", "image_creator", "image_source_url",
                "image_attribution", "image_title", "image_license_url"):
        assert key in first, key


def test_progress_output_survives_non_ascii_titles(ledger_db, capsys):
    """A Commons title with characters outside cp1252 must not abort the batch.

    Titles such as "Kyōto" carry a macron that Windows' ANSI code page cannot
    encode; without forcing UTF-8 the progress print raised
    UnicodeEncodeError and killed the whole run, which is exactly what
    "continue if one destination fails" forbids.  The title here still scores
    0.9 so the run takes the *match* branch, which is the print that crashed.
    """
    fetcher._force_utf8_output()               # what main() does on startup
    add_destination(ledger_db, name="Ryoan-ji Rock Garden")
    client = make_client({"Ryoan": _payload(
        _page("File:Ryoan-ji Rock Garden Kyoto Japan ō 京.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=True)

    assert report.matched == 1                 # the run survived
    out = capsys.readouterr().out
    assert "Ryoan-ji Rock Garden" in out
    assert "ō" in out                          # printed, not mangled


def test_force_utf8_output_is_safe_to_call_twice():
    """Reconfiguring an already-UTF-8 stream must not raise."""
    fetcher._force_utf8_output()
    fetcher._force_utf8_output()


# ------------------------------------------------------- --failures-csv -----
def test_failures_csv_records_review_and_error_rows(ledger_db, tmp_path):
    """Rows the run could not resolve are exported so they can be retried."""
    add_destination(ledger_db, name="Petra", city=None, country="Jordan")
    add_destination(ledger_db, name="Broken Link", city="Kyoto", country="Japan")
    client = make_client({
        "Petra": _payload(_page("File:Petra Treasury.jpg")),      # 0.60 -> review
        "Broken": urllib.error.URLError("name resolution failed"),
    })
    report = fetcher.fetch_images(ledger_db, client, verbose=False)
    assert report.review == 1 and report.errors == 1

    target = tmp_path / "failures.csv"
    assert fetcher.write_failures_csv(report, target) == 2

    with open(target, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["destination_id", "destination_name", "city",
                       "country", "error"]
    by_name = {row[1]: row for row in rows[1:]}
    # A destination with no city stores an empty cell, not the string "None".
    assert by_name["Petra"][2] == "" and by_name["Petra"][3] == "Jordan"
    assert "best score" in by_name["Petra"][4]
    assert by_name["Broken Link"][2] == "Kyoto"
    assert "network error" in by_name["Broken Link"][4]
    assert all(row[0].isdigit() for row in rows[1:])


def test_failures_csv_writes_just_a_header_when_nothing_failed(ledger_db,
                                                               tmp_path):
    """A clean run still produces a well-formed, importable file."""
    add_destination(ledger_db)
    client = make_client({"Fushimi": _payload(
        _page("File:Fushimi Inari Taisha Kyoto Japan.jpg"))})
    report = fetcher.fetch_images(ledger_db, client, verbose=False)
    assert report.matched == 1 and not report.failure_rows

    target = tmp_path / "clean.csv"
    assert fetcher.write_failures_csv(report, target) == 0
    assert target.read_text(encoding="utf-8").strip() == (
        "destination_id,destination_name,city,country,error")


def test_failures_csv_is_a_public_helper_used_by_the_cli():
    """The CLI flag and the unit-tested helper are the same code path.

    ``main`` builds a real ``CommonsClient``, so it cannot be driven from a
    test without touching the network; asserting the shared constants keeps the
    flag honest without breaking this file's no-network guarantee.
    """
    assert fetcher.FAILURE_CSV_HEADER == (
        "destination_id", "destination_name", "city", "country", "error")
    assert callable(fetcher.write_failures_csv)


# ---------------------------------------------- broken-image fallback -------
def test_browse_card_image_has_a_broken_image_fallback(app, db, client):
    """A dead Commons URL reveals the placeholder instead of a broken icon."""
    with app.app_context():
        destination_id = add_destination(db, name="Fallback Test Shrine",
                                         city="Nara")
        db.execute("UPDATE destinations SET image_url = ? WHERE destination_id = ?",
                   ["https://upload.wikimedia.org/gone.jpg", destination_id])
    body = client.get("/destinations",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "onerror=" in body
    assert "this.nextElementSibling.hidden=false" in body
    # The placeholder onerror reveals is present in the markup but hidden.
    assert 'class="dest-placeholder" aria-hidden="true" hidden' in body


def test_detail_image_has_a_broken_image_fallback(app, db, client):
    with app.app_context():
        destination_id = add_destination(db, name="Detail Fallback Ruins",
                                         city="Nara")
        db.execute("UPDATE destinations SET image_url = ? WHERE destination_id = ?",
                   ["https://upload.wikimedia.org/gone.jpg", destination_id])
    body = client.get(f"/destinations/{destination_id}",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "onerror=" in body
    assert "detail-placeholder" in body


def test_placeholder_stays_hidden_until_an_image_fails(app, db, client):
    """A destination that *does* have an image must not show both at once."""
    with app.app_context():
        destination_id = add_destination(db, name="Both Shown Shrine", city="Nara")
        db.execute("UPDATE destinations SET image_url = ? WHERE destination_id = ?",
                   ["https://upload.wikimedia.org/ok.jpg", destination_id])
    body = client.get(f"/destinations/{destination_id}",
                      headers={"Accept": "text/html"}).get_data(as_text=True)
    # Show the real image and keep only its placeholder hidden.
    assert '<img class="detail-image" src="https://upload.wikimedia.org/ok.jpg"' in body
    assert 'detail-placeholder" aria-hidden="true" hidden' in body