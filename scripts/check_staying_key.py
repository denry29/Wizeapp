"""One-off diagnostic: verify STAYING_API_KEY works against the live API.

Run with the project venv:
    .venv\\Scripts\\python.exe scripts\\check_staying_key.py

Prints only non-secret result summaries (never the key itself).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_config  # noqa: E402
from services.stayingapi import StayingAPIClient, StayingAPIError  # noqa: E402


def main() -> int:
    key = get_config().STAYING_API_KEY
    if not key:
        print("FAIL: STAYING_API_KEY is empty after loading .env")
        return 1
    print(f"OK: key loaded from .env (length {len(key)}, prefix {key[:8]}...)")

    check_in = (date.today() + timedelta(days=7)).isoformat()
    check_out = (date.today() + timedelta(days=9)).isoformat()
    client = StayingAPIClient(key, timeout=30, max_job_wait=240)
    try:
        result = client.search_hotels(
            city="Bangkok", country_code="TH",
            check_in=check_in, check_out=check_out,
            adults=2, rooms=1, currency="USD")
    except StayingAPIError as error:
        print(f"FAIL: live search rejected: {error}")
        return 1

    hotels = result["hotels"]
    print(f"OK: live search returned {len(hotels)} hotel(s)")
    if not hotels:
        return 1

    sample = hotels[0]
    print("--- first hotel field coverage ---")
    for field in ("name", "image_url", "images", "price_per_night",
                  "total_price", "currency", "rating", "review_count",
                  "star_rating", "provider", "platform_listing_id"):
        value = sample.get(field)
        if isinstance(value, list):
            value = f"{len(value)} item(s)"
        print(f"  {field}: {value!r}")

    with_photos = sum(1 for h in hotels if h.get("images"))
    with_price = sum(1 for h in hotels if h.get("total_price") is not None)
    with_rating = sum(1 for h in hotels if h.get("rating") is not None)
    print(f"hotels with photos: {with_photos}/{len(hotels)}")
    print(f"hotels with price:  {with_price}/{len(hotels)}")
    print(f"hotels with rating: {with_rating}/{len(hotels)}")

    listing = sample.get("platform_listing_id")
    platform = sample.get("provider")
    if listing and platform in {"booking", "google"}:
        try:
            reviews = client.get_reviews(platform, str(listing))
            data = reviews["data"]
            count = (len(data.get("reviews", [])) if isinstance(data, dict)
                     else len(data) if isinstance(data, list) else 0)
            print(f"OK: reviews endpoint works for {platform}/{listing} "
                  f"({count} review(s))")
        except StayingAPIError as error:
            print(f"NOTE: reviews fetch failed: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
