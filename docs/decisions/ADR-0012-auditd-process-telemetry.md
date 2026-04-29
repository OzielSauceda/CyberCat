# ADR-0012 — auditd-Driven Process Telemetry (Phase 16.9)

**Date:** 2026-04-28
**Status:** Accepted
**Deciders:** Oziel (owner)
**Extends:** ADR-0011 — the custom telemetry agent now ingests process events in addition to auth/session events

---

## Context

Phase 16 replaced Wazuh as the default telemetry source with the `cct-agent` Python container, which tails `/var/log/auth.log` and emits `auth.*` and `session.*` events. That path is sufficient for the **identity-compromise** demo end-to-end. However, the **endpoint-compromise** demo — driven by detector `py.process.suspicious_child` and correlators `endpoint_compromise_standalone` / `endpoint_compromise_join` — still has no event source when Wazuh is off: process events stop at the source.

The backend already accepts `process.created` and `process.exited` (they are in `KNOWN_KINDS` since Phase 6), and `lab-debian` already runs auditd with an EXECVE capture rule (`cybercat_exec`). Phase 16.9 wires the existing auditd output into the agent, closing the gap so that `./start.sh` (no Wazuh profile) is sufficient for **both** the identity and endpoint compromise demos.

This ADR records four architectural choices that were non-obvious or had meaningful alternatives considered.

---

## Decisions

### 1. Event scope: `process.created` always, `process.exited` tracked-PID only

**Chosen:** The agent emits a `process.created` event for every EXECVE record it parses. It emits `process.exited` only for PIDs it previously recorded as having started — i.e., PIDs that already exist in the agent's in-memory tracked-PID table.

Unmatched exits (processes that started before the agent launched, or before the audit tail caught up) are dropped and logged at DEBUG. The tracked-PID table is bounded at 4096 entries with LRU eviction; an evicted entry's eventual exit is silently dropped.

**Why this scope:** `process.created` is what every existing detector and correlator consumes. The bounded `process.exited` emission keeps in-memory state O(number of active children) rather than O(all processes ever seen). A lab-debian idle system generates dozens of short-lived processes per minute; emitting an exit event for every one of them — including auditd's own children, cron wakeups, and shell built-ins — would flood the backend with events that no detector consumes.

**Rejected alternatives:**
- *Emit `process.exited` for every exit_group syscall.* Generates ~ 5× the event volume with no detector benefit. The detectors that matter (`endpoint_compromise_*`) are correlated on `process.created` signals; they do not currently consume `process.exited`.
- *Suppress `process.exited` entirely.* Deprives future detectors of process lifetime data, which is useful for anomaly detection (process running unusually long, process exited abnormally). Including it now, even bounded, is low cost.
- *Persistent cross-restart tracked-PID state.* Would require persisting the PID table to disk on shutdown. The complexity is not justified for v1: the gap window (agent restart → process exit for a pre-restart process) is small in a lab setting and the dropped events are logged.

### 2. Source: auditd EXECVE+SYSCALL pair from `/var/log/audit/audit.log`

**Chosen:** Tail the file that auditd already writes inside `lab-debian`. No new daemon, no new package, no new Docker capability. The `lab_logs` named volume already shares `/var/log` from `lab-debian` (rw) to `cct-agent` (`/lab/var/log:ro`), so `/var/log/audit/audit.log` is reachable at `/lab/var/log/audit/audit.log` inside the agent container without any compose change.

**Rejected alternatives:**
- *Netlink audit socket.* Requires the agent container to open `NETLINK_AUDIT` directly, which needs `CAP_AUDIT_READ` or `--privileged`. Violates CLAUDE.md §8 host safety constraint. Also ties the agent to the same Linux host as the auditd daemon, eliminating the architectural separation between lab container and agent container.
- *Wazuh `audit_log` localfile.* Would re-introduce a Wazuh dependency in the default (no-Wazuh) path, defeating the point of Phase 16.
- *eBPF / bpftrace.* Powerful, but requires `CAP_BPF` or `CAP_SYS_ADMIN`, both of which require `--privileged` inside Docker Desktop on Windows. Out of scope for v1.

### 3. Why no `--privileged` and why the existing capabilities are sufficient

**Chosen:** `lab-debian` runs with `cap_add: [AUDIT_WRITE, AUDIT_CONTROL]`. These two capabilities are sufficient for auditd to load rules (AUDIT_CONTROL) and for processes to write audit records to the kernel ring buffer (AUDIT_WRITE). The cct-agent container needs no elevated capabilities at all — it reads a file via a shared volume.

`--privileged` grants the full host capability set and disables seccomp + AppArmor profiles. On a personal development machine this means a compromised container could affect the host OS. CLAUDE.md §8 explicitly prohibits this unless justified by an ADR. No such justification exists here — the required functionality is fully achievable without it.

**Evidence that the current capabilities are sufficient:** `lab-debian` has been loading the `cybercat_exec` EXECVE rule since Phase 14 without `--privileged` and auditctl confirms the rule is active (`docker exec compose-lab-debian-1 auditctl -l`). Adding a second rule (`cybercat_exit`) requires no additional capabilities.

**Rejected alternative:**
- *`--privileged` for simplicity.* Not acceptable per CLAUDE.md §8. The elevated capability set in `docker-compose.yml` was explicitly sized to the minimum required.

### 4. Dual tail topology (sshd + auditd as independent sources), not a unified multi-format parser

