# Phase 16.9 — auditd-driven process telemetry (`process.created` + `process.exited`)

## Context

Phase 16 replaced Wazuh as the default telemetry source with a custom Python agent (`agent/`, `cct-agent` container). The agent ships today emits only `auth.*` and `session.*` events derived from `/var/log/auth.log`. That's enough to drive the **identity-compromise** demo end-to-end without Wazuh, but the **endpoint-compromise** demo (detector `py.process.suspicious_child` + correlator `endpoint_compromise_standalone` / `endpoint_compromise_join`) still has no event source when Wazuh is off — process events stop at the source.

Phase 16.9 closes that gap. The agent gains a second source that tails `/var/log/audit/audit.log`, parses the EXECVE-pair records auditd already emits, and produces canonical `process.created` and `process.exited` events. After 16.9, `./start.sh` (no Wazuh profile) is sufficient for **both** the identity and endpoint compromise demos — the original promise of the Phase 16 cutover.

Almost everything we need already exists:
- Backend already accepts both kinds (`backend/app/ingest/normalizer.py:5-14` — `process.created` requires `host, pid, ppid, image, cmdline`; `process.exited` requires `host, pid`).
- `EventSource.direct` already exists (`backend/app/enums.py:16`).
- `lab-debian` already installs auditd, ships with `-a always,exit -F arch=b64 -S execve -k cybercat_exec`, and starts the daemon (`infra/lab-debian/Dockerfile:7,35`, `infra/lab-debian/entrypoint.sh:14`). `AUDIT_WRITE` + `AUDIT_CONTROL` capabilities are already granted (`docker-compose.yml:170-173`); `--privileged` is **not** required, satisfying CLAUDE.md §8.
- A `lab_logs` named volume already shares `/var/log` between lab-debian (rw) and `cct-agent` (`:/lab/var/log:ro` at `docker-compose.yml:176,211`). `audit.log` rides this same mount for free.
- Detection is already wired: `py.process.suspicious_child` (`backend/app/detection/rules/process_suspicious_child.py`), 8 Sigma `process_creation` rules, and both `endpoint_compromise_*` correlators all consume `process.created`.

So 16.9 is almost entirely a new agent module. **No backend code changes. No detection-rule changes. No frontend changes.**

## Confirmed architectural decisions

| Decision | Choice | Why |
|---|---|---|
| ADR slot | **ADR-0012** | Next free slot; ADR-0011 is the agent decision itself |
| Event scope (v1) | `process.created` (always) + `process.exited` (tracked-PID only) | `process.created` drives every existing detector. `process.exited` is bounded by emitting only for PIDs we already saw start — keeps in-memory state O(active children) and avoids flooding from broad exit-syscall rules |
| Source | auditd EXECVE+SYSCALL pair from `/var/log/audit/audit.log` | Already running in lab-debian; no new daemon, no new package |
| Audit rule for exits | New rule: `-a always,exit -F arch=b64 -S exit_group -F key=cybercat_exit` (filtered downstream by tracked-PID set) | Cheaper than userspace ptrace; agent does the filtering, kernel emits everything |
| Parser model | Stateful `AuditdParser` class that buffers lines by `audit(timestamp:event_id)` and flushes on event-id change or 100-line buffer | EXECVE+SYSCALL+PATH+PROCTITLE arrive as separate lines sharing one event id; we need all of them assembled before we can build a canonical event |
| Multi-source orchestration | Two `tail_lines()` tasks (sshd + auditd), each with its own `Checkpoint`, both feeding the same `Shipper` queue | Mirrors the existing single-source pattern; no shipper changes |
| Tracked-PID set | Plain `dict[int, ProcessRecord]` capped at 4096 entries with LRU eviction; flushed on agent restart | Cheap, bounded; an unmatched exit just gets dropped (logged at debug) |
| Wazuh status | Untouched. Phase 16.9 is purely additive on the agent side | Wazuh-via-`--profile wazuh` continues to deliver process events through its own pipeline (auditd→Wazuh agent→manager→bridge); the two paths are interchangeable |

