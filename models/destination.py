"""Destination domain models.

OOP - Polymorphism (the meaningful case in this project)
    ``Destination`` covers the shared Asian catalogue.
    ``CustomDestination`` is the user-created variant stored in the same table
    (``is_custom = 1``).  Both share the ``BaseModel`` interface, so the
    ``DestinationManager`` can return a mixed list and templates/JSON treat
    both identically, while each subclass supplies its own ``serialize`` /
    ``origin`` information.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from typing import Any, Mapping

from models.base import BaseModel


def normalise_name(name: str) -> str:
    """Lower-cased, accent-free, punctuation-free key used for de-duplication.

    ``Kinkaku-ji``, ``kinkakuji`` and ``Kinkaku Ji`` all collapse to the same
    ``name_key`` so the UNIQUE constraint in SQLite blocks duplicates.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(name))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped.lower())
    return " ".join(cleaned.split())


class Destination(BaseModel):
    """A tourist attraction from the shared catalogue."""

    primary_key = "destination_id"

    def __init__(self, destination_id: int | None = None, name: str = "",
                 country: str = "", city: str | None = None,
                 category: str = "other", description: str | None = None,
                 image_url: str | None = None,
                 estimated_entrance_fee: float | None = None,
                 currency: str | None = None, is_custom: int = 0,
                 user_id: int | None = None,
                 created_at: str | None = None, **extra: Any) -> None:
        super().__init__(
            destination_id=destination_id, name=name, country=country,
            city=city, category=category, description=description,
            image_url=image_url, estimated_entrance_fee=estimated_entrance_fee,
            currency=currency, is_custom=is_custom, user_id=user_id,
            created_at=created_at, **extra,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "Destination":
        """Polymorphic factory: returns a CustomDestination when required."""
        data = dict(row)
        if int(data.get("is_custom") or 0) == 1:
            return CustomDestination.from_dict(data)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Destination":
        known = {
            "destination_id", "name", "name_key", "country", "city", "category",
            "description", "image_url", "estimated_entrance_fee", "currency",
            "is_custom", "user_id", "created_at",
            # Attribution for the Commons photo, filled by
            # scripts/fetch_destination_images.py.  Listed explicitly so they
            # appear in serialize() instead of leaking through `extra`.
            "image_title", "image_creator", "image_source_url",
            "image_license", "image_license_url", "image_attribution",
            "is_listed", "best_time_to_visit", "recommended_duration",
            "latitude", "longitude",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            destination_id=data.get("destination_id"),
            name=data.get("name", ""), country=data.get("country", ""),
            city=data.get("city"), category=data.get("category", "other"),
            description=data.get("description"), image_url=data.get("image_url"),
            estimated_entrance_fee=data.get("estimated_entrance_fee"),
            currency=data.get("currency"),
            is_custom=int(data.get("is_custom") or 0),
            user_id=data.get("user_id"),
            created_at=data.get("created_at"),
            image_title=data.get("image_title"),
            image_creator=data.get("image_creator"),
            image_source_url=data.get("image_source_url"),
            image_license=data.get("image_license"),
            image_license_url=data.get("image_license_url"),
            image_attribution=data.get("image_attribution"),
            **extra,
        )

    # ------------------------------------------------------ polymorphism ----
    def serialize(self) -> dict[str, Any]:
        payload = {
            "destination_id": self.get("destination_id"),
            "name": self.get("name"),
            "country": self.get("country"),
            "city": self.get("city"),
            "category": self.get("category"),
            "description": self.get("description"),
            "image_url": self.get("image_url"),
            "estimated_entrance_fee": self.get("estimated_entrance_fee"),
            "currency": self.get("currency"),
            "is_custom": bool(self.get("is_custom")),
            "origin": self.origin,
            # Attribution for the reused Commons photo (all NULL when the
            # destination still shows the placeholder).
            "image_title": self.get("image_title"),
            "image_creator": self.get("image_creator"),
            "image_source_url": self.get("image_source_url"),
            "image_license": self.get("image_license"),
            "image_license_url": self.get("image_license_url"),
            "image_attribution": self.get("image_attribution"),
            "best_time_to_visit": self.get("best_time_to_visit"),
            "recommended_duration": self.get("recommended_duration"),
            "latitude": self.get("latitude"),
            "longitude": self.get("longitude"),
        }
        payload.update(self.extra_fields())
        return payload

    def extra_fields(self) -> dict[str, Any]:
        """Extra context (join columns such as visit_date) - base returns {}."""
        return {}

    @property
    def origin(self) -> str:
        return "custom" if int(self.get("is_custom") or 0) == 1 else "catalogue"

    @property
    def destination_id(self) -> int | None:
        return self.get("destination_id")

    @property
    def name(self) -> str:
        """Attraction name.

        Exposed as a property so routes and templates can write
        ``destination.name`` instead of ``destination.get("name")``.
        """
        return self.get("name", "")

    @property
    def country(self) -> str:
        return self.get("country", "")

    @property
    def city(self) -> str:
        return self.get("city") or ""

    @property
    def category(self) -> str:
        return self.get("category", "other")

    @property
    def name_key(self) -> str:
        return normalise_name(self.get("name", ""))

    def location_label(self) -> str:
        city, country = self.get("city"), self.get("country")
        return f"{city}, {country}" if city else str(country or "")

    def fee_label(self) -> str:
        fee, currency = self.get("estimated_entrance_fee"), self.get("currency")
        if fee in (None, ""):
            return "Fee not available"
        return f"{float(fee):,.0f} {currency}" if currency else f"{float(fee):,.2f}"


class CustomDestination(Destination):
    """A destination invented by a user for one of their own trips."""

    def serialize(self) -> dict[str, Any]:
        payload = super().serialize()
        payload["owner_user_id"] = self.get("user_id")
        return payload