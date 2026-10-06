"""End-to-end verification of /api/hotels/search with the real app config.

Registers a throwaway user, runs a live Bangkok hotel search through the
Flask route (exactly what the browser does), prints the outcome, then
removes the throwaway user again.

Run with the project venv:
    .venv\\Scripts\\python.exe scripts\\verify_hotel_flow.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402

EMAIL = "hotel-flow-check@wize.local"
PASSWORD = "Str0ngPass!"


def main() -> int:
    app = create_app()
    client = app.test_client()

    client.get("/auth/login")  # establishes session + CSRF token
    with client.session_transaction() as session:
        token = session.get("_csrf_token", "")
    headers = {"X-CSRF-Token": token, "Accept": "application/json"}

    response = client.post("/api/auth/register", json={
        "full_name": "Hotel Flow Check", "email": EMAIL,
        "password": PASSWORD, "confirm_password": PASSWORD,
    }, headers=headers)
    if response.status_code == 409:  # left over from a previous run
        response = client.post("/api/auth/login", json={
            "email": EMAIL, "password": PASSWORD}, headers=headers)
    print("auth status:", response.status_code)
    if response.status_code not in {200, 201}:
        print("auth failed:", response.get_json())
        return 1

    check_in = (date.today() + timedelta(days=7)).isoformat()
    check_out = (date.today() + timedelta(days=9)).isoformat()
    response = client.get(
        "/api/hotels/search?city=Bangkok&country=TH"
        f"&check_in={check_in}&check_out={check_out}"
        "&adults=2&rooms=1&currency=USD")
    payload = response.get_json()
    print("search status:", response.status_code)

    if response.status_code == 200:
        hotels = payload["hotels"]
        print(f"provider: {payload['provider']}  hotels: {len(hotels)}")
        if hotels:
            first = hotels[0]
            print("first hotel:", json.dumps({
                "name": first.get("name"),
                "image_url": first.get("image_url"),
                "num_images": len(first.get("images") or []),
                "price_per_night": first.get("price_per_night"),
                "total_price": first.get("total_price"),
                "currency": first.get("currency"),
                "rating": first.get("rating"),
                "review_count": first.get("review_count"),
                "provider": first.get("provider"),
            }, indent=2))
            print("with photos:", sum(1 for h in hotels if h.get("images")),
                  "/", len(hotels))
            print("with price:", sum(
                1 for h in hotels if h.get("total_price") is not None),
                "/", len(hotels))
            print("with rating:", sum(
                1 for h in hotels if h.get("rating") is not None),
                "/", len(hotels))
        outcome = 0
    else:
        print("provider message:", payload.get("error"))
        # A clear provider message (not a crash, not "configure the key")
        # means the server-side chain is healthy.
        outcome = 0 if "Configure STAYING_API_KEY" not in (
            payload.get("error") or "") else 1

    db = app.extensions["wize_db"]
    db.execute("DELETE FROM users WHERE email = ?", [EMAIL])
    print("throwaway user removed")
    return outcome


if __name__ == "__main__":
    raise SystemExit(main())
