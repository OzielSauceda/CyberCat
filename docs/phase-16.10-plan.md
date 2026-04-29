# Phase 16.10 — Conntrack-driven network telemetry (`network.connection`)

## Context

Phase 16.9 closed the endpoint-compromise demo on the agent path: the `cct-agent` now tails both `/var/log/auth.log` and `/var/log/audit/audit.log` and emits `auth.*`, `session.*`, `process.created`, and `process.exited` events without any Wazuh dependency. The remaining canonical event kind the backend already accepts but **nothing in the default stack ever produces** is `network.connection` — `backend/app/ingest/normalizer.py:13` requires `{host, src_ip, dst_ip, dst_port, proto}` and the schema, sigma field map, and entity extractor are all already wired (`backend/app/ingest/entity_extractor.py:64-70` extracts `host` + `src_ip` entities; `backend/app/detection/sigma/field_map.py:32` maps `network_connection` Sigma logsource → `network.connection`).

Phase 16.10 plugs that hole. The agent gains a **third tail source** that consumes Linux netfilter conntrack events from `/var/log/conntrack.log` (a file written by `conntrack -E` running inside `lab-debian`) and ships them as canonical `network.connection` events. After 16.10:

- Every TCP/UDP connection lab-debian initiates is observable in CyberCat.
- The existing `py.blocked_observable_match` detector (`backend/app/detection/rules/blocked_observable.py:19,46-59` — already checks `dst_ip` and `src_ip` against blocked observables) starts firing on real lab traffic that touches blocked IPs, closing the `block_observable → enforcement → detection` loop.
- The "egress to a known-bad IP" story is demonstrable end-to-end on the default profile, with no Wazuh.

This is **purely telemetry**: no new detectors, no new correlators, no backend code changes, no frontend changes. Scope is intentionally narrow — same shape as Phase 16.9 (auditd) and Phase 16 (sshd) before it.

**Confirmed by exploration:**

| Already in place | Where |
|---|---|
| `network.connection` in `KNOWN_KINDS` with required-fields contract | `backend/app/ingest/normalizer.py:13` |
| Entity extraction for `host` + `src_ip` from `network.connection` events | `backend/app/ingest/entity_extractor.py:64-70` |
| Sigma `network_connection` logsource → `network.connection` | `backend/app/detection/sigma/field_map.py:32` |
| `blocked_observable_match` detector keys on `dst_ip`, `src_ip` (and 5 other fields) | `backend/app/detection/rules/blocked_observable.py:19` |
| `lab-debian` has `NET_ADMIN` capability already | `infra/compose/docker-compose.yml:170-173` |
| `lab_logs:/var/log` (rw) ↔ `lab_logs:/lab/var/log:ro` shared volume | `docker-compose.yml:174-176, 212-216` |
| Reference for `network.connection` event shape | `labs/simulator/event_templates.py:103-126` |

**Gap the lab container has:** `conntrack-tools` package (provides `conntrack -E`) is NOT installed (`infra/lab-debian/Dockerfile:5-16`); `iptables` is. This is the only system-package add for 16.10.

## Architectural decisions

