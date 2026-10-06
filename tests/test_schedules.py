"""Itinerary / schedule tests including date-window validation."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from tests.conftest import VALID_USER, login, register, switch_user, trip_payload

JSON = {"Accept": "application/json"}

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def make_trip(client, **overrides) -> int:
    response = client.post("/api/trips", json=dict(trip_payload(), **overrides),
                           headers=JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]["trip_id"]


def activity_payload(**overrides) -> dict:
    """Activity dated inside the default trip window."""
    payload = {
        "activity_name": "Visit Fushimi Inari at sunrise",
        "activity_date": (date.today() + timedelta(days=11)).isoformat(),
        "start_time": "07:00",
        "end_time": "09:30",
        "notes": "Go early to avoid the crowds.",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------- CRUD --
def test_add_activity(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(f"/api/trips/{trip_id}/schedules",
                           json=activity_payload(), headers=JSON)
    assert response.status_code == 201
    activity = response.get_json()["schedule"]
    assert activity["activity_name"] == "Visit Fushimi Inari at sunrise"
    assert activity["duration_minutes"] == 150
    assert activity["time_label"] == "07:00 - 09:30"


def test_list_itinerary_is_sorted_by_date(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/schedules",
                json=activity_payload(activity_name="Later"), headers=JSON)
    client.post(f"/api/trips/{trip_id}/schedules",
                json=activity_payload(activity_name="Sooner",
                                      activity_date=(date.today() +
                                                     timedelta(days=10)).isoformat()),
                headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/schedules", headers=JSON).get_json()
    assert [a["activity_name"] for a in body["schedules"]] == ["Sooner", "Later"]


def test_filter_itinerary_by_day(client):
    register(client)
    trip_id = make_trip(client)
    day_one = (date.today() + timedelta(days=10)).isoformat()
    day_two = (date.today() + timedelta(days=11)).isoformat()
    client.post(f"/api/trips/{trip_id}/schedules",
                json=activity_payload(activity_date=day_one), headers=JSON)
    client.post(f"/api/trips/{trip_id}/schedules",
                json=activity_payload(activity_date=day_two), headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/schedules?day={day_one}",
                      headers=JSON).get_json()
    assert len(body["schedules"]) == 1


def test_update_activity(client):
    register(client)
    trip_id = make_trip(client)
    schedule_id = client.post(f"/api/trips/{trip_id}/schedules",
                              json=activity_payload(),
                              headers=JSON).get_json()["schedule"]["schedule_id"]
    response = client.patch(f"/api/schedules/{schedule_id}",
                            json={"activity_name": "Renamed activity"}, headers=JSON)
    assert response.status_code == 200
    body = response.get_json()["schedule"]
    assert body["activity_name"] == "Renamed activity"
    assert body["start_time"] == "07:00"          # untouched field survives


def test_delete_activity(client):
    register(client)
    trip_id = make_trip(client)
    schedule_id = client.post(f"/api/trips/{trip_id}/schedules",
                              json=activity_payload(),
                              headers=JSON).get_json()["schedule"]["schedule_id"]
    assert client.delete(f"/api/schedules/{schedule_id}", headers=JSON).status_code == 200
    assert client.get(f"/api/schedules/{schedule_id}", headers=JSON).status_code == 404


# ------------------------------------------------------------- validation --
def test_activity_date_outside_trip_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(
        f"/api/trips/{trip_id}/schedules",
        json=activity_payload(activity_date=(date.today() +
                                             timedelta(days=99)).isoformat()),
        headers=JSON)
    assert response.status_code == 400


def test_end_time_before_start_time_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(f"/api/trips/{trip_id}/schedules",
                           json=activity_payload(start_time="18:00", end_time="09:00"),
                           headers=JSON)
    assert response.status_code == 400


def test_malformed_time_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(f"/api/trips/{trip_id}/schedules",
                           json=activity_payload(start_time="9am"), headers=JSON)
    assert response.status_code == 400


def test_missing_activity_name_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    payload = activity_payload()
    payload.pop("activity_name")
    assert client.post(f"/api/trips/{trip_id}/schedules",
                       json=payload, headers=JSON).status_code == 400


# --------------------------------------------- itinerary page renders ----
def test_trip_detail_page_renders_with_balanced_html(client):
    """The trip page must not contain unclosed blocks.

    Regression: the "Add a custom destination" <form> and its <details>
    wrapper were never closed, which swallowed the rest of the document.
    """
    register(client)
    trip_id = make_trip(client)
    body = client.get(f"/trips/{trip_id}").get_data(as_text=True)
    assert body.count("<section") == body.count("</section>")
    assert body.count("<details") == body.count("</details>")
    assert body.count("<form") == body.count("</form>")


def test_trip_detail_page_contains_every_section(client):
    register(client)
    trip_id = make_trip(client)
    body = client.get(f"/trips/{trip_id}").get_data(as_text=True)
    assert 'id="destinations"' in body
    assert 'id="itinerary"' in body
    assert 'id="expenses"' in body
    assert 'id="checklists"' in body
    assert 'id="c_country"' in body          # custom-destination form survives


def test_templates_contain_no_inline_style_attributes(client):
    """Templates must not interpolate Jinja into a ``style`` attribute.

    ``style="width: {{ ... }}"`` is valid Jinja but the CSS linter reads the
    attribute as a stylesheet, sees ``{{`` where a property value belongs and
    reports "property value expected". Dynamic widths belong in the stylesheet
    or in a ``<progress>`` element instead.
    """
    register(client)
    make_trip(client)
    for path in TEMPLATE_DIR.glob("**/*.html"):
        source = path.read_text(encoding="utf-8")
        assert "style=" not in source, f"inline style in {path.name}"


def test_trip_detail_page_renders_progress_bar(client):
    """Checklist progress renders a <progress> element with a numeric value."""
    register(client)
    trip_id = make_trip(client)
    checklist = client.post(f"/api/trips/{trip_id}/checklists",
                            json={"checklist_name": "Packing"},
                            headers=JSON).get_json()["checklist"]["checklist_id"]
    item_id = client.post(f"/api/checklists/{checklist}/items",
                          json={"item_name": "Passport"},
                          headers=JSON).get_json()["item"]["item_id"]
    client.post(f"/api/checklist-items/{item_id}/toggle", headers=JSON)

    body = client.get(f"/trips/{trip_id}").get_data(as_text=True)
    assert "<progress" in body
    assert 'max="100"' in body
    assert 'value="100"' in body
    assert "style=" not in body              # no inline styles leak into the page


def test_itinerary_is_ordered_by_time_within_a_day(client):
    """Activities are sequenced by start_time regardless of insertion order."""
    register(client)
    trip_id = make_trip(client)
    day = (date.today() + timedelta(days=11)).isoformat()
    for label, time in (("Late", "14:00"), ("Early", "09:00"), ("Middle", "11:00")):
        client.post(f"/api/trips/{trip_id}/schedules",
                    json={"activity_name": label, "activity_date": day,
                          "start_time": time}, headers=JSON)
    body = client.get(f"/trips/{trip_id}").get_data(as_text=True)
    assert body.index("Early") < body.index("Middle") < body.index("Late")


def test_untimed_activity_is_listed_last_in_its_day(client):
    register(client)
    trip_id = make_trip(client)
    day = (date.today() + timedelta(days=11)).isoformat()
    client.post(f"/api/trips/{trip_id}/schedules",
                json={"activity_name": "Timed one", "activity_date": day,
                      "start_time": "09:00"}, headers=JSON)
    client.post(f"/api/trips/{trip_id}/schedules",
                json={"activity_name": "No time given", "activity_date": day},
                headers=JSON)
    body = client.get(f"/trips/{trip_id}").get_data(as_text=True)
    assert body.index("Timed one") < body.index("No time given")


def test_itinerary_day_number_matches_trip_start(client):
    register(client)
    trip_id = make_trip(client)          # starts in 10 days
    client.post(f"/api/trips/{trip_id}/schedules", json={
        "activity_name": "First day", "activity_date": trip_payload()["start_date"],
    }, headers=JSON)
    body = client.get(f"/trips/{trip_id}").get_data(as_text=True)
    assert "First day" in body
    days = client.get(f"/api/trips/{trip_id}/schedules", headers=JSON).get_json()
    assert days["schedules"][0]["activity_date"] == trip_payload()["start_date"]


# ---------------------------------------------------------- authorisation --
def test_cannot_add_activity_to_another_users_trip(client):
    register(client)
    trip_id = make_trip(client)
    switch_user(client, "other@wize.local")
    assert client.post(f"/api/trips/{trip_id}/schedules",
                       json=activity_payload(), headers=JSON).status_code == 404


def test_cannot_manage_another_users_activity(client):
    register(client)
    trip_id = make_trip(client)
    schedule_id = client.post(f"/api/trips/{trip_id}/schedules",
                              json=activity_payload(),
                              headers=JSON).get_json()["schedule"]["schedule_id"]
    switch_user(client, "other@wize.local")
    assert client.get(f"/api/schedules/{schedule_id}", headers=JSON).status_code == 404
    assert client.delete(f"/api/schedules/{schedule_id}", headers=JSON).status_code == 404


def test_activity_can_reference_a_destination(client):
    register(client)
    trip_id = make_trip(client)
    destination_id = client.get("/api/destinations?country=Japan",
                                headers=JSON).get_json()["destinations"][0]["destination_id"]
    expected = client.get(f"/api/destinations/{destination_id}",
                          headers=JSON).get_json()["destination"]["name"]
    response = client.post(f"/api/trips/{trip_id}/schedules",
                           json=activity_payload(destination_id=destination_id),
                           headers=JSON)
    assert response.status_code == 201
    assert response.get_json()["schedule"]["destination_name"] == expected