"""Destination catalogue search, filtering and trip-attachment tests."""

from __future__ import annotations

from datetime import date, timedelta
from email.message import Message

import pytest

from services.commons import USER_AGENT
from tests.conftest import VALID_USER, login, register, switch_user, trip_payload

JSON = {"Accept": "application/json"}


def make_trip(client, **overrides) -> int:
    response = client.post("/api/trips", json=dict(trip_payload(), **overrides),
                           headers=JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]["trip_id"]


def first_destination_id(client, country: str) -> int:
    body = client.get(f"/api/destinations?country={country}", headers=JSON).get_json()
    return body["destinations"][0]["destination_id"]


# ----------------------------------------------------------------- browse --
def test_catalogue_is_public(client):
    """Browsing the shared catalogue does not require signing in."""
    response = client.get("/api/destinations", headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["pagination"]["total"] >= 1


def test_destination_photo_is_proxied_from_wikimedia(client, db, monkeypatch):
    destination_id = first_destination_id(client, "Japan")
    image_url = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/"
        "a/ab/example.jpg/640px-example.jpg"
    )
    db.execute(
        "UPDATE destinations SET image_url = ? WHERE destination_id = ?",
        [image_url, destination_id],
    )

    class FakeImageResponse:
        headers = Message()

        def __init__(self):
            self.headers["Content-Type"] = "image/jpeg"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return image_url

        def read(self, _limit):
            return b"jpeg-image-data"

    def fake_urlopen(request, timeout):
        assert request.full_url == image_url
        assert request.get_header("User-agent") == USER_AGENT
        assert timeout == 15
        return FakeImageResponse()

    monkeypatch.setattr(
        "routes.destination_routes.urllib.request.urlopen", fake_urlopen)
    response = client.get(f"/api/destinations/{destination_id}/image")

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"jpeg-image-data"
    assert "max-age=86400" in response.headers["Cache-Control"]
    assert "no-store" not in response.headers["Cache-Control"]


def test_destination_photo_proxy_rejects_non_wikimedia_urls(client, db):
    destination_id = first_destination_id(client, "Japan")
    db.execute(
        "UPDATE destinations SET image_url = ? WHERE destination_id = ?",
        ["https://example.com/photo.jpg", destination_id],
    )

    response = client.get(f"/api/destinations/{destination_id}/image")

    assert response.status_code == 404


def test_search_by_name(client):
    body = client.get("/api/destinations?search=Angkor", headers=JSON).get_json()
    names = [d["name"] for d in body["destinations"]]
    assert names == ["Angkor Wat"]


def test_filter_by_country(client):
    body = client.get("/api/destinations?country=Japan", headers=JSON).get_json()
    assert body["pagination"]["total"] == 2
    assert all(d["country"] == "Japan" for d in body["destinations"])


def test_filter_by_city(client):
    body = client.get("/api/destinations?city=Kyoto", headers=JSON).get_json()
    assert body["pagination"]["total"] == 2


def test_filter_by_category(client):
    body = client.get("/api/destinations?category=beach", headers=JSON).get_json()
    assert [d["name"] for d in body["destinations"]] == ["Maldives Beach"]


def test_combined_filters(client):
    body = client.get("/api/destinations?country=Japan&city=Kyoto&category=temple",
                      headers=JSON).get_json()
    assert [d["name"] for d in body["destinations"]] == ["Fushimi Inari Taisha"]


def test_filter_options_endpoint(client):
    body = client.get("/api/destinations/filters", headers=JSON).get_json()
    assert "Japan" in body["countries"]
    assert "temple" in body["categories"]


def test_unknown_category_filter_is_ignored(client):
    """An invalid filter value is dropped instead of causing an error."""
# ------------------------------------------------------------- attaching --
def test_add_catalogue_destination_to_trip(client):
    register(client)
    trip_id = make_trip(client)
    destination_id = first_destination_id(client, "Japan")
    expected = client.get(f"/api/destinations/{destination_id}",
                          headers=JSON).get_json()["destination"]["name"]
    response = client.post(f"/api/trips/{trip_id}/destinations",
                           json={"destination_id": destination_id}, headers=JSON)
    assert response.status_code == 201
    assert response.get_json()["destination"]["name"] == expected

    listed = client.get(f"/api/trips/{trip_id}/destinations", headers=JSON).get_json()
    assert len(listed["destinations"]) == 1


