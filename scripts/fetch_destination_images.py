"""Attach Wikimedia Commons photos to the destination catalogue.

Usage (from the project root)
----------------------------
    python scripts/fetch_destination_images.py                 # fetch what is missing
    python scripts/fetch_destination_images.py --limit 25       # try a small batch
    python scripts/fetch_destination_images.py --dry-run        # search, write nothing
    python scripts/fetch_destination_images.py --retry-errors   # re-try failed rows
    python scripts/fetch_destination_images.py --report-only    # counts, no network
    python scripts/fetch_destination_images.py --failures-csv failures.csv

What the script guarantees
--------------------------
1. **Never overwrites an existing image.**  A destination that already has a
   usable ``image_url`` is skipped before any search happens.
2. **Resumable.**  Every processed destination gets a row in
   ``destination_images``; a later run skips those rows entirely, so an
   interrupted 525-row run costs only the remainder.
3. **Conservative.**  An image is written only when the best candidate scores
   at least ``--min-score`` (default 0.75).  Anything weaker is recorded as
   ``review`` and left without an image rather than guessed at.
4. **No duplicates.**  A Commons file already used by another destination is
   skipped, both in memory during the run and by a unique index in SQLite.
5. **Licence-aware.**  Candidates whose licence is not clearly free are
   discarded before they can be chosen.
6. **Never destructive.**  Only image columns and the ledger are written;
   names, fees, currencies and descriptions are never touched.

Exit code is 0 on success and 1 when the database cannot be opened, so the
script is safe to call from CI or a Makefile.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.db import DatabaseManager          # noqa: E402
from services.commons import (                   # noqa: E402
    CommonsClient, ImageCandidate, build_attribution)

#: A candidate must reach this score before an image is written.  A perfect
#: name+city+country match scores 0.9; name-only matches top out at 0.6, so
#: the default deliberately rejects anything not confirmed by location.
DEFAULT_MIN_SCORE = 0.75

#: Statuses that still need attention on a later run.
RETRYABLE = {"error"}

#: ``image_url`` values that are not real remote photos (blank or the literal
#: placeholder) and may therefore be replaced.
PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "null", "todo", "placeholder"}


def _has_real_image(row) -> bool:
    """True when a destination already shows a genuine image."""
    value = (row["image_url"] or "").strip().lower()
    return bool(value) and value not in PLACEHOLDER_VALUES and value.startswith("http")


@dataclass
class FetchReport:
    """Counters for the final summary."""

    total: int = 0
    skipped_processed: int = 0
    skipped_has_image: int = 0
    matched: int = 0
    review: int = 0
    no_result: int = 0
    errors: int = 0
    duplicates_avoided: int = 0
    dry_run: bool = False
    #: ``(destination_id, name, city, country, reason)`` - the exact shape the
    #: ``--failures-csv`` file needs, so a later retry pass can be driven from it.
    review_rows: list[tuple[int, str, str, str, str]] = field(default_factory=list)
    error_rows: list[tuple[int, str, str, str, str]] = field(default_factory=list)

    @property
    def failure_rows(self) -> list[tuple[int, str, str, str, str]]:
        """Review and error rows combined - what ``--failures-csv`` exports."""
        return [*self.review_rows, *self.error_rows]

    def summary(self) -> str:
        return (
            f"Destinations examined : {self.total}\n"
            f"Already processed     : {self.skipped_processed}\n"
            f"Already had an image  : {self.skipped_has_image}\n"
            f"Images matched        : {self.matched}\n"
            f"Needs manual review   : {self.review}\n"
            f"No result found       : {self.no_result}\n"
            f"Errors (API/network)  : {self.errors}\n"
            f"Duplicates avoided    : {self.duplicates_avoided}"
            + ("\n(dry run - the database was not modified)"
               if self.dry_run else "")
        )


def _pending_rows(db: DatabaseManager, limit: int | None,
                  retry_errors: bool) -> list:
    """Destinations that still need a search, honouring the resume ledger.

    A destination is skipped when it already has a ledger row, unless
    ``retry_errors`` is set and that row failed with a network/API error.
    """
    sql = """
    SELECT d.destination_id, d.name, d.city, d.country, d.image_url, i.status
    FROM destinations d
    LEFT JOIN destination_images i ON i.destination_id = d.destination_id
    WHERE d.is_custom = 0
      AND (i.destination_id IS NULL
           OR (? = 1 AND i.status IN ('error')))
    ORDER BY d.destination_id
    """
    params: list = [1 if retry_errors else 0]
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return db.query_all(sql, params)


def _used_source_pages(db: DatabaseManager) -> set[str]:
    """Commons files already assigned to some destination (dedup seed).

    ``destination_images`` names the column ``source_page_url``; the
    identically named column on ``destinations`` is ``image_source_url``.
    """
    return {row[0] for row in db.query_all(
        "SELECT source_page_url FROM destination_images "
        "WHERE source_page_url IS NOT NULL AND source_page_url <> ''")}


def _record(db: DatabaseManager, destination_id: int, status: str,
            candidate: ImageCandidate | None = None, query: str = "",
            confidence: float | None = None, note: str = "",
            dry_run: bool = False) -> None:
    """Write the ledger row (and, when matched, the image columns).

    ``INSERT OR REPLACE`` keeps this correct when a destination is re-processed
    by ``--retry-errors``.  The destination's own data is never modified
    except for the six image columns.

    Only a ``matched`` row records ``source_page_url``.  A ``review`` row has
    merely *suggested* a candidate - it has not claimed the file - and writing
    the URL there would collide with the partial unique index
    ``idx_dest_image_unique`` and silently evict the destination that really
    does use that image.
    """
    if dry_run:
        return
    claimed = status == "matched" and candidate is not None
    db.execute(
        """
        INSERT OR REPLACE INTO destination_images
            (destination_id, status, image_title, creator, source_page_url,
             license, license_url, query_used, confidence, note, checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        [destination_id, status,
         candidate.title if candidate else None,
         candidate.creator if candidate else None,
         candidate.source_page_url if claimed else None,
         candidate.license_name if candidate else None,
         candidate.license_url if candidate else None,
         query or None, confidence, note or None])

    if status == "matched" and candidate:
        db.execute(
            """
            UPDATE destinations
               SET image_url = ?, image_title = ?, image_creator = ?,
                   image_source_url = ?, image_license = ?,
                   image_license_url = ?, image_attribution = ?
             WHERE destination_id = ?
            """,
            [candidate.url, candidate.title, candidate.creator,
             candidate.source_page_url, candidate.license_name,
             candidate.license_url, build_attribution(candidate),
             destination_id])


