from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import UTC, datetime

import httpx
from sqlalchemy import text

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.enums import EventSource
from app.ingest.pipeline import ingest_normalized_event
from app.ingest.retry import with_ingest_retry
from app.ingest.wazuh_decoder import decode_wazuh_alert

logger = logging.getLogger(__name__)

_SINGLETON = "singleton"
_prev_reachable: bool | None = None  # tracks reachability across poll cycles

# Phase 19: circuit-breaker for sustained per-hit ingest failures.
# After this many *consecutive* ingest exceptions in a single batch, abort the
# batch without advancing the cursor past the failed hits. The outer poll loop
# applies its existing exponential backoff and replays the unprocessed tail on
# the next iteration.
_CONSECUTIVE_INGEST_FAIL_LIMIT = 10


class WazuhPollerCircuitOpen(Exception):
    """Raised when the per-hit ingest circuit-breaker trips."""


def build_query(
    cursor_value: list | None,
    batch: int,
    first_run_lookback_min: int,
) -> dict:
    filters: list[dict] = [
        {
            "terms": {
                "rule.groups": [
                    "authentication_failed",
                    "authentication_success",
                    "audit",
                ]
            }
        }
    ]
    if cursor_value is None:
        filters.append(
            {"range": {"@timestamp": {"gte": f"now-{first_run_lookback_min}m"}}}
        )

    query: dict = {
        "size": batch,
        "sort": [{"@timestamp": "asc"}, {"_id": "asc"}],
        "query": {"bool": {"filter": filters}},
    }
    if cursor_value is not None:
        query["search_after"] = cursor_value
    return query


async def poller_loop(stop_event: asyncio.Event) -> None:
    """Pull-mode Wazuh Indexer poller. Runs for the lifetime of the FastAPI process."""
    url = f"{settings.wazuh_indexer_url.rstrip('/')}/{settings.wazuh_indexer_index_pattern}/_search"
    backoff = 5
    max_backoff = 60

    if settings.wazuh_indexer_verify_tls:
        # Verify cert is signed by our CA; skip hostname check (cert SAN is 127.0.0.1,
        # not the docker service name). Same trust model as FILEBEAT_SSL_VERIFICATION_MODE=certificate.
        _ssl_ctx = ssl.create_default_context(cafile=settings.wazuh_ca_bundle_path)
        _ssl_ctx.check_hostname = False
        tls_verify: bool | ssl.SSLContext = _ssl_ctx
    else:
        tls_verify = False
    async with httpx.AsyncClient(
        verify=tls_verify,
        auth=(settings.wazuh_indexer_user, settings.wazuh_indexer_password),
        timeout=10.0,
    ) as client:
        # Ensure singleton cursor row exists
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO wazuh_cursor (id) VALUES (:id) ON CONFLICT DO NOTHING"
                ),
                {"id": _SINGLETON},
            )
            await db.commit()

        while not stop_event.is_set():
            try:
                await _poll_once(client, url, stop_event)
                backoff = 5
            except Exception as exc:  # noqa: BLE001
                logger.exception("poller iteration failed unexpectedly: %s", exc)
                try:
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            text(
                                "UPDATE wazuh_cursor SET last_poll_at=:now, last_error=:err"
                                " WHERE id=:id"
                            ),
                            {"now": _now(), "err": str(exc)[:500], "id": _SINGLETON},
                        )
                        await db.commit()
                except Exception:  # noqa: BLE001
                    pass
                await _interruptible_sleep(stop_event, backoff)
                backoff = min(backoff * 2, max_backoff)