## Sub-phases (verify between each, mirroring 16.1–16.8 cadence)

### Phase 16.9.1 — ADR + audit rule extension
- Write `docs/decisions/ADR-0012-auditd-process-telemetry.md`. Records: scope (process.created always, process.exited tracked-PID only), why no `--privileged`, why we add an exit_group rule, why we keep the dual sshd/auditd tail topology rather than a single multi-format parser.
- `infra/lab-debian/audit.rules` (new file, or append to existing rule in `Dockerfile:35`): add `-a always,exit -F arch=b64 -S exit_group -k cybercat_exit`.
- **Verify:** `docker compose up -d lab-debian && docker exec compose-lab-debian-1 auditctl -l` lists both `cybercat_exec` and `cybercat_exit` rules.

### Phase 16.9.2 — auditd parser
- `agent/cct_agent/parsers/auditd.py` — stateful `AuditdParser` class:
  - `feed(line: str) -> list[ParsedProcessEvent]` — accumulates lines by event id, returns a list of finalized events whenever the event id rolls forward (or buffer hits cap).
  - Recognizes `type=SYSCALL`, `type=EXECVE`, `type=PATH item=0`, `type=PROCTITLE`. Ignores other types silently.
  - Extracts: `pid`, `ppid`, `uid` → `user` (resolved best-effort via stored uid→name map; falls back to numeric), `exe` → `image`, decoded `argv` (a0…aN unhex if needed) → `cmdline`, `cwd` (optional), syscall id (59=execve → process.created; 231=exit_group → process.exited).