def fetch_images(db: DatabaseManager, client: CommonsClient, *,
                 limit: int | None = None, min_score: float = DEFAULT_MIN_SCORE,
                 dry_run: bool = False, retry_errors: bool = False,
                 verbose: bool = True) -> FetchReport:
    """Walk the catalogue and attach a Commons image to each destination."""
    report = FetchReport(dry_run=dry_run)
    used_pages = _used_source_pages(db)
    rows = _pending_rows(db, limit, retry_errors)
    report.total = len(rows)

    for index, row in enumerate(rows, start=1):
        destination_id, name = row["destination_id"], row["name"]
        city, country = row["city"], row["country"]

        if _has_real_image(row):
            # Never clobber a photo somebody already put there.
            report.skipped_has_image += 1
            continue

        result = client.search(name, city, country)

        if not result.ok:
            report.errors += 1
            report.error_rows.append((destination_id, name, city or "",
                                      country or "", result.error or ""))
            _record(db, destination_id, "error", query=result.query,
                    note=result.error, dry_run=dry_run)
            if verbose:
                print(f"  [{index}/{report.total}] ERROR  {name}: {result.error}")
            continue

        if not result.candidates:
            report.no_result += 1
            _record(db, destination_id, "no_result", query=result.query,
                    dry_run=dry_run)
            if verbose:
                print(f"  [{index}/{report.total}] none   {name}")
            continue

        best = result.best
        if best.score < min_score:
            # Results existed but were not clearly this destination.
            report.review += 1
            report.review_rows.append(
                (destination_id, name, city or "", country or "",
                 f"best score {best.score:.2f} < {min_score:.2f}"))
            _record(db, destination_id, "review", candidate=best,
                    query=result.query, confidence=best.score,
                    note=f"score {best.score:.2f} below threshold {min_score:.2f}",
                    dry_run=dry_run)
            if verbose:
                print(f"  [{index}/{report.total}] review {name} "
                      f"(score {best.score:.2f})")
            continue

        if best.source_page_url in used_pages:
            # Same file already backs another destination - take the runner-up.
            alternative = next(
                (c for c in result.candidates[1:]
                 if c.score >= min_score
                 and c.source_page_url not in used_pages), None)
            if alternative is None:
                report.duplicates_avoided += 1
                report.review += 1
                report.review_rows.append(
                    (destination_id, name, city or "", country or "",
                     "only candidate already used elsewhere"))
                _record(db, destination_id, "review", candidate=best,
                        query=result.query, confidence=best.score,
                        note="duplicate image avoided", dry_run=dry_run)
                if verbose:
                    print(f"  [{index}/{report.total}] dup    {name}")
                continue
            best = alternative

        used_pages.add(best.source_page_url)
        report.matched += 1
        _record(db, destination_id, "matched", candidate=best,
                query=result.query, confidence=best.score, dry_run=dry_run)
        if verbose:
            print(f"  [{index}/{report.total}] match  {name} "
                  f"({best.score:.2f}) {best.display_title}")

    return report