| Decision | Choice | Why |
|---|---|---|
| **ADR slot** | **ADR-0013** | Next free slot (0011=agent core, 0012=auditd) |
| **Event scope (v1)** | `network.connection` on conntrack `[NEW]` events only | `[NEW]` carries both endpoints + ports and is what every downstream detector cares about. `[DESTROY]` adds duplicate events with no new field semantics (no `network.disconnect` kind exists in the backend; introducing one is out-of-scope and unjustified for v1). `[UPDATE]` is internal state churn — useless to the analyst layer |
| **Source mechanism** | `conntrack -E -e NEW -o timestamp -o extended` running inside `lab-debian`, output appended to `/var/log/conntrack.log`; agent tails it via the existing `lab_logs` shared volume | Mirrors the auditd dual-tail pattern exactly. `conntrack` runs in lab-debian (where `NET_ADMIN` already lives and the netfilter conntrack table is populated by the kernel netns); the agent stays unprivileged. No new Docker capability on `cct-agent`. No new shared volume. Operator-debug story is identical: `tail -f /var/log/conntrack.log` inside lab-debian shows what the agent will ship |
| **Why not run conntrack inside the agent** | Rejected | Would require `NET_ADMIN` on `cct-agent` AND access to the host network namespace — neither is needed today. Violates the agent's "telemetry-only, read-only" posture |
| **Why not netlink directly** | Rejected | Same `NET_ADMIN` problem; also requires writing a Python netlink parser when `conntrack -E` already gives us a structured single-line text format for free |
| **Why not eBPF** | Rejected | Requires `CAP_BPF` / `--privileged` on Docker Desktop on Windows. Out of scope for v1 (same reasoning as ADR-0012 §3) |
| **Parser model** | **Stateless single-line parser** — function `parse_line(line: str) -> ParsedNetworkEvent \| None` | conntrack `[NEW]` records are self-contained single lines. No buffering, no state. Strictly simpler than the auditd parser; closer to the sshd parser shape |
| **Multi-source orchestration** | Add a third async task `_run_conntrack_source()` to `__main__.py`; gated on `config.conntrack_enabled` AND `Path(conntrack_log_path).exists()` (mirrors `audit_source_active`) | Same dual-tail pattern, just a triple now. Each source owns its checkpoint; all feed the shared `Shipper`. Zero coupling between sources |
| **Filtering at the agent** | Drop loopback (`127.0.0.0/8`, `::1`), drop link-local (`169.254/16`, `fe80::/10`); ship everything else (including RFC1918) | Loopback/link-local is pure self-noise that no detector wants. RFC1918 traffic IS interesting (lateral movement story); detectors decide. Conservative initial scope — easy to extend later |
| **Tracked-state** | **None.** Each event is independent | Unlike auditd (process lifetime tracking) we have no "matched exit" requirement. No `network.disconnect` events to emit |
| **Dedupe key** | `direct:network.connection:{conntrack_id}:{src_ip}:{dst_ip}:{dst_port}` if `id=` field present, else SHA256 of the raw line | conntrack's `id=N` (extended output) is monotonic-ish per kernel boot; using it makes restart-replay idempotent. Falls back to line hash when id is missing (same pattern as sshd) |
| **Wazuh** | Untouched | Wazuh's existing path already includes Sysmon EventID 3 / netfilter logs via its own decoders. The two sources stay interchangeable |

## Sub-phases (mirror 16.9 cadence — verify between each)

### Phase 16.10.1 — ADR + lab-debian conntrack install

- Write `docs/decisions/ADR-0013-conntrack-network-telemetry.md`. Mirrors ADR-0012's structure: Context → 4 numbered decisions (event scope, source mechanism, no `--privileged`, single-line parser) → Consequences → Files affected. Explicitly defers: a dedicated `py.network.suspicious_connection` detector, dst-port allow/denylists, process↔connection correlation (eBPF-only).
- `infra/lab-debian/Dockerfile`:
  - Add `conntrack` (the `conntrack-tools` Debian package) to the `apt-get install` line on line 5–16.
- `infra/lab-debian/entrypoint.sh`:
  - Before `exec /usr/sbin/sshd -D` (line 41), spawn `conntrack -E -e NEW -o timestamp -o extended >> /var/log/conntrack.log 2>/dev/null &` wrapped in `( ... ) || true` so it degrades gracefully on hosts where conntrack netlink isn't available (Docker Desktop on Windows). Touch the file beforehand: `touch /var/log/conntrack.log && chmod 644 /var/log/conntrack.log`.
- **Verify:**
  - `docker compose build lab-debian && docker compose up -d lab-debian`
  - `docker exec compose-lab-debian-1 which conntrack` → `/usr/sbin/conntrack`
  - `docker exec compose-lab-debian-1 ls -la /var/log/conntrack.log` exists
  - On Linux hosts: `docker exec compose-lab-debian-1 bash -c 'curl -m 2 -s http://example.com >/dev/null; sleep 1; tail -3 /var/log/conntrack.log'` shows live `[NEW]` lines

### Phase 16.10.2 — conntrack parser

