# Scenario: Identity → Endpoint Chain

The first end-to-end lab scenario. Every v1 phase is built in service of this scenario producing a real, explainable, responsive incident. It is both a demo script and a smoke test — if this scenario works end-to-end, the product's core value proposition is proven.

**Narrative summary:** An attacker guesses or sprays credentials for a lab user `alice@corp.local`, eventually succeeds from a previously-unseen IP, logs into a lab Windows host, and runs an encoded PowerShell command. CyberCat should recognize the identity-side anomaly, correlate the subsequent endpoint activity into the *same* incident, produce a coherent rationale and ATT&CK mapping, auto-tag, and surface guarded response options to the analyst.

---

## Cast

| Entity | Kind | Natural key | Role |
|---|---|---|---|
| Alice | user | `alice@corp.local` | Target identity |
| Lab host | host | `lab-win10-01` | Target endpoint (registered in `lab_assets`) |
| Attacker IP | ip | `203.0.113.7` | Previously unseen source |
| Known-good IP | ip | `198.51.100.20` | Alice's usual source (pre-seeded history) |

Pre-seed state (test fixture, not part of the scripted timeline):
- Entities for Alice and the known-good IP have `first_seen` at least 7 days before `t=0` and a history of successful `auth.succeeded` events from `198.51.100.20`.
- `lab-win10-01` and `alice@corp.local` are registered in `lab_assets` so executor actions targeting them are in-scope.
- `203.0.113.7` is **not** in entities yet; it will be created on first ingest.

---

## Timeline

All times relative to `t=0` (the first ingested event). Each row describes: input → normalized result → detection reaction → correlator reaction → incident state.

### t = 0s — `auth.failed` #1

**Ingest (`POST /events/raw`):**
```json
{
  "source": "seeder",
  "kind": "auth.failed",
  "occurred_at": "<t0>",
  "raw": {"user": "alice@corp.local", "src_ip": "203.0.113.7", "reason": "bad_password", "auth_type": "basic"},
  "normalized": {"user": "alice@corp.local", "source_ip": "203.0.113.7", "auth_type": "basic", "reason": "bad_password"}
}
```

**Normalizer:**
- Upsert entity `user:alice@corp.local` (already exists, update `last_seen`).
- Upsert entity `ip:203.0.113.7` (new; `first_seen = t0`).
- Insert `events` row (kind=`auth.failed`, source=`seeder`).
- Insert `event_entities`: `(event, alice, actor)`, `(event, 203.0.113.7, source_ip)`.

**Detections:** None (single failure is not a detection).
**Correlator:** Starts a Redis window `corr:auth_failures:alice@corp.local` with a 5-minute TTL, increments count to 1.
**Incident state:** None.

### t = 15s, 30s, 45s, 60s, 75s — `auth.failed` #2–#6

Same shape as #1. Same source IP. Same user.

**Normalizer:** 5 more `events` rows + `event_entities`.
**Detections:**
- After #4 (t=45s): `py.auth.failed_burst` fires (rule definition: ≥4 failures for same user within 60s). Severity hint: `medium`. Confidence hint: `0.60`. ATT&CK tags: `T1110`, `T1110.003`. `matched_fields`: `{"count": 4, "window_sec": 60, "user": "alice@corp.local"}`.
- After #5 and #6: rule suppressed by cooldown (Redis key `corr:rule_cooldown:py.auth.failed_burst:alice@corp.local` with 120s TTL) — avoids detection spam.

**Correlator:** Records the detection but does not open an incident yet. A burst of failures without a success is noisy but not strongly actionable on its own; the correlator waits for either a success-from-same-source or a timeout.
**Incident state:** Still none.

### t = 120s — `auth.succeeded` from the same IP

**Ingest:**
```json
{
  "source": "seeder",
  "kind": "auth.succeeded",
  "occurred_at": "<t0+120>",
  "raw": {"user": "alice@corp.local", "src_ip": "203.0.113.7", "auth_type": "basic"},
  "normalized": {"user": "alice@corp.local", "source_ip": "203.0.113.7", "auth_type": "basic"}
}
```

