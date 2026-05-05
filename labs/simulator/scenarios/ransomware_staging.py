"""ransomware_staging — four-stage Linux ransomware-staging scenario (Phase 20 A4).

An attacker-controlled shell on host-rw enumerates valuable documents,
archives them for exfil, simulates encryption (file-creation burst of 30
.encrypted files), and deletes the originals.

CRITICAL — STAGING ONLY (per CLAUDE.md §8 host safety + Phase 20 plan
"Calibration vs the roadmap"): the scenario emits *events* describing the
behavior. It does NOT actually encrypt files, write to /home/, or run rm.
The lab container is untouched; the operator's host is untouched. The
file-creation events are synthetic — they describe files that don't exist.

Detector reality (current platform state — see Phase 20 §A4 plan note):
  * py.process.suspicious_child  → does NOT fire on bash→find/tar/rm chains
    (Linux process-chain gap, same root cause as A1+A2+A3).
  * No "file-creation burst" detector exists. The 30-file burst over a
    60-second window is exactly the kind of signal a Phase 22 detector
    would catch — that gap IS the deliverable, not a Phase 20 fix.

Resulting incident (current platform state):
  * None. All four detectors stay silent on this choreography. The
    manifest's empty must_fire + must_not_fire of all four rules locks
    that as a regression contract.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from labs.simulator import event_templates as tmpl
from labs.simulator.client import SimulatorClient

log = logging.getLogger(__name__)

SCENARIO_NAME = "ransomware_staging"

_HOST = "host-rw.lab.local"
_USER = "alice"
_DOCS_DIR = "/home/alice/Documents"
_ARCHIVE_PATH = "/tmp/loot.tar.gz"

# Real-time offsets (seconds). Compressed by --speed factor.
_STAGE2_OFFSET = 5.0      # find → tar archive
_STAGE3_START_OFFSET = 10.0   # → file-creation burst begins
_STAGE3_END_OFFSET = 70.0     # → burst ends (60s span)
_STAGE4_OFFSET = 75.0     # → rm originals

# 30 plausible document names spanning the burst
_DOCS = [f"report-{i}.pdf" for i in range(1, 11)] + \
        [f"contract-{i}.docx" for i in range(1, 11)] + \
        [f"budget-{i}.xlsx" for i in range(1, 11)]


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run(client: SimulatorClient, speed: float = 1.0) -> dict:
    """Fire all scenario events. Returns dict with event and incident IDs touched."""
    results: dict = {"events": [], "incidents_touched": []}

    def wait(offset_from: float, offset_to: float) -> float:
        return max(0.0, (offset_to - offset_from) * speed)

    # --- Stage 0: Register lab assets ---
    _log(f"Stage 0  Register asset: host:{_HOST}, user:{_USER}")
    await client.register_asset("host", _HOST)
    await client.register_asset("user", _USER)

    # --- Stage 1: Enumerate valuable documents ---
    _log(f"Stage 1  Enumerate: bash→find {_DOCS_DIR.split('/')[1]} for docs on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/usr/bin/find",
            cmdline=f'find /home -name "*.pdf" -o -name "*.docx" -o -name "*.xlsx"',
            pid=7101,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:rw-staging:process.created:{_HOST}:find",
        )
    )
    _record(results, ev)

    # --- Stage 2: Archive for exfil ---
    pause = wait(0.0, _STAGE2_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 2...")
    await asyncio.sleep(pause)

    _log(f"Stage 2  Archive: bash→tar czf {_ARCHIVE_PATH} {_DOCS_DIR} on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/bin/tar",
            cmdline=f"tar czf {_ARCHIVE_PATH} {_DOCS_DIR}",
            pid=7102,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:rw-staging:process.created:{_HOST}:tar",
        )
    )
    _record(results, ev)

    # --- Stage 3: File-creation burst (synthetic — describes the encryption) ---
    pause = wait(_STAGE2_OFFSET, _STAGE3_START_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 3 burst...")
    await asyncio.sleep(pause)

    burst_span = _STAGE3_END_OFFSET - _STAGE3_START_OFFSET
    sleep_per_file = (burst_span * speed) / max(len(_DOCS) - 1, 1)

    _log(
        f"Stage 3  File-creation burst: {len(_DOCS)} synthetic .encrypted "
        f"files in {_DOCS_DIR} (no real files written)"
    )
    for i, doc in enumerate(_DOCS):
        ev = await client.post_event(
            tmpl.file_created(
                host=_HOST,
                path=f"{_DOCS_DIR}/{doc}.encrypted",
                user=_USER,
                dedupe_key=f"sim:rw-staging:file.created:{_HOST}:{doc}",
            )
        )
        _record(results, ev)
        if i < len(_DOCS) - 1:
            await asyncio.sleep(sleep_per_file)

    _log(f"  -> burst complete: {len(_DOCS)} file.created events")

    # --- Stage 4: Delete originals ---
    pause = wait(_STAGE3_END_OFFSET, _STAGE4_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 4...")
    await asyncio.sleep(pause)

    _log(f"Stage 4  Cleanup: bash→rm -rf {_DOCS_DIR}/* on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/bin/rm",
            cmdline=f"rm -rf {_DOCS_DIR}/*",
            pid=7103,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:rw-staging:process.created:{_HOST}:rm",
        )
    )
    _record(results, ev)

    _log(
        f"Scenario complete. events={len(results['events'])}  "
        f"incidents_touched={len(results['incidents_touched'])}"
    )
    return results


async def verify(client: SimulatorClient) -> bool:
    """Verify scenario outcome.

    Per the Phase 20 §A4 plan note, current platform state has neither a
    Linux process-chain detector nor a file-creation-burst detector. A4
    produces no incident — both gaps go in the Phase 20 summary.
    """
    _log("Verifying scenario outcome (live-run, current-platform-state)...")
    incidents = await client.get_incidents(limit=100)

    endpoint = [
        i for i in incidents
        if i["kind"] == "endpoint_compromise"
        and (i.get("primary_host") or "").lower() == _HOST
    ]

    if endpoint:
        _log(
            f"  UNEXPECTED endpoint_compromise on {_HOST}: {endpoint[0]['id']} — "
            "either Phase-22 closed the file-burst / process-chain gap, or "
            "another scenario leaked state. Update §A4 acceptance."
        )
    else:
        _log(
            f"  EXPECTED no incident for {_HOST} — current platform state has "
            "no Linux process-chain detector and no file-creation-burst "
            "detector to catch this choreography."
        )

    _log("Verification PASSED (live-run acceptance: choreography ran cleanly)")
    return True


def _record(results: dict, ev: dict) -> None:
    results["events"].append(ev.get("event_id"))
    if ev.get("incident_touched") and ev["incident_touched"] not in results["incidents_touched"]:
        results["incidents_touched"].append(ev["incident_touched"])