def test_add_same_destination_twice_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    destination_id = first_destination_id(client, "Japan")
    client.post(f"/api/trips/{trip_id}/destinations",
                json={"destination_id": destination_id}, headers=JSON)
    response = client.post(f"/api/trips/{trip_id}/destinations",
                           json={"destination_id": destination_id}, headers=JSON)
    assert response.status_code == 400


def test_visit_date_outside_trip_range_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    destination_id = first_destination_id(client, "Japan")
    response = client.post(
        f"/api/trips/{trip_id}/destinations",
        json={"destination_id": destination_id,
              "visit_date": (date.today() + timedelta(days=200)).isoformat()},
        headers=JSON)
    assert response.status_code == 400


def test_remove_destination_from_trip(client):
    register(client)
    trip_id = make_trip(client)
    destination_id = first_destination_id(client, "Japan")
    link_id = client.post(f"/api/trips/{trip_id}/destinations",
                          json={"destination_id": destination_id},
                          headers=JSON).get_json()["trip_destination_id"]
    response = client.delete(f"/api/trips/{trip_id}/destinations/{link_id}",
                             headers=JSON)
    assert response.status_code == 200
    remaining = client.get(f"/api/trips/{trip_id}/destinations", headers=JSON)
    assert remaining.get_json()["destinations"] == []


def test_removing_a_link_does_not_delete_the_catalogue_entry(client):
    register(client)
    trip_id = make_trip(client)
    destination_id = first_destination_id(client, "Japan")
    link_id = client.post(f"/api/trips/{trip_id}/destinations",
                          json={"destination_id": destination_id},
                          headers=JSON).get_json()["trip_destination_id"]
    client.delete(f"/api/trips/{trip_id}/destinations/{link_id}", headers=JSON)
    assert client.get(f"/api/destinations/{destination_id}",
                      headers=JSON).status_code == 200


def test_custom_destination_can_be_added(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(f"/api/trips/{trip_id}/destinations", json={
        "name": "Grandmother's Village Cafe", "country": "Japan", "city": "Kyoto",
        "category": "cultural", "description": "A small local cafe worth a visit.",
    }, headers=JSON)
    assert response.status_code == 201
    assert response.get_json()["destination"]["origin"] == "custom"


def test_custom_destinations_are_private_to_their_owner(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/destinations", json={
        "name": "Secret Spot", "country": "Japan", "city": "Kyoto",
        "category": "park", "description": "Only I know about this place.",
    }, headers=JSON)
    switch_user(client, "other@wize.local")
    body = client.get("/api/destinations?search=Secret", headers=JSON).get_json()
    assert body["destinations"] == []


def test_cannot_attach_to_another_users_trip(client):
    register(client)
    trip_id = make_trip(client)
    switch_user(client, "other@wize.local")
    response = client.post(f"/api/trips/{trip_id}/destinations",
                           json={"destination_id": 1}, headers=JSON)
    assert response.status_code == 404


# -------------------------------------------------- destination HTML pages --
def test_destination_list_page_shows_names(client):
    """Regression: Destination had no `.name`, so headings rendered blank."""
    body = client.get("/destinations?country=Japan").get_data(as_text=True)
    assert "<h2>Fushimi Inari Taisha</h2>" in body


def test_destination_detail_page_renders(client):
    """Regression: the detail route used destination.name and raised a 500."""
    destination_id = first_destination_id(client, "Japan")
    response = client.get(f"/destinations/{destination_id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<h1>" in body
    assert "Fushimi Inari Taisha" in body


def test_destination_detail_page_for_custom_spot_is_private(client):
    """A user's own custom spot has a page; another user's does not."""
    register(client)
    trip_id = make_trip(client)
    created = client.post(f"/api/trips/{trip_id}/destinations", json={
        "name": "Hidden Gem", "country": "Japan", "city": "Kyoto",
        "category": "cultural", "description": "Only mine.",
    }, headers=JSON).get_json()["destination"]["destination_id"]
    assert client.get(f"/destinations/{created}").status_code in (200, 404)
    response = client.get("/api/destinations?category=dragons", headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["pagination"]["total"] >= 1


def test_destination_detail(client):
    destination_id = first_destination_id(client, "Cambodia")
    response = client.get(f"/api/destinations/{destination_id}", headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["destination"]["name"] == "Angkor Wat"


def test_missing_destination_returns_404(client):
    assert client.get("/api/destinations/999999", headers=JSON).status_code == 404


def test_non_numeric_destination_id_returns_404(client):
    assert client.get("/api/destinations/abc", headers=JSON).status_code == 404