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


def test_edit_plan(client):
    client.post("/admin/plans", data={"name": "1 hour", "minutes": 60, "price": 1000}, auth=ADMIN)
    assert client.get("/admin/plans/1/edit", auth=ADMIN).status_code == 200
    client.post("/admin/plans/1/edit", data={"name": "2 hours", "minutes": 120, "price": 1500}, auth=ADMIN)
    assert "1,500 UGX" in client.get("/").text
    assert "2 hours" in client.get("/").text


def test_delete_plan_without_tokens(client):
    client.post("/admin/plans", data={"name": "1 hour", "minutes": 60, "price": 1000}, auth=ADMIN)
    page = client.post("/admin/plans/1/delete", auth=ADMIN)
    assert "Plan deleted." in page.text
    assert "1 hour" not in client.get("/").text


def test_delete_plan_with_tokens_is_refused(client):
    client.post("/admin/plans", data={"name": "1 hour", "minutes": 60, "price": 1000}, auth=ADMIN)
    client.post("/admin/tokens", data={"plan_id": 1, "count": 1}, auth=ADMIN)
    page = client.post("/admin/plans/1/delete", auth=ADMIN)
    assert "cannot delete" in page.text
    assert "1 hour" in client.get("/").text


def _make_token(client):
    client.post("/admin/plans", data={"name": "1 hour", "minutes": 60, "price": 1000}, auth=ADMIN)
    made = client.post("/admin/tokens", data={"plan_id": 1, "count": 1}, auth=ADMIN, follow_redirects=False)
    return made.headers["location"].split("new=")[1]


def test_use_token_from_admin(client):
    code = _make_token(client)
    page = client.post(f"/admin/tokens/{code}/use", auth=ADMIN)
    assert "Your Wi-Fi is on" in page.text
    assert f"<code>{code}</code></td>" not in page.text
    assert client.app.state.jirani.slot.calls[0][0] == "on"


def test_delete_unused_token(client):
    code = _make_token(client)
    page = client.post(f"/admin/tokens/{code}/delete", auth=ADMIN)
    assert "deleted" in page.text
    assert "does not exist" in client.post("/redeem", data={"code": code}).text


def test_cannot_delete_used_token(client):
    code = _make_token(client)
    client.post("/redeem", data={"code": code})
    assert "only unused" in client.post(f"/admin/tokens/{code}/delete", auth=ADMIN).text