- `agent/cct_agent/parsers/conntrack.py` — stateless single-line parser:
  - `parse_line(line: str) -> ParsedNetworkEvent | None`. Returns `None` for non-`[NEW]` records, malformed lines, or filtered (loopback/link-local) entries.
  - Recognized format (from `conntrack -E -e NEW -o timestamp -o extended`):
    ```
    [TS] [NEW] tcp 6 120 SYN_SENT src=10.0.0.5 dst=203.0.113.42 sport=54321 dport=443 [UNREPLIED] src=203.0.113.42 dst=10.0.0.5 sport=443 dport=54321 mark=0 use=1 id=12345
    ```
    Use the **first** `src=`/`dst=`/`sport=`/`dport=` (the original-direction tuple). Ignore the `[UNREPLIED]` reverse-direction tuple.
  - `proto` ∈ `{"tcp", "udp", "icmp"}` extracted from the first whitespace-separated token after `[NEW]`. Drop other protos (e.g. `igmp`, `gre`) silently.
- New dataclass `ParsedNetworkEvent` (in same module, distinct from `ParsedEvent` and `ParsedProcessEvent`):
  - `kind: Literal["network.connection"]`
  - `occurred_at: datetime` (parsed from the leading timestamp; UTC)
  - `src_ip: str`, `dst_ip: str`, `src_port: int`, `dst_port: int`, `proto: str`
  - `conntrack_id: int | None`
  - `raw_line: str`
- Filter helper `_should_drop(src_ip: str, dst_ip: str) -> bool`: returns True for loopback, link-local. (IPv4 + IPv6.)
- `agent/tests/fixtures/conntrack_new.log` — 6 lines: 2 TCP NEW, 1 UDP NEW, 1 ICMP NEW, 1 NEW with loopback (must be dropped), 1 malformed line.
- `agent/tests/test_conntrack_parser.py` — covers: TCP NEW parsed, UDP NEW parsed, ICMP NEW parsed, loopback dropped, link-local dropped, malformed line returns None, conntrack id extracted, original-direction tuple chosen (not reverse), timestamp parsed correctly.
- **Verify:** `cd agent && pytest tests/test_conntrack_parser.py` — all pass; `cd agent && pytest` — full suite green (92/92 prior + new conntrack tests).

### Phase 16.10.3 — Event builder dispatch

- `agent/cct_agent/events.py`:
  - Add `ParsedNetworkEvent` to the type union in `build_event()`.
  - New `_network_event(parsed: ParsedNetworkEvent, host: str) -> dict` returns a `RawEventIn`-shaped dict:
    - `source="direct"`, `kind="network.connection"`
    - `normalized={"host": host, "src_ip": parsed.src_ip, "dst_ip": parsed.dst_ip, "dst_port": parsed.dst_port, "proto": parsed.proto}`
    - `raw={"host": host, "src_port": parsed.src_port, "conntrack_id": parsed.conntrack_id, "raw_line": parsed.raw_line}`
    - `dedupe_key=f"direct:network.connection:{conntrack_id}:{src_ip}:{dst_ip}:{dst_port}"` if id present, else SHA256-of-raw-line fallback (mirror `_dedupe_key` at `agent/cct_agent/events.py:103-111`).
- `agent/tests/test_events_network.py` — confirms emitted dict matches `RawEventIn` and required fields per `backend/app/ingest/normalizer.py:13` (host, src_ip, dst_ip, dst_port, proto).
- **Verify:** `cd agent && pytest` — full suite green.

### Phase 16.10.4 — Multi-source orchestration

- `agent/cct_agent/config.py` — add three fields (mirror lines 30–34):
  - `conntrack_log_path: str = Field(default="/lab/var/log/conntrack.log")` — env: `CCT_CONNTRACK_LOG_PATH`
  - `conntrack_checkpoint_path: str = Field(default="/var/lib/cct-agent/conntrack-checkpoint.json")` — env: `CCT_CONNTRACK_CHECKPOINT_PATH`
  - `conntrack_enabled: bool = Field(default=True)` — env: `CCT_CONNTRACK_ENABLED`
- `agent/cct_agent/__main__.py`:
  - Add `_run_conntrack_source(config, shipper, stop_event)` coroutine; structurally identical to `_run_sshd_source` (stateless: parser yields events directly, no enrichment step like the auditd `TrackedProcesses`).
  - Add `conntrack_source_active(config) -> bool` helper (mirrors `audit_source_active` at lines 145-154).
  - In `_run`, after the auditd source spawn block (lines 193–197), conditionally spawn the conntrack task. Banner extends to `agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log + /lab/var/log/conntrack.log`.
  - Update the module docstring topology diagram (lines 6–31) to add the third leg.
