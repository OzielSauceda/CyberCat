# ADR-0013 — Conntrack-Driven Network Telemetry (Phase 16.10)

**Date:** 2026-04-28
**Status:** Accepted
**Deciders:** Oziel (owner)
**Extends:** ADR-0011 (custom telemetry agent), ADR-0012 (auditd process telemetry)

---

## Context

Phase 16.9 closed the endpoint-compromise demo on the no-Wazuh path: the
`cct-agent` now tails both `/var/log/auth.log` (sshd) and
`/var/log/audit/audit.log` (auditd), shipping `auth.*`, `session.*`,
`process.created`, and `process.exited` canonical events.

The remaining canonical event kind already accepted by the backend but never
emitted in the default profile is `network.connection`. The ingest layer
defines its required fields at `backend/app/ingest/normalizer.py:13`
(`{host, src_ip, dst_ip, dst_port, proto}`); the entity extractor produces
`host` + `src_ip` from it (`backend/app/ingest/entity_extractor.py:64-70`);
the Sigma field map already routes the `network_connection` logsource onto
this kind (`backend/app/detection/sigma/field_map.py:32`); and the existing
`py.blocked_observable_match` detector (`backend/app/detection/rules/blocked_observable.py:19`)
already matches on `dst_ip` / `src_ip`. Everything downstream is wired —
the gap is the source.

Phase 16.10 plugs that gap by adding a third tail source to the agent:
Linux netfilter conntrack events from `/var/log/conntrack.log` (a file
written by `conntrack -E` running inside `lab-debian`), shipped as
canonical `network.connection` events. After this phase, every TCP/UDP
connection lab-debian initiates is observable in CyberCat, and the
`block_observable → enforcement → detection` loop closes end-to-end on
real (or synthetic) lab traffic without Wazuh.

This ADR records four architectural choices that were non-obvious or had
meaningful alternatives considered.

---

## Decisions

### 1. Event scope: `[NEW]` records only

**Chosen:** The agent emits `network.connection` events for conntrack
`[NEW]` records and ignores `[UPDATE]` and `[DESTROY]` (and any other
event types from `conntrack -E`).

**Why this scope:** `[NEW]` carries the original-direction five-tuple
(src_ip, src_port, dst_ip, dst_port, proto) — exactly what every
downstream detector cares about. `[DESTROY]` adds a duplicate event
with no new field semantics; there is no `network.disconnect` kind in
`KNOWN_KINDS` and introducing one is out of scope and unjustified for
v1. `[UPDATE]` is internal kernel state churn (TCP state transitions,
mark changes) — useless to the analyst layer.

**Rejected alternatives:**
- *Emit `[DESTROY]` as a `network.connection` event.* Doubles event volume.
  No detector benefits.
- *Add a new `network.disconnect` kind.* Requires backend schema work,
  detector updates, and produces an event no current consumer wants.
  Defer until a future detector justifies it.

### 2. Source mechanism: `conntrack -E` inside lab-debian, file-based handoff

**Chosen:** `conntrack -E -e NEW -o timestamp -o extended` runs inside
`lab-debian` (where `NET_ADMIN` already lives — see `docker-compose.yml:170-173`)
and appends to `/var/log/conntrack.log`. The `cct-agent` tails the file
through the existing `lab_logs` shared volume at
`/lab/var/log/conntrack.log`. The agent stays unprivileged.

**Why this design:** It mirrors the dual-tail pattern from Phase 16.9
(auditd) exactly. `conntrack` runs in the namespace where the netfilter
conntrack table is populated by the kernel netns. The agent never needs
`NET_ADMIN`. No new Docker capability anywhere; no new shared volume.
Operator-debug story is identical to auditd: `tail -f /var/log/conntrack.log`
inside lab-debian shows what the agent will ship.

**Rejected alternatives:**
- *Run `conntrack -E` inside the agent.* Would require `NET_ADMIN` on
  `cct-agent` AND access to the host network namespace — neither is
  needed today. Violates the agent's "telemetry-only, read-only" posture.
- *Netlink directly (NFNETLINK_CONNTRACK).* Same `NET_ADMIN` problem,
  plus we'd need to write a Python netlink parser when `conntrack -E`
  already produces a structured single-line text format.
- *eBPF.* Requires `CAP_BPF` / `--privileged` on Docker Desktop on
  Windows. Out of scope for v1 (same reasoning as ADR-0012 §3).

### 3. Why no `--privileged`, even though conntrack is in the picture

**Chosen:** lab-debian keeps its existing `cap_add: [AUDIT_WRITE,
AUDIT_CONTROL, NET_ADMIN]` set; the agent keeps its empty cap set.
`conntrack -E` requires `NET_ADMIN` to subscribe to the kernel
conntrack netlink group, and `lab-debian` already has it (since Phase 14,
predating Phase 16.10).

`--privileged` grants the full host capability set and disables
seccomp + AppArmor. CLAUDE.md §8 explicitly prohibits this without an
ADR justifying it. No such justification exists here — the required
functionality is fully achievable without it.

**Evidence the existing capability is sufficient:** lab-debian has been
running with `NET_ADMIN` since Phase 14 (`iptables` Active Response).
Subscribing to the conntrack netlink group uses the same capability
bit. The smoke test exercises the path with synthetic injection because
the kernel netlink path is unavailable on Docker Desktop on Windows
(same constraint as ADR-0012 for auditd) — that is a host-environment
limitation, not a missing capability.

