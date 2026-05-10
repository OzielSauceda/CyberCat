"""labs/caldera/seed_fact_source.py — Phase 21.5 helper.

Reads labs/caldera/facts.yml and upserts it into Caldera as a fact
source via PUT /api/v2/sources/{source_id}. Idempotent — the source_id
is taken from the YAML, not auto-generated, so re-running after edits
replaces the prior version cleanly.

The operation payload built by build_operation_request.py references
this source by name. Phase 21.5 changes that reference from the empty
default `basic` to whatever `source_name` this file declares.

Why this exists: Phase 21's first scorecard had 9 ability rows error
mid-execution because Caldera's default `basic` fact source is empty,
so any stockpile ability with `#{trait}` templating failed at
substitution time. Seeding a CyberCat-specific source with realistic
lab values closes that gap.

Usage:

    docker compose -f infra/compose/docker-compose.yml exec -T \
        -e CALDERA_API_KEY="$CALDERA_KEY" backend \
        python -m labs.caldera.seed_fact_source \
            --caldera "http://caldera:8888" \
            --here "//app/labs/caldera"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Caldera REST helpers (urllib only — same shape as the sibling scripts).
# ---------------------------------------------------------------------------


def _caldera_request(
    url: str, key: str, *, method: str = "GET", payload: dict | None = None
) -> tuple[int, object]:
    headers = {"KEY": key, "Accept": "application/json"}
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — operator-controlled
            raw = resp.read()
            try:
                return resp.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# YAML → Caldera SourceSchema transform
# ---------------------------------------------------------------------------


def _build_source_payload(facts_doc: dict) -> dict:
    """Turn facts.yml's structure into the JSON shape Caldera 4.2.0's
    PUT /api/v2/sources/{source_id} accepts.

    Caldera's FactSchema accepts {trait, value, score, source}. The
    `source` field on each fact is the source_id we're attached to;
    Caldera enforces that for cross-source filtering. Score defaults to
    1 (trusted enough to be picked).
    """
    source_id = facts_doc.get("source_id")
    if not source_id or not isinstance(source_id, str):
        raise ValueError("facts.yml missing required string `source_id`")
    source_name = facts_doc.get("source_name", source_id)

    facts_in = facts_doc.get("facts") or []
    if not isinstance(facts_in, list) or not facts_in:
        raise ValueError("facts.yml must declare a non-empty `facts:` list")

    facts_out: list[dict] = []
    for entry in facts_in:
        if not isinstance(entry, dict):
            raise ValueError(f"every fact entry must be a mapping, got {type(entry).__name__}")
        trait = entry.get("trait")
        value = entry.get("value")
        if not isinstance(trait, str) or not trait:
            raise ValueError(f"fact missing required string `trait`: {entry!r}")
        if value is None:
            raise ValueError(f"fact `{trait}` missing required `value`")
        facts_out.append({
            "trait": trait,
            "value": str(value),
            "score": int(entry.get("score", 1)),
            "source": source_id,
        })

    return {
        "id": source_id,
        "name": source_name,
        "facts": facts_out,
        # Empty rules/adjustments/relationships keep Caldera 4.2.0's
        # SourceSchema happy — it expects the keys to be present even
        # when the lists are empty.
        "rules": [],
        "adjustments": [],
        "relationships": [],
    }


# ---------------------------------------------------------------------------
# Main upsert loop
# ---------------------------------------------------------------------------


def seed(here: Path, caldera_url: str, key: str) -> int:
    facts_path = here / "facts.yml"
    if not facts_path.is_file():
        print(f"facts file not found: {facts_path}", file=sys.stderr)
        return 1

    try:
        import yaml  # type: ignore
    except ImportError:
        print(
            "PyYAML required. Run inside the backend container, where it is installed:\n"
            "  docker compose ... exec backend python -m labs.caldera.seed_fact_source ...",
            file=sys.stderr,
        )
        return 2

    facts_doc = yaml.safe_load(facts_path.read_text())
    if not isinstance(facts_doc, dict):
        print(f"{facts_path}: top-level must be a mapping", file=sys.stderr)
        return 1

    try:
        payload = _build_source_payload(facts_doc)
    except ValueError as e:
        print(f"{facts_path}: {e}", file=sys.stderr)
        return 1

    source_id = payload["id"]
    fact_count = len(payload["facts"])
    url = f"{caldera_url}/api/v2/sources/{source_id}"

    print(
        f"Upserting fact source `{source_id}` ({fact_count} fact"
        f"{'s' if fact_count != 1 else ''}) → {caldera_url}",
        file=sys.stderr,
    )
    status, body = _caldera_request(url, key, method="PUT", payload=payload)
    if status not in (200, 201, 204):
        print(f"  ✗ PUT /api/v2/sources/{source_id} returned {status}: {body!r}", file=sys.stderr)
        return 3

    # Verify by fetching it back and counting facts.
    v_status, v_body = _caldera_request(url, key, method="GET")
    if v_status != 200 or not isinstance(v_body, dict):
        print(f"  ✗ verify GET returned {v_status}: {v_body!r}", file=sys.stderr)
        return 3
    got = len(v_body.get("facts") or [])
    if got != fact_count:
        print(
            f"  ! verify mismatch: sent {fact_count} fact(s), Caldera reports {got}",
            file=sys.stderr,
        )
        # Don't fail — Caldera may dedupe or reshape — but flag it.
    print(
        f"  ✓ source `{source_id}` upserted, verified ({got} fact{'s' if got != 1 else ''} live)",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Seed Caldera's fact source registry from labs/caldera/facts.yml."
    )
    p.add_argument(
        "--caldera",
        default="http://127.0.0.1:8888",
        help="Caldera base URL (default http://127.0.0.1:8888).",
    )
    p.add_argument(
        "--key",
        default="",
        help="Caldera API key. Falls back to CALDERA_API_KEY env var.",
    )
    p.add_argument(
        "--here",
        default=str(Path(__file__).resolve().parent),
        help="labs/caldera/ directory (default: this script's parent).",
    )
    args = p.parse_args()

    key = args.key or os.environ.get("CALDERA_API_KEY", "")
    if not key:
        print("CALDERA_API_KEY not provided (use --key or env var).", file=sys.stderr)
        return 4

    return seed(Path(args.here), args.caldera, key)


if __name__ == "__main__":
    sys.exit(main())
