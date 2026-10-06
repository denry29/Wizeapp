"""Checklist, item and progress tests."""

from __future__ import annotations

from tests.conftest import VALID_USER, login, register, switch_user, trip_payload

JSON = {"Accept": "application/json"}


def make_trip(client, **overrides) -> int:
    response = client.post("/api/trips", json=dict(trip_payload(), **overrides),
                           headers=JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]["trip_id"]


def make_checklist(client, trip_id: int, name: str = "Packing") -> int:
    response = client.post(f"/api/trips/{trip_id}/checklists",
                           json={"checklist_name": name}, headers=JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["checklist"]["checklist_id"]


def add_item(client, checklist_id: int, name: str = "Passport") -> int:
    return client.post(f"/api/checklists/{checklist_id}/items",
                       json={"item_name": name},
                       headers=JSON).get_json()["item"]["item_id"]


# ------------------------------------------------------------- checklists --
def test_create_checklist(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(f"/api/trips/{trip_id}/checklists",
                           json={"checklist_name": "Packing"}, headers=JSON)
    assert response.status_code == 201
    assert response.get_json()["checklist"]["checklist_name"] == "Packing"


def test_duplicate_checklist_name_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    make_checklist(client, trip_id)
    response = client.post(f"/api/trips/{trip_id}/checklists",
                           json={"checklist_name": "Packing"}, headers=JSON)
    assert response.status_code == 400


def test_rename_checklist(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    response = client.patch(f"/api/checklists/{checklist_id}",
                            json={"checklist_name": "Documents"}, headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["checklist"]["checklist_name"] == "Documents"


def test_delete_checklist_removes_items(client, app, db):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    add_item(client, checklist_id)
    assert client.delete(f"/api/checklists/{checklist_id}",
                         headers=JSON).status_code == 200
    with app.app_context():
        assert db.scalar("SELECT COUNT(*) FROM checklist_items") == 0


# ------------------------------------------------------------------ items --
def test_add_item(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    response = client.post(f"/api/checklists/{checklist_id}/items",
                           json={"item_name": "Passport"}, headers=JSON)
    assert response.status_code == 201
    assert response.get_json()["item"]["item_name"] == "Passport"
    assert response.get_json()["item"]["is_completed"] is False


def test_toggle_item_completes_and_reopens(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    item_id = add_item(client, checklist_id)
    toggled = client.post(f"/api/checklist-items/{item_id}/toggle",
                          headers=JSON).get_json()["item"]
    assert toggled["is_completed"] is True
    again = client.post(f"/api/checklist-items/{item_id}/toggle",
                        headers=JSON).get_json()["item"]
    assert again["is_completed"] is False


def test_rename_item(client):
    register(client)
    trip_id = make_trip(client)
# --------------------------------------------------------------- progress --
def test_progress_is_calculated(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    first = add_item(client, checklist_id, "Passport")
    add_item(client, checklist_id, "Insurance")
    client.post(f"/api/checklist-items/{first}/toggle", headers=JSON)

    body = client.get(f"/api/trips/{trip_id}/checklists", headers=JSON).get_json()
    checklist = body["checklists"][0]
    assert checklist["item_count"] == 2
    assert checklist["completed_count"] == 1
    assert checklist["pending_count"] == 1
    assert checklist["progress_percent"] == 50
    assert checklist["is_complete"] is False
    assert body["progress"]["pending_items"] == 1


def test_checklist_is_complete_when_all_done(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    item_id = add_item(client, checklist_id, "Only item")
    client.post(f"/api/checklist-items/{item_id}/toggle", headers=JSON)
    checklist = client.get(f"/api/checklists/{checklist_id}",
                           headers=JSON).get_json()["checklist"]
    assert checklist["is_complete"] is True
    assert checklist["progress_percent"] == 100


def test_empty_checklist_progress_is_zero(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    checklist = client.get(f"/api/checklists/{checklist_id}",
                           headers=JSON).get_json()["checklist"]
    assert checklist["progress_percent"] == 0
    assert checklist["is_complete"] is False


# ---------------------------------------------------------- authorisation --
def test_cannot_manage_another_users_checklist(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    item_id = add_item(client, checklist_id)
    switch_user(client, "other@wize.local")
    assert client.get(f"/api/checklists/{checklist_id}",
                      headers=JSON).status_code == 404
    assert client.delete(f"/api/checklists/{checklist_id}",
                         headers=JSON).status_code == 404
    assert client.post(f"/api/checklist-items/{item_id}/toggle",
                       headers=JSON).status_code == 404


def test_rename_item(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    item_id = add_item(client, checklist_id, "Passprot")
    response = client.patch(f"/api/checklist-items/{item_id}",
                            json={"item_name": "Passport"}, headers=JSON)
    assert response.status_code == 200
    assert response.get_json()["item"]["item_name"] == "Passport"


def test_delete_item(client):
    register(client)
    trip_id = make_trip(client)
    checklist_id = make_checklist(client, trip_id)
    item_id = add_item(client, checklist_id)
    assert client.delete(f"/api/checklist-items/{item_id}",
                         headers=JSON).status_code == 200
    body = client.get(f"/api/checklists/{checklist_id}", headers=JSON).get_json()
    assert body["checklist"]["items"] == []