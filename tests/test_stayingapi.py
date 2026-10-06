"""StayingAPI adapter and Asia-only hotel route tests."""

from __future__ import annotations

import json
from datetime import date, timedelta

from services.stayingapi import StayingAPIClient
from tests.conftest import register


def test_client_sends_api_key_only_in_server_side_authorization_header(monkeypatch):
    requests = []

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({"data": [], "meta": {}}).encode()

    def fake_urlopen(request, timeout):
        requests.append(request)
        assert timeout == 20
        return Response()

    monkeypatch.setattr("services.stayingapi.urllib.request.urlopen", fake_urlopen)
    client = StayingAPIClient("test-only-key")

    response = client._request("/search", [])

    assert response["data"] == []
    assert requests[0].get_header("Cache-control") == "no-cache, no-store"
    assert requests[0].get_header("Pragma") == "no-cache"
    assert requests[0].get_header("Authorization") == "Bearer test-only-key"


def test_search_maps_only_provider_supplied_hotel_fields(monkeypatch):
    client = StayingAPIClient("test-only-key")
    calls = []

    def fake_request(path, params):
        calls.append((path, dict(params)))
        return {
            "_http_status": 200,
            "data": [{
                "id": "stays_booking_opaque",
                "platformListingId": "opaque",
                "platform": "booking",
                "url": "https://booking.example/stay",
                "name": "Real Tokyo Hotel",
                "location": {"city": "Tokyo", "country": "JP"},
                "images": [
                    "https://images.example/hotel.jpg?width=800",
                    "https://images.example/hotel-2.jpg",
                ],
                "guestRating": 8.8,
                "ratingScale": 10,
                "reviewCount": 241,
                "propertyType": "hotel",
                "maxOccupancy": 4,
                "amenities": ["wifi"],
                "price": {
                    "currency": "JPY",
                    "nightlyPrice": 12000,
                    "totalPrice": 24000,
                    "nights": 2,
                    "fees": {"cleaning": 400, "taxes": 2000},
                },
            }],
            "meta": {"creditsCharged": 5},
        }

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.search_hotels(
        "Tokyo", "JP", "2099-03-10", "2099-03-12", adults=2,
        rooms=1, children=1, child_ages=[8], currency="PHP")

    hotel = result["hotels"][0]
    assert calls[0][0] == "/search"
    assert calls[0][1]["location"] == "Tokyo, JP"
    assert calls[0][1]["platforms"] == "booking,google"
    assert calls[0][1]["propertyType[]"] == "hotel"
    assert calls[0][1]["childAges[]"] == 8
    assert hotel["images"] == [
        "https://images.example/hotel.jpg?width=800",
        "https://images.example/hotel-2.jpg",
    ]
    assert hotel["image_url"] == "https://images.example/hotel.jpg?width=800"
    assert hotel["rating"] == 8.8
    assert hotel["rating_scale"] == 10
    assert hotel["review_count"] == 241
    assert hotel["price_per_night"] == 12000
    assert hotel["total_price"] == 24000
    assert hotel["currency"] == "JPY"
    assert hotel["nights"] == 2
    assert hotel["rooms"] == 1
    assert hotel["taxes"] == 2000
    assert hotel["fees"] == {"cleaning": 400}
    assert hotel["property_type"] == "hotel"
    assert hotel["max_occupancy"] == 4
    assert hotel["description"] is None
    assert hotel["availability"] is None


def test_search_endpoint_returns_provider_image_urls_unchanged(
        client, monkeypatch):
    register(client)
    image_urls = [
        "https://cf.bstatic.com/example.jpg?width=800&token=preserve",
        "https://cf.bstatic.com/example-2.jpg",
    ]

    class SearchResult:
        def search_hotels(self, **params):
            assert params["city"] == "Tokyo"
            assert params["country_code"] == "JP"
            return {
                "hotels": [{
                    "hotel_id": "provider-id",
                    "name": "Provider hotel",
                    "images": image_urls,
                    "image_url": image_urls[0],
                }],
                "meta": {},
            }

    monkeypatch.setattr("routes.hotel_routes._client", SearchResult)
    check_in = date.today() + timedelta(days=10)
    check_out = check_in + timedelta(days=2)
    response = client.get(
        f"/api/hotels/search?city=Tokyo&country=JP"
        f"&check_in={check_in.isoformat()}&check_out={check_out.isoformat()}")

    assert response.status_code == 200
    hotel = response.get_json()["hotels"][0]
    assert hotel["images"] == image_urls
    assert hotel["image_url"] == image_urls[0]


def test_live_search_polls_jobs_until_result(monkeypatch):
    client = StayingAPIClient("test-only-key", max_job_wait=10)
    responses = iter([
        {"_http_status": 202, "_retry_after": "1",
         "data": {"jobId": "job_123", "status": "pending"}},
        {"_http_status": 200, "meta": {"creditsCharged": 5},
         "data": {"status": "completed", "result": [{
             "id": "stays_booking_1", "name": "Live result",
             "platform": "booking",
         }]}},
    ])
    calls = []
    monkeypatch.setattr(
        client, "_request",
        lambda path, params: (calls.append(path) or next(responses)))
    monkeypatch.setattr("services.stayingapi.time.sleep", lambda _: None)

    result = client.search_hotels(
        "Tokyo", "JP", "2099-03-10", "2099-03-12")

    assert calls == ["/search", "/jobs/job_123"]
    assert result["hotels"][0]["name"] == "Live result"
    assert result["meta"] == {"creditsCharged": 5}


def test_hotel_page_renders_without_api_key_and_keeps_key_server_side(
        client, app, monkeypatch):
    register(client)
    app.config["STAYING_API_KEY"] = "test-only-secret"

    response = client.get("/hotels")

    assert response.status_code == 200
    assert b"Find a place to stay in Asia" in response.data
    assert b"Japan" in response.data
    assert b"test-only-secret" not in response.data


def test_hotel_search_rejects_non_asian_destination_before_provider_call(
        client, monkeypatch):
    register(client)

    def unexpected_call():
        raise AssertionError("The provider must not be called for non-Asia.")

    monkeypatch.setattr("routes.hotel_routes._client", unexpected_call)
    check_in = date.today() + timedelta(days=10)
    check_out = check_in + timedelta(days=2)
    response = client.get(
        f"/api/hotels/search?city=Paris&country=FR"
        f"&check_in={check_in.isoformat()}&check_out={check_out.isoformat()}")

    assert response.status_code == 400
    assert "Asia" in response.get_json()["error"]
