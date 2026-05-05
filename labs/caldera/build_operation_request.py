"""labs/caldera/build_operation_request.py — Phase 21 helper.

Builds the JSON payload that POST /api/v2/operations expects, given our
adversary profile and expectations registry. Caldera's operations
endpoint requires a resolved adversary_id, a planner_id, and a present
agent group — it does NOT accept our profile.yml or expectations.yml
directly.

Two modes:

  --resolve-uuids    First-run helper. Reads profile.yml entries with
                     STOCKPILE:executor:platform:slug placeholders,
                     queries Caldera /api/v2/abilities, and writes
                     expectations.resolved.yml + profile.resolved.yml
                     sidecars with the real GUIDs filled in.

  (default)          Operation-payload mode. Reads profile.resolved.yml
                     (or falls back to profile.yml if no STOCKPILE: refs
                     remain), POSTs the adversary to /api/v2/adversaries
                     idempotently, looks up the 'atomic' planner GUID,
                     confirms ≥1 agent in --group, and prints the
                     operation-creation JSON to stdout.

Pure stdlib: no requests, no yaml, no httpx. We hand-parse the small
slice of YAML this file needs (block scalars + simple lists). That keeps
the helper runnable from any host without a venv.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Tiny YAML reader — handles only what profile.yml + expectations.yml use.
# We avoid the PyYAML dependency so this script can run anywhere.
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    """Minimal YAML loader for our two file shapes.

    Supports: top-level scalar key/value, top-level list of dicts under
    `abilities:` or `atomic_ordering:`, simple block-scalar (`|`) values.
    Does NOT support: anchors, flow style, complex types. That's fine —
    these files are linter-clean and stable.
    """
    text = path.read_text()
    # Defer to PyYAML if it happens to be installed (cleaner round-trip);
    # otherwise fall back to the hand parser below.
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    out: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "|":
                # Block scalar — collect indented lines.
                i += 1
                buf = []
                while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                    buf.append(lines[i][2:] if lines[i].startswith("  ") else "")
                    i += 1
                out[key] = "\n".join(buf).rstrip() + "\n"
                continue
            if val == "":
                # Either an empty scalar or the start of a list/map.
                # Peek next non-blank line.
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].lstrip().startswith("- "):
                    out[key] = _parse_block_list(lines, i + 1)
                else:
                    out[key] = ""
                # Skip past the consumed list/empty.
                i = _skip_block(lines, i + 1)
                continue
            out[key] = val
        i += 1
    return out


def _parse_block_list(lines: list[str], start: int) -> list:
    """Parse a block list of dicts or scalars starting at lines[start]."""
    items: list = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        # Stop at an unindented line that is not a list item.
        if not line.startswith("  "):
            break
        stripped = line.lstrip()
        if stripped.startswith("- "):
            # Start a new item.
            head = stripped[2:].strip()
            item: dict | str
            if ":" in head:
                k, _, v = head.partition(":")
                item = {k.strip(): v.strip()}
                i += 1
                # Continuation lines belong to this item.
                while i < len(lines):
                    nxt = lines[i]
                    if not nxt.strip():
                        i += 1
                        continue
                    if not nxt.startswith("    "):
                        break
                    cstripped = nxt.lstrip()
                    if ":" in cstripped:
                        ck, _, cv = cstripped.partition(":")
                        cv = cv.strip()
                        if cv == "|":
                            i += 1
                            buf = []
                            while i < len(lines) and (lines[i].startswith("      ") or not lines[i].strip()):
                                buf.append(lines[i][6:] if lines[i].startswith("      ") else "")
                                i += 1
                            assert isinstance(item, dict)
                            item[ck.strip()] = "\n".join(buf).rstrip() + "\n"
                            continue
                        assert isinstance(item, dict)
                        item[ck.strip()] = cv
                    i += 1
                items.append(item)
                continue
            else:
                items.append(head)
                i += 1
                continue
        i += 1
    return items


def _skip_block(lines: list[str], start: int) -> int:
    i = start
    while i < len(lines):
        line = lines[i]
        if line and not line.startswith(" ") and not line.startswith("#") and ":" in line.split("#", 1)[0]:
            return i
        i += 1
    return i


def _dump_yaml(data: dict | list, path: Path) -> None:
    """Serialize back to YAML — try PyYAML, else hand-render the
    expectations.resolved.yml shape we own."""
    try:
        import yaml  # type: ignore

        path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
        return
    except ImportError:
        pass
    out: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                out.append(f"{k}:")
                for entry in v:
                    first = True
                    for ek, ev in entry.items():
                        prefix = "  - " if first else "    "
                        first = False
                        if isinstance(ev, str) and "\n" in ev:
                            out.append(f"{prefix}{ek}: |")
                            for ln in ev.rstrip().splitlines():
                                out.append(f"      {ln}")
                        else:
                            out.append(f"{prefix}{ek}: {ev}")
            elif isinstance(v, list):
                out.append(f"{k}:")
                for item in v:
                    out.append(f"  - {item}")
            elif isinstance(v, str) and "\n" in v:
                out.append(f"{k}: |")
                for ln in v.rstrip().splitlines():
                    out.append(f"  {ln}")
            else:
                out.append(f"{k}: {v}")
    path.write_text("\n".join(out) + "\n")


# ---------------------------------------------------------------------------
# Caldera REST helpers (urllib only — no requests dep)
# ---------------------------------------------------------------------------


def _caldera_get(url: str, key: str) -> object:
    req = urllib.request.Request(url, headers={"KEY": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — caldera URL is operator-controlled
        return json.loads(resp.read())


def _caldera_post(url: str, key: str, payload: dict) -> object:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "KEY": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Resolution + payload modes
# ---------------------------------------------------------------------------


def resolve_uuids(here: Path, caldera_url: str, key: str) -> int:
    """Walk profile.yml + expectations.yml, replace STOCKPILE:* placeholders
    with concrete Caldera UUIDs by querying /api/v2/abilities, and write
    *.resolved.yml sidecars."""
    profile = _load_yaml(here / "profile.yml")
    expectations = _load_yaml(here / "expectations.yml")
    print(f"Resolving against {caldera_url}/api/v2/abilities ...", file=sys.stderr)
    abilities = _caldera_get(f"{caldera_url}/api/v2/abilities", key)
    assert isinstance(abilities, list)

    # Build (executor, platform, slug) → UUID index. The slug is matched
    # case-insensitively on the ability's name with non-alphanumeric runs
    # collapsed to '-'. Stockpile abilities tend to have stable names
    # within a major release.
    def _slugify(s: str) -> str:
        out = []
        prev_dash = False
        for ch in (s or "").lower():
            if ch.isalnum():
                out.append(ch)
                prev_dash = False
            elif not prev_dash:
                out.append("-")
                prev_dash = True
        return "".join(out).strip("-")

    index: dict[tuple[str, str, str], str] = {}
    for ab in abilities:
        if not isinstance(ab, dict):
            continue
        slug = _slugify(ab.get("name", ""))
        for ex in ab.get("executors", []) or []:
            executor = (ex.get("name") or "").lower()
            for plat in ex.get("platforms", []) or [ex.get("platform")]:
                if not plat:
                    continue
                index[(executor, plat.lower(), slug)] = ab["ability_id"]

    def _resolve_one(ref: str) -> str | None:
        if not ref.startswith("STOCKPILE:"):
            return ref  # custom ability — leave as-is
        _, executor, platform, slug = ref.split(":", 3)
        return index.get((executor.lower(), platform.lower(), slug.lower()))

    # Resolve profile ordering.
    resolved_ordering: list[str] = []
    unresolved: list[str] = []
    for ref in profile.get("atomic_ordering", []):
        got = _resolve_one(ref)
        if got is None:
            unresolved.append(ref)
            resolved_ordering.append(ref)  # leave placeholder; runner will fail loudly
        else:
            resolved_ordering.append(got)
    profile["atomic_ordering"] = resolved_ordering

    # Resolve expectation IDs in lock-step.
    for entry in expectations.get("abilities", []):
        got = _resolve_one(entry["id"])
        if got is not None:
            entry["id"] = got

    _dump_yaml(profile, here / "profile.resolved.yml")
    _dump_yaml(expectations, here / "expectations.resolved.yml")
    print("Wrote profile.resolved.yml + expectations.resolved.yml.", file=sys.stderr)
    if unresolved:
        print(f"WARNING: {len(unresolved)} placeholder(s) did not resolve:", file=sys.stderr)
        for u in unresolved:
            print(f"  - {u}", file=sys.stderr)
        print(
            "Stockpile may have renamed these abilities; either patch the "
            "STOCKPILE: slug in profile.yml + expectations.yml or remove "
            "the entry. The runner will fail fast on placeholder UUIDs.",
            file=sys.stderr,
        )
        return 1
    return 0


def build_payload(here: Path, caldera_url: str, key: str, group: str) -> int:
    """Print the operation-creation payload to stdout. The caller pipes
    this into curl -d @-."""
    # Prefer resolved sidecars; fall back to source files.
    profile_path = here / "profile.resolved.yml"
    if not profile_path.exists():
        profile_path = here / "profile.yml"
    profile = _load_yaml(profile_path)

    # Validate every entry resolved.
    for ref in profile.get("atomic_ordering", []):
        if isinstance(ref, str) and ref.startswith("STOCKPILE:"):
            print(
                f"unresolved Stockpile placeholder in profile: {ref}\n"
                f"run `python {sys.argv[0]} --resolve-uuids` first.",
                file=sys.stderr,
            )
            return 1

    # Idempotent adversary upsert: search by name first.
    name = profile["name"]
    adv_list = _caldera_get(f"{caldera_url}/api/v2/adversaries", key)
    assert isinstance(adv_list, list)
    adv_id = None
    for adv in adv_list:
        if isinstance(adv, dict) and adv.get("name") == name:
            adv_id = adv.get("adversary_id")
            break
    if not adv_id:
        body = {
            "name": name,
            "description": profile.get("description", ""),
            "atomic_ordering": profile["atomic_ordering"],
        }
        created = _caldera_post(f"{caldera_url}/api/v2/adversaries", key, body)
        assert isinstance(created, dict)
        adv_id = created["adversary_id"]

    # Planner: prefer 'atomic' (sequential, deterministic — what we want
    # for a coverage scorecard).
    planners = _caldera_get(f"{caldera_url}/api/v2/planners", key)
    assert isinstance(planners, list)
    planner_id = None
    for pl in planners:
        if isinstance(pl, dict) and pl.get("name") == "atomic":
            planner_id = pl.get("planner_id")
            break
    if not planner_id:
        print("could not find 'atomic' planner in Caldera /api/v2/planners.", file=sys.stderr)
        return 2

    # Confirm ≥1 agent in the requested group.
    agents = _caldera_get(f"{caldera_url}/api/v2/agents", key)
    assert isinstance(agents, list)
    in_group = [a for a in agents if isinstance(a, dict) and a.get("group") == group]
    if not in_group:
        print(
            f"no Caldera agents in group '{group}' — is --profile agent up "
            f"alongside --profile caldera, and has Sandcat had ≥60s to enroll?",
            file=sys.stderr,
        )
        return 3

    payload = {
        "name": f"{name} run",
        "adversary": {"adversary_id": adv_id},
        "planner": {"planner_id": planner_id},
        "source": {"name": "basic"},  # default fact source ships with stockpile
        "auto_close": True,
        "state": "running",
        "obfuscator": "plain-text",
    }
    print(json.dumps(payload))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--resolve-uuids", action="store_true",
                   help="Resolve STOCKPILE:* placeholders to UUIDs and write *.resolved.yml.")
    p.add_argument("--caldera", default="http://127.0.0.1:8888",
                   help="Caldera base URL (default http://127.0.0.1:8888).")
    p.add_argument("--key", default="",
                   help="Caldera API key. Falls back to CALDERA_API_KEY env var.")
    p.add_argument("--group", default="red",
                   help="Sandcat agent group to target (default 'red').")
    p.add_argument("--here", default=str(Path(__file__).resolve().parent),
                   help="labs/caldera/ directory (default: this script's parent).")
    args = p.parse_args()

    import os

    key = args.key or os.environ.get("CALDERA_API_KEY", "")
    if not key:
        print("CALDERA_API_KEY not provided (use --key or env var).", file=sys.stderr)
        return 4

    here = Path(args.here)
    if args.resolve_uuids:
        return resolve_uuids(here, args.caldera, key)
    return build_payload(here, args.caldera, key, args.group)


if __name__ == "__main__":
    sys.exit(main())
