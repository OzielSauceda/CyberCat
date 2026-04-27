# ADR-0005 — Response Handler Shape: DB State First, Active Response Later

**Date:** 2026-04-22
**Status:** Accepted
**Context:** Phase 9A — Response completeness

---

## Context

Phase 9A ships the five response handlers that were stubs (`skipped`) since Phase 6. The handlers cover: `quarantine_host_lab`, `kill_process_lab`, `invalidate_lab_session`, `block_observable`, `request_evidence`.

The question was: should Phase 9A handlers produce *real OS/network side-effects* (e.g., actually kill the process, firewall-drop the host) or should they produce *DB-state changes only*, deferring Active Response to Phase 9B?

---

## Decision

**Phase 9A handlers are DB-state focused.** Actual OS/network side-effects arrive in Phase 9B via Wazuh Active Response dispatch points. Each handler still produces a **verifiable, product-meaningful state change**:

| Handler | DB state produced |
|---|---|
| `quarantine_host_lab` | `LabAsset.notes` ← quarantine marker; `Note` on incident |
| `kill_process_lab` | `EvidenceRequest` (process_list) auto-created; process Entity annotated |
| `invalidate_lab_session` | `LabSession.invalidated_at = now()` (reversible) |
| `block_observable` | `BlockedObservable` row inserted, `active=true`; detection engine checks this table on every event (30s Redis cache) |
| `request_evidence` | `EvidenceRequest` row inserted, `status=open`; analyst marks collected/dismissed |

The `block_observable` handler is the most product-complete: it makes the platform's detection engine actively respond to the block — any future event referencing a blocked IP/domain/hash fires `py.blocked_observable_match`. This is a real platform feature, not state theater.

---

## Rationale

1. **9A is independently valuable.** The response story is complete for a portfolio demo without a running Wazuh Active Response setup. The DB state is real, auditable, and visible in the UI.

2. **9B extension points are explicit.** Each disruptive handler has a `# 9B extension: dispatch Wazuh AR ...` comment marking where the AR call would go. The handlers are not half-finished; they produce the full app-layer side of the action.

3. **Disruptive handlers still give product value without AR.** A quarantine marker in `LabAsset.notes` + a note on the incident tells the analyst exactly what happened. When 9B wires the AR side, the DB state will be there to match.

4. **Reversibility is correctly modeled.** `invalidate_lab_session` and `block_observable` are `reversible` — they have working `revert()` functions. Disruptive handlers (`quarantine_host_lab`, `kill_process_lab`) correctly have no `revert`. `request_evidence` is `suggest_only` and has no revert.

---

## Consequences

- Phase 9B must add the Wazuh AR dispatch to `quarantine_host.execute()` and `kill_process.execute()`. The current handlers are the right shape to extend.
- `block_observable` becomes the first handler with a direct feedback loop into the detection engine. The Redis cache (30s TTL) is intentional — trade off between freshness and query load.
- The `evidence_requests` table is the foundation for an analyst workflow: request → collect → close. Future phases can add payload URLs (from Wazuh file collection) and automated collection triggers.
