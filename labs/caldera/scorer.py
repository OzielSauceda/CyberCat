"""labs/caldera/scorer.py — Phase 21 coverage scorecard generator.

Reads the expectations registry, Caldera's operation report, and
CyberCat's detections-since-window response. Emits a markdown table +
JSON sidecar at the paths passed via --out-md / --out-json.

Status enum per row:
  - covered         — ability ran AND expected_rule_id fired
  - gap             — ability ran AND expected == 'GAP' AND nothing
                      attributable fired (the honest miss)
  - false-negative  — ability ran AND expected != 'GAP' AND that rule
                      did NOT fire (bug or brittleness — investigate)
  - unexpected-hit  — ability ran AND expected == 'GAP' BUT a rule with
                      overlapping ATT&CK tags fired
  - ability-failed  — Caldera reported the ability did not execute
  - ability-skipped — ability not in the operation report at all

Attribution is conservative: a rule fire is attributed to an ability
iff any detection's `attack_tags` overlaps the ability's `technique`
(or its parent technique — e.g. T1059 is the parent of T1059.004).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


def _load_yaml(path: Path) -> dict:
    if yaml is not None:
        return yaml.safe_load(path.read_text()) or {}
    # Fall back to the in-tree mini-loader (importable when this module
    # is invoked as `python -m labs.caldera.scorer`).
    from labs.caldera.build_operation_request import _load_yaml as load
    return load(path)


def score(
    expectations: dict,
    caldera_report: dict,
    detections_payload: dict,
) -> tuple[list[dict], dict]:
    detections = detections_payload.get("items", []) or []

    # Index detections by rule_id for fast lookup; capture all hits.
    rules_fired: dict[str, list[dict]] = {}
    for d in detections:
        rules_fired.setdefault(d.get("rule_id", "?"), []).append(d)

    # Caldera's operation report shape: { 'steps': { agent_paw: [
    #   {ability_id, status, output, ...}, ... ] } }. Flatten.
    ran: dict[str, dict] = {}
    steps_obj = caldera_report.get("steps") or {}
    if isinstance(steps_obj, dict):
        for agent_steps in steps_obj.values():
            for step in agent_steps or []:
                aid = step.get("ability_id")
                if aid:
                    ran[aid] = step

    rows: list[dict] = []
    for ab in expectations.get("abilities", []):
        run_info = ran.get(ab["id"])
        expected = ab.get("expected_rule_id", "GAP")

        if not run_info:
            status, fired = "ability-skipped", []
        elif run_info.get("status") not in (0, "0", "success"):
            status, fired = "ability-failed", []
        elif expected == "GAP":
            attrib = [r for r in rules_fired if _attribution_match(ab, r, rules_fired[r])]
            status, fired = (("unexpected-hit", attrib) if attrib else ("gap", []))
        else:
            if expected in rules_fired:
                status, fired = "covered", [expected]
            else:
                status, fired = "false-negative", []

        rows.append(
            {
                "ability_id": ab["id"],
                "name": ab["name"],
                "technique": ab["technique"],
                "expected_rule_id": expected,
                "caldera_status": (run_info or {}).get("status", "n/a"),
                "fired_rules": fired,
                "status": status,
                "notes": ab.get("notes", ""),
            }
        )

    summary = {
        "total":           len(rows),
        "covered":         sum(1 for r in rows if r["status"] == "covered"),
        "gap":             sum(1 for r in rows if r["status"] == "gap"),
        "false_negative":  sum(1 for r in rows if r["status"] == "false-negative"),
        "unexpected_hit":  sum(1 for r in rows if r["status"] == "unexpected-hit"),
        "ability_failed":  sum(1 for r in rows if r["status"] == "ability-failed"),
        "ability_skipped": sum(1 for r in rows if r["status"] == "ability-skipped"),
    }
    return rows, summary


def _attribution_match(ability: dict, rule_id: str, dets: list[dict]) -> bool:
    """Return True iff any detection's attack_tags overlaps the ability's
    ATT&CK family. Symmetric overlap: {tag, parent(tag)} ∩ {target,
    parent(target)} non-empty. This catches both directions — an ability
    tagged T1059 matches a detection tagged T1059.001, and vice versa."""
    target = ability.get("technique", "")
    target_set = {target, target.split(".", 1)[0]}
    for d in dets:
        for tag in d.get("attack_tags") or []:
            tag_set = {tag, tag.split(".", 1)[0]}
            if tag_set & target_set:
                return True
    return False


def render_markdown(rows: list[dict], summary: dict, operation_id: str) -> str:
    out = [
        "# Phase 21 — Coverage Scorecard",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from "
        f"Caldera operation `{operation_id}`._",
        "",
        f"**Summary:** covered **{summary['covered']}** / {summary['total']}  ·  "
        f"gaps {summary['gap']}  ·  "
        f"false-negatives {summary['false_negative']}  ·  "
        f"unexpected hits {summary['unexpected_hit']}  ·  "
        f"ability errors {summary['ability_failed'] + summary['ability_skipped']}",
        "",
        "Status enum: **covered** | **gap** | **false-negative** | "
        "**unexpected-hit** | **ability-failed** | **ability-skipped**. "
        "See `labs/caldera/README.md` for definitions.",
        "",
        "| # | Ability | Technique | Caldera | Expected rule | Fired rules | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, start=1):
        fired = ", ".join(f"`{x}`" for x in r["fired_rules"]) or "—"
        expected = r["expected_rule_id"]
        expected_md = "`GAP`" if expected == "GAP" else f"`{expected}`"
        out.append(
            f"| {i} | {r['name']} | {r['technique']} | "
            f"{r['caldera_status']} | {expected_md} | {fired} | "
            f"**{r['status']}** |"
        )
    out.append("")
    out.append(
        "Phase 22 input: every row with status `gap` or `false-negative` "
        "is an ordered candidate. The Phase 22 plan will pick from this "
        "list by frequency, scenario coverage, and detector authoring "
        "complexity — not by the order they appear here."
    )
    return "\n".join(out) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expectations", required=True, type=Path)
    p.add_argument("--caldera-report", required=True, type=Path)
    p.add_argument("--detections", required=True, type=Path)
    p.add_argument("--operation-id", required=True)
    p.add_argument("--out-md", required=True, type=Path)
    p.add_argument("--out-json", required=True, type=Path)
    args = p.parse_args()

    expectations = _load_yaml(args.expectations)
    caldera = json.loads(args.caldera_report.read_text())
    dets = json.loads(args.detections.read_text())

    rows, summary = score(expectations, caldera, dets)

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown(rows, summary, args.operation_id))
    args.out_json.write_text(
        json.dumps(
            {
                "operation_id": args.operation_id,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "summary": summary,
                "rows": rows,
            },
            indent=2,
        )
    )
    print(f"covered {summary['covered']}/{summary['total']} — see {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