- `agent/tests/test_main_orchestration.py` — extend with: conntrack source spins up when enabled+exists; skipped when disabled; skipped when path missing.
- **Verify:** `cd agent && pytest` — green; manual smoke locally with hand-crafted `/lab/var/log/conntrack.log`.

### Phase 16.10.5 — Compose integration

- `infra/compose/docker-compose.yml` — add to `cct-agent.environment` (after the `CCT_AUDIT_*` block at lines 207–211):
  ```yaml
  # Phase 16.10: conntrack source for network.connection events.
  # The lab_logs volume already exposes /var/log/conntrack.log from lab-debian.
  CCT_CONNTRACK_LOG_PATH: /lab/var/log/conntrack.log
  CCT_CONNTRACK_CHECKPOINT_PATH: /var/lib/cct-agent/conntrack-checkpoint.json
  CCT_CONNTRACK_ENABLED: ${CCT_CONNTRACK_ENABLED:-true}
  ```
- `infra/compose/.env.example` — document `CCT_CONNTRACK_ENABLED` under the existing cct-agent block.
- No changes to `start.sh` (banner is what the agent logs).
- **Verify:**
  - `./start.sh` (default profiles: `core agent`) — 6 containers up, no Wazuh.
  - `docker logs compose-cct-agent-1 --tail 30` shows `agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log + /lab/var/log/conntrack.log`.

### Phase 16.10.6 — End-to-end smoke test

- `labs/smoke_test_phase16_10.sh` — mirrors `smoke_test_phase16_9.sh` structure (see `labs/smoke_test_phase16_9.sh:1-267`):
  1. `./start.sh` (default profiles).
  2. Wait for agent banner including `conntrack.log`.
  3. Truncate DB + flush Redis.
  4. **Pre-stage a blocked observable** for `203.0.113.42` (direct INSERT into `blocked_observables` via `psql`, `active=true`). Cheaper than spinning up an incident + propose+execute just for the smoke; the detector keys on the table content directly.
  5. **Inject 3 synthetic conntrack lines** into `/var/log/conntrack.log` inside lab-debian (via `docker exec ... bash -c 'cat >> /var/log/conntrack.log'`):
     - 1 TCP NEW to `203.0.113.42:443` (the blocked dst)
     - 1 UDP NEW to `8.8.8.8:53` (clean traffic)
     - 1 NEW with loopback `127.0.0.1:80` (must be dropped at parser)
     - **Synthetic injection is necessary** because Docker Desktop on Windows / WSL2 does not expose the host kernel's nf_conntrack netlink to containers, so `conntrack -E` inside lab-debian never emits live events. The agent code path is identical regardless of whether lines come from the real kernel or a here-doc — same justification as Phase 16.9.6.
  6. Wait 15s for ingestion + detection.
  7. **Assert 1:** `GET /v1/events?source=direct&kind=network.connection` returns ≥ 2 (TCP to 203.0.113.42 + UDP to 8.8.8.8). Loopback must NOT be among them.
  8. **Assert 2:** `GET /v1/entities?kind=ip` includes `203.0.113.42` and `8.8.8.8`.
  9. **Assert 3:** `GET /v1/detections?rule_id=py.blocked_observable_match` returns ≥ 1, with `matched_field=dst_ip` and `matched_value=203.0.113.42`.
  10. **Assert 4:** Wazuh dormant (mirror smoke_test_phase16_9.sh:227-243).
  11. **Assert 5:** Conntrack checkpoint file exists at `/var/lib/cct-agent/conntrack-checkpoint.json` with `offset>0`.
  12. **Regression check:** `bash labs/smoke_test_phase16_9.sh` and `bash labs/smoke_test_agent.sh` still pass (no auditd/sshd path regression).
- Honour `labs/.smoke-env` `SMOKE_API_TOKEN` like the other 16.x smokes.
- **Verify:** `bash labs/smoke_test_phase16_10.sh` exits 0; `pytest backend/tests` still 173/173; `cd agent && pytest` green.

### Phase 16.10.7 — Documentation + memory note

