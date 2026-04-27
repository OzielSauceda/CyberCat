# ADR-0007 — Wazuh Active Response Dispatch

**Status:** Accepted  
**Date:** 2026-04-23  
**Deciders:** Oziel (owner)

---

## Context

ADR-0005 scoped Phase 9A response handlers as **DB-state only**: `quarantine_host_lab` writes a quarantine marker to `LabAsset.notes`; `kill_process_lab` annotates the process entity and auto-creates an evidence request. Neither actually drops network traffic or terminates a process. The DB state was always intended as Phase 9A's interim scope; real OS/network side-effects were deferred to Phase 11.

Phase 11 closes that gap. Every portfolio review question of the form "does this thing actually *do* anything?" previously had a caveat answer. Phase 11 removes the caveat.

---

## Decisions

### 1. Both disruptive handlers are in scope

`quarantine_host_lab` uses Wazuh's built-in `firewall-drop` active response (no custom agent work required — the command ships with every Wazuh agent). `kill_process_lab` uses a new custom `kill-process` AR script installed on the lab agents via Dockerfile — ~40 lines of shell with a PID-to-cmdline safety check.

### 2. `ActionResult.partial` is added

If DB state commits but AR dispatch fails (manager unreachable, 5xx, timeout, agent not enrolled), the action resolves as `partial` with a human-readable reason. DB rollback is **not** used — the audit trail of what was attempted is load-bearing for "every incident explainable." `ActionStatus.partial` is also added and mapped from `ActionResult.partial` in the executor.

### 3. Separate `wazuh_ar_enabled` flag (default false)

Independent of `wazuh_bridge_enabled` so telemetry-only demos remain safe. Setting `WAZUH_AR_ENABLED=true` in `.env` enables the dispatch path; all existing Phase 9A smoke tests pass with the flag off.

### 4. AR metadata stored in existing `ActionLog.reversal_info` JSONB

No schema migration for metadata structure — JSONB absorbs the new keys. Shape:
```json
{
  "ar_dispatch_status": "dispatched|failed|skipped|disabled",
  "wazuh_command_id": "string|null",
  "ar_response": "object|null",
  "ar_dispatched_at": "ISO-8601",
  "error": "string|null"
}
```

### 5. Idempotency: dispatch anyway

`firewall-drop` is idempotent against existing iptables rules; killing a dead PID is a benign no-op. The handler does not pre-check whether the rule already exists.

### 6. Disruptive actions remain non-revertible

Phase 11 does not add a revert path for the two disruptive handlers. Demo cleanup uses a documented out-of-band step in `smoke_test_phase11.sh --cleanup` (flush iptables, restart lab-debian).

---

## Rationale

**Why `firewall-drop` for quarantine:** It is a first-class built-in Wazuh command, already installed on every agent, and idempotent. No custom script, no Dockerfile change for this path.

**Why a custom `kill-process` script:** Wazuh has no built-in process-kill AR. The custom script is small, safety-checked (validates cmdline against process_name before kill -9 to prevent PID reuse accidents), and self-logging to `/var/ossec/logs/active-responses.log`.

**Why `partial` instead of `fail` on dispatch failure:** The DB state committed and is correct — the incident is auditably quarantined in our system. "fail" implies the whole action failed, which is misleading. "partial" correctly communicates "we did our part; the enforcement layer did not confirm."

**Why not roll back DB on dispatch failure:** Rolling back the audit trail when enforcement fails is the wrong trade-off for a security system. An analyst must know what was *attempted*, not just what was confirmed.

---

## Consequences

**Known lab limitations:**

- `firewall-drop` writes runtime iptables rules only. A container restart wipes them while the DB still says "quarantined." Acceptable for lab demo; documented in runbook as the expected cleanup step.
- The Wazuh manager password lives in `infra/compose/.env` (gitignored). The token dispatcher cache invalidates on 401 and re-auths once.
- `kill-process.sh` runs as root on the agent. The cmdline/process_name safety check must be reviewed before any widening of this script's scope.

**Deferred:**
- Persistent iptables rules across agent restart.
- Windows/Sysmon agent AR (lab-debian only in Phase 11).
- Rate limiting / circuit breaking on AR dispatch (Phase 14+).
- Revert path for disruptive actions.
