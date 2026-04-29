"""Demo data seeder — runs once on startup when CCT_AUTOSEED_DEMO=true.

Safety contract:
  - Postgres advisory lock prevents concurrent replicas from racing.
  - Redis key ``cybercat:demo_active`` acts as the durable seed marker.
  - Events-table non-empty check provides a second guard if Redis is cleared.
  - All three must pass before seeding runs.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import LabAsset
from app.enums import EventSource, LabAssetKind
from app.ingest.pipeline import ingest_normalized_event

log = logging.getLogger(__name__)

DEMO_REDIS_KEY = "cybercat:demo_active"
_ADVISORY_LOCK_ID = 9_876_543_210  # stable bigint key for this seeder

# ---------------------------------------------------------------------------
# Event payload builders (mirrors labs/simulator/event_templates.py)
# ---------------------------------------------------------------------------

def _ts(dt: datetime) -> str:
    return dt.isoformat()


def _auth_failed(user: str, source_ip: str, occurred_at: datetime, dedupe_key: str) -> dict:
    n = {"user": user, "source_ip": source_ip, "auth_type": "ssh"}
    return {"source": "seeder", "kind": "auth.failed", "occurred_at": _ts(occurred_at),
            "raw": n.copy(), "normalized": n, "dedupe_key": dedupe_key}


def _auth_succeeded(user: str, source_ip: str, occurred_at: datetime, dedupe_key: str) -> dict:
    n = {"user": user, "source_ip": source_ip, "auth_type": "ssh"}
    return {"source": "seeder", "kind": "auth.succeeded", "occurred_at": _ts(occurred_at),
            "raw": n.copy(), "normalized": n, "dedupe_key": dedupe_key}


def _session_started(user: str, host: str, session_id: str, occurred_at: datetime, dedupe_key: str) -> dict:
    n = {"user": user, "host": host, "session_id": session_id}
    return {"source": "seeder", "kind": "session.started", "occurred_at": _ts(occurred_at),
            "raw": n.copy(), "normalized": n, "dedupe_key": dedupe_key}


def _process_created(
    host: str, image: str, cmdline: str, pid: int, ppid: int,
    user: str, occurred_at: datetime, dedupe_key: str,
) -> dict:
    n = {"host": host, "pid": pid, "ppid": ppid, "image": image, "cmdline": cmdline, "user": user}
    return {"source": "seeder", "kind": "process.created", "occurred_at": _ts(occurred_at),
            "raw": n.copy(), "normalized": n, "dedupe_key": dedupe_key}


def _network_connection(
    host: str, src_ip: str, dst_ip: str, dst_port: int,
    occurred_at: datetime, dedupe_key: str,
) -> dict:
    n = {"host": host, "src_ip": src_ip, "dst_ip": dst_ip, "dst_port": dst_port, "proto": "tcp"}
    return {"source": "seeder", "kind": "network.connection", "occurred_at": _ts(occurred_at),
            "raw": n.copy(), "normalized": n, "dedupe_key": dedupe_key}


# ---------------------------------------------------------------------------
# Lab asset upsert
# ---------------------------------------------------------------------------

async def _register_asset(db: AsyncSession, kind: LabAssetKind, natural_key: str) -> None:
    stmt = (
        pg_insert(LabAsset)
        .values(id=uuid.uuid4(), kind=kind, natural_key=natural_key)
        .on_conflict_do_nothing(constraint="uq_lab_assets_kind_natural_key")
    )
    await db.execute(stmt)
    await db.commit()


# ---------------------------------------------------------------------------
# Core seed routine
# ---------------------------------------------------------------------------

async def _run_seed(db: AsyncSession, redis: aioredis.Redis) -> None:
    """Replay credential_theft_chain with historical timestamps (no sleeps)."""
    _USER = "alice"
    _HOST = "workstation-42"
    _ATTACKER_IP = "203.0.113.42"
    _WORKSTATION_IP = "10.0.0.50"

    base = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Stage 0: lab assets
    await _register_asset(db, LabAssetKind.user, _USER)
    await _register_asset(db, LabAssetKind.host, _HOST)

    async def ingest(payload: dict) -> None:
        await ingest_normalized_event(
            db,
            redis,
            source=EventSource(payload["source"]),
            kind=payload["kind"],
            occurred_at=datetime.fromisoformat(payload["occurred_at"]),
            raw=payload["raw"],
            normalized=payload["normalized"],
            dedupe_key=payload.get("dedupe_key"),
        )

    # Stage 1: 6× auth.failed (brute force)
    for i in range(6):
        await ingest(_auth_failed(
            user=_USER, source_ip=_ATTACKER_IP,
            occurred_at=base + timedelta(seconds=i * 5),
            dedupe_key=f"seed:cred-chain:auth.failed:{_USER}:{_ATTACKER_IP}:{i}",
        ))

    # Stage 2: auth.succeeded (attacker logs in)
    await ingest(_auth_succeeded(
        user=_USER, source_ip=_ATTACKER_IP,
        occurred_at=base + timedelta(seconds=60),
        dedupe_key=f"seed:cred-chain:auth.succeeded:{_USER}:{_ATTACKER_IP}",
    ))

    # Stage 3: session.started on workstation
    await ingest(_session_started(
        user=_USER, host=_HOST, session_id="seed-cred-chain-alice-01",
        occurred_at=base + timedelta(seconds=75),
        dedupe_key=f"seed:cred-chain:session.started:{_USER}:{_HOST}",
    ))

    # Stage 4: encoded PowerShell (triggers identity_endpoint_chain)
    await ingest(_process_created(
        host=_HOST, image="powershell.exe",
        cmdline="powershell.exe -enc SGVsbG8gV29ybGQ=",
        pid=4242, ppid=2828, user=_USER,
        occurred_at=base + timedelta(seconds=180),
        dedupe_key=f"seed:cred-chain:process.created:{_USER}:{_HOST}:enc-ps",
    ))

    # Stage 5a: net use (lateral movement)
    await ingest(_process_created(
        host=_HOST, image="net.exe",
        cmdline=r"net use \\192.168.1.100\IPC$",
        pid=4243, ppid=4242, user=_USER,
        occurred_at=base + timedelta(seconds=240),
        dedupe_key=f"seed:cred-chain:process.created:{_USER}:{_HOST}:net-use",
    ))

    # Stage 5b: C2 beacon outbound
    await ingest(_network_connection(
        host=_HOST, src_ip=_WORKSTATION_IP, dst_ip=_ATTACKER_IP, dst_port=4444,
        occurred_at=base + timedelta(seconds=250),
        dedupe_key=f"seed:cred-chain:network.connection:{_HOST}:{_ATTACKER_IP}:4444",
    ))


# ---------------------------------------------------------------------------
# Public entry point — called from main.py lifespan
# ---------------------------------------------------------------------------

async def maybe_seed(
    db_factory: async_sessionmaker[AsyncSession],
    redis: aioredis.Redis,
) -> None:
    """Seed demo data if all guards pass. Safe to call on every startup."""
    async with db_factory() as db:
        # Acquire advisory lock — returns False if another process has it
        result = await db.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": _ADVISORY_LOCK_ID},
        )
        if not result.scalar():
            log.info("demo-seed: advisory lock held by another instance — skipping")
            return

        try:
            # Guard 1: Redis seed marker
            if await redis.get(DEMO_REDIS_KEY):
                log.info("demo-seed: Redis marker present — already seeded, skipping")
                return

            # Guard 2: events table not empty
            count_result = await db.execute(text("SELECT COUNT(*) FROM events"))
            count = count_result.scalar_one()
            if count > 0:
                log.info("demo-seed: events table has %d rows — skipping", count)
                return

            log.info("demo-seed: seeding credential_theft_chain demo data...")
            await _run_seed(db, redis)
            await redis.set(DEMO_REDIS_KEY, "1")
            log.info("demo-seed: complete")

        except Exception:
            log.exception("demo-seed: seed failed — stack will start with empty DB")
        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": _ADVISORY_LOCK_ID},
            )