- `docs/architecture.md` — extend "Telemetry sources" section: agent now has three tail sources (sshd, auditd, conntrack). Add the `network.connection` row to the per-kind table.
- `docs/runbook.md` — add: how to verify conntrack is running in lab-debian, how to disable via `CCT_CONNTRACK_ENABLED=false`, how to inspect the third checkpoint file, why `conntrack -E` is silent on Docker Desktop on Windows (kernel netlink inaccessible).
- `Project Brief.md` — minor update: agent now covers identity, endpoint, **and outbound-network** signals end-to-end.
- `PROJECT_STATE.md` — mark Phase 16.10 complete with verification artifacts (smoke script path, test counts).
- New memory file `project_phase16_10.md` and a one-line entry in `MEMORY.md` summarizing what shipped (mirror `project_phase16_9.md`).
- **Verify:** docs render cleanly; PROJECT_STATE matches reality.

## Files created (new)

```
docs/decisions/ADR-0013-conntrack-network-telemetry.md
agent/cct_agent/parsers/conntrack.py
agent/tests/test_conntrack_parser.py
agent/tests/test_events_network.py
agent/tests/fixtures/conntrack_new.log
labs/smoke_test_phase16_10.sh
```

## Files modified (minimal touches)

| File | Change |
|---|---|
| `infra/lab-debian/Dockerfile` | Add `conntrack` to apt-get install list |
| `infra/lab-debian/entrypoint.sh` | Spawn `conntrack -E -e NEW -o timestamp -o extended >> /var/log/conntrack.log` (degrades gracefully) |
| `agent/cct_agent/config.py` | Add `conntrack_log_path`, `conntrack_checkpoint_path`, `conntrack_enabled` |
| `agent/cct_agent/events.py` | Add `ParsedNetworkEvent` to dispatch; new `_network_event()` builder |
| `agent/cct_agent/__main__.py` | Add `_run_conntrack_source()` + `conntrack_source_active()`; spawn third task; extend banner + topology docstring |
| `agent/tests/test_main_orchestration.py` | Add 2 tests for conntrack gating |
| `infra/compose/docker-compose.yml` | Add 3 `CCT_CONNTRACK_*` env vars to cct-agent |
| `infra/compose/.env.example` | Document `CCT_CONNTRACK_ENABLED` |
| `docs/architecture.md` | Extend Telemetry sources section |
| `docs/runbook.md` | Add conntrack-source operations |
| `Project Brief.md` | Note network telemetry now agent-driven |
| `PROJECT_STATE.md` | Mark 16.10 complete |

## Files explicitly NOT touched

| File | Why it stays untouched |
|---|---|
| `backend/app/ingest/normalizer.py` | `network.connection` already in `KNOWN_KINDS` (line 13) |
| `backend/app/api/schemas/events.py` | `RawEventIn.source` already accepts `"direct"` |
| `backend/app/enums.py` | `EventSource.direct` already exists |
| `backend/app/ingest/entity_extractor.py` | `network.connection` → host+src_ip extraction already wired (lines 64-70) |
| `backend/app/detection/rules/blocked_observable.py` | Already keys on `dst_ip`, `src_ip` (line 19) — source-agnostic |
| `backend/app/detection/sigma/field_map.py` | `network_connection` → `network.connection` already mapped |
| `backend/app/correlators/*` | None currently consume `network.connection`; future detector work is out of scope |
| `agent/cct_agent/parsers/sshd.py`, `parsers/auditd.py` | Existing parser paths unchanged |
| `agent/cct_agent/sources/tail.py`, `checkpoint.py`, `shipper.py`, `process_state.py` | Reused as-is; third instances of `Checkpoint` and `tail_lines` |
| Frontend | No API contract change |
| `backend/tests/` | 173/173 must continue passing |

## Existing code to REUSE