def _counts_by_status(db: DatabaseManager) -> Counter:
    return Counter(row[0] for row in db.query_all(
        "SELECT status, COUNT(*) FROM destination_images GROUP BY status"))


def _catalogue_images(db: DatabaseManager) -> tuple[int, int]:
    """(with_image, total) across the shared catalogue."""
    total = int(db.scalar("SELECT COUNT(*) FROM destinations WHERE is_custom = 0"))
    with_image = int(db.scalar(
        "SELECT COUNT(*) FROM destinations "
        "WHERE is_custom = 0 AND image_url IS NOT NULL AND trim(image_url) <> ''"))
    return with_image, total


def print_ledger_report(db: DatabaseManager) -> None:
    """Print the current state of the ledger without touching the network."""
    counts = _counts_by_status(db)
    with_image, total = _catalogue_images(db)
    print("=" * 66)
    print("Wize - destination image report (no network)")
    print("=" * 66)
    print(f"  Catalogue destinations : {total}")
    print(f"  With an image          : {with_image}")
    print(f"  Without an image       : {total - with_image}")
    print("  Ledger by status:")
    for status in ("matched", "review", "no_result", "error", "pending"):
        if counts.get(status):
            print(f"    {status:10}: {counts[status]}")
    review_rows = db.query_all(
        "SELECT destination_id, note FROM destination_images "
        "WHERE status = 'review' ORDER BY destination_id LIMIT 20")
    if review_rows:
        print("  Needing manual review (first 20):")
        for row in review_rows:
            print(f"    #{row['destination_id']}: {row['note']}")
    print("=" * 66)


#: Column order (and header row) for ``--failures-csv``.
FAILURE_CSV_HEADER = ("destination_id", "destination_name", "city",
                      "country", "error")


def write_failures_csv(report: FetchReport, path: str | Path) -> int:
    """Write every review/error row to ``path``; returns how many were written.

    A run with no failures still produces a file containing just the header, so
    whatever consumes it later never has to special-case a missing file.
    """
    rows = report.failure_rows
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FAILURE_CSV_HEADER)
        writer.writerows(rows)
    return len(rows)


