"""Tests for the web pages. A fake slot replaces the router."""

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from app.billing import Billing
from app.config import Settings
from app.main import create_app
from app.web import State
from tests.test_billing import FakeSlot

ADMIN = ("admin", "secret")


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        router_host="test", router_user="u", router_pass="p", slot_index=2,
        slot_ssid="Jirani-1", admin_pass="secret", timezone="Africa/Kampala",
        currency="UGX", data_dir=tmp_path,
    )
    state = State.__new__(State)
    state.settings = settings
    state.engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(state.engine)
    state.slot = FakeSlot()
    state.billing = Billing(state.engine, state.slot)
    state.tz = ZoneInfo(settings.timezone)
    with TestClient(create_app(state, run_scheduler=False)) as c:
        yield c


def test_admin_needs_password(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401
    assert client.get("/admin", auth=ADMIN).status_code == 200


def test_full_flow(client):
    client.post("/admin/plans", data={"name": "1 hour", "minutes": 60, "price": 1000}, auth=ADMIN)
    home = client.get("/")
    assert "1,000 UGX" in home.text
    assert "The guest Wi-Fi is off" in home.text

    made = client.post("/admin/tokens", data={"plan_id": 1, "count": 1}, auth=ADMIN, follow_redirects=False)
    code = made.headers["location"].split("new=")[1]

    page = client.post("/redeem", data={"code": code})
    assert "Your Wi-Fi is on" in page.text
    assert "Jirani-1" in page.text
    assert client.app.state.jirani.slot.calls[0][0] == "on"

    again = client.post("/redeem", data={"code": code})
    assert "already used" in again.text

    client.post("/admin/stop", auth=ADMIN)
    assert client.app.state.jirani.slot.calls[-1] == ("off",)


def test_admin_start_and_restore(client):
    client.post("/admin/plans", data={"name": "1 day", "minutes": 1440, "price": 3000}, auth=ADMIN)
    client.post("/admin/start", data={"plan_id": 1}, auth=ADMIN)
    assert "Your Wi-Fi is on" in client.get("/admin", auth=ADMIN).text
    client.post("/admin/restore", auth=ADMIN)
    assert client.app.state.jirani.slot.calls[-1] == ("restore",)
    assert "Guest Wi-Fi is off" in client.get("/admin", auth=ADMIN).text
