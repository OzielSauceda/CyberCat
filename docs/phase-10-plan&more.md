# Phase 10 Plan — Chain Correlation + Attack Simulator

## Context

Phase 9B closed 2026-04-23 with 5 real response handlers (DB-state only), Sysmon decoder, TLS hardening, and 78/78 pytests green. The custom layer works end-to-end against a live Wazuh stack.

The project is currently **~7.5/10** as a portfolio piece. What's holding it back is not more capability — it's **a compelling narrative**. The most impressive capability of an XDR/SOAR is *cross-layer correlation* (an attacker's identity compromise linked to their endpoint activity as one incident), and today `IncidentKind.identity_endpoint_chain` exists in the enum but has **no correlator producing it**. That's the most glaring gap between what the project claims and what it does.

Additionally, everything is demonstrated via bash smoke tests that require a full Wazuh stack. There's no way to run a narrative demo end-to-end without infrastructure. This blocks every future phase from producing anything viewable.

**Phase 10 closes both.** One sub-track adds the chain correlator (pure custom-layer work — the product's "star"). The second adds a scripted attack simulator that fires a multi-stage attack over ~5 minutes, giving us a reproducible demo that exercises the entire stack including the new chain correlator.

This is sized as **two sub-tracks** (like Phase 9B), independently verified.

**Status:** Sub-track 1 ✅ complete and verified 2026-04-23. Sub-track 2 ⏳ implemented 2026-04-23 — awaiting live-stack verification (`bash labs/smoke_test_phase10.sh`).

---

## Sub-track 1 — `identity_endpoint_chain` correlator ✅ verified 2026-04-23

### Design decisions (resolved from exploration)

- **Trigger signal:** same rule-ID prefixes as `endpoint_compromise_standalone.py` (`py.process.*`, `sigma-proc_creation_*`, `sigma-proc-creation-*`). The chain correlator fires on endpoint signals *after* identity correlation has already run on prior auth events.
- **Dual-path logic** (inspired by `endpoint_compromise_join.py:68-83` but extended):
  - Look up open `identity_compromise` incidents where the linked `user` entity matches the event's user, opened in the last **30 minutes**.
  - **If match found:** create a **new** `identity_endpoint_chain` incident linked to the same user + the new host, with rationale referencing the prior identity incident. (Not `extend_incident()` like the join correlator — chain incidents are their own first-class kind, not an extension of identity_compromise.)
  - **If no match:** fall through and do nothing. `endpoint_compromise_standalone.py` will still run and produce a standalone `endpoint_compromise` incident. The chain correlator only activates when there's a real chain to express.
- **Dedup:** Postgres `dedupe_key` lookup, host + user scoped: `identity_endpoint_chain:{user}:{host}:{YYYYMMDDHH}`. Uses the unique-index pattern of `identity_compromise.py:55-62`.
- **Correlator ordering:** register this correlator **before** `endpoint_compromise_standalone` in `backend/app/correlation/__init__.py` so the chain gets first crack. The engine's `run_correlators` loop (engine.py:32-44) returns on first match, so if chain fires, standalone is skipped — which is correct (no double-counting).
- **Incident shape:**
  - `kind`: `identity_endpoint_chain`
  - `severity`: `high` (blended from identity's high + endpoint's medium; chain is worse than either alone)
  - `confidence`: `0.85` (higher than either parent because two independent signals converge)
  - `title`: `f"Identity + endpoint compromise chain: {user} @ {host}"`
  - `rationale`: includes reference to the source identity incident's ID and the process signal that triggered the chain
- **Linkages:**
  - `IncidentEvent`: trigger event (process.created) as `trigger`; also link the original auth.succeeded event from the identity incident as `supporting` (query `IncidentEvent` rows of the matched identity incident)
  - `IncidentEntity`: user (role `user`), host (role `host`), source_ip (role `source_ip`) if present on the user
  - `IncidentDetection`: the process detection that triggered this, plus the anomalous-signin detection from the identity incident
  - `IncidentAttack`: union of both parents' ATT&CK rows (dedup via the expression unique index at models.py:267-269 which already guards this)

### Files

**New:**
- `backend/app/correlation/rules/identity_endpoint_chain.py` — the correlator. Mirror the shape of `identity_compromise.py:39-176`: module-level `@register` decorator, async function returning `incident_id | None`, explicit dedup check, sync DB writes without commit (pipeline commits).
- `backend/tests/integration/test_identity_endpoint_chain.py` — 3 tests:
  1. **positive chain:** seed user+host assets, POST auth.failed burst → POST auth.succeeded from new IP (creates identity_compromise) → POST process.created on same host (creates chain incident). Assert exactly one `identity_endpoint_chain` incident with both user and host linked.
  2. **no identity incident → no chain:** POST process.created only. Assert chain does NOT fire; standalone `endpoint_compromise` fires instead.
  3. **identity incident for different user → no chain:** identity incident on user A, process event on user B's host. Assert no chain, but standalone endpoint does fire.

**Modified:**
- `backend/app/correlation/__init__.py` — import `identity_endpoint_chain` **before** `endpoint_compromise_standalone` so it runs first.
- `backend/app/correlation/auto_actions.py` — extend the `_AUTO_ACTIONS` dict (lines 13-22) with an entry for `IncidentKind.identity_endpoint_chain`:
  ```
  IncidentKind.identity_endpoint_chain: [
      (ActionKind.tag_incident, {"tag": "cross-layer-chain"}),
      (ActionKind.elevate_severity, {"to": "critical"}),
      (ActionKind.request_evidence, {"evidence_kind": "process_list"}),
      (ActionKind.request_evidence, {"evidence_kind": "triage_log"}),
  ]
  ```
  Chain incidents propose more actions than either parent kind because they represent higher-confidence, cross-layer compromise.
- `backend/tests/conftest.py` — no change expected; existing truncation already covers all `incidents*` tables.

### Verification (actual results 2026-04-23)

- `pytest tests/integration/test_identity_endpoint_chain.py` — **4/4 pass** (positive chain, dedup, no-chain-without-identity, no-chain-different-user)
- `pytest` full suite — **79/79 pass** (4 new + 75 existing; 0 regressions including `test_join_wins_over_standalone`)
- Correlator ordering confirmed: chain fires before join and standalone; standalone correctly takes over when no identity incident exists
- One deviation from plan: test suite grew to 4 tests (not 3) — added explicit dedup test. Severity assertion is `critical` (not `high`) because `elevate_severity` auto-action fires immediately on creation.
- Browser check: deferred to Sub-track 2 (simulator makes it repeatable).

---

## Sub-track 2 — Attack Simulator (`labs/simulator/`) ⏳ implemented 2026-04-23

### Architecture

A **Python package at `labs/simulator/`** (not a bash script — bash is too brittle for timing-sensitive scenarios and hard to extend). Fires events against `POST /v1/events/raw` using `httpx.AsyncClient` against the running backend container. No backend code imports — the simulator is a peer of the smoke tests, not part of the app.

```
labs/simulator/
├── __init__.py
├── __main__.py           # CLI entry: python -m labs.simulator --scenario credential_theft_chain
├── client.py             # thin wrapper: register_asset(), post_event(), get_incident()
├── scenarios/
│   ├── __init__.py       # registry (scenario name → runner)
│   ├── credential_theft_chain.py   # the flagship scenario
│   └── README.md         # one-line description per scenario + how to add new ones
└── event_templates.py    # parameterized builders (e.g., build_auth_failed(user, src_ip, ts))
```

### Canonical scenario: `credential_theft_chain`

Five-stage narrative on one fictional target (e.g., `alice@acme.local` on `workstation-42`):

| Stage | t+ | Event(s) fired | Expected system reaction |
|-------|-----|----------------|--------------------------|
| 1. Brute force | 0s | 6× `auth.failed` for `alice` from `203.0.113.42` | `py.auth.failed_burst` fires (supporting signal, no incident yet) |
| 2. Successful login from new IP | 60s | `auth.succeeded` for `alice` from `203.0.113.42` | `py.auth.anomalous_source_success` fires → **identity_compromise** incident opens |
| 3. Session starts | 75s | `session.started` on `workstation-42` for `alice` | lab_session row appears (Phase 9A) |
| 4. Suspicious process | 180s | `process.created` with `cmdline="powershell -enc <base64>"` on `workstation-42` | `py.process.suspicious_child` (or sigma rule) fires → **identity_endpoint_chain** incident opens (new!) |
| 5. Post-exploit activity | 240s | `process.created` for `net use` + `network.connection` outbound to attacker IP | chain incident gains supporting events; auto-action `request_evidence` proposed |

All timestamps configurable via `--speed` flag (default `1.0` = real-time 5 min; `0.1` = compressed to ~30s for quick testing).

### Reused components (no duplication)

- **API contract:** uses the canonical `POST /v1/events/raw` endpoint at `backend/app/api/routers/events.py:57-98`. Same `RawEventIn` pydantic shape (`{source, kind, occurred_at, raw, normalized, dedupe_key}`) used by smoke tests.
- **Asset registration:** uses `POST /v1/lab/assets` at `backend/app/api/routers/lab_assets.py:32-63`, mirroring the snippet in `labs/smoke_test_phase5.sh:36-41`.
- **Incident observation:** `GET /v1/incidents` — same pattern as `smoke_test_phase3.sh:54-56`.
- **Event kind vocabulary:** uses the exact kinds in `backend/app/ingest/normalizer.py:5-14` (`auth.failed`, `auth.succeeded`, `session.started`, `process.created`, `network.connection`). No new kinds required.
- **No fixture duplication:** event templates are parameterized Python builders, not static JSON. Existing fixtures under `backend/tests/fixtures/wazuh/` stay test-only.

### CLI shape

```
python -m labs.simulator --scenario credential_theft_chain \
    --api http://localhost:8080 \
    --speed 1.0 \
    --verify
```

`--verify` (default on): after scenario ends, assert the expected incident tree was produced (1 identity_compromise + 1 identity_endpoint_chain, both linked to `alice`). Exit non-zero if not. Prints a diff of actual vs expected.

### Files

**New:**
- `labs/simulator/__init__.py`
- `labs/simulator/__main__.py` — argparse + scenario dispatch
- `labs/simulator/client.py` — `httpx.AsyncClient` wrapper for asset/event/incident calls
- `labs/simulator/event_templates.py` — one builder per event kind; each returns a `RawEventIn`-shaped dict
- `labs/simulator/scenarios/__init__.py` — registry
- `labs/simulator/scenarios/credential_theft_chain.py`
- `labs/simulator/scenarios/README.md` — scenario catalog + how to add one
- `labs/smoke_test_phase10.sh` — thin wrapper that invokes `python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify` against a running stack, then greps for the chain incident in the API response. ~15-20 checks.
- `docs/decisions/ADR-0006-attack-simulator.md` — records: chose Python over bash for timing/extensibility; chose HTTP over in-process imports so simulator exercises the real API surface; scenario registry is Python module-level so new scenarios are a one-file addition.
- `docs/scenarios/credential-theft-chain.md` — operator-facing scenario description (what it simulates, what it should produce, how to run). Links from the runbook.

**Modified:**
- `docs/runbook.md` — add a "Running a demo scenario" section pointing at `python -m labs.simulator ...`.
- `PROJECT_STATE.md` — Phase 10 entry on completion, future-phases roadmap section.

### Verification

- `python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify` returns exit 0 against a clean stack
- `labs/smoke_test_phase10.sh` passes all checks
- Manual browser verification: incident list page shows both incidents; chain incident detail page shows the cross-layer rationale and proposed auto-actions
- Re-running the scenario is idempotent within its dedup window (no duplicate incidents on second run inside the hour bucket) — critical for repeatable demos

---

## Future phases (not Phase 10, but documented so we know the runway)

These are committed next-up phases per the agreed roadmap. Each is roughly one Phase-10-sized effort.

### Phase 11 — Wazuh Active Response dispatch
Wires the `quarantine_host` and `kill_process` handlers to real Wazuh AR commands via the manager API, so responses produce actual OS side-effects instead of just DB notes. Extension points are already marked in `backend/app/response/handlers/quarantine_host.py` and `kill_process.py`. Needs: a Wazuh manager API client (`backend/app/response/wazuh_ar.py`), AR script config in `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf`, a `firewall-drop` script mounted into `lab-debian`. Closes the "DB-state only" gap flagged in PROJECT_STATE.md Known gaps.

### Phase 12 — Analyst UX polish
The product's visual signature. Three deliverables:
1. **Entity graph** on the incident detail page — nodes for user/host/process/ip, edges for relationships, built from `incident_entities` + `events`. Likely `react-flow` or `cytoscape.js`.
2. **Incident timeline** — events + detections + actions plotted on a horizontal time axis, color-coded by layer (identity/endpoint/network).
3. **ATT&CK kill-chain view** — for each incident, render the matching techniques on an ATT&CK Enterprise matrix heatmap. Data is already in `incident_attack`; this is presentation only.

This phase is where screenshots become portfolio-grade.

### Phase 13 — Ship story
Not code. Turns the project into something viewable without cloning.
1. `README.md` rewrite: what CyberCat is in 2 paragraphs, demo GIF at the top, architecture diagram, runbook link.
2. 3-5 minute demo video: run the credential_theft_chain scenario, narrate what's happening in the UI, show the chain incident forming.
3. Technical writeup (blog post or `docs/case-study.md`): "Building the correlation engine" — the interesting engineering problems, not the CRUD.
4. Public repo, clean license, issue templates.

Most portfolio projects skip this phase. It's the single largest contributor to whether anyone outside you ever looks at the project.

### Optional post-Phase-13 — The 9→10 push
After Phase 13, the next "impressive" delta comes from outside the codebase: running CyberCat on a real environment (home network, VPS honeypot) for a few weeks to get a real catch story, and external engagement (HN/r/netsec post, conference talk). Revisit after Phase 13 ships.

---

## Critical files referenced

Read these before implementation:
- `backend/app/correlation/engine.py` — correlator registration and dispatch
- `backend/app/correlation/rules/identity_compromise.py` — shape to mirror for dedup + create-incident path
- `backend/app/correlation/rules/endpoint_compromise_join.py:68-83` — lookback query pattern to adapt for finding open identity incidents
- `backend/app/correlation/auto_actions.py:13-22` — dict to extend
- `backend/app/enums.py:44-48` — IncidentKind enum (identity_endpoint_chain already present)
- `backend/app/db/models.py:183,267-269` — dedupe_key unique constraint + incident_attack unique index (simulator/correlator both rely on these)
- `backend/app/api/routers/events.py:57-98` — POST /v1/events/raw schema
- `backend/app/ingest/normalizer.py:5-14` — KNOWN_KINDS for event templates
- `labs/smoke_test_phase5.sh:36-41` — asset registration snippet
- `backend/tests/integration/test_endpoint_standalone.py` — integration test pattern to mirror

## Risks / watch-outs

- **Correlator ordering.** Placing chain before standalone in the registry is intentional, but the existing test `test_endpoint_standalone.py` expects standalone to fire when there's no identity context. Confirm it still does (it should — chain only fires when a matching identity incident exists). If not, widen chain's guard.
- **Dedup race between chain and standalone.** If both correlators somehow create incidents on the same trigger event, we get duplicates. The engine's first-match-wins behavior (engine.py:32-44) prevents this as long as chain is registered first and returns an `incident_id` on success.
- **Simulator drift vs real events.** Simulator fixtures must stay shape-compatible with what the Wazuh decoder produces. If the decoder's output format changes, simulator templates must too. ADR-0006 should note this and require simulator updates in any decoder-changing phase.
- **Demo fragility.** If any phase between now and Phase 13 breaks the simulator, we lose our demo asset. Treat `smoke_test_phase10.sh` as a permanent regression gate in every future phase's verification checklist.