def _force_utf8_output() -> None:
    """Make progress printing safe for non-ASCII names and file titles.

    Commons titles routinely contain characters that Windows' cp1252 code page
    cannot represent - the macron in "Kyōto", for example - and one destination
    in the catalogue is "Bahai'í Gardens".  When stdout is redirected to a file
    Python picks the ANSI code page, so printing such a title raises
    ``UnicodeEncodeError`` and takes the entire batch down with it, which
    contradicts the promise that one bad row never aborts the run.  Switching
    the streams to UTF-8 keeps the run alive and is a no-op when they already
    speak UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:              # e.g. captured by pytest
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):        # already detached/closed
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        description="Attach Wikimedia Commons photos to destination rows.")
    parser.add_argument("--db", help="Path to the SQLite file "
                                     "(default: database/wize.db)")
    parser.add_argument("--limit", type=int,
                        help="Only examine the first N pending destinations.")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE,
                        help=f"Minimum confidence to accept a match "
                             f"(default {DEFAULT_MIN_SCORE}).")
    parser.add_argument("--delay", type=float, default=0.34,
                        help="Minimum seconds between API calls "
                             "(default 0.34; Wikimedia asks scripts to be slow).")
    parser.add_argument("--retries", type=int, default=3,
                        help="Attempts per request before giving up.")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Per-request timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Search and report, but write nothing.")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Also re-try destinations whose last run errored.")
    parser.add_argument("--report-only", action="store_true",
                        help="Print the ledger summary and exit (no network).")
    parser.add_argument("--failures-csv", metavar="PATH",
                        help="Write the review/error rows to PATH as CSV "
                             "(destination_id, destination_name, city, "
                             "country, error) so they can be retried later.")
    parser.add_argument("--quiet", action="store_true",
                        help="Only print the final summary.")
    args = parser.parse_args(argv)

    db_path = Path(args.db) if args.db else PROJECT_ROOT / "database" / "wize.db"
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}")
        print("Run 'python scripts/seed_destinations.py' first.")
        return 1

    db = DatabaseManager(db_path, PROJECT_ROOT / "database" / "schema.sql")
    try:
        db.create_tables()          # also upgrades an older database in place

        if args.report_only:
            print_ledger_report(db)
            return 0

        catalogue = int(db.scalar(
            "SELECT COUNT(*) FROM destinations WHERE is_custom = 0"))
        client = CommonsClient(timeout=args.timeout, min_interval=args.delay,
                               retries=args.retries)

        print("=" * 66)
        print("Wize - Wikimedia Commons image fetch")
        print("=" * 66)
        print(f"  Database : {db_path}")
        print(f"  Catalogue: {catalogue} destinations")
        print(f"  Min score: {args.min_score}")
        if args.dry_run:
            print("  Mode     : DRY RUN - nothing will be written")
        print("-" * 66)

        report = fetch_images(
            db, client, limit=args.limit, min_score=args.min_score,
            dry_run=args.dry_run, retry_errors=args.retry_errors,
            verbose=not args.quiet)

        print("-" * 66)
        print(report.summary())
        if report.review_rows:
            print("-" * 66)
            print(f"Manual review needed ({len(report.review_rows)}):")
            for row in report.review_rows[:40]:
                destination_id, name, _city, _country, reason = row
                print(f"  #{destination_id} {name}: {reason}")
            if len(report.review_rows) > 40:
                print(f"  ... and {len(report.review_rows) - 40} more "
                      f"(run with --report-only to browse)")
        if report.error_rows:
            print(f"Errors ({len(report.error_rows)}) - re-run with --retry-errors:")
            for row in report.error_rows[:20]:
                destination_id, name, _city, _country, reason = row
                print(f"  #{destination_id} {name}: {reason}")
        if args.failures_csv:
            written = write_failures_csv(report, args.failures_csv)
            print("-" * 66)
            print(f"Failure CSV written : {args.failures_csv} ({written} rows)")
        print("=" * 66)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