**Normalizer:** Insert `events` row + `event_entities`.
**Detections:**
- `py.auth.anomalous_source_success` fires (rule: successful auth from a source IP not seen for this user in the last 7 days, where recent failures from the same source exist). Severity `high`, confidence `0.70`. ATT&CK tags: `T1078`, `T1078.002` (Domain Accounts — placeholder; refined later).

**Correlator — `identity_endpoint_chain` rule opens incident:**
- Computes `dedupe_key = identity_endpoint_chain:alice@corp.local:<t0_hour_bucket>`. No existing incident matches → open new.
- Insert `incidents` row:
  - `kind = identity_compromise` (we don't have the endpoint piece yet; it'll upgrade later)
  - `correlator_rule = identity_endpoint_chain`
  - `title = "Suspicious sign-in for alice@corp.local from new source 203.0.113.7"`
  - `severity` computed: max detection severity = `high` (3); +1 for ≥3 detections? No, only 2 detections. +1 for identity+endpoint? No, endpoint not present. → `high`.
  - `confidence` computed: avg hints = (0.60 + 0.70)/2 = 0.65; +0.10 rule bonus; +0.05 for 1 tactic = 0.05; +0 entity bonus. → 0.80.
  - `rationale` rendered from template: *"6 failed authentications for alice@corp.local from 203.0.113.7 within 75 seconds, followed by a successful authentication from the same previously-unseen source at t+120s. Pattern consistent with successful credential guessing or password spraying."*
- Insert junctions:
  - `incident_events`: all 6 failures (role=`supporting`) + the success (role=`trigger`). Add `py.auth.failed_burst` and `py.auth.anomalous_source_success` detections via `incident_detections`.
  - `incident_entities`: `(incident, alice, user)`, `(incident, 203.0.113.7, source_ip)`.
  - `incident_attack`: `T1110`, `T1110.003`, `T1078` (source: `rule_derived`).
- Insert `incident_transitions`: `(null → new, actor=system)`.

**Response policy evaluation:**
- `tag_incident(["credential_abuse", "new_source"])` → classification `auto_safe` → executed immediately. Row written to `actions` (status=`executed`) + `action_logs` (result=`ok`).
- `block_observable(203.0.113.7)` → `suggest_only`. Row written to `actions` (status=`proposed`). Not executed.
- `invalidate_lab_session(alice)` → `suggest_only` but no session exists yet (session starts at t=180). Row written with status=`proposed` and `params.session_id = null`.

**Incident state after t=120s:** severity=`high`, confidence=`0.80`, status=`new`, kind=`identity_compromise`, 7 events linked, 2 detections linked, 2 entities linked, 3 ATT&CK rows, 1 auto-executed action, 2 proposed actions.

### t = 180s — `session.started` on lab-win10-01

**Ingest:**
```json
{
  "source": "seeder",
  "kind": "session.started",
  "occurred_at": "<t0+180>",
  "raw": {"user": "alice@corp.local", "host": "lab-win10-01", "session_id": "sess-8841", "logon_type": "interactive"},
  "normalized": {"user": "alice@corp.local", "host": "lab-win10-01", "session_id": "sess-8841", "logon_type": "interactive"}
}
```

**Normalizer:** Insert `events` row + `event_entities` (`actor=alice`, `host=lab-win10-01`).
**Detections:** None on its own — sessions start all the time.
**Correlator:**
- Queries open incidents for user=alice within the last 30 minutes → finds our incident.
- Adds `incident_events` (role=`supporting`) and `incident_entities` (host=`lab-win10-01`).
- Does not yet change kind/severity — a session alone isn't endpoint compromise.
- Updates the outstanding `invalidate_lab_session` proposed action's `params.session_id = "sess-8841"` so it's actionable if the analyst confirms.
- Updates `incidents.updated_at`.

### t = 240s — `process.created`: encoded PowerShell

**Ingest:**
```json
{
  "source": "seeder",
  "kind": "process.created",
  "occurred_at": "<t0+240>",
  "raw": {
    "host": "lab-win10-01",
    "user": "alice@corp.local",
    "pid": 4732,
    "ppid": 3104,
    "image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "cmdline": "powershell.exe -nop -w hidden -enc JABzAD0ATgBlAHcA..."
  },
  "normalized": {
    "host": "lab-win10-01",
    "user": "alice@corp.local",
    "pid": 4732,
    "ppid": 3104,
    "image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "cmdline": "powershell.exe -nop -w hidden -enc JABzAD0ATgBlAHcA...",
    "cmdline_decoded": "$s=New-Object Net.WebClient; $s.DownloadString('http://...')"
  }
}
```

