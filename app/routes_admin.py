"""Pages for the owner. Protected by the ADMIN_PASS setting."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session, select

from app.billing import BillingError
from app.models import Plan, Token, WifiSession
from app.router_client import RouterError
from app.web import templates, time_left, wifi_qr_svg

security = HTTPBasic()


def require_admin(request: Request, credentials: HTTPBasicCredentials = Depends(security)) -> None:
    expected = request.app.state.jirani.settings.admin_pass.encode()
    if not secrets.compare_digest(credentials.password.encode(), expected):
        raise HTTPException(401, "Wrong password", headers={"WWW-Authenticate": "Basic"})


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _back(message: str = "", error: str = "") -> RedirectResponse:
    params = {"msg": message} if message else ({"err": error} if error else {})
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"/admin{query}", status_code=303)


@router.get("")
def dashboard(request: Request, msg: str = "", err: str = "", new: str = ""):
    state = request.app.state.jirani
    with Session(state.engine) as db:
        current = state.billing.active_session(db)
        plans = db.exec(select(Plan).order_by(Plan.minutes)).all()
        unused = db.exec(select(Token).where(Token.used_at.is_(None)).order_by(Token.created_at.desc())).all()
        history = db.exec(select(WifiSession).order_by(WifiSession.started_at.desc()).limit(10)).all()
    plan_names = {p.id: p.name for p in plans}
    context = {
        "msg": msg,
        "err": err,
        "new_codes": [c for c in new.split(",") if c],
        "plans": plans,
        "plan_names": plan_names,
        "unused": unused,
        "history": history,
        "currency": state.settings.currency,
        "ssid": state.settings.slot_ssid,
        "local": state.local,
        "backup_exists": state.settings.backup_file.exists(),
    }
    if current:
        context.update(
            wifi=True,
            password=current.password,
            qr=wifi_qr_svg(state.settings.slot_ssid, current.password),
            ends=state.local(current.ends_at),
            left=time_left(current.ends_at),
        )
    return templates.TemplateResponse(request, "admin.html", context)


@router.post("/plans")
def add_plan(request: Request, name: str = Form(...), minutes: int = Form(...), price: int = Form(...)):
    if minutes <= 0 or price < 0:
        return _back(error="Minutes must be more than 0 and price cannot be less than 0.")
    with Session(request.app.state.jirani.engine) as db:
        db.add(Plan(name=name.strip(), minutes=minutes, price=price))
        db.commit()
    return _back("Plan added.")


@router.get("/plans/{plan_id}/edit")
def edit_plan_page(request: Request, plan_id: int):
    with Session(request.app.state.jirani.engine) as db:
        plan = db.get(Plan, plan_id)
    if plan is None:
        return _back(error="Plan not found.")
    return templates.TemplateResponse(
        request, "plan_edit.html", {"plan": plan, "currency": request.app.state.jirani.settings.currency}
    )


@router.post("/plans/{plan_id}/edit")
def edit_plan(
    request: Request, plan_id: int, name: str = Form(...), minutes: int = Form(...), price: int = Form(...)
):
    if minutes <= 0 or price < 0:
        return _back(error="Minutes must be more than 0 and price cannot be less than 0.")
    with Session(request.app.state.jirani.engine) as db:
        plan = db.get(Plan, plan_id)
        if plan is None:
            return _back(error="Plan not found.")
        plan.name = name.strip()
        plan.minutes = minutes
        plan.price = price
        db.add(plan)
        db.commit()
    return _back("Plan changed.")


@router.post("/plans/{plan_id}/delete")
def delete_plan(request: Request, plan_id: int):
    with Session(request.app.state.jirani.engine) as db:
        plan = db.get(Plan, plan_id)
        if plan is None:
            return _back(error="Plan not found.")
        if db.exec(select(Token).where(Token.plan_id == plan_id)).first():
            return _back(error="This plan has tokens, so you cannot delete it. Hide it instead.")
        db.delete(plan)
        db.commit()
    return _back("Plan deleted.")


@router.post("/plans/{plan_id}/toggle")
def toggle_plan(request: Request, plan_id: int):
    with Session(request.app.state.jirani.engine) as db:
        plan = db.get(Plan, plan_id)
        if plan:
            plan.active = not plan.active
            db.add(plan)
            db.commit()
    return _back("Plan changed.")


@router.post("/tokens")
def make_tokens(request: Request, plan_id: int = Form(...), count: int = Form(1), note: str = Form("")):
    count = max(1, min(count, 50))
    try:
        codes = request.app.state.jirani.billing.create_tokens(plan_id, count, note.strip())
    except BillingError as exc:
        return _back(error=str(exc))
    return RedirectResponse(f"/admin?new={','.join(codes)}", status_code=303)


@router.post("/start")
def start(request: Request, plan_id: int = Form(...)):
    """Make a token and use it at once, for a neighbor who paid you directly."""
    billing = request.app.state.jirani.billing
    try:
        code = billing.create_tokens(plan_id, 1, "started by admin")[0]
        billing.redeem(code)
    except BillingError as exc:
        return _back(error=str(exc))
    except (RouterError, httpx.HTTPError) as exc:
        return _back(error=f"Router problem: {exc}")
    return _back("Guest Wi-Fi is on.")


@router.post("/tokens/{code}/use")
def use_token(request: Request, code: str):
    """Use a token for the neighbor, for example after they pay you."""
    try:
        request.app.state.jirani.billing.redeem(code)
    except BillingError as exc:
        return _back(error=str(exc))
    except (RouterError, httpx.HTTPError) as exc:
        return _back(error=f"Router problem: {exc}")
    return _back(f"Token {code} used. Guest Wi-Fi is on.")


@router.post("/tokens/{code}/delete")
def delete_token(request: Request, code: str):
    with Session(request.app.state.jirani.engine) as db:
        token = db.get(Token, code)
        if token is None or token.used_at is not None:
            return _back(error="You can delete only unused tokens.")
        db.delete(token)
        db.commit()
    return _back(f"Token {code} deleted.")


@router.post("/stop")
def stop(request: Request):
    try:
        request.app.state.jirani.billing.stop()
    except (RouterError, httpx.HTTPError) as exc:
        return _back(error=f"Router problem: {exc}")
    return _back("Guest Wi-Fi is off.")


@router.post("/restore")
def restore(request: Request):
    try:
        request.app.state.jirani.billing.restore()
    except (RouterError, httpx.HTTPError) as exc:
        return _back(error=f"Router problem: {exc}")
    return _back("The Wi-Fi slot is back to its original settings.")
