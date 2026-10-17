"""Database tables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Plan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    minutes: int
    price: int
    active: bool = True


class Token(SQLModel, table=True):
    code: str = Field(primary_key=True)
    plan_id: int = Field(foreign_key="plan.id")
    created_at: datetime = Field(default_factory=utcnow)
    used_at: Optional[datetime] = None
    note: str = ""


class WifiSession(SQLModel, table=True):
    """One period when the guest Wi-Fi is on. Tokens can make it longer."""

    id: Optional[int] = Field(default=None, primary_key=True)
    password: str
    started_at: datetime = Field(default_factory=utcnow)
    ends_at: datetime
    ended_at: Optional[datetime] = None
