"""Expense tests, with emphasis on correct currency handling."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.conftest import VALID_USER, login, register, switch_user, trip_payload

JSON = {"Accept": "application/json"}


def make_trip(client, **overrides) -> int:
    response = client.post("/api/trips", json=dict(trip_payload(), **overrides),
                           headers =JSON)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["trip"]["trip_id"]


def expense_payload(**overrides) -> dict:
    payload = {
        "expense_name": "Kinkaku-ji entry",
        "category": "entrance_fees",
        "amount": 8.50,
        "currency": "USD",
        "expense_date": (date.today() + timedelta(days=10)).isoformat(),
        "notes": "Paid by card.",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------- CRUD --
def test_add_expense(client):
    register(client)
    trip_id = make_trip(client)
    response = client.post(f"/api/trips/{trip_id}/expenses",
                           json=expense_payload(), headers=JSON)
    assert response.status_code == 201
    expense = response.get_json()["expense"]
    assert expense["amount"] == 8.50
    assert expense["currency"] == "USD"
    assert expense["category_label"] == "Entrance Fees"


def test_list_expenses(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(expense_name="Dinner"), headers=JSON)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(expense_name="Bus fare"), headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/expenses", headers=JSON).get_json()
    assert len(body["expenses"]) == 2


def test_filter_expenses_by_category(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(category="food"), headers=JSON)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(category="transportation"), headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/expenses?category=food",
                      headers=JSON).get_json()
    assert len(body["expenses"]) == 1


def test_update_expense(client):
    register(client)
    trip_id = make_trip(client)
    expense_id = client.post(f"/api/trips/{trip_id}/expenses",
                             json=expense_payload(),
                             headers=JSON).get_json()["expense"]["expense_id"]
    response = client.patch(f"/api/expenses/{expense_id}",
                            json={"amount": 12.00}, headers=JSON)
    assert response.status_code == 200
    body = response.get_json()["expense"]
    assert body["amount"] == 12.00
    assert body["expense_name"] == "Kinkaku-ji entry"    # preserved


def test_delete_expense(client):
    register(client)
    trip_id = make_trip(client)
    expense_id = client.post(f"/api/trips/{trip_id}/expenses",
                             json=expense_payload(),
                             headers=JSON).get_json()["expense"]["expense_id"]
    assert client.delete(f"/api/expenses/{expense_id}", headers=JSON).status_code == 200
    assert client.get(f"/api/expenses/{expense_id}", headers=JSON).status_code == 404


# --------------------------------------------------------------- totals ---
def test_total_for_single_currency(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=10.0), headers=JSON)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=15.5, expense_name="Taxi"), headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/expenses/summary", headers=JSON).get_json()
    assert body["totals_by_currency"] == {"USD": 25.5}
    assert body["grand_total_display"] == "25.50 USD"


def test_mixed_currencies_are_never_merged(client):
    """The core currency rule: different currencies stay separate."""
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=10.0, currency="USD"), headers=JSON)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=1500.0, currency="JPY",
                                    expense_name="Ryokan night"),
                headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/expenses/summary", headers=JSON).get_json()
    assert body["totals_by_currency"] == {"JPY": 1500.0, "USD": 10.0}
    assert "JPY" in body["grand_total_display"]
    assert "USD" in body["grand_total_display"]
    assert "1510" not in body["grand_total_display"]   # no bogus cross-currency sum


def test_summary_by_category(client):
    register(client)
    trip_id = make_trip(client)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(category="food", amount=20.0), headers=JSON)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(category="food", amount=5.0,
                                    expense_name="Snacks"), headers=JSON)
    body = client.get(f"/api/trips/{trip_id}/expenses/summary", headers=JSON).get_json()
    food = next(row for row in body["by_category"] if row["category"] == "food")
    assert food["totals"] == {"USD": 25.0}
    assert food["entries"] == 2


def test_empty_trip_reports_no_expenses(client):
    register(client)
    trip_id = make_trip(client)
    body = client.get(f"/api/trips/{trip_id}/expenses/summary", headers=JSON).get_json()
    assert body["totals_by_currency"] == {}
    assert body["grand_total_display"] == "No expenses yet"


# ------------------------------------------------------------- validation --
@pytest.mark.parametrize("amount", [0, -5, "abc", ""])
def test_invalid_amounts_are_rejected(client, amount):
    register(client)
    trip_id = make_trip(client)
    assert client.post(f"/api/trips/{trip_id}/expenses",
                       json=expense_payload(amount=amount),
                       headers=JSON).status_code == 400


def test_invalid_currency_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    assert client.post(f"/api/trips/{trip_id}/expenses",
                       json=expense_payload(currency="DOLLARS"),
                       headers=JSON).status_code == 400


def test_invalid_category_is_rejected(client):
    register(client)
    trip_id = make_trip(client)
    assert client.post(f"/api/trips/{trip_id}/expenses",
                       json=expense_payload(category="yachts"),
                       headers=JSON).status_code == 400


# ---------------------------------------------------------------- budget --
def test_trip_budget_is_saved(client):
    register(client)
    trip = client.post("/api/trips",
                       json=trip_payload(budget=1500, budget_currency="JPY"),
                       headers=JSON).get_json()["trip"]
    assert trip["budget"] == 1500.0
    assert trip["budget_currency"] == "JPY"


def test_trip_budget_defaults_to_usd(client):
    register(client)
    trip = client.post("/api/trips", json=trip_payload(budget=200),
                       headers=JSON).get_json()["trip"]
    assert trip["budget"] == 200.0
    assert trip["budget_currency"] == "USD"


def test_negative_budget_is_rejected(client):
    register(client)
    response = client.post("/api/trips", json=trip_payload(budget=-10), headers=JSON)
    assert response.status_code == 400
    assert response.get_json()["field"] == "budget"


def test_remaining_budget_is_calculated(client):
    register(client)
    trip_id = make_trip(client, budget=1000, budget_currency="USD")
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=250.0), headers=JSON)
    budget = client.get(f"/api/trips/{trip_id}/expenses/summary",
                        headers=JSON).get_json()["budget"]
    assert budget["budget"] == 1000.0
    assert budget["spent_in_budget_currency"] == 250.0
    assert budget["remaining"] == 750.0
    assert budget["is_over_budget"] is False


def test_budget_can_be_exceeded(client):
    register(client)
    trip_id = make_trip(client, budget=100, budget_currency="USD")
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=150.0), headers=JSON)
    budget = client.get(f"/api/trips/{trip_id}/expenses/summary",
                        headers=JSON).get_json()["budget"]
    assert budget["remaining"] == -50.0
    assert budget["is_over_budget"] is True


def test_other_currencies_are_excluded_from_remaining(client):
    """A JPY expense must not be subtracted from a USD budget."""
    register(client)
    trip_id = make_trip(client, budget=500, budget_currency="USD")
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=100.0), headers=JSON)
    client.post(f"/api/trips/{trip_id}/expenses",
                json=expense_payload(amount=50000.0, currency="JPY",
                                    expense_name="Ryokan"), headers=JSON)
    budget = client.get(f"/api/trips/{trip_id}/expenses/summary",
                        headers=JSON).get_json()["budget"]
    assert budget["remaining"] == 400.0
    assert budget["other_currencies"] == {"JPY": 50000.0}


def test_trip_without_budget_reports_null(client):
    register(client)
    trip_id = make_trip(client)
    budget = client.get(f"/api/trips/{trip_id}/expenses/summary",
                        headers=JSON).get_json()["budget"]
    assert budget["budget"] is None
    assert budget["remaining"] is None


# ---------------------------------------------------------- authorisation --
def test_cannot_access_another_users_expenses(client):
    register(client)
    trip_id = make_trip(client)
    expense_id = client.post(f"/api/trips/{trip_id}/expenses",
                             json=expense_payload(),
                             headers=JSON).get_json()["expense"]["expense_id"]
    switch_user(client, "other@wize.local")
    assert client.get(f"/api/expenses/{expense_id}", headers=JSON).status_code == 404
    assert client.delete(f"/api/expenses/{expense_id}", headers=JSON).status_code == 404


def test_update_expense(client):
    register(client)
    trip_id = make_trip(client)
    expense_id = client.post(f"/api/trips/{trip_id}/expenses",
                             json=expense_payload(),
                             headers=JSON).get_json()["expense"]["expense_id"]
    response = client.patch(f"/api/expenses/{expense_id}",
                            json={"amount": 12.00}, headers=JSON)
    assert response.status_code == 200
    body = response.get_json()["expense"]
    assert body["amount"] == 12.00
    assert body["expense_name"] == "Kinkaku-ji entry"    # preserved


def test_delete_expense(client):
    register(client)
    trip_id = make_trip(client)
    expense_id = client.post(f"/api/trips/{trip_id}/expenses",
                             json=expense_payload(),
                             headers=JSON).get_json()["expense"]["expense_id"]
    assert client.delete(f"/api/expenses/{expense_id}", headers=JSON).status_code == 200
    assert client.get(f"/api/expenses/{expense_id}", headers=JSON).status_code == 404