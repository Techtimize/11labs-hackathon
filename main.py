"""AuthRelay control plane. Run with `uvicorn main:app`.

Builds the app, opens the store for its lifetime, stamps every response as synthetic,
and mounts the routers. Everything else lives in the layers below.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from api.dependencies import build_store
from api.v1 import call, health, review, tools, webhooks
from core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the store on startup, close it on shutdown."""
    app.state.store = build_store(settings.database_path)
    try:
        yield
    finally:
        app.state.store.close()


app = FastAPI(title="AuthRelay control plane", version="0.5.0", lifespan=lifespan)


@app.middleware("http")
async def data_mode_header(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Data-Mode"] = "synthetic"
    return resp


# Same order the routes were declared in before the split.
for module in (tools, call, review, webhooks, health):
    app.include_router(module.router)
