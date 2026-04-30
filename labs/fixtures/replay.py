"""Replay a fixture JSONL into the backend (Phase 19 detection-as-code).

Each line is a canonical event with a synthetic `_t_offset_sec` field; the
replayer computes `occurred_at = now() - _t_offset_sec` so timestamps stay
within the 30-day past bound regardless of when the fixture was authored.

Usage:
    python labs/fixtures/replay.py auth/ssh_brute_force_burst.jsonl \\
        --base-url http://localhost:8000

Exits non-zero if any event was rejected (4xx/5xx).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

_FIXTURES_DIR = Path(__file__).resolve().parent


def _resolve_path(p: str) -> Path:
    candidate = Path(p)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    relative = _FIXTURES_DIR / p
    if relative.exists():
        return relative
    raise FileNotFoundError(p)


def load_fixture(path: Path) -> list[dict]:
    """Read a JSONL fixture file into a list of event dicts."""
    events = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON ({exc})") from exc
    return events


def materialize_event(template: dict, *, now: datetime | None = None) -> dict:
    """Strip `_t_offset_sec` and produce a payload suitable for /v1/events/raw."""
    base = (now or datetime.now(timezone.utc))
    event = dict(template)
    offset = event.pop("_t_offset_sec", 0)
    event["occurred_at"] = (base - timedelta(seconds=int(offset))).isoformat()
    return event


async def replay(
    fixture_path: Path,
    base_url: str,
    token: str | None = None,
    timeout: float = 10.0,
) -> tuple[int, int, list[str]]:
    """Replay a fixture against `base_url`. Returns (sent, accepted, errors)."""
    events = load_fixture(fixture_path)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    accepted = 0
    errors: list[str] = []

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=headers) as client:
        for i, template in enumerate(events):
            payload = materialize_event(template)
            resp = await client.post("/v1/events/raw", json=payload)
            if resp.status_code in (200, 201):
                accepted += 1
            else:
                errors.append(
                    f"line {i + 1}: {resp.status_code} {resp.text[:200]}"
                )

    return len(events), accepted, errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fixture", help="Path under labs/fixtures/, or absolute path")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--token", default=None,
                   help="Bearer token if AUTH_REQUIRED=true on backend")
    p.add_argument("--timeout", type=float, default=10.0)
    args = p.parse_args()

    try:
        path = _resolve_path(args.fixture)
    except FileNotFoundError:
        print(f"fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    sent, accepted, errors = asyncio.run(replay(path, args.base_url, args.token, args.timeout))
    print(f"{path.name}: sent={sent} accepted={accepted} rejected={len(errors)}")
    for err in errors:
        print(f"  REJECT {err}", file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
