"""Trip CRUD, validation, authorisation and cascade tests."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import (VALID_USER, login, logout, register, switch_user,
                            trip_payload)

JSON = {"Accept": "application/json"}


def make_trip(client, **overrides) -> int:
    """Create a trip through the API and return its id."""
    response = client.post("/api/trips", json=dict(trip_payload(), **overrides),
                           headers=JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]["trip_id"]


def switch_user(client, email):
    """Sign out, then register/sign in a second user."""
    logout(client)
    register(client, email=email)


# ------------------------------------------------------------------- CRUD --
def test_create_trip(client):
    register(client)
    response = client.post("/api/trips", json=trip_payload(), headers=JSON)
    assert response.status_code == 201
    trip = response.get_json()["trip"]
    assert trip["trip_name"] == "Kyoto in Spring"
    assert trip["status"] == "planning"
    assert trip["duration_days"] == 8


def test_list_trips(client):
    register(client)
    make_trip(client)
    make_trip(client, trip_name="Osaka Trip")
    body = client.get("/api/trips", headers=JSON).get_json()
    assert body["pagination"]["total"] == 2
    assert {t["trip_name"] for t in body["trips"]} == {"Kyoto in Spring", "Osaka Trip"}


def test_get_trip_detail(client):
    register(client)
    trip_id = make_trip(client)
    response = client.get(f"/api/trips/{trip_id}", headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["trip"]["trip_id"] == trip_id


def test_update_trip(client):
    register(client)
# ------------------------------------------------------------- validation --
def test_end_date_before_start_date_is_rejected(client):
    register(client)
    response = client.post("/api/trips", json=trip_payload(
        start_date=(date.today() + timedelta(days=10)).isoformat(),
        end_date=(date.today() + timedelta(days=2)).isoformat()), headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "end_date"


def test_invalid_date_format_is_rejected(client):
    register(client)
    response = client.post("/api/trips", json=trip_payload(start_date="01/01/2030"),
                           headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "start_date"


def test_missing_trip_name_is_rejected(client):
    register(client)
    payload = trip_payload()
    payload.pop("trip_name")
    response = client.post("/api/trips", json=payload, headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "trip_name"


def test_unknown_status_is_rejected(client):
    register(client)
    response = client.post("/api/trips", json=trip_payload(status="teleporting"),
                           headers=JSON)
    assert response.status_code == 400


def test_overlong_trip_is_rejected(client):
    register(client)
    response = client.post("/api/trips", json=trip_payload(
        end_date=(date.today() + timedelta(days=400)).isoformat()), headers=JSON)
    assert response.status_code == 400


# ---------------------------------------------------------- authorisation --
def test_user_cannot_see_another_users_trip(client):
    """A second user gets 404 (not 403) so trip ids cannot be enumerated."""
    register(client)
    trip_id = make_trip(client)
    switch_user(client, "other@wize.local")
    assert client.get(f"/api/trips/{trip_id}", headers=JSON).status_code == 404


def test_user_cannot_update_another_users_trip(client):
    register(client)
    trip_id = make_trip(client)
    switch_user(client, "other@wize.local")
    assert client.patch(f"/api/trips/{trip_id}", json={"trip_name": "Hijacked"},
                        headers=JSON).status_code == 404


def test_user_cannot_delete_another_users_trip(client):
    register(client)
    trip_id = make_trip(client)
    switch_user(client, "other@wize.local")
    assert client.delete(f"/api/trips/{trip_id}", headers=JSON).status_code == 404


def test_trip_list_only_shows_own_trips(client):
    register(client)
    make_trip(client)
    switch_user(client, "other@wize.local")
    body = client.get("/api/trips", headers=JSON).get_json()
    assert body["pagination"]["total"] == 0


# ------------------------------------------------------------ html pages ---
def test_trip_pages_render(client):
    register(client)
    trip_id = make_trip(client)
    assert client.get("/trips").status_code == 200
    assert client.get(f"/trips/{trip_id}").status_code == 200
    assert client.get("/trips/new").status_code == 200
    trip_id = make_trip(client)
    response = client.patch(f"/api/trips/{trip_id}",
                            json={"trip_name": "Kyoto Autumn"}, headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["trip"]["trip_name"] == "Kyoto Autumn"


def test_delete_trip(client):
    register(client)
    trip_id = make_trip(client)
    assert client.delete(f"/api/trips/{trip_id}", headers=JSON).status_code == 200
    assert client.get(f"/api/trips/{trip_id}", headers=JSON).status_code == 404


def test_update_keeps_unspecified_fields(client):
    register(client)
    trip_id = make_trip(client)
    client.patch(f"/api/trips/{trip_id}", json={"status": "completed"}, headers=JSON)
    trip = client.get(f"/api/trips/{trip_id}", headers=JSON).get_json()["trip"]
    assert trip["trip_name"] == "Kyoto in Spring"
    assert trip["status"] == "completed"