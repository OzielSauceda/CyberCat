"""Phase 19 — backpressure load harness for /v1/events/raw.

Fires synthetic auth.failed events at a target rate for a fixed duration and
emits a JSON summary covering acceptance rate, latency percentiles, and any
5xx responses observed. Used to verify Phase 19 acceptance criteria:

- 1000 events/sec for 60s → 0% drop at the API layer
- p95 detection-fire latency < 500ms
- No 5xx, no client-side timeouts

Usage (against the dev compose stack):
    python labs/perf/load_harness.py --rate 1000 --duration 60

Output: prints one JSON object summarizing the run, plus a non-zero exit
code if acceptance criteria were violated.

This is a deliberately simple harness — no warmup, no ramp, no async per-host
connection pooling tricks. The goal is "does the platform survive 1000/s?"
not "what's the absolute peak throughput?". Phase 21 baseline.py extends
this with snapshot/diff comparison.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx


@dataclass
class Run:
    target_rate: int
    duration_sec: float
    sent: int = 0
    accepted: int = 0
    dedup: int = 0
    rejected_4xx: int = 0
    failed_5xx: int = 0
    transport_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def _make_payload(seq: int, host: str = "loadtest-host") -> dict:
    return {
        "source": "direct",
        "kind": "auth.failed",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "raw": {"seq": seq, "agent": "load_harness"},
        "normalized": {
            "user": f"loaduser_{seq % 50}",
            "source_ip": f"10.{(seq // 65536) % 256}.{(seq // 256) % 256}.{seq % 256}",
            "auth_type": "password",
        },
        "dedupe_key": f"loadharness:{uuid.uuid4().hex}:{seq}",
    }


async def _fire(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    run: Run,
    headers: dict[str, str],
) -> None:
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers=headers)
    except (httpx.HTTPError, asyncio.TimeoutError):
        run.transport_errors += 1
        return
    elapsed_ms = (time.perf_counter() - t0) * 1000
    run.latencies_ms.append(elapsed_ms)
    if resp.status_code == 201:
        body = resp.json()
        if body.get("dedup_hit"):
            run.dedup += 1
        else:
            run.accepted += 1
    elif 400 <= resp.status_code < 500:
        run.rejected_4xx += 1
    elif resp.status_code >= 500:
        run.failed_5xx += 1


async def run_load(args: argparse.Namespace) -> Run:
    url = f"{args.base_url.rstrip('/')}/v1/events/raw"
    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    run = Run(target_rate=args.rate, duration_sec=args.duration)
    period = 1.0 / args.rate
    seq = 0
    pending: list[asyncio.Task] = []

    limits = httpx.Limits(max_keepalive_connections=200, max_connections=400)
    timeout = httpx.Timeout(args.request_timeout)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        run.started_at = time.perf_counter()
        deadline = run.started_at + args.duration

        next_fire = run.started_at
        while time.perf_counter() < deadline:
            now = time.perf_counter()
            if now < next_fire:
                await asyncio.sleep(next_fire - now)

            payload = _make_payload(seq)
            seq += 1
            run.sent += 1
            pending.append(
                asyncio.create_task(_fire(client, url, payload, run, headers))
            )

            next_fire += period

            # Reap completed tasks periodically so the list doesn't grow unbounded.
            if len(pending) > 1000:
                pending = [t for t in pending if not t.done()]

        await asyncio.gather(*pending, return_exceptions=True)
        run.ended_at = time.perf_counter()

    return run


def summarize(run: Run) -> dict:
    elapsed = max(run.ended_at - run.started_at, 0.001)
    achieved_rate = run.sent / elapsed
    return {
        "target_rate": run.target_rate,
        "achieved_rate_per_sec": round(achieved_rate, 1),
        "duration_sec": round(elapsed, 2),
        "sent": run.sent,
        "accepted": run.accepted,
        "dedup_hits": run.dedup,
        "rejected_4xx": run.rejected_4xx,
        "failed_5xx": run.failed_5xx,
        "transport_errors": run.transport_errors,
        "latency_ms": {
            "p50": _percentile(run.latencies_ms, 50),
            "p95": _percentile(run.latencies_ms, 95),
            "p99": _percentile(run.latencies_ms, 99),
            "max": max(run.latencies_ms) if run.latencies_ms else None,
        },
    }


def check_acceptance(summary: dict) -> tuple[bool, list[str]]:
    """Apply the Phase 19 acceptance criteria. Returns (passed, list_of_violations)."""
    violations: list[str] = []
    if summary["failed_5xx"] > 0:
        violations.append(f"failed_5xx={summary['failed_5xx']} (must be 0)")
    if summary["transport_errors"] > 0:
        violations.append(f"transport_errors={summary['transport_errors']} (must be 0)")
    p95 = summary["latency_ms"]["p95"]
    if p95 is not None and p95 > 500:
        violations.append(f"latency p95={p95:.1f}ms (must be < 500ms)")
    # Achieved rate within 5% of target
    target = summary["target_rate"]
    achieved = summary["achieved_rate_per_sec"]
    if achieved < target * 0.95:
        violations.append(
            f"achieved_rate={achieved} below 95% of target={target}"
        )
    return (not violations), violations


def main() -> int:
    p = argparse.ArgumentParser(description="CyberCat ingest load harness")
    p.add_argument("--base-url", default="http://localhost:8000",
                   help="Backend base URL (default: http://localhost:8000)")
    p.add_argument("--rate", type=int, default=1000,
                   help="Events per second to fire (default: 1000)")
    p.add_argument("--duration", type=float, default=60.0,
                   help="Run duration in seconds (default: 60)")
    p.add_argument("--token", default=None,
                   help="Bearer token if AUTH_REQUIRED=true on backend")
    p.add_argument("--request-timeout", type=float, default=5.0,
                   help="Per-request timeout seconds (default: 5)")
    p.add_argument("--enforce-acceptance", action="store_true",
                   help="Exit non-zero if Phase 19 acceptance criteria are violated")
    args = p.parse_args()

    run = asyncio.run(run_load(args))
    summary = summarize(run)
    passed, violations = check_acceptance(summary)
    summary["acceptance_passed"] = passed
    summary["acceptance_violations"] = violations

    print(json.dumps(summary, indent=2))
    if args.enforce_acceptance and not passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
