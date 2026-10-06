"""User domain model."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from models.base import BaseModel


class User(BaseModel):
    """A registered traveller.

    OOP - Encapsulation: ``password_hash`` can only be set through
    ``set_password`` (which hashes it) and is never returned by
    ``serialize()``, so it cannot leak into a JSON response by accident.
    """

    primary_key = "user_id"

    def __init__(self, user_id: int | None = None, full_name: str = "",
                 email: str = "", password_hash: str = "",
                 created_at: str | None = None, **extra: Any) -> None:
        super().__init__(
            user_id=user_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            created_at=created_at,
            **extra,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "User":
        data = dict(row)
        return cls(
            user_id=data.get("user_id"),
            full_name=data.get("full_name", ""),
            email=data.get("email", ""),
            password_hash=data.get("password_hash", ""),
            created_at=data.get("created_at"),
            email_verified=bool(data.get("email_verified", 1)),
            email_verified_at=data.get("email_verified_at"),
            last_login_at=data.get("last_login_at"),
        )

    def serialize(self) -> dict[str, Any]:
        """Public representation - the password hash is intentionally absent."""
        return {
            "user_id": self.get("user_id"),
            "full_name": self.get("full_name"),
            "email": self.get("email"),
            "created_at": self.get("created_at"),
            "email_verified": bool(self.get("email_verified", True)),
            "email_verified_at": self.get("email_verified_at"),
        }

    # ------------------------------------------------- encapsulation -------
    @property
    def user_id(self) -> int | None:
        return self.get("user_id")

    @property
    def email(self) -> str:
        return self.get("email", "")

    @property
    def full_name(self) -> str:
        return self.get("full_name", "")

    @property
    def password_hash(self) -> str:
        return self.get("password_hash", "")

    @property
    def email_verified(self) -> bool:
        return bool(self.get("email_verified", True))

    def initials(self) -> str:
        """Helper used by the mobile UI avatar."""
        parts = [p for p in self.full_name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()