**Normalizer:**
- Upsert `process` entity with natural_key `lab-win10-01/4732/<started_epoch>`.
- Insert `events` row + `event_entities` (`actor=alice`, `host=lab-win10-01`, `process=<proc>`).

**Detections:**
- `sigma.windows.powershell.encoded_command` fires. Severity `high`, confidence `0.75`. ATT&CK tags: `T1059`, `T1059.001`, `T1027`. `matched_fields`: `{"image": "powershell.exe", "cmdline_flags": ["-enc", "-nop", "-w hidden"]}`.
- Optional `py.process.suspicious_cmdline` also fires at medium if decoded body contains `DownloadString` / `IEX` / etc.

**Correlator — `identity_endpoint_chain` rule grows incident:**
- Queries open incidents involving user=alice within the last 30 minutes → finds our incident.
- Host `lab-win10-01` is already linked (from t=180s). The incident now has confirmed endpoint activity by the compromised identity.
- **Growth actions:**
  - `incident_events`: add process event (role=`trigger`).
  - `incident_detections`: add new PowerShell detection(s).
  - `incident_entities`: add the process entity (role=`target_host` already covered; process adds as `observable` in v1 — or we add a new role `process` if cleaner; leave as `observable` for now).
  - `incident_attack`: add `T1059`, `T1059.001`, `T1027`.
  - `incidents.kind` → `identity_endpoint_chain` (the hero label).
  - `incidents.title` → "Identity → endpoint chain: alice@corp.local from 203.0.113.7 → encoded PowerShell on lab-win10-01"
  - **Severity recompute:** max hint = `high` (3); +1 for ≥3 detections (now 3–4); +1 for identity + endpoint both present → 4 → `critical`.
  - **Confidence recompute:** avg hints ≈ 0.68; +0.10 rule; +0.05 × min(3, 3 tactics covered: Initial Access/Credential Access/Execution) = 0.15; +0.05 entity bonus (alice appears in many events) → ≈ 0.98, capped 1.00. Realistically we want `0.90` feel; tune bonus weights if this looks inflated during implementation.
  - **Rationale rewrite:** *"Successful authentication for alice@corp.local from 203.0.113.7 (previously unseen; preceded by 6 failures within 75s) was followed at t+60s by interactive session on lab-win10-01 and, at t+120s, execution of an encoded PowerShell command with obfuscation flags (-nop, -w hidden, -enc). Pattern consistent with credential compromise materializing into endpoint post-compromise activity."*
- Insert `incident_transitions` row for severity change? No — transitions are for `status`. Severity change is audit-visible via `updated_at` + `action_logs` if we later add `elevate_severity` actions; for correlator-driven severity we do not write a transition row.

**Response policy re-evaluation:**
- New proposed actions because endpoint compromise is now confirmed:
  - `kill_process_lab({process_entity_id})` → classification `disruptive` → status=`proposed`.
  - `flag_host_in_lab(lab-win10-01)` → classification `reversible` → status=`proposed`.
  - `quarantine_host_lab(lab-win10-01)` → classification `disruptive` → status=`proposed`.
  - `request_evidence({host, user, kinds: ["process_tree", "session_history"]})` → `suggest_only` → status=`proposed`.
- Existing `block_observable(203.0.113.7)` remains `proposed`.
- Another auto-tag: `tag_incident(["powershell_encoded", "post_compromise_activity"])` → `auto_safe` → executed.

**Incident state after t=240s:** severity=`critical`, confidence≈`0.95`, kind=`identity_endpoint_chain`, status=`new`, 9 events linked, 4 detections linked, 4 entities linked (alice, 203.0.113.7, lab-win10-01, process), 6 ATT&CK rows, 2 executed auto-tag actions, 5 proposed actions.

### t = ~5 min — Analyst inspects