| Existing artifact | Used for |
|---|---|
| `agent/cct_agent/sources/tail.py:tail_lines` | Third instance for `/lab/var/log/conntrack.log` |
| `agent/cct_agent/checkpoint.py:Checkpoint` | Third instance for conntrack-checkpoint.json |
| `agent/cct_agent/shipper.py:Shipper` | Same shared instance — three producers |
| `agent/cct_agent/__main__.py:_run_sshd_source` (pattern, lines 61-94) | Closer model than auditd because conntrack is also stateless single-line |
| `agent/cct_agent/__main__.py:audit_source_active` (lines 145-154) | Mirror for `conntrack_source_active` |
| `agent/cct_agent/events.py:_dedupe_key` (lines 103-111) | Fallback hash for conntrack id-less lines |
| `labs/simulator/event_templates.py:network_connection` (lines 103-126) | Reference for the canonical dict shape |
| `backend/app/detection/rules/blocked_observable.py:19,46-59` | Detector that the smoke uses to prove end-to-end flow |
| `labs/smoke_test_phase16_9.sh` | Direct template for smoke_test_phase16_10.sh |

## End-to-end verification (after 16.10.6)

```bash
# 1. Clean slate
./stop.sh
docker compose -f infra/compose/docker-compose.yml down -v

# 2. Default profiles (no Wazuh)
./start.sh

# 3. Confirm conntrack present in lab-debian
docker exec compose-lab-debian-1 which conntrack          # /usr/sbin/conntrack
docker exec compose-lab-debian-1 ls -la /var/log/conntrack.log  # exists, owned root

# 4. Confirm agent banner shows three sources
docker logs compose-cct-agent-1 --tail 30
# expect: "agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log + /lab/var/log/conntrack.log"

# 5. Run new smoke
bash labs/smoke_test_phase16_10.sh
# expect: all assertions pass, exit 0

# 6. Confirm prior smokes still pass (no regression)
bash labs/smoke_test_phase16_9.sh   # 15/15 must still pass
bash labs/smoke_test_agent.sh       # 14/14 must still pass

# 7. Backend pytest (unchanged)
docker compose exec backend pytest                 # 173/173

# 8. Agent pytest
cd agent && pytest                  # 92 prior + new conntrack tests, all green

# 9. Memory check (no regression on Phase 16 footprint goal)
docker stats --no-stream
# expect total RSS roughly unchanged from Phase 16.9 (~900 MB) — conntrack tailer is a few KB
```

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Kernel conntrack netlink not exposed to containers on Docker Desktop on Windows → `conntrack -E` exits or stays silent | `entrypoint.sh` wraps the spawn in `( ... ) || true` and uses `2>/dev/null`. Agent additionally checks `Path(conntrack_log_path).exists()` and logs a warning + skips the source rather than crashing. Smoke test injects synthetic lines (same model as 16.9.6) so the code path is exercised regardless of host capability |
| Conntrack volume floods on a busy lab | `[NEW]`-only filtering + loopback/link-local drop already cuts ~80% of typical noise. Logrotate inside lab-debian bounds disk. If real-world demos generate too much, future phase adds a dst-port allowlist |
| Conntrack id format varies across kernel versions / `nf_conntrack` build flags | Parser treats `id=` as optional; falls back to SHA256-of-line dedupe key when absent. Same robustness pattern as sshd parser's raw-line dedupe |
| `conntrack -E` permission denied even with `NET_ADMIN` (some kernels also need `net.netfilter.nf_conntrack_acct=1` set) | Document in runbook; non-blocking — graceful degradation kicks in |
| Privacy: shipping every src/dst IP from the lab to the backend logs | Not a real risk — this is a closed lab container by design. `lab-debian` doesn't initiate connections outside the demo flows. Same posture as auditd shipping every EXECVE |
| `network.connection` events not consumed by any current correlator → they sit in the events table without triggering incidents | Acceptable for v1 — Phase 16.10 is purely telemetry. The `blocked_observable_match` detector already triggers on them, which is enough to drive the smoke. Building a `py.network.suspicious_connection` detector or a network-flavored correlator is explicitly deferred |

## Deferred (explicitly OUT of 16.10)

- A dedicated `py.network.suspicious_connection` detector (e.g., outbound to non-RFC1918 on uncommon ports, rare-dst-IP heuristic). Future phase.
- Process ↔ connection correlation (which PID opened this socket). Requires eBPF or `/proc/net/tcp` polling + PID inspection. Out of scope.
- DNS-layer telemetry (`dns.query` events). Different log source; future phase if/when needed.
- IPv6 conntrack output validation beyond loopback/link-local drop (parser handles it, but no test fixture).
- Pruning RFC1918 traffic at the agent — kept on-by-default in v1 because lateral-movement detection wants it.
