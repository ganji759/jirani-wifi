"""Shared parts of the website: app state, templates, time and QR helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, create_engine

from app.billing import Billing
from app.config import Settings
from app.slot import SlotManager

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class State:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        self.slot = SlotManager(settings)
        self.billing = Billing(self.engine, self.slot)
        self.tz = ZoneInfo(settings.timezone)

    def local(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(self.tz).strftime("%d %b %Y, %H:%M")


def time_left(ends_at: datetime) -> str:
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    seconds = int((ends_at - datetime.now(timezone.utc)).total_seconds())
    if seconds <= 0:
        return "0 min"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


def wifi_qr_svg(ssid: str, password: str) -> str:
    """QR code that a phone camera reads to join the Wi-Fi."""
    text = f"WIFI:T:WPA;S:{ssid};P:{password};;"
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    return image.to_string(encoding="unicode")
