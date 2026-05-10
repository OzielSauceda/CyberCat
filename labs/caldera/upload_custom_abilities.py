"""labs/caldera/upload_custom_abilities.py — Phase 21.5 helper.

Uploads every YAML in labs/caldera/abilities/ to Caldera's stockpile via
PUT /api/v2/abilities/{ability_id}. Idempotent — re-running upserts
without changing the ability_id, so the script is safe to call before
every run.sh invocation.

Why this exists: Phase 21's first scorecard rendered 5 abilities as
`ability-skipped` because their YAMLs only existed on the host
filesystem; Caldera never saw them. This script closes that gap.

API shape transform (YAML → Caldera 4.2.0 AbilitySchema):

    id                    → ability_id
    name                  → name
    description           → description
    tactic                → tactic
    technique.attack_id   → technique_id
    technique.name        → technique_name
    platforms.<plat>.<exec>.{command,cleanup,payloads,timeout}
                          → executors: [{platform, name, command,
                                         cleanup, payloads, timeout}, ...]

PyYAML is preferred. The script will fail loudly if PyYAML is missing —
unlike build_operation_request.py, the ability YAMLs use enough YAML
machinery (nested maps, multi-line block scalars in multiple positions)
that hand-parsing is brittle. Runs inside the backend container where
PyYAML is reliably installed.

Usage:

    docker compose -f infra/compose/docker-compose.yml exec -T \
        -e CALDERA_API_KEY="$CALDERA_KEY" backend \
        python -m labs.caldera.upload_custom_abilities \
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
# Caldera REST helpers (urllib only — no requests dep, mirrors
# build_operation_request.py).
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
# YAML → Caldera AbilitySchema transform
# ---------------------------------------------------------------------------


def _transform(yaml_doc: dict) -> dict:
    """Convert one labs/caldera/abilities/*.yml document into the JSON
    shape Caldera 4.2.0's PUT /api/v2/abilities/{ability_id} accepts.

    The ability YAMLs use Caldera's older `platforms: {plat: {exec: ...}}`
    nesting (the same shape Caldera reads from disk-loaded stockpile
    files). The REST API expects a flat `executors: [...]` list. We
    flatten here.
    """
    if not isinstance(yaml_doc, dict):
        raise ValueError(f"ability YAML root is {type(yaml_doc).__name__}, expected mapping")

    ability_id = yaml_doc.get("id")
    if not ability_id or not isinstance(ability_id, str):
        raise ValueError("ability YAML missing required string `id`")

    technique = yaml_doc.get("technique") or {}
    if not isinstance(technique, dict):
        raise ValueError(f"{ability_id}: `technique` must be a mapping")

    out: dict = {
        "ability_id": ability_id,
        "name": yaml_doc.get("name", ability_id),
        "description": (yaml_doc.get("description") or "").strip(),
        "tactic": yaml_doc.get("tactic", ""),
        "technique_id": technique.get("attack_id", ""),
        "technique_name": technique.get("name", ""),
        "executors": [],
    }

    platforms = yaml_doc.get("platforms") or {}
    if not isinstance(platforms, dict) or not platforms:
        raise ValueError(f"{ability_id}: `platforms` is empty or not a mapping")

    for platform_name, executors in platforms.items():
        if not isinstance(executors, dict):
            raise ValueError(
                f"{ability_id}: platforms.{platform_name} must be a mapping of executor name → spec"
            )
        for executor_name, spec in executors.items():
            if not isinstance(spec, dict):
                raise ValueError(
                    f"{ability_id}: platforms.{platform_name}.{executor_name} must be a mapping"
                )
            executor: dict = {
                "platform": platform_name,
                "name": executor_name,
                "command": (spec.get("command") or "").rstrip("\n"),
            }
            cleanup = spec.get("cleanup")
            if isinstance(cleanup, str) and cleanup.strip():
                # Caldera's link runner expects a list of cleanup commands.
                executor["cleanup"] = [cleanup.rstrip("\n")]
            timeout = spec.get("timeout")
            if isinstance(timeout, int):
                executor["timeout"] = timeout
            payloads = spec.get("payloads")
            if isinstance(payloads, list):
                executor["payloads"] = list(payloads)
            out["executors"].append(executor)

    if not out["executors"]:
        raise ValueError(f"{ability_id}: produced 0 executors after flattening")
    return out


# ---------------------------------------------------------------------------
# Main upload loop
# ---------------------------------------------------------------------------


def upload_all(here: Path, caldera_url: str, key: str) -> int:
    abilities_dir = here / "abilities"
    if not abilities_dir.is_dir():
        print(f"abilities directory not found: {abilities_dir}", file=sys.stderr)
        return 1

    try:
        import yaml  # type: ignore
    except ImportError:
        print(
            "PyYAML required. Run inside the backend container, where it is installed:\n"
            "  docker compose ... exec backend python -m labs.caldera.upload_custom_abilities ...",
            file=sys.stderr,
        )
        return 2

    yaml_files = sorted(p for p in abilities_dir.iterdir() if p.suffix in {".yml", ".yaml"})
    if not yaml_files:
        print(f"no *.yml files in {abilities_dir}", file=sys.stderr)
        return 1

    print(f"Uploading {len(yaml_files)} custom abilit{'y' if len(yaml_files)==1 else 'ies'} → {caldera_url}", file=sys.stderr)

    failures: list[str] = []
    for path in yaml_files:
        text = path.read_text()
        # Stockpile abilities are a top-level list (`- id: ...`); ours mirror
        # that convention. Take the first (and only) document.
        loaded = yaml.safe_load(text)
        if isinstance(loaded, list):
            if not loaded:
                print(f"  ✗ {path.name}: empty list", file=sys.stderr)
                failures.append(path.name)
                continue
            doc = loaded[0]
        else:
            doc = loaded

        try:
            payload = _transform(doc)
        except ValueError as e:
            print(f"  ✗ {path.name}: transform failed — {e}", file=sys.stderr)
            failures.append(path.name)
            continue

        ability_id = payload["ability_id"]
        url = f"{caldera_url}/api/v2/abilities/{ability_id}"
        status, body = _caldera_request(url, key, method="PUT", payload=payload)
        if status not in (200, 201, 204):
            print(f"  ✗ {path.name} ({ability_id}): PUT returned {status}: {body!r}", file=sys.stderr)
            failures.append(path.name)
            continue

        # Verify by fetching it back.
        v_status, v_body = _caldera_request(url, key, method="GET")
        if v_status != 200 or not isinstance(v_body, dict) or v_body.get("ability_id") != ability_id:
            print(f"  ✗ {path.name} ({ability_id}): verify GET failed (status {v_status})", file=sys.stderr)
            failures.append(path.name)
            continue
        executors_count = len(v_body.get("executors") or [])
        print(f"  ✓ {ability_id} ({executors_count} executor{'s' if executors_count!=1 else ''})", file=sys.stderr)

    if failures:
        print(f"\n{len(failures)} upload(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 3
    print(f"\nAll {len(yaml_files)} ability uploads verified.", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Upload labs/caldera/abilities/*.yml to Caldera's stockpile (idempotent)."
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

    return upload_all(Path(args.here), args.caldera, key)


if __name__ == "__main__":
    sys.exit(main())