**Rejected alternative:**
- *`--privileged` for simplicity.* Not acceptable per CLAUDE.md §8.

### 4. Stateless single-line parser, not buffered

**Chosen:** `parse_line(line: str) -> ParsedNetworkEvent | None`. No
buffering, no per-event-id state, no flush at EOF.

**Why stateless:** conntrack `[NEW]` records are self-contained
single lines. Unlike auditd (which interleaves SYSCALL + EXECVE + EOE
records under one event-id and requires a stateful assembler), conntrack
gives us everything in one row. Building stateful machinery for a
stateless input would be over-engineering. The parser shape ends up
closer to `parsers/sshd.py` than `parsers/auditd.py`.

**Rejected alternatives:**
- *Track conntrack `[NEW]`/`[DESTROY]` pairs to emit duration.* Out of
  scope per Decision 1.
- *Buffer to dedupe rapid-fire identical 5-tuples.* The agent's
  `Shipper` already dedupes on `(source, dedupe_key)` against the
  backend's idempotency window. A second layer in the parser would
  duplicate that work.

---

## Consequences

**Positive:**
- `./start.sh` (default profiles: `core agent`) is now sufficient for
  identity-compromise, endpoint-compromise, AND outbound-network demos.
- The `block_observable → blocked_observable_match` loop fires on real
  (or synthetic) lab traffic — the existing detector keys on `dst_ip`
  with no source-specific code.
- No new Docker capabilities, no `--privileged`. Host safety
  (CLAUDE.md §8) is preserved.
- Triple-tail topology is a straightforward extension of the dual-tail
  pattern from 16.9. No architectural novelty.

**Negative / accepted trade-offs:**
- Conntrack volume on a busy host can be high. `[NEW]`-only filtering
  + loopback/link-local drop already cuts ~80% of typical noise; if
  real-world demos still flood, a future phase adds a dst-port allowlist.
  Logrotate inside lab-debian bounds disk impact.
- On Docker Desktop on Windows / WSL2 the kernel conntrack netlink
  group is not exposed to containers, so `conntrack -E` exits silently.
  The entrypoint wraps the spawn in `( ... ) || true` and the agent
  treats a missing log file as "skip this source." The smoke test
  uses synthetic injection (same justification as ADR-0012).
- `network.connection` events are not yet consumed by any correlator.
  They flow into the events table and trigger `blocked_observable_match`
  when applicable, but a dedicated network-flavored correlator is
  deferred.

**Deferred to future phases:**
- A dedicated `py.network.suspicious_connection` detector (outbound to
  non-RFC1918 on uncommon ports, rare-dst-IP heuristic).
- Process ↔ connection correlation (which PID opened this socket).
  Requires eBPF or `/proc/net/tcp` polling + PID inspection.
- DNS-layer telemetry (`dns.query` events). Different log source.
- Pruning RFC1918 traffic at the agent — kept on-by-default in v1
  because lateral-movement detection wants it.

---

## Files affected

**New:**
- `docs/decisions/ADR-0013-conntrack-network-telemetry.md` — this file
- `agent/cct_agent/parsers/conntrack.py` — stateless single-line parser
- `agent/tests/fixtures/conntrack_new.log` — fixture
- `agent/tests/test_conntrack_parser.py` — unit tests
- `agent/tests/test_events_network.py` — event-builder tests
- `labs/smoke_test_phase16_10.sh` — end-to-end smoke

**Modified:**
- `infra/lab-debian/Dockerfile` — add `conntrack` to apt-get install list
- `infra/lab-debian/entrypoint.sh` — spawn `conntrack -E -e NEW -o timestamp -o extended`
- `agent/cct_agent/config.py` — add `conntrack_log_path`, `conntrack_checkpoint_path`, `conntrack_enabled`
- `agent/cct_agent/events.py` — dispatch `ParsedNetworkEvent`; new `_network_event()` builder
- `agent/cct_agent/__main__.py` — third async tail task + banner update
- `agent/tests/test_main_orchestration.py` — conntrack gating tests
- `infra/compose/docker-compose.yml` — three `CCT_CONNTRACK_*` env vars
- `infra/compose/.env.example` — document `CCT_CONNTRACK_ENABLED`
- `docs/architecture.md`, `docs/runbook.md`, `Project Brief.md`,
  `PROJECT_STATE.md` — updated in Phase 16.10.7

**Explicitly NOT touched:**
- `backend/app/ingest/normalizer.py` — `network.connection` already in `KNOWN_KINDS`
- `backend/app/api/schemas/events.py` — `RawEventIn.source` already accepts `"direct"`
- `backend/app/enums.py` — `EventSource.direct` already exists
- `backend/app/ingest/entity_extractor.py` — `network.connection` → host+src_ip already wired
- `backend/app/detection/rules/blocked_observable.py` — already source-agnostic
- `backend/app/detection/sigma/field_map.py` — `network_connection` mapping already present
- `agent/cct_agent/parsers/sshd.py`, `parsers/auditd.py` — unchanged
- `agent/cct_agent/sources/tail.py`, `checkpoint.py`, `shipper.py`,
  `process_state.py` — reused as-is
- Frontend — no API contract change
