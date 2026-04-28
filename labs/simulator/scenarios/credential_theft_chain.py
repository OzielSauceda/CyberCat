"""credential_theft_chain — five-stage credential theft + endpoint compromise scenario.

Produces:
  1. identity_compromise incident (alice signed in from new attacker IP after burst of failures)
  2. identity_endpoint_chain incident (encoded PowerShell on workstation-42 cross-correlated)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from labs.simulator import event_templates as tmpl
from labs.simulator.client import SimulatorClient

log = logging.getLogger(__name__)

SCENARIO_NAME = "credential_theft_chain"

_USER = "alice"
_HOST = "workstation-42"
_ATTACKER_IP = "203.0.113.42"
_WORKSTATION_IP = "10.0.0.50"

# Real-time offsets (seconds). Compressed by --speed factor.
_STAGE2_OFFSET = 60.0   # brute force -> successful login
_STAGE3_OFFSET = 75.0   # -> session starts
_STAGE4_OFFSET = 180.0  # -> suspicious process (triggers chain)
_STAGE5A_OFFSET = 240.0 # -> net use lateral movement
_STAGE5B_OFFSET = 250.0 # -> C2 beacon outbound


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run(client: SimulatorClient, speed: float = 1.0) -> dict:
    """Fire all scenario events. Returns dict with event and incident IDs touched."""
    results: dict = {"events": [], "incidents_touched": []}

    def wait(offset_from: float, offset_to: float) -> float:
        return max(0.0, (offset_to - offset_from) * speed)

    # --- Stage 0: Register lab assets ---
    _log(f"Stage 0  Register assets: user:{_USER}  host:{_HOST}")
    await client.register_asset("user", _USER)
    await client.register_asset("host", _HOST)

    # --- Stage 1: Brute force — 6× auth.failed ---
    _log(f"Stage 1  Brute force: 6× auth.failed for {_USER} from {_ATTACKER_IP}")
    for i in range(6):
        ev = await client.post_event(
            tmpl.auth_failed(
                user=_USER,
                source_ip=_ATTACKER_IP,
                auth_type="ssh",
                dedupe_key=f"sim:cred-chain:auth.failed:{_USER}:{_ATTACKER_IP}:{i}",
            )
        )
        _record(results, ev)
        await asyncio.sleep(0.05)

    # --- Stage 2: Successful login from attacker IP ---
    pause = wait(0.0, _STAGE2_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 2...")
    await asyncio.sleep(pause)

    _log(f"Stage 2  Successful login: auth.succeeded for {_USER} from {_ATTACKER_IP}")
    ev = await client.post_event(
        tmpl.auth_succeeded(
            user=_USER,
            source_ip=_ATTACKER_IP,
            auth_type="ssh",
            dedupe_key=f"sim:cred-chain:auth.succeeded:{_USER}:{_ATTACKER_IP}",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> identity_compromise: {ev['incident_touched']}")

    # --- Stage 3: Session starts on workstation ---
    pause = wait(_STAGE2_OFFSET, _STAGE3_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 3...")
    await asyncio.sleep(pause)

    _log(f"Stage 3  Session started: {_USER} @ {_HOST}")
    ev = await client.post_event(
        tmpl.session_started(
            user=_USER,
            host=_HOST,
            session_id="sim-cred-chain-alice-01",
            dedupe_key=f"sim:cred-chain:session.started:{_USER}:{_HOST}",
        )
    )
    _record(results, ev)

    # --- Stage 4: Suspicious encoded PowerShell (triggers chain) ---
    pause = wait(_STAGE3_OFFSET, _STAGE4_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 4...")
    await asyncio.sleep(pause)

    _log(f"Stage 4  Suspicious process: encoded PowerShell on {_HOST} as {_USER}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="powershell.exe",
            cmdline="powershell.exe -enc SGVsbG8gV29ybGQ=",
            pid=4242,
            ppid=2828,
            user=_USER,
            dedupe_key=f"sim:cred-chain:process.created:{_USER}:{_HOST}:enc-ps",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> identity_endpoint_chain: {ev['incident_touched']}")

    # --- Stage 5a: net use (lateral movement signal) ---
    pause = wait(_STAGE4_OFFSET, _STAGE5A_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 5a...")
    await asyncio.sleep(pause)

    _log(f"Stage 5a Post-exploit: net use on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="net.exe",
            cmdline=r"net use \\192.168.1.100\IPC$",
            pid=4243,
            ppid=4242,
            user=_USER,
            dedupe_key=f"sim:cred-chain:process.created:{_USER}:{_HOST}:net-use",
        )
    )
    _record(results, ev)

    # --- Stage 5b: C2 beacon outbound ---
    pause = wait(_STAGE5A_OFFSET, _STAGE5B_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 5b...")
    await asyncio.sleep(pause)

    _log(f"Stage 5b C2 beacon: outbound TCP from {_HOST} to {_ATTACKER_IP}:4444")
    ev = await client.post_event(
        tmpl.network_connection(
            host=_HOST,
            src_ip=_WORKSTATION_IP,
            dst_ip=_ATTACKER_IP,
            dst_port=4444,
            proto="tcp",
            dedupe_key=f"sim:cred-chain:network.connection:{_HOST}:{_ATTACKER_IP}:4444",
        )
    )
    _record(results, ev)

    _log(
        f"Scenario complete. events={len(results['events'])}  "
        f"incidents_touched={len(results['incidents_touched'])}"
    )
    return results


async def verify(client: SimulatorClient) -> bool:
    """Assert expected incident tree was produced. Returns True on pass, False on fail."""
    _log("Verifying scenario outcome...")
    incidents = await client.get_incidents(limit=100)

    identity = [
        i for i in incidents
        if i["kind"] == "identity_compromise"
        and (i.get("primary_user") or "").lower() == _USER
    ]
    chain = [
        i for i in incidents
        if i["kind"] == "identity_endpoint_chain"
        and (i.get("primary_user") or "").lower() == _USER
    ]

    ok = True

    if identity:
        _log(f"  PASS  identity_compromise for {_USER}: {identity[0]['id']}")
    else:
        _log(f"  FAIL  identity_compromise incident not found for user {_USER!r}")
        ok = False

    if chain:
        _log(f"  PASS  identity_endpoint_chain for {_USER}: {chain[0]['id']}")
        host = chain[0].get("primary_host") or ""
        if host == _HOST:
            _log(f"  PASS  chain incident primary_host = {host!r}")
        else:
            _log(f"  FAIL  chain incident primary_host expected {_HOST!r}, got {host!r}")
            ok = False
    else:
        _log(f"  FAIL  identity_endpoint_chain incident not found for user {_USER!r}")
        ok = False

    if ok:
        _log("Verification PASSED")
    else:
        _log("Verification FAILED — check logs above")

    return ok


def _record(results: dict, ev: dict) -> None:
    results["events"].append(ev.get("event_id"))
    if ev.get("incident_touched") and ev["incident_touched"] not in results["incidents_touched"]:
        results["incidents_touched"].append(ev["incident_touched"])
