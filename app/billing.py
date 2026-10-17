"""Tokens and Wi-Fi time.

A token holds a plan, for example 1 hour. When a neighbor redeems a token:
  - If the guest Wi-Fi is off, the app turns it on with a new password.
  - If the guest Wi-Fi is on, the app adds the time to the open session.
When the time ends, tick() turns the guest Wi-Fi off.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional, Protocol

from sqlmodel import Session, select

from app.models import Plan, Token, WifiSession, utcnow
from app.slot import new_password

# No 0, O, 1, I or L, so codes are easy to read out loud.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class SlotControl(Protocol):
    def turn_on(self, password: str) -> None: ...
    def turn_off(self) -> None: ...


class BillingError(Exception):
    pass


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    raw = code.strip().upper().replace("-", "").replace(" ", "")
    return f"{raw[:4]}-{raw[4:]}"


class Billing:
    def __init__(self, engine, slot: SlotControl) -> None:
        self.engine = engine
        self.slot = slot
        # One router change at a time.
        self._lock = threading.Lock()

    def create_tokens(self, plan_id: int, count: int, note: str = "") -> list[str]:
        with Session(self.engine) as db:
            if db.get(Plan, plan_id) is None:
                raise BillingError("unknown plan")
            codes = []
            for _ in range(count):
                code = new_code()
                db.add(Token(code=code, plan_id=plan_id, note=note))
                codes.append(code)
            db.commit()
            return codes

    def active_session(self, db: Session, now: Optional[datetime] = None) -> Optional[WifiSession]:
        now = now or utcnow()
        stmt = select(WifiSession).where(WifiSession.ended_at.is_(None))
        current = db.exec(stmt).first()
        if current and current.ends_at > now:
            return current
        return None

    def redeem(self, code: str, now: Optional[datetime] = None) -> WifiSession:
        now = now or utcnow()
        with self._lock, Session(self.engine) as db:
            token = db.get(Token, normalize_code(code))
            if token is None:
                raise BillingError("This token does not exist.")
            if token.used_at is not None:
                raise BillingError("This token is already used.")
            plan = db.get(Plan, token.plan_id)
            minutes = timedelta(minutes=plan.minutes)

            current = self.active_session(db, now)
            if current:
                current.ends_at += minutes
            else:
                current = WifiSession(password=new_password(), started_at=now, ends_at=now + minutes)
                # Turn on first. If the router fails, the token stays unused.
                self.slot.turn_on(current.password)
            token.used_at = now
            db.add(token)
            db.add(current)
            db.commit()
            db.refresh(current)
            return current

    def stop(self, now: Optional[datetime] = None) -> None:
        """End the open session now."""
        now = now or utcnow()
        with self._lock, Session(self.engine) as db:
            open_session = db.exec(select(WifiSession).where(WifiSession.ended_at.is_(None))).first()
            self.slot.turn_off()
            if open_session:
                open_session.ended_at = now
                db.add(open_session)
                db.commit()

    def tick(self, now: Optional[datetime] = None) -> bool:
        """Turn the guest Wi-Fi off when time is up. Return True if it did."""
        now = now or utcnow()
        with Session(self.engine) as db:
            open_session = db.exec(select(WifiSession).where(WifiSession.ended_at.is_(None))).first()
            if open_session is None or open_session.ends_at > now:
                return False
        self.stop(now)
        return True
