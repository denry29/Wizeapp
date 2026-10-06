"""Destination catalogue browsing, filtering and trip attachment."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import current_app

from managers.base_manager import BaseManager, NotFoundError
from models.destination import Destination, normalise_name
from services import validation


class DestinationManager(BaseManager):
    """Searches the shared Asian catalogue and manages trip attachments.

    OOP note: this manager is the only place that knows how a catalogue
    destination differs from a user-created one (``is_custom`` flag).  The
    catalogue is never deleted by a user - only their own custom rows are.
    """

    table = "destinations"
    primary_key = "destination_id"
    owner_column = None                    # catalogue rows have no owner
    model = Destination
    writable_fields = ("name", "name_key", "country", "city", "category",
                       "description", "image_url", "estimated_entrance_fee",
                       "currency", "is_custom", "user_id")

    def _to_model(self, row: sqlite3.Row | None) -> Destination | None:
        """Polymorphic factory - returns Destination or CustomDestination."""
        return Destination.from_row(row) if row is not None else None

    # ---------------------------------------------------------- catalogue ---
    def search_catalogue(self, search: str | None = None, country: str | None = None,
                         city: str | None = None, category: str | None = None,
                         page: int = 1, per_page: int = 12) -> dict[str, Any]:
        """Browse/filter the 300+ attraction catalogue with pagination."""
        clauses = ["is_custom = 0", "is_listed = 1"]
        params: list[Any] = []

        search = validation.clean_optional(search, 80)
        if search:
            clauses.append("(name LIKE ? OR description LIKE ? OR city LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])
        if country:
            clauses.append("country = ? COLLATE NOCASE")
            params.append(validation.clean(country))
        if city:
            clauses.append("city = ? COLLATE NOCASE")
            params.append(validation.clean(city))
        category = validation.optional_choice(category,
                                             current_app.config["DESTINATION_CATEGORIES"])
        if category:
            clauses.append("category = ?")
            params.append(category)

        where = " AND ".join(clauses)
        total = int(self.db.scalar(
            f"SELECT COUNT(*) FROM destinations WHERE {where}", params))
        per_page = min(max(1, int(per_page)), 100)
        page = max(1, int(page))
        offset = (page - 1) * per_page
        rows = self.db.query_all(
            f"SELECT * FROM destinations WHERE {where} "
            f"ORDER BY country, city, name LIMIT ? OFFSET ?",
            [*params, per_page, offset])
        return {
            "items": self._to_models(rows),
            "page": page, "per_page": per_page, "total": total,
            "pages": max(1, (total + per_page - 1) // per_page),
            "has_next": offset + per_page < total,
            "has_prev": page > 1,
        }

    def catalogue_total(self) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM destinations "
            "WHERE is_custom = 0 AND is_listed = 1"))

    def distinct_countries(self) -> list[str]:
        rows = self.db.query_all(
            "SELECT DISTINCT country FROM destinations "
            "WHERE is_custom = 0 AND is_listed = 1 "
            "AND country IS NOT NULL AND TRIM(country) <> '' ORDER BY country")
        return [row["country"] for row in rows]

    def cities_for_country(self, country: str) -> list[str]:
        rows = self.db.query_all(
            "SELECT DISTINCT city FROM destinations "
            "WHERE is_custom = 0 AND is_listed = 1 "
            "AND country = ? COLLATE NOCASE AND city IS NOT NULL "
            "ORDER BY city", [validation.clean(country)])
        return [row[0] for row in rows]

    def get_catalogue_destination(self, destination_id: int) -> Destination:
        """Fetch a catalogue entry; custom rows of other users stay invisible."""
        destination_id = validation.positive_int(destination_id, "destination_id")
        model = self._select_one(
            "destination_id = ? AND is_custom = 0 AND is_listed = 1",
            [destination_id])
        if model is None:
            raise NotFoundError("Destination not found.", "destination")
        return model

    # ---------------------------------------------------- custom entries ----
    def create_custom(self, user_id: int, payload: dict[str, Any]) -> Destination:
        """Add a user-invented destination, then return it."""
        data = validation.validate_destination(
            payload, current_app.config["DESTINATION_CATEGORIES"],
            current_app.config["SUPPORTED_CURRENCIES"])
        data["name_key"] = normalise_name(data["name"])
        data["is_custom"] = 1
        data["user_id"] = user_id

        duplicate = self._select_one(
            "name_key = ? AND country = ? COLLATE NOCASE AND city IS ?",
            [data["name_key"], data["country"], data["city"]])
        if duplicate is not None:
            raise validation.ValidationError(
                "You already have a destination with this name in that place.",
                "name")
        return self.create(data, user_id)
# ----------------------------------------------- trip attachment ------
    def attach_to_trip(self, trip_id: int, user_id: int, payload: dict[str, Any]
                       ) -> dict[str, Any]:
        """Link a catalogue destination (or create a new custom one) to a trip.

        The trip is checked against ``user_id`` first, so a user can never
        attach anything to somebody else's trip - not even when no visit date
        is supplied.
        """
        if trip_id not in self._user_trip_ids(user_id):
            raise NotFoundError("Trip not found.", "trip")

        destination_id = validation.positive_int(
            payload.get("destination_id"), "destination_id", default=0)

        if destination_id:
            destination = self.get_catalogue_destination(destination_id)
        else:
            destination = self.create_custom(user_id, payload)

        visit_date = validation.clean(payload.get("visit_date")) or None
        if visit_date and not validation.is_valid_date(visit_date):
            raise validation.ValidationError("Visit date must be a valid YYYY-MM-DD date.",
                                             "visit_date")
        self._assert_visit_date(trip_id, visit_date)

        exists = self.db.query_one(
            "SELECT trip_destination_id FROM trip_destinations "
            "WHERE trip_id = ? AND destination_id = ?", [trip_id, destination.destination_id])
        if exists is not None:
            raise validation.ValidationError(
                "That destination is already on this trip.", "destination_id")

        sequence = validation._optional_int(payload.get("sequence_number"),
                                           "sequence_number")
        if sequence is None:
            sequence = int(self.db.scalar(
                "SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM trip_destinations "
                "WHERE trip_id = ?", [trip_id]))
        notes = validation.clean_optional(payload.get("notes"), 500)

        self.db.execute(
            "INSERT INTO trip_destinations "
            "(trip_id, destination_id, visit_date, notes, sequence_number) "
            "VALUES (?, ?, ?, ?, ?)",
            [trip_id, destination.destination_id, visit_date, notes, sequence])
        return {"destination": destination,
                "trip_destination_id": int(self.db.scalar("SELECT last_insert_rowid()"))}

    def _assert_visit_date(self, trip_id: int, visit_date: str | None) -> None:
        """A visit date must sit inside the trip window."""
        if not visit_date:
            return
        row = self.db.query_one(
            "SELECT start_date, end_date FROM trips WHERE trip_id = ?", [trip_id])
        if row is None:
            raise NotFoundError("Trip not found.", "trip")
        if not (row["start_date"] <= visit_date <= row["end_date"]):
            raise validation.ValidationError(
                f"Visit date must be between {row['start_date']} and {row['end_date']}.",
                "visit_date")

    def list_for_trip(self, trip_id: int) -> list[dict[str, Any]]:
        """All destinations of a trip, ordered by visit sequence."""
        rows = self.db.query_all(
            """
            SELECT d.*, td.trip_destination_id, td.visit_date,
                   td.notes AS trip_notes, td.sequence_number
            FROM trip_destinations td
            JOIN destinations d ON d.destination_id = td.destination_id
            WHERE td.trip_id = ?
            ORDER BY COALESCE(td.visit_date, '9999-12-31'), td.sequence_number
            """, [trip_id])
        items: list[dict[str, Any]] = []
        for row in rows:
            destination = Destination.from_row(row)
            payload = destination.serialize() | {
                "trip_destination_id": row["trip_destination_id"],
                "visit_date": row["visit_date"],
                "notes": row["trip_notes"],
                "sequence_number": row["sequence_number"],
            }
            items.append({"destination": destination, "payload": payload,
                          "trip_destination_id": row["trip_destination_id"]})
        return items

    def detach_from_trip(self, trip_id: int, link_id: int, user_id: int) -> bool:
        """Remove a destination from a trip (the catalogue entry survives)."""
        if trip_id not in self._user_trip_ids(user_id):
            raise NotFoundError("Trip not found.", "trip")
        link_id = validation.positive_int(link_id, "trip_destination_id")
        row = self.db.query_one(
            "SELECT 1 FROM trip_destinations WHERE trip_destination_id = ? AND trip_id = ?",
            [link_id, trip_id])
        if row is None:
            raise NotFoundError("That destination is not on this trip.", "trip_destination")
        self.db.execute("DELETE FROM trip_destinations WHERE trip_destination_id = ?",
                        [link_id])
        return True

    def update_trip_link(self, trip_id: int, link_id: int, user_id: int,
                         payload: dict[str, Any]) -> dict[str, Any]:
        """Edit the visit date / notes / sequence of an attached destination."""
        if trip_id not in self._user_trip_ids(user_id):
            raise NotFoundError("Trip not found.", "trip")
        link_id = validation.positive_int(link_id, "trip_destination_id")

        visit_date = validation.clean(payload.get("visit_date")) or None
        if visit_date and not validation.is_valid_date(visit_date):
            raise validation.ValidationError("Visit date must be a valid YYYY-MM-DD date.",
                                             "visit_date")
        self._assert_visit_date(trip_id, visit_date)

        updates: dict[str, Any] = {
            "visit_date": visit_date,
            "notes": validation.clean_optional(payload.get("notes"), 500),
        }
        sequence = validation._optional_int(payload.get("sequence_number"),
                                           "sequence_number")
        if sequence is not None:
            updates["sequence_number"] = sequence
        assignments = ", ".join(f"{k} = ?" for k in updates)
        self.db.execute(
            f"UPDATE trip_destinations SET {assignments} WHERE trip_destination_id = ?",
            [*updates.values(), link_id])
        return {"trip_destination_id": link_id, **updates}

    def count_for_trip(self, trip_id: int) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM trip_destinations WHERE trip_id = ?", [trip_id]))

    def _user_trip_ids(self, user_id: int) -> list[int]:
        rows = self.db.query_all("SELECT trip_id FROM trips WHERE user_id = ?", [user_id])
        return [row[0] for row in rows]