**Chosen:** The agent runs two independent asyncio tail tasks: one for `/lab/var/log/auth.log` (sshd events, existing) and one for `/lab/var/log/audit/audit.log` (auditd events, new). Each source owns its own `Checkpoint` instance and its own parser instance. Both enqueue to the single shared `Shipper`.

**Why independent sources:** The two log formats are structurally incompatible. `/var/log/auth.log` is single-line syslog records, each self-contained. `/var/log/audit/audit.log` is a stream of structured key=value records where a single logical event (an EXECVE) spans multiple lines sharing an `audit(timestamp:event_id)` cookie. A unified parser would need to detect format on every line (expensive, fragile) and route to sub-parsers — which is functionally equivalent to two independent parsers with extra dispatch glue.

The two-checkpoint design is also necessary: auth.log and audit.log grow at different rates and are rotated independently. A single checkpoint would couple them; a restart that resumes from the wrong offset for one format would silently parse the other format's lines with the wrong parser.

**Rejected alternatives:**
- *Single unified multi-format tail loop.* Conflates two distinct parsing concerns, makes testing harder (test fixtures would need to interleave two line formats), and requires format detection per line.
- *Separate agent processes / containers.* Operationally expensive: doubles the number of containers to manage, doubles the token/auth configuration, and splits the Shipper's dedup window across two independent processes. One agent with two internal sources is cleaner.

---

## Consequences

**Positive:**
- `./start.sh` (default profiles: `core agent`) is now sufficient for both identity-compromise and endpoint-compromise demos. The original Phase 16 promise is fully delivered.
- No new Docker capabilities, no `--privileged`. Host safety (CLAUDE.md §8) is preserved.
- The dual-tail topology is a straightforward extension of the single-tail pattern already tested in Phase 16. No architectural novelty.
- `process.exited` emission is included now, even in bounded form, so future detectors that need process lifetime data have a source without another agent refactor.

**Negative / accepted trade-offs:**
- Adding the `cybercat_exit` exit_group rule increases auditd write volume proportionally to process creation rate. In an idle lab this is negligible; under heavy load (e.g., a benchmark running hundreds of processes/sec) the audit log can grow quickly. Logrotate inside lab-debian bounds the disk impact; the agent's checkpoint prevents re-processing rotated files.
- Unmatched exits (processes that started before agent launch, or after LRU eviction) are silently dropped. An operator who restarts the agent mid-demo loses exit attribution for processes that started before the restart. Logged at DEBUG; acceptable for v1.
- In-memory tracked-PID state (up to 4096 entries) is lost on agent restart. A process that exits after an agent restart will not produce a `process.exited` event. Documented as a deferred consideration.

**Deferred to future phases:**
- Persistent tracked-PID state across agent restarts (would require checkpoint file for the PID table).
- `network.connection` events via conntrack — Phase 16.10.
- File events via auditd `-w /etc -p wa` style watches — future phase.
- Emitting `process.exited` for untracked PIDs (processes that predate agent start) — requires a different mechanism (e.g., reading `/proc` on startup to pre-populate the table).

---

## Files affected

**New:**
- `infra/lab-debian/audit.rules` — two-rule file replacing the inline Dockerfile echo
- `docs/decisions/ADR-0012-auditd-process-telemetry.md` — this file
- `agent/cct_agent/parsers/auditd.py` — stateful auditd line parser (Phase 16.9.2)
- `agent/cct_agent/process_state.py` — tracked-PID LRU table (Phase 16.9.3)
- `agent/tests/test_auditd_parser.py`, `agent/tests/test_events_process.py`, `agent/tests/test_main_orchestration.py` — new test modules (16.9.2–16.9.4)
- `agent/tests/fixtures/audit_execve.log`, `agent/tests/fixtures/audit_exit.log` — test fixtures (16.9.2)
- `labs/smoke_test_phase16_9.sh` — end-to-end smoke script (16.9.6)

**Modified:**
- `infra/lab-debian/Dockerfile` — replace inline RUN echo with `COPY audit.rules` (Phase 16.9.1)
- `agent/cct_agent/config.py` — add `audit_log_path`, `audit_checkpoint_path`, `audit_enabled` (Phase 16.9.4)
- `agent/cct_agent/events.py` — dispatch `ParsedProcessEvent` (Phase 16.9.3)
- `agent/cct_agent/__main__.py` — multi-source orchestration (Phase 16.9.4)
- `infra/compose/docker-compose.yml` — add `CCT_AUDIT_*` env vars to cct-agent (Phase 16.9.5)
- `infra/compose/.env.example` — document new vars (Phase 16.9.5)
- `docs/architecture.md`, `docs/runbook.md`, `Project Brief.md`, `PROJECT_STATE.md` — updated in Phase 16.9.7

**Explicitly NOT touched:**
- `backend/app/ingest/normalizer.py` — `process.created`/`process.exited` already in `KNOWN_KINDS`
- `backend/app/api/schemas/events.py` — `RawEventIn.source` already accepts `"direct"`
- `backend/app/enums.py` — `EventSource.direct` already exists
- `backend/app/detection/rules/process_suspicious_child.py` — already source-agnostic
- `agent/cct_agent/parsers/sshd.py` — sshd path unchanged
- `agent/cct_agent/sources/tail.py` — reused as-is for the second source
- `agent/cct_agent/checkpoint.py` — reused as-is; second instance for audit checkpoint
- `agent/cct_agent/shipper.py` — one shipper, multiple producers
