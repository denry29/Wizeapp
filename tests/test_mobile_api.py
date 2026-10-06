"""Expo-facing REST APIs and planning-only transport searches."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import logout, register, trip_payload


def _create_trip(client, **overrides):
    payload = trip_payload(**overrides)
    response = client.post("/api/trips", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]


def test_expo_csrf_bootstrap_and_cors(client):
    response = client.get("/api/auth/csrf", headers={"Origin": "http://localhost:8081"})
    assert response.status_code == 200
    assert response.get_json()["csrf_token"]
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8081"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_hotel_search_route_returns_provider_details_without_booking(
        client, monkeypatch):
    register(client)

    class Provider:
        def search_hotels(self, city, country_code, check_in, check_out,
                          adults, rooms, children, child_ages, currency):
            return {
                "hotels": [{
                    "name": "Provider Hotel",
                    "image_url": "https://provider.example/hotel.jpg",
                    "rating": None,
                    "total_price": 19500,
                    "currency": "PHP",
                }],
                "meta": {"creditsCharged": 0},
            }

    monkeypatch.setattr("routes.hotel_routes._client", lambda: Provider())
    check_in = date.today() + timedelta(days=10)
    check_out = check_in + timedelta(days=3)
    hotel_response = client.get(
        f"/api/hotels/search?city=Tokyo&country=JP"
        f"&check_in={check_in.isoformat()}&check_out={check_out.isoformat()}")

    assert hotel_response.status_code == 200
    assert hotel_response.get_json()["hotels"][0]["total_price"] == 19500
    assert hotel_response.get_json()["provider"] == "StayingAPI"
    assert hotel_response.get_json()["live_search"] is True
    assert hotel_response.get_json()["searched_at"]
    assert "no-store" in hotel_response.headers["Cache-Control"]
    assert hotel_response.get_json()["booking_enabled"] is False


def test_favorites_are_owned_by_the_signed_in_user(client):
    register(client)
    destination_id = client.get("/api/destinations").get_json()["destinations"][0]["destination_id"]
    assert client.post(f"/api/favorites/{destination_id}").status_code == 201
    assert len(client.get("/api/favorites").get_json()["favorites"]) == 1

    logout(client)
    register(client, email="second@wize.local")
    assert client.get("/api/favorites").get_json()["favorites"] == []


def test_notes_and_saved_options_are_scoped_to_the_trip_owner(client):
    register(client)
    trip = _create_trip(client)
    note_response = client.post(
        f"/api/trips/{trip['trip_id']}/notes",
        json={"title": "Arrival", "content": "Pick up a transit card."})
    assert note_response.status_code == 201
    note = note_response.get_json()["note"]
    assert client.patch(
        f"/api/notes/{note['note_id']}",
        json={"title": "Arrival plan", "content": "Use the airport train."},
    ).get_json()["note"]["title"] == "Arrival plan"

    forbidden_option_response = client.post(
        f"/api/trips/{trip['trip_id']}/saved-options",
        json={
            "option_type": "flight",
            "title": "Airline AB123",
            "amount": 18500,
            "currency": "PHP",
            "details": {"airline": "Airline", "credit_card": "must not be persisted"},
        },
    )
    assert forbidden_option_response.status_code == 400
    option_response = client.post(
        f"/api/trips/{trip['trip_id']}/saved-options",
        json={"option_type": "flight", "title": "Airline AB123", "amount": 18500,
              "currency": "PHP",
              "details": {"airline": "Airline", "flight_number": "AB123"}},
    )
    assert option_response.status_code == 201

    logout(client)
    register(client, email="second@wize.local")
    assert client.get(f"/api/trips/{trip['trip_id']}/notes").status_code == 404
    assert client.get(f"/api/trips/{trip['trip_id']}/saved-options").status_code == 404


def test_planned_and_actual_amounts_are_separate(client):
    register(client)
    trip = _create_trip(client, budget=30000, budget_currency="PHP")
    for kind, amount in (("planned", 1000), ("actual", 1200)):
        response = client.post(
            f"/api/trips/{trip['trip_id']}/expenses",
            json={
                "expense_name": "Train",
                "category": "transportation",
                "amount": amount,
                "currency": "PHP",
                "expense_kind": kind,
            },
        )
        assert response.status_code == 201, response.get_json()

    summary = client.get(
        f"/api/trips/{trip['trip_id']}/expenses/summary").get_json()
    assert summary["totals_by_kind_and_currency"] == {
        "planned": {"PHP": 1000.0},
        "actual": {"PHP": 1200.0},
    }
    assert summary["variance_by_currency"] == {"PHP": 200.0}
    assert summary["budget"]["spent_in_budget_currency"] == 1200.0


def test_saved_flight_and_hotel_prices_become_planned_expenses(client):
    register(client)
    trip = _create_trip(client, budget=30000, budget_currency="PHP")
    trip_id = trip["trip_id"]
    offers = (
        ("flight", "MNL to NRT", 12500,
         {
             "airline": "Example Air",
             "flight_number": "EA123",
             "airline_logo_url": "https://commons.example/air.png",
             "segments": [{"flight_number": "EA123", "origin": "MNL",
                           "destination": "NRT"}],
         }),
        ("hotel", "Tokyo Stay", 8000,
         {
             "hotel_id": "HOTEL123",
             "rating": None,
             "image_url": "https://commons.example/hotel.jpg",
             "image_attribution": "Tokyo Stay by Author, CC BY 4.0",
             "image_source_url": "https://commons.wikimedia.org/wiki/File:Hotel.jpg",
             "image_license": "CC BY 4.0",
             "search_criteria": {"adults": 2, "children": 1, "rooms": 1},
         }),
    )

    for kind, title, amount, details in offers:
        response = client.post(
            f"/api/trips/{trip_id}/saved-options",
            json={
                "option_type": kind,
                "title": title,
                "amount": amount,
                "currency": "PHP",
                "details": details,
            },
        )
        assert response.status_code == 201, response.get_json()

    saved = client.get(
        f"/api/trips/{trip_id}/saved-options").get_json()["options"]
    saved_by_type = {option["option_type"]: option["details"] for option in saved}
    assert saved_by_type["flight"]["segments"][0]["flight_number"] == "EA123"
    assert saved_by_type["flight"]["airline_logo_url"] == "https://commons.example/air.png"
    assert saved_by_type["hotel"]["image_attribution"] == (
        "Tokyo Stay by Author, CC BY 4.0")
    assert saved_by_type["hotel"]["image_source_url"].startswith(
        "https://commons.wikimedia.org/")
    assert saved_by_type["hotel"]["search_criteria"] == {
        "adults": 2, "children": 1, "rooms": 1}

    expenses = client.get(f"/api/trips/{trip_id}/expenses").get_json()["expenses"]
    assert len(expenses) == 2
    assert {expense["expense_kind"] for expense in expenses} == {"planned"}
    assert {expense["category"] for expense in expenses} == {
        "flights", "hotels"}
    summary = client.get(
        f"/api/trips/{trip_id}/expenses/summary").get_json()
    assert summary["totals_by_kind_and_currency"] == {
        "planned": {"PHP": 20500.0},
        "actual": {},
    }
    assert summary["budget"]["remaining"] == 30000.0

    option_id = client.get(
        f"/api/trips/{trip_id}/saved-options").get_json()["options"][0]["option_id"]
    assert client.delete(f"/api/saved-options/{option_id}").status_code == 200
    remaining_expenses = client.get(
        f"/api/trips/{trip_id}/expenses").get_json()["expenses"]
    assert len(remaining_expenses) == 1


def test_saved_option_without_price_does_not_create_expense(client):
    register(client)
    trip = _create_trip(client)
    response = client.post(
        f"/api/trips/{trip['trip_id']}/saved-options",
        json={
            "option_type": "hotel",
            "title": "Hotel with no listed rate",
            "details": {"hotel_id": "HOTEL123"},
        },
    )
    assert response.status_code == 201
    assert client.get(
        f"/api/trips/{trip['trip_id']}/expenses").get_json()["expenses"] == []


def test_hotel_saved_to_trip_is_date_checked_and_added_to_planned_total(client):
    register(client)
    trip = _create_trip(client)
    trip_id = trip["trip_id"]
    check_in = trip["start_date"]
    check_out = (date.fromisoformat(check_in) + timedelta(days=2)).isoformat()
    response = client.post(
        f"/api/trips/{trip_id}/saved-options",
        json={
            "option_type": "hotel",
            "title": "Tokyo Inn",
            "amount": 24000,
            "currency": "JPY",
            "details": {
                "hotel_id": "stays_booking_hotel",
                "dates": {"check_in": check_in, "check_out": check_out},
                "nights": 2,
                "rooms": 1,
            },
        })
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["option"]["details"]["dates"]["check_in"] == check_in

    totals = client.get(
        f"/api/trips/{trip_id}/expenses/summary").get_json()
    assert totals["totals_by_kind_and_currency"]["planned"] == {
        "JPY": 24000.0,
    }

    outside_trip = trip["end_date"]
    invalid = client.post(
        f"/api/trips/{trip_id}/saved-options",
        json={
            "option_type": "hotel",
            "title": "Dates outside trip",
            "amount": 1000,
            "currency": "JPY",
            "details": {
                "dates": {
                    "check_in": outside_trip,
                    "check_out": (date.fromisoformat(outside_trip)
                                  + timedelta(days=1)).isoformat(),
                },
            },
        })
    assert invalid.status_code == 400


def test_saved_hotel_date_change_recalculates_estimate_and_trip_total(client):
    register(client)
    trip = _create_trip(client)
    trip_id = trip["trip_id"]
    check_in = trip["start_date"]
    original_check_out = (date.fromisoformat(check_in) + timedelta(days=2)).isoformat()
    updated_check_out = (date.fromisoformat(check_in) + timedelta(days=3)).isoformat()
    response = client.post(
        f"/api/trips/{trip_id}/saved-options",
        json={
            "option_type": "hotel",
            "title": "Tokyo Inn",
            "amount": 24000,
            "currency": "JPY",
            "details": {
                "price_per_night": 12000,
                "total_price": 24000,
                "currency": "JPY",
                "nights": 2,
                "dates": {
                    "check_in": check_in,
                    "check_out": original_check_out,
                },
            },
        },
    )
    assert response.status_code == 201, response.get_json()
    option_id = response.get_json()["option"]["option_id"]

    invalid = client.patch(
        f"/api/saved-options/{option_id}",
        json={"check_in": check_in, "check_out": check_in},
    )
    assert invalid.status_code == 400

    updated = client.patch(
        f"/api/saved-options/{option_id}",
        json={"check_in": check_in, "check_out": updated_check_out},
    )
    assert updated.status_code == 200, updated.get_json()
    option = updated.get_json()["option"]
    assert option["amount"] == 36000
    assert option["details"]["total_price"] is None
    assert option["details"]["nights"] == 3
    assert option["details"]["dates"]["check_out"] == updated_check_out

    expenses = client.get(
        f"/api/trips/{trip_id}/expenses").get_json()["expenses"]
    assert len(expenses) == 1
    assert expenses[0]["amount"] == 36000
    assert "taxes and fees may be additional" in expenses[0]["notes"]
    summary = client.get(
        f"/api/trips/{trip_id}/expenses/summary").get_json()
    assert summary["totals_by_kind_and_currency"]["planned"] == {
        "JPY": 36000,
    }

    removed = client.delete(f"/api/saved-options/{option_id}")
    assert removed.status_code == 200
    summary = client.get(
        f"/api/trips/{trip_id}/expenses/summary").get_json()
    assert summary["totals_by_kind_and_currency"]["planned"] == {}


def test_changed_hotel_dates_do_not_reuse_stale_total_without_nightly_rate(client):
    register(client)
    trip = _create_trip(client)
    trip_id = trip["trip_id"]
    check_in = trip["start_date"]
    original_check_out = (date.fromisoformat(check_in) + timedelta(days=2)).isoformat()
    updated_check_out = (date.fromisoformat(check_in) + timedelta(days=3)).isoformat()
    response = client.post(
        f"/api/trips/{trip_id}/saved-options",
        json={
            "option_type": "hotel",
            "title": "Hotel without nightly rate",
            "amount": 9000,
            "currency": "JPY",
            "details": {
                "currency": "JPY",
                "total_price": 9000,
                "dates": {
                    "check_in": check_in,
                    "check_out": original_check_out,
                },
            },
        },
    )
    assert response.status_code == 201, response.get_json()
    option_id = response.get_json()["option"]["option_id"]

    updated = client.patch(
        f"/api/saved-options/{option_id}",
        json={"check_in": check_in, "check_out": updated_check_out},
    )
    assert updated.status_code == 200, updated.get_json()
    assert updated.get_json()["option"]["amount"] is None
    assert updated.get_json()["option"]["details"]["total_price"] is None
    assert client.get(
        f"/api/trips/{trip_id}/expenses").get_json()["expenses"] == []
    summary = client.get(
        f"/api/trips/{trip_id}/expenses/summary").get_json()
    assert summary["totals_by_kind_and_currency"]["planned"] == {}