Analyst opens the incident in the UI:
- Header: title, `critical`, confidence bar at ~0.95, status `new`.
- Timeline: 9 events in chronological order, grouped by entity (4 auth events under alice, 1 session under lab-win10-01, 1 process under lab-win10-01, etc.).
- Entities panel: alice (role=user), 203.0.113.7 (source_ip), lab-win10-01 (host), process entity (observable).
- ATT&CK panel: T1110, T1110.003, T1078, T1059, T1059.001, T1027.
- Rationale: the rewritten text above.
- Response panel: 2 executed auto-tags, 5 proposed actions with classification badges.

Analyst transitions `new → triaged` (reason: "confirmed malicious, taking action") → `incident_transitions` row.

### t = ~6 min — Analyst confirms flag_host_in_lab

Analyst clicks **Execute** on the `flag_host_in_lab` proposed action.
- Executor checks `lab_assets` → `host:lab-win10-01` is in-scope → proceeds.
- `action.status` → `executed`.
- `action_logs` row: `result=ok`, `reversal_info = {"prev_lab_flagged": false}`.
- Side effect: `entities.attrs` JSONB updated for the host: `lab_flagged = true`, `lab_flagged_at = <now>`.
- UI re-renders; response panel shows 1 more executed action.

### t = ~7 min — Analyst transitions to `investigating` then `contained`

- `triaged → investigating` (reason: "isolating host, pulling process tree"). Transition row.
- Analyst executes `request_evidence` (suggest_only, safe): `action_logs` row.
- `investigating → contained` (reason: "host flagged, session invalidated, observable tagged"). Transition row.

Incident remains open; status `contained`. `closed_at` still NULL.

---

## Explainability audit — every question answerable from the DB

| Question | How it's answered |
|---|---|
| What events contributed? | `incident_events` join with roles |
| Which rules fired? | `incident_detections` join `detections` (includes `rule_id`, `rule_source`, `matched_fields`) |
| Who/what is involved? | `incident_entities` with roles |
| Why is severity this? | `detections.severity_hint` values + computation policy doc |
| Why is confidence this? | `detections.confidence_hint` + computation policy (rule bonus, tactic bonus, entity bonus) |
| What ATT&CK applies? | `incident_attack` with `source` column indicating rule-derived vs correlator-inferred |
| Why does the correlator think this is one incident? | `incidents.correlator_rule` + `incidents.rationale` |
| What actions ran? | `actions` + `action_logs` |
| Who changed status, when, why? | `incident_transitions` |

No black-box fields. No "trust me" values.

---

## Lab-safety audit

- All response actions involve entities whose natural keys are in `lab_assets`. Confirmed: alice, lab-win10-01, 203.0.113.7 (we register the attacker IP in lab_assets explicitly since we want to allow blocking — else `block_observable` would be skipped).
- No action targets anything outside the operator's controlled environment.
- Every executed action has a reversal path (or is clearly irreversible and classified `disruptive`).

---

## Demo choreography (for runbook Phase 7)

1. Start core stack (`compose up`).
2. Run the seeder: `python -m labs.seeders.identity_endpoint_chain`.
3. Watch the UI at `http://localhost:3000/incidents`. Within ~5 minutes a new incident appears and grows twice.
4. Open the incident — narrate through timeline, entities, ATT&CK, rationale.
5. Execute `flag_host_in_lab`. Show `action_logs` and host entity update.
6. Transition through statuses. Show transition log.
7. Refresh list; incident is `contained` and sorted accordingly.

Total demo time: ~8–10 minutes. Entire scenario reproducible from a clean DB.

---

## Open items this scenario deliberately defers

- **Real Wazuh source.** Phase 8 replaces the seeder with a Wazuh adapter that emits the same normalized events. Scenario re-plays identically.
- **Session entity as first-class.** v1 treats session as a field on `session.started` events, not an entity. If session invalidation grows into a real capability we'll add a `session` entity kind.
- **Process tree graph.** v1 stores individual processes; a full process tree is a later enhancement (Phase 9+).
- **Auto-containment policy.** All containment actions in this scenario are `suggest_only` / `disruptive`. We're intentionally not auto-quarantining in v1 until the policy engine has more maturity.
