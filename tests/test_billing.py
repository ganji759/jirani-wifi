"""Tests for tokens and Wi-Fi time. A fake slot replaces the router."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.billing import Billing, BillingError, normalize_code
from app.models import Plan

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


class FakeSlot:
    def __init__(self):
        self.calls = []

    def turn_on(self, password):
        self.calls.append(("on", password))

    def turn_off(self):
        self.calls.append(("off",))


@pytest.fixture
def setup():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Plan(name="1 hour", minutes=60, price_kes=1))
        db.commit()
    slot = FakeSlot()
    return Billing(engine, slot), slot


def test_redeem_turns_wifi_on(setup):
    billing, slot = setup
    code = billing.create_tokens(1, 1)[0]
    session = billing.redeem(code, now=T0)
    assert session.ends_at == T0 + timedelta(minutes=60)
    assert slot.calls == [("on", session.password)]


def test_token_works_once(setup):
    billing, _ = setup
    code = billing.create_tokens(1, 1)[0]
    billing.redeem(code, now=T0)
    with pytest.raises(BillingError):
        billing.redeem(code, now=T0)


def test_unknown_token(setup):
    billing, _ = setup
    with pytest.raises(BillingError):
        billing.redeem("AAAA-BBBB", now=T0)


def test_second_token_adds_time(setup):
    billing, slot = setup
    a, b = billing.create_tokens(1, 2)
    first = billing.redeem(a, now=T0)
    second = billing.redeem(b, now=T0 + timedelta(minutes=10))
    assert second.id == first.id
    assert second.ends_at == T0 + timedelta(minutes=120)
    assert len(slot.calls) == 1


def test_tick_turns_wifi_off_at_end(setup):
    billing, slot = setup
    billing.redeem(billing.create_tokens(1, 1)[0], now=T0)
    assert billing.tick(now=T0 + timedelta(minutes=59)) is False
    assert billing.tick(now=T0 + timedelta(minutes=60)) is True
    assert slot.calls[-1] == ("off",)
    assert billing.tick(now=T0 + timedelta(minutes=61)) is False


def test_router_failure_keeps_token_unused(setup):
    billing, slot = setup
    code = billing.create_tokens(1, 1)[0]

    def broken(password):
        raise RuntimeError("router down")

    slot.turn_on = broken
    with pytest.raises(RuntimeError):
        billing.redeem(code, now=T0)
    slot.turn_on = FakeSlot().turn_on
    billing.redeem(code, now=T0)


def test_normalize_code():
    assert normalize_code(" abcd efgh ") == "ABCD-EFGH"
