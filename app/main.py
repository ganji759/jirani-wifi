"""The web app."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import routes_admin, routes_public, scheduler
from app.config import load_settings
from app.web import State


def create_app(state: State | None = None, run_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = scheduler.start(app.state.jirani.billing) if run_scheduler else None
        yield
        if stop:
            stop.set()

    app = FastAPI(title="Jirani Wi-Fi", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.jirani = state or State(load_settings())
    app.include_router(routes_public.router)
    app.include_router(routes_admin.router)
    return app
