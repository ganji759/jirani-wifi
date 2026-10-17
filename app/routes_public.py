"""Pages for neighbors."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Form, Request
from sqlmodel import Session, select

from app.billing import BillingError
from app.models import Plan
from app.router_client import RouterError
from app.web import templates, time_left, wifi_qr_svg

router = APIRouter()


def _page(request: Request, **extra):
    state = request.app.state.jirani
    with Session(state.engine) as db:
        current = state.billing.active_session(db)
        plans = db.exec(select(Plan).where(Plan.active).order_by(Plan.minutes)).all()
    context = {
        "active": current is not None,
        "plans": plans,
        "currency": state.settings.currency,
    }
    if current:
        context["left"] = time_left(current.ends_at)
        context["ends"] = state.local(current.ends_at)
    context.update(extra)
    return templates.TemplateResponse(request, "home.html", context)


@router.get("/")
def home(request: Request):
    return _page(request)


@router.post("/redeem")
def redeem(request: Request, code: str = Form(...)):
    state = request.app.state.jirani
    try:
        session = state.billing.redeem(code)
    except BillingError as exc:
        return _page(request, error=str(exc))
    except (RouterError, httpx.HTTPError):
        return _page(request, error="The router did not answer. Your token is still good. Try again soon.")
    ssid = state.settings.slot_ssid
    return _page(
        request,
        wifi=True,
        ssid=ssid,
        password=session.password,
        qr=wifi_qr_svg(ssid, session.password),
        ends=state.local(session.ends_at),
        left=time_left(session.ends_at),
    )