async def _poll_once(
    client: httpx.AsyncClient,
    url: str,
    stop_event: asyncio.Event,
) -> None:
    """Execute one poll cycle: read cursor → query indexer → ingest hits → update cursor."""
    accepted = 0
    dropped = 0
    last_sort: list | None = None

    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text("SELECT search_after FROM wazuh_cursor WHERE id = :id"),
            {"id": _SINGLETON},
        )
        cursor_row = row.fetchone()
        cursor_value: list | None = cursor_row[0] if cursor_row else None

    query = build_query(
        cursor_value,
        settings.wazuh_poll_batch_size,
        settings.wazuh_first_run_lookback_minutes,
    )

    try:
        resp = await client.post(url, json=query)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        err_msg = str(exc)
        logger.warning("wazuh poller error: %s", err_msg)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE wazuh_cursor SET last_poll_at=:now, last_error=:err"
                    " WHERE id=:id"
                ),
                {"now": _now(), "err": err_msg, "id": _SINGLETON},
            )
            await db.commit()
        await _emit_wazuh_transition(reachable=False, last_error=err_msg)
        await _interruptible_sleep(stop_event, settings.wazuh_poll_interval_seconds)
        return

    hits: list[dict] = resp.json().get("hits", {}).get("hits", [])

    breaker_tripped = False
    consecutive_ingest_failures = 0
    if hits:
        from app.db.redis import get_redis as _get_redis  # noqa: PLC0415
        redis = _get_redis()
        for hit in hits:
            hit_sort = hit.get("sort")
            source = hit.get("_source", {})
            source["_id"] = hit.get("_id", "")
            decoded = decode_wazuh_alert(source)
            if decoded is None:
                # Decoder rejection is a poison-message case; advance past it so we
                # don't loop on the same bad hit. Does not feed the circuit-breaker.
                dropped += 1
                last_sort = hit_sort
                continue
            try:
                async def _ingest(db, _decoded=decoded):
                    return await ingest_normalized_event(
                        db,
                        redis,
                        source=EventSource.wazuh,
                        kind=_decoded.kind,
                        occurred_at=_decoded.occurred_at,
                        raw=_decoded.raw,
                        normalized=_decoded.normalized,
                        dedupe_key=_decoded.dedupe_key,
                    )

                result = await with_ingest_retry(_ingest)
                if result.dedup_hit:
                    logger.debug(
                        "wazuh dedup hit dedupe_key=%s", decoded.dedupe_key
                    )
                else:
                    accepted += 1
                consecutive_ingest_failures = 0
                last_sort = hit_sort
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "wazuh ingest error dedupe_key=%s err=%s",
                    decoded.dedupe_key,
                    exc,
                )
                dropped += 1
                consecutive_ingest_failures += 1
                if consecutive_ingest_failures >= _CONSECUTIVE_INGEST_FAIL_LIMIT:
                    logger.error(
                        "wazuh poller circuit-breaker tripped"
                        " consecutive_failures=%d batch_size=%d"
                        " — aborting batch, cursor will not advance past failed hits",
                        consecutive_ingest_failures,
                        len(hits),
                    )
                    breaker_tripped = True
                    break

        async with AsyncSessionLocal() as db:
            # Only advance search_after when last_sort is set; otherwise keep existing
            # checkpoint so we don't reset to first-run (now-5m) on PAM-only batches.
            if last_sort is not None:
                await db.execute(
                    text(
                        "UPDATE wazuh_cursor SET"
                        " search_after=CAST(:sa AS JSONB),"
                        " last_poll_at=:now,"
                        " last_success_at=:now,"
                        " last_error=NULL,"
                        " events_ingested_total=events_ingested_total+:acc,"
                        " events_dropped_total=events_dropped_total+:drp"
                        " WHERE id=:id"
                    ),
                    {
                        "sa": json.dumps(last_sort),
                        "now": _now(),
                        "acc": accepted,
                        "drp": dropped,
                        "id": _SINGLETON,
                    },
                )
            else:
                await db.execute(
                    text(
                        "UPDATE wazuh_cursor SET"
                        " last_poll_at=:now,"
                        " last_success_at=:now,"
                        " last_error=NULL,"
                        " events_ingested_total=events_ingested_total+:acc,"
                        " events_dropped_total=events_dropped_total+:drp"
                        " WHERE id=:id"
                    ),
                    {
                        "now": _now(),
                        "acc": accepted,
                        "drp": dropped,
                        "id": _SINGLETON,
                    },
                )
            await db.commit()

        if breaker_tripped:
            # Outer poller_loop catches this, applies exponential backoff, and
            # the next poll replays the unprocessed tail of the batch via the
            # un-advanced search_after cursor.
            raise WazuhPollerCircuitOpen(
                f"{consecutive_ingest_failures} consecutive ingest failures"
            )
    else:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE wazuh_cursor SET last_poll_at=:now, last_success_at=:now,"
                    " last_error=NULL WHERE id=:id"
                ),
                {"now": _now(), "id": _SINGLETON},
            )
            await db.commit()

    await _emit_wazuh_transition(reachable=True)

    if len(hits) < settings.wazuh_poll_batch_size:
        await _interruptible_sleep(stop_event, settings.wazuh_poll_interval_seconds)


async def _emit_wazuh_transition(reachable: bool, last_error: str | None = None) -> None:
    """Emit wazuh.status_changed only when reachability flips."""
    global _prev_reachable
    if reachable == _prev_reachable:
        return
    _prev_reachable = reachable
    try:
        from app.streaming.publisher import publish
        await publish("wazuh.status_changed", {
            "enabled": True,
            "reachable": reachable,
            "last_error": last_error,
        })
    except Exception as exc:
        logger.warning("wazuh transition emit failed: %s", exc)


async def _interruptible_sleep(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        pass


def _now() -> datetime:
    return datetime.now(tz=UTC)
