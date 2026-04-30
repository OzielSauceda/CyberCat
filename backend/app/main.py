from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.correlation  # noqa: F401 — registers all correlators
import app.detection  # noqa: F401 — registers all detectors
from app.api.admin import router as admin_router
from app.api.routers import attack as attack_router
from app.api.routers import blocked_observables as blocked_observables_router
from app.api.routers import detections as detections_router
from app.api.routers import entities as entities_router
from app.api.routers import events as events_router
from app.api.routers import evidence_requests as evidence_requests_router
from app.api.routers import incidents as incidents_router
from app.api.routers import lab_assets as lab_assets_router
from app.api.routers import responses as responses_router
from app.api.routers import streaming as streaming_router
from app.api.routers import wazuh as wazuh_router
from app.auth.oidc import discover_oidc
from app.auth.router import router as auth_router
from app.config import settings
from app.db.redis import close_redis, get_redis, init_redis
from app.db.session import AsyncSessionLocal, get_db
from app.ingest.wazuh_poller import poller_loop
from app.seeder import maybe_seed
from app.streaming.bus import close_bus, init_bus


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Phase 19 A1.1: bump asyncio's default thread executor so concurrent
    # getaddrinfo() calls during a Redis/Wazuh outage don't queue up. Python's
    # default is min(32, cpu_count + 4); on a 4-core lab box that's 8, which is
    # exhausted by a few simultaneous DNS lookups (each ~3.6s on NXDOMAIN).
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=64))
    await init_redis()
    await init_bus()
    app.state.oidc = await discover_oidc()
    stop_event = asyncio.Event()
    poller_task = None
    if settings.wazuh_bridge_enabled:
        poller_task = asyncio.create_task(poller_loop(stop_event))
    if settings.cct_autoseed_demo:
        asyncio.create_task(maybe_seed(AsyncSessionLocal, get_redis()))
    yield
    stop_event.set()
    if poller_task is not None:
        try:
            await asyncio.wait_for(poller_task, timeout=10)
        except TimeoutError:
            poller_task.cancel()
    await close_bus()
    await close_redis()


app = FastAPI(
    title="CyberCat",
    description="Threat-informed automated incident response platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router, prefix="/v1")
app.include_router(events_router.router, prefix="/v1")
app.include_router(incidents_router.router, prefix="/v1")
app.include_router(responses_router.router, prefix="/v1")
app.include_router(lab_assets_router.router, prefix="/v1")
app.include_router(attack_router.router, prefix="/v1")
app.include_router(entities_router.router, prefix="/v1")
app.include_router(detections_router.router, prefix="/v1")
app.include_router(wazuh_router.router, prefix="/v1")
app.include_router(evidence_requests_router.router, prefix="/v1")
app.include_router(blocked_observables_router.router, prefix="/v1")
app.include_router(streaming_router.router, prefix="/v1")
app.include_router(admin_router, prefix="/v1")


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    return {"status": "ok", "version": "0.1.0", "env": settings.app_env}


@app.get("/readyz", tags=["ops"])
async def readyz(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "postgres": "ok"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "postgres": str(exc)},
        ) from exc