- New dataclass `ParsedProcessEvent` (in same module, kept distinct from sshd's `ParsedEvent` so each parser owns its own shape):
  - `kind: Literal["process.created", "process.exited"]`
  - `occurred_at: datetime`
  - `pid: int`, `ppid: int | None`, `user: str | None`, `image: str | None`, `cmdline: str | None`, `parent_image: str | None`, `exit_code: int | None`, `audit_event_id: int`, `raw_lines: list[str]`
- `agent/tests/fixtures/audit_execve.log` — real `auditctl -l` output with 5–7 EXECVE+SYSCALL pairs (mix of bash, sshd-spawned shells, Python interpreter, suspicious patterns we'll later trip the detector with).
- `agent/tests/fixtures/audit_exit.log` — exit_group records covering both clean (exit=0) and abnormal (exit=137 SIGKILL) cases.
- `agent/tests/test_auditd_parser.py` — covers: assembled execve event, missing PROCTITLE → still parseable, hex-encoded argv decoded correctly, multi-event interleaving, malformed line silently skipped, exit_group parsed.
- **Verify:** `cd agent && pytest tests/test_auditd_parser.py` — all tests pass.

### Phase 16.9.3 — tracked-PID emitter + event builders
- `agent/cct_agent/process_state.py` — small `TrackedProcesses` class:
  - `record(event: ParsedProcessEvent)` — on process.created, store `pid → (image, user, started_at)` in a bounded LRU (4096 cap, evict oldest).
  - `resolve_exit(event: ParsedProcessEvent) -> ParsedProcessEvent | None` — on process.exited, return enriched event only if pid is in the table; pop on hit, return `None` on miss (debug-logged).
- `agent/cct_agent/events.py` — extend `build_event()` dispatcher:
  - Recognize `ParsedProcessEvent` alongside the existing `ParsedEvent` sshd dataclass.
  - New `_process_event(parsed, host, *, kind)` returns a `RawEventIn`-shaped dict with `source="direct"`, `dedupe_key=f"direct:{kind}:{audit_event_id}:{pid}"` and the normalized fields backend requires:
    - `process.created` → `{host, pid, ppid, image, cmdline}` + optional `user`, `parent_image`
    - `process.exited` → `{host, pid}` + optional `user`, `image`, `exit_code` (carried in `raw` for debuggability)
- `agent/tests/test_events_process.py` — confirms emitted dict matches `backend/app/api/schemas/events.py:RawEventIn` shape and that `process.exited` for an unknown pid returns `None`.
- **Verify:** `cd agent && pytest` — full agent suite green (44 + new tests).

### Phase 16.9.4 — Multi-source orchestration
- `agent/cct_agent/config.py` — add fields:
  - `audit_log_path: Path = Path("/lab/var/log/audit/audit.log")` (env: `CCT_AUDIT_LOG_PATH`)
  - `audit_checkpoint_path: Path = Path("/var/lib/cct-agent/audit-checkpoint.json")` (env: `CCT_AUDIT_CHECKPOINT_PATH`)
  - `audit_enabled: bool = True` (env: `CCT_AUDIT_ENABLED`) — kill switch so tests / single-source operators can flip it off.
- `agent/cct_agent/__main__.py` — refactor the current single tail loop into a `_run_source(name, log_path, checkpoint_path, parser_factory, build_event_fn, shipper)` coroutine and spawn:
  - `sshd` source (existing behavior; no functional change)
  - `auditd` source, gated on `config.audit_enabled` AND `audit_log_path.exists()` at startup (logs warning + skips if missing — graceful degradation when running outside lab-debian or when kernel audit is unavailable)
- Each source owns its checkpoint; both share the single `Shipper`.
- Startup banner extended: `agent ready, tailing /var/log/auth.log [+ /var/log/audit/audit.log]`.
- `agent/tests/test_main_orchestration.py` (new, or extend existing) — confirms both sources spin up when both paths exist; only sshd spins up when audit path missing.
- **Verify:** `cd agent && pytest` — green; manual smoke locally with hand-crafted `audit.log`.

### Phase 16.9.5 — Compose integration
- `infra/compose/docker-compose.yml` — add to `cct-agent.environment`:
  - `CCT_AUDIT_LOG_PATH: /lab/var/log/audit/audit.log`
  - `CCT_AUDIT_ENABLED: "true"`
  - (no new volume needed — `lab_logs:/lab/var/log:ro` already covers `/var/log/audit/`)
- `infra/compose/.env.example` — document the two new vars under the existing `# cct-agent` block.
- `start.sh` — no logic change; banner already prints whatever the agent logs.
- **Verify:**
  - `./start.sh` (default profiles: `core agent`) — 6 containers up, no Wazuh.
  - `docker logs compose-cct-agent-1 --tail 30` shows `agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log`.
  - `docker exec compose-lab-debian-1 ls -la /var/log/audit/audit.log` confirms the file exists and is being written.

### Phase 16.9.6 — End-to-end smoke test
- `labs/smoke_test_phase16_9.sh`:
  1. `./start.sh` (default profiles).
  2. Wait for agent to log `tailing /lab/var/log/audit/audit.log`.
  3. Inside lab-debian: trigger an Office→shell-style spawn (one of the patterns `py.process.suspicious_child` keys on at `process_suspicious_child.py:30-86`):
     ```
     docker exec compose-lab-debian-1 bash -c \
       'cp /bin/bash /tmp/winword.exe && /tmp/winword.exe -c "id; uname -a; exit"'
     ```
     (Triggers the Office-spawn-shell branch via `parent_image` matching, plus an exit_group for tracked-PID emission.)
  4. Wait 15s for ingestion + correlation.
  5. Assert: `GET /v1/events?source=direct&kind=process.created` returns ≥ 1 with matching `image`/`cmdline`.
  6. Assert: `GET /v1/events?source=direct&kind=process.exited` returns ≥ 1 with the same pid.
  7. Assert: `GET /v1/detections` shows a fresh `py.process.suspicious_child`.
  8. Assert: `GET /v1/incidents?kind=endpoint_compromise` shows a fresh incident with the matching detection in its evidence.
  9. Assert: `GET /v1/wazuh/status` still returns `{"enabled": false, ...}` (no regression to Phase 16.6).
- Mirror exit/output style of `labs/smoke_test_agent.sh` (color, numbered assertions, exit code on first failure).
- **Verify:** `bash labs/smoke_test_phase16_9.sh` exits 0; full backend `pytest` still 173/173; `cd agent && pytest` green.

### Phase 16.9.7 — Documentation + memory note
- `docs/architecture.md` — extend the "Telemetry sources" section: agent now ingests both auth and process events; show the dual-tail topology diagram in prose.
- `docs/runbook.md` — add: how to verify auditd is running in lab-debian, how to disable the audit source via `CCT_AUDIT_ENABLED=false`, how to inspect the second checkpoint file, common parse-warning shapes.
- `Project Brief.md` — minor update: agent now covers identity **and** endpoint compromise demos without Wazuh.
- `PROJECT_STATE.md` — mark Phase 16.9 complete with verification artifacts (smoke script path, test counts).
- New memory file `project_phase16_9.md` and a one-line entry in `MEMORY.md` summarizing what shipped.
- **Verify:** docs render cleanly; PROJECT_STATE matches reality.

## Files created (new)

```
docs/decisions/ADR-0012-auditd-process-telemetry.md
infra/lab-debian/audit.rules                  (or inline append to Dockerfile)
agent/cct_agent/parsers/auditd.py
agent/cct_agent/process_state.py
agent/tests/test_auditd_parser.py
agent/tests/test_events_process.py
agent/tests/test_main_orchestration.py        (or extension of existing)
agent/tests/fixtures/audit_execve.log
agent/tests/fixtures/audit_exit.log
labs/smoke_test_phase16_9.sh
```

## Files modified (minimal touches)

| File | Change |
|---|---|
| `agent/cct_agent/config.py` | Add `audit_log_path`, `audit_checkpoint_path`, `audit_enabled` |
| `agent/cct_agent/events.py` | Dispatch `ParsedProcessEvent` → `_process_event()` |
| `agent/cct_agent/__main__.py` | Refactor to multi-source `_run_source()`; spawn sshd + auditd tails |
| `infra/lab-debian/Dockerfile` | Append exit_group audit rule (or copy in `audit.rules`) |
| `infra/compose/docker-compose.yml` | Add `CCT_AUDIT_LOG_PATH`, `CCT_AUDIT_ENABLED` to cct-agent env |
| `infra/compose/.env.example` | Document the two new env vars |
| `docs/architecture.md` | Extend "Telemetry sources" section |
| `docs/runbook.md` | Add audit-source operations |
| `Project Brief.md` | Note endpoint-compromise demo no longer needs Wazuh |
| `PROJECT_STATE.md` | Mark 16.9 complete |

## Files explicitly NOT touched (the "don't break what we built" promise)

| File | Why it stays untouched |
|---|---|
| `backend/app/ingest/normalizer.py` | `process.created` + `process.exited` already in `KNOWN_KINDS` |
| `backend/app/api/schemas/events.py` | `RawEventIn.source` already accepts `"direct"` |
| `backend/app/enums.py` | `EventSource.direct` already exists |
| `backend/app/detection/rules/process_suspicious_child.py` | Detector already keys on `process.created` normalized fields — source-agnostic |
| `backend/app/detection/sigma_pack/*` (8 process_creation rules) | Compile to `process.created`; agnostic to source |
| `backend/app/correlators/endpoint_compromise_*.py` | Already trigger on `py.process.*` and `sigma-proc_creation_*` rule prefixes |
| `backend/app/ingest/wazuh_*` | Dormant when Wazuh profile off; unaffected when it's on |
| `agent/cct_agent/parsers/sshd.py` | Sshd parsing path unchanged |
| `agent/cct_agent/sources/tail.py` | Tail logic reused as-is for the second source |
| `agent/cct_agent/checkpoint.py` | Reused as-is; second instance for audit checkpoint |
| `agent/cct_agent/shipper.py` | One shipper, multiple producers — already supports this |
| Frontend | No API contract change |
| `backend/tests/` | 173/173 must continue passing |

## Existing code to REUSE

| Existing artifact | Used for |
|---|---|
| `agent/cct_agent/sources/tail.py:tail_lines` | Second instance for `/lab/var/log/audit/audit.log` |
| `agent/cct_agent/checkpoint.py:Checkpoint` | Second instance for audit-checkpoint.json |
| `agent/cct_agent/shipper.py:Shipper` | Both sources enqueue to the same instance |
| `agent/cct_agent/events.py:_auth_event` (pattern) | Model for `_process_event` builder |
| `agent/cct_agent/parsers/sshd.py` (pattern) | Reference for parser shape; not the regex catalogue |
| `labs/simulator/event_templates.py:process_created` | Reference for the canonical dict shape (only this one — no `process_exited` exists yet) |
| `backend/app/ingest/normalizer.py:_REQUIRED` | Single source of truth for required fields per kind |
| `backend/app/detection/rules/process_suspicious_child.py:30-86` | Pattern set the smoke-test trigger needs to match |
| `labs/smoke_test_agent.sh` | Template for `smoke_test_phase16_9.sh` |

## End-to-end verification (after 16.9.6)

```bash
# 1. Clean slate
./stop.sh
docker compose -f infra/compose/docker-compose.yml down -v

# 2. Default profiles (no Wazuh)
./start.sh

# 3. Confirm both audit rules loaded inside lab-debian
docker exec compose-lab-debian-1 auditctl -l
# expect: cybercat_exec AND cybercat_exit rules listed

# 4. Confirm agent banner shows both sources
docker logs compose-cct-agent-1 --tail 30
# expect: "agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log"

# 5. Run new smoke
bash labs/smoke_test_phase16_9.sh
# expect: 9/9 assertions pass, exit 0

# 6. Confirm prior smokes still pass (no regression to 16.7)
bash labs/smoke_test_agent.sh
# expect: 7/7 pass

# 7. Backend pytest
"C:/Users/oziel/AppData/Local/Programs/Python/Python313/python.exe" -m pytest backend/tests
# expect: 173 passed, 0 failed

# 8. Agent pytest
cd agent && pytest
# expect: all green (44 prior + new auditd / events / orchestration tests)

# 9. Memory check (no regression on the Phase 16 footprint goal)
docker stats --no-stream
# expect total RSS roughly unchanged from Phase 16.6 (~700–900 MB) — auditd tailer is cheap
```

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Kernel audit not available inside Docker Desktop on some Windows hosts → audit.log empty | `entrypoint.sh:14` already runs `service auditd start ... || true`. Agent additionally checks `audit_log_path.exists()` at startup and logs a warning + skips the audit source rather than crashing. |
| auditd line interleaving (multiple events emit lines simultaneously) | Parser keys buffers by `audit_event_id` — interleaving is already the kernel's normal behavior and the buffer-by-id model handles it correctly. Tests cover interleaved fixtures. |
| Hex-encoded argv (when args contain spaces or special chars) | Parser detects bare-hex form (no quotes, even-length hex) and decodes to UTF-8 with `errors='replace'`. Test fixture includes both forms. |
| Untracked exits flooding logs at debug level | Cap LRU at 4096 entries; debug-log only; production log level is INFO so noise is invisible by default. |
| Adding exit_group rule increases auditd write volume | Bounded by lab activity (idle lab = idle log); rotated by logrotate inside lab-debian. ADR-0012 documents that we accept this for v1. |
| `cmdline` from EXECVE arg list isn't byte-identical to what Wazuh ships | Acceptable. Detection keys on substring matches over normalized fields, not exact equality. Verified by smoke step 7 (detector still fires). |
| Future `process.exited` requirement for untracked PIDs (e.g., backfill restart case) | Out of scope for v1. Documented in ADR-0012 as a deferred consideration. |

## Deferred (explicitly OUT of 16.9)

- Untracked-PID exit emission (would need persistent state across agent restarts).
- `network.connection` events via conntrack — Phase 16.10.
- File events via auditd `-w /etc -p wa` style watches — future phase.
- Token rotation, multi-source dedupe — Phase 18.
