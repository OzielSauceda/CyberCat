# Learning Plan — Phase 19.7 Consolidation Sprint

A 4-week structured re-read of CyberCat from Phase 0 through Phase 19.5. The goal is to convert the working codebase into a working *mental model*: by the end, you should be able to walk a recruiter, a teammate, or yourself-six-months-from-now through every layer of the system without needing to look something up first.

This plan is the answer to one question: *"I built something impressive but I don't fully understand how it works. What do I do?"*

---

## Why a sprint, not a permanent slowdown

You moved Phase 0 → 19.5 in roughly two months with heavy AI assistance. That shipped a working incident-response platform faster than learning-by-typing would have, but it also outran your retention. The codebase contains concepts you've used but not internalized: ASGI request lifecycles, async event loops, Pydantic v2 validation, SQLAlchemy session boundaries, Alembic migration ordering, Redis pub/sub semantics, MITRE ATT&CK tactic vs. technique distinctions, Sigma rule field mapping, JWT vs. session cookie tradeoffs, Postgres advisory locks, conntrack state tables, sshd PAM hooks, Next.js App Router server vs. client component boundaries, OpenAPI-typed client generation, and so on.

A 4-week consolidation sprint converts that latent surface into active knowledge. After the sprint, you resume Phase 20+ from a position of actually owning the foundation — which makes the headline work (Caldera coverage scorecard, LotL detection thesis, behavior-chain detection) shippable from the same depth a senior engineer would ship it from.

**Sprint exit criterion:** you can answer, without looking, "what happens when an sshd login failure arrives at the agent until the analyst sees an incident in the UI" — every step, every file, every tradeoff at every step.

---

## Operating principles

1. **No new feature phases during the sprint.** The chaos work that's already in flight (A1 from the Wed remote agent, regression-injection sanity check, optional CI workflow runs) finishes on its own track and is unblocked by this plan.
2. **Daily commits come from the sprint itself.** Walkthrough sections, learning-notes expansions, code comments surfaced during tracing, small refactors. The streak is a side effect of doing the work, not a goal you optimize toward.
3. **Read before write.** Every day starts with reading specified files in a specified order. The writing comes second and is your evidence that the reading produced understanding.
4. **The assistant explains; you type.** When a daily task requires writing prose into `walkthroughs.md` or `learning-notes.md`, *you* type it. The assistant can answer questions, point at files, expand a learning-notes entry, but the prose in `walkthroughs.md` is operator-authored. Friction is the entire point.
5. **One concept stack-deep, no skips.** If a daily task touches a concept you don't follow, stop and resolve it before moving on. A 20-minute detour on the day's topic beats two weeks of compounding confusion.
6. **Modular by week.** If life intervenes, completing only Week 1 is a real win. Each week stands on its own. Don't power through if a week reveals deeper gaps — extend the week, don't skip it.

---

## Files this plan touches

- **`docs/walkthroughs.md`** *(new)* — five end-to-end slice traces written by the operator. The headline artifact of the sprint.
- **`docs/learning-notes.md`** *(existing)* — expanded as gaps surface. The assistant rewrites entries on request; you re-read.
- **Code files** — small comment additions and tiny refactors surfaced while tracing. Not the main output, but real commits.
- **`PROJECT_STATE.md`** — header tracks Phase 19.7 progress. Updated weekly.

---

## Daily structure

Each weekday follows the same shape. Time-budget: 60–120 minutes. Cap at 2 hours; if a day runs over, push the rest into the next day rather than burning yourself out.

```
1. READ    (~30 min)  — open specified files in specified order. No assistant summary.
2. TRACE   (~30 min)  — follow the data flow or concept across files. Take rough notes.
3. WRITE   (~30–60 min) — produce the day's artifact: a walkthrough section, a learning-notes
                          expansion, or a code-comment commit. Operator types the prose.
4. COMMIT  (~5 min)   — `git add` + meaningful message. One commit if work was coherent;
                          two or three if natural seams existed. Don't pad.
```

Exit criterion per day = the question the day's writing answers. If you can answer that question cold a week later by re-reading what you committed, the day worked.

**Weekend days** are reserved for the parallel mini-project (Week 1 weekend onward). The mini-project lives in a separate public repo and produces its own commits. Two evenings per weekend, ~2 hours each. See `docs/walkthroughs.md` § "Parallel mini-project" for scope.

---

## Week 1 — Foundations & Data Plane (Phases 0–8)

**Theme:** what CyberCat is, why it's shaped the way it is, and how an event physically gets from the wire into the database.

### Mon — Project identity & decisions

- **Read (in order):** `CLAUDE.md` § 1–9, `Project Brief.md`, `docs/decisions/ADR-0001-project-scope.md`, `ADR-0002-tech-stack.md`, `ADR-0003-resource-constraints.md`.
- **Trace:** the *why* chain. Why FastAPI not Flask? Why Postgres + Redis not just Postgres? Why a custom agent not pure Wazuh? Each ADR closes one such question. Notice the format: Context → Decision → Consequences.
- **Write:** `docs/walkthroughs.md` § "Slice 0 — What CyberCat is and isn't" — a 200–400 word operator-voice summary in your own words. Not a copy of the brief: your version of the elevator pitch.
- **Exit criterion:** you can finish the sentence "CyberCat is not a SIEM because…" with a concrete answer naming a specific feature CyberCat *does* have and a SIEM doesn't.
- **Commit:** `docs: walkthrough slice 0 — project identity and ADR rationale`.

### Tue — Schema and migration ordering

- **Read:** `backend/app/db/models.py` (start to finish — the canonical table definitions), then `backend/alembic/versions/` migrations 0001–0008 in order. `docs/learning-notes.md` § "Alembic migrations" entry.
- **Trace:** how each migration extended the schema. Migration 0001 = the spine. Migration 0002 added what? 0008 added `incidents.summary` (Phase 18). Build a mental timeline.
- **Write:** `learning-notes.md` § "Schema evolution" — *new entry*. Use the standard entry format (Intuition / Precise / Why / Where / Where else / Tradeoffs / Related). Frame it as "how this project's schema grew over 19 phases without breaking."
- **Exit criterion:** you can state, without looking, which Alembic migration introduced `incidents`, `entities`, `actions`, and `users`.
- **Commit:** `docs: learning-notes — schema evolution across 8 migrations`.

### Wed — FastAPI request lifecycle on a real route

- **Read:** `backend/app/main.py` (app construction, middleware order, router includes), then `backend/app/api/routers/incidents.py` (pick `GET /v1/incidents` and `POST /v1/incidents/{id}/transitions`). `learning-notes.md` § "FastAPI" entry.
- **Trace:** for `GET /v1/incidents` — the path from uvicorn accept → middleware → dependency resolution (`Depends(get_db)`, `require_user`) → handler → Pydantic serialization → JSON response. Open `auth/dependencies.py` to see what `require_user` actually does.
- **Write:** `walkthroughs.md` § "Slice 1 — A request arrives at the FastAPI backend" — operator-voice walkthrough of one route, end-to-end.
- **Exit criterion:** you can explain what `Depends(get_db)` does and why it's there (request-scoped session, automatic cleanup).
- **Commit:** `docs: walkthrough slice 1 — FastAPI request lifecycle on /v1/incidents`.

### Thu — Direct ingest path: an event becomes a row

- **Read (in order):** `backend/app/api/routers/events.py` (`POST /v1/events/raw`), `backend/app/ingest/pipeline.py` (`ingest_normalized_event` — the master function), `backend/app/ingest/normalizer.py`, `backend/app/ingest/dedup.py`, `backend/app/ingest/entity_extractor.py`. `learning-notes.md` § "ON CONFLICT DO UPDATE / DO NOTHING" + "SETNX for dedup".
- **Trace:** the seven stages of `ingest_normalized_event`: dedup → persist → entity extract → detect → correlate → commit → auto-actions. Each stage has its own file or function. Walk them in order.
- **Write:** `walkthroughs.md` § "Slice 2 — A raw event becomes an incident-eligible row". This is the most important walkthrough in the whole sprint — every other detection/correlation flow assumes this one. Spend the time.
- **Exit criterion:** you can name the seven pipeline stages without looking.
- **Commit:** `docs: walkthrough slice 2 — ingest pipeline (POST /v1/events/raw to row in events table)`.

### Fri — Wazuh alternate ingest path

- **Read:** `backend/app/ingest/wazuh_poller.py`, `backend/app/ingest/wazuh_decoder.py`, `docs/decisions/ADR-0004-wazuh-bridge.md`, `ADR-0011-direct-agent-telemetry.md`. `learning-notes.md` § "Wazuh Active Response" + "Pluggable telemetry adapter pattern".
- **Trace:** how a Wazuh alert becomes the *same* canonical event the direct path produces. Notice the `EventSource` enum split. Read the `search_after` cursor pattern in `wazuh_poller.py` — that's how the poller resumes without re-ingesting.
- **Write:** `learning-notes.md` § "Pluggable telemetry adapter pattern" — *expand the existing entry* with a concrete worked example contrasting the direct path and the Wazuh path. (Tell the assistant which entry to expand; operator types the diff.)
- **Exit criterion:** you can explain why both paths converge on the same `ingest_normalized_event` and what would break if they didn't.
- **Commit:** `docs: learning-notes — expand pluggable telemetry adapter pattern with direct vs. Wazuh worked example`.

### Sat–Sun — Parallel mini-project kickoff

- **Goal:** new public repo, FastAPI app with one POST endpoint, one Postgres table, one Alembic migration. No AI, no copy-paste. Use the FastAPI docs and the Postgres docs only.
- **Output:** working endpoint that accepts `{ "name": "...", "value": 123 }`, persists it to a `notes` table with `id UUID PRIMARY KEY`, returns the row. A 50-line `README.md` written by you.
- **Scope guardrail:** no Pydantic ORMs, no SQLModel, no shortcut libraries. Raw SQLAlchemy + Alembic exactly as CyberCat uses them. The friction is the entire point.
- **Commits:** initial scaffold (Sat), first migration + endpoint (Sun). Two commits, both meaningful, both in a public repo.

---

## Week 2 — Detection & Correlation (Phases 9–13)

**Theme:** how raw events become detections, how detections become incidents, and how the analyst sees them in real time.

### Mon — Detection engine and the auth_failed_burst rule

- **Read:** `backend/app/detection/engine.py` (`@register()`, `run_detectors()`), `backend/app/detection/rules/auth_failed_burst.py`, `backend/app/db/redis_state.py` (the sliding-window helper). `learning-notes.md` § "Sliding windows for rate detection" + "Sigma rule format".
- **Trace:** how `auth_failed_burst` decides "≥4 failures for the same user in 60 seconds." The Redis sorted-set trick. Why this can't be done in pure Postgres without performance pain.
- **Write:** `walkthroughs.md` § "Slice 3 — A detection fires" (event → detector → fired-detection row).
- **Exit criterion:** you can explain why `auth_failed_burst` uses Redis instead of `SELECT count(*) FROM events WHERE ...`.
- **Commit:** `docs: walkthrough slice 3 — detection engine and auth_failed_burst rule`.

### Tue — Correlator and the incident model

- **Read:** `backend/app/correlation/engine.py`, `backend/app/correlation/rules/identity_compromise.py`, `backend/app/correlation/rules/endpoint_compromise_standalone.py`, `backend/app/correlation/rules/identity_endpoint_chain.py`. `learning-notes.md` § "Junction tables (many-to-many)" + "Explainability contract".
- **Trace:** how multiple detections + entities become *one* `incidents` row with linked `incident_detections` and `incident_entities` junction rows. Notice the `summary` field populated by every rule (Phase 18).
- **Write:** `walkthroughs.md` § "Slice 4 — Detections become an incident" (the correlator).
- **Exit criterion:** you can name the three correlator rules and what each one looks for.
- **Commit:** `docs: walkthrough slice 4 — correlation rules and incident materialization`.

### Wed — Response policy and action handlers

- **Read:** `backend/app/response/policy.py`, `backend/app/response/executor.py`, then any *two* handlers: `handlers/block_observable.py` and `handlers/quarantine_host.py`. `docs/decisions/ADR-0005-response-handler-shape.md`. `learning-notes.md` § "Action classification".
- **Trace:** the auto-safe / suggest-only / reversible / disruptive classification. Why `block_observable` is reversible but `kill_process` isn't.
- **Write:** `learning-notes.md` § "Action classification" — re-read the existing entry and have the assistant expand any thin part. Operator types the expansion in.
- **Exit criterion:** you can name all four classifications and give one example handler from each.
- **Commit:** `docs: learning-notes — expand action classification entry with worked examples`.

### Thu — Real-time SSE streaming

- **Read:** `backend/app/streaming/bus.py` (the `EventBus` class — Phase 19's `_supervisor` lives here), `backend/app/streaming/publisher.py`, `backend/app/api/routers/streaming.py` (the `/v1/stream` SSE endpoint). `learning-notes.md` § "Server-Sent Events (SSE)" + "Pub/Sub".
- **Trace:** Postgres write → publisher → Redis pub/sub → EventBus consumer → SSE response stream → frontend `EventSource` → frontend refetch. Every hop matters.
- **Write:** `walkthroughs.md` § "Slice 5 — An incident appears in the analyst's browser without polling" (the SSE flow).
- **Exit criterion:** you can explain what would happen if `safe_redis` returned `None` instead of executing the publish (Phase 19 chaos work).
- **Commit:** `docs: walkthrough slice 5 — SSE streaming pipeline (Postgres write to browser refetch)`.

### Fri — Frontend incident detail page

- **Read:** `frontend/app/incidents/[id]/page.tsx` and the panel components it imports (kill chain, timeline, recommended actions, evidence requests). `learning-notes.md` § "Next.js App Router" + "openapi-typescript".
- **Trace:** the typed-API-client → component data flow. Notice how `Incident.summary` (Phase 18) is read first and `rationale` is behind a "Show technical detail" expander.
- **Write:** `walkthroughs.md` § "Slice 5 (continued) — From SSE refetch to rendered DOM."
- **Exit criterion:** you can describe what makes a Next.js Server Component different from a Client Component and which one fetches the incident detail.
- **Commit:** `docs: walkthrough slice 5 — frontend rendering of incident detail page`.

### Sat–Sun — Mini-project: add Redis pub/sub

- **Goal:** in your mini-project, add a Redis pub/sub layer. Publish a message every time the `/notes` endpoint is hit. Add a second endpoint that opens an SSE stream and emits each published message to subscribed clients.
- **Output:** two browser tabs — one calling POST `/notes`, the other connected to the SSE stream — visibly receiving each message in real time.
- **Why this exercise:** it forces you to feel the same primitive CyberCat uses for streaming. Two evenings, end of weekend.

---

## Week 3 — Auth, Recommendations, Custom Agent (Phases 14–16.10)

**Theme:** how multi-operator auth, recommended actions, and the custom telemetry agent work — the components that distinguish CyberCat from a thin Wazuh wrapper.

### Mon — Auth foundation: bcrypt + session cookies

- **Read:** `backend/app/auth/security.py`, `backend/app/auth/router.py`, `backend/app/auth/dependencies.py`, `backend/app/auth/models.py`. `learning-notes.md` § "Bcrypt password hashing" + "HMAC session cookies" + "RBAC".
- **Trace:** login → password verify → cookie issue → request with cookie → `require_user` → `require_analyst` for mutating routes. The actor-attribution chain (`actor_user_id` on every audit row).
- **Write:** `walkthroughs.md` § "Slice 6 — A login becomes a request the backend trusts."
- **Exit criterion:** you can explain why bcrypt uses a salt and what would break if it didn't.
- **Commit:** `docs: walkthrough slice 6 — auth flow from login to actor attribution`.

### Tue — OIDC opt-in and JWT validation

- **Read:** `backend/app/auth/oidc.py`, `frontend/app/login/page.tsx` (SSO button rendering). `docs/decisions/ADR-0009-multi-operator-auth.md`. `learning-notes.md` § "JWT" + "OIDC".
- **Trace:** OIDC button click → discovery doc → authorization-code redirect → callback → JWT signature validation against JWKS → JIT user provisioning. Notice the JWKS rotation handling.
- **Write:** `learning-notes.md` § "OIDC" — expand with an explicit "what happens during a single OIDC login" sequence (operator types).
- **Exit criterion:** you can explain why OIDC needs JWKS and what the keys are signing.
- **Commit:** `docs: learning-notes — expand OIDC entry with login sequence walkthrough`.

### Wed — Recommendations engine

- **Read:** `backend/app/response/recommendations.py`, `backend/app/api/routers/incidents.py` (the `/recommended-actions` endpoint), `frontend/app/incidents/[id]/RecommendedActionsPanel.tsx`. `docs/decisions/ADR-0010-recommended-actions.md`. `learning-notes.md` § "Recommendation engine (two-level mapping)".
- **Trace:** incident → kind → base candidates → ATT&CK technique boost → top-N → pre-filled action suggestion → "Use this" button → `ProposeActionModal` pre-population.
- **Write:** `walkthroughs.md` § "Slice 7 — From an incident to a one-click response suggestion."
- **Exit criterion:** you can explain why the engine is static rules and not ML, and what tradeoff that buys.
- **Commit:** `docs: walkthrough slice 7 — recommendation engine (incident kind to suggested action)`.

### Thu — Custom telemetry agent: sshd source

- **Read:** `agent/cct_agent/main.py`, `agent/cct_agent/sources/sshd.py`, `agent/cct_agent/parsers/sshd.py`, `agent/cct_agent/shipper.py`, `agent/cct_agent/checkpoint.py`. `docs/decisions/ADR-0011-direct-agent-telemetry.md`. `learning-notes.md` § "Tail-and-checkpoint pattern" + "sshd auth events".
- **Trace:** sshd writes to `/var/log/auth.log` → tail loop reads new lines → parser produces canonical event → shipper queues → POST to `/v1/events/raw`. The checkpoint persistence on inode change / truncation.
- **Write:** `walkthroughs.md` § "Slice 8 — An SSH login on lab-debian becomes a backend event."
- **Exit criterion:** you can explain what the agent does on truncation versus rotation.
- **Commit:** `docs: walkthrough slice 8 — custom agent sshd source (tail to canonical event)`.

### Fri — Auditd + conntrack: dual-tail / triple-tail

- **Read:** `agent/cct_agent/sources/auditd.py`, `agent/cct_agent/parsers/auditd.py`, `agent/cct_agent/process_state.py`, `agent/cct_agent/sources/conntrack.py`, `agent/cct_agent/parsers/conntrack.py`. ADRs 0012 + 0013. `learning-notes.md` § "auditd" + "conntrack".
- **Trace:** stateful auditd parser (EXECVE+SYSCALL+PROCTITLE+PATH grouping by `audit(ts:event_id)`, EOE flush). PID enrichment via `TrackedProcesses` LRU. Conntrack `[NEW]`-only filter, dedupe by `id=` or SHA256.
- **Write:** `learning-notes.md` § "Tail-and-checkpoint pattern" — expand to show how three sources share the pattern with three checkpoints.
- **Exit criterion:** you can explain why auditd needs a stateful parser but conntrack doesn't.
- **Commit:** `docs: learning-notes — expand tail-and-checkpoint pattern with auditd and conntrack examples`.

### Sat–Sun — Mini-project: add a simple detector

- **Goal:** in your mini-project, add a "≥3 notes posted in 10 seconds" detector. Use the same Redis sorted-set sliding-window pattern CyberCat uses.
- **Output:** when the threshold trips, log a line to stdout. (Don't build incidents — that's CyberCat's job. Just feel the detector primitive.)

---

## Week 4 — Polish, Resilience, Closing (Phases 17–19.5)

**Theme:** how the dossier UI works, why the resilience primitives exist, and what chaos testing actually verifies.

### Mon — Frontend dossier theme & first-run

- **Read:** `frontend/app/lib/labels.ts`, `frontend/app/components/PlainTerm.tsx`, `frontend/app/lib/timelineLayout.ts`, `frontend/tailwind.config.ts` (dossier color tokens). ADR-0014. ADR-0008.
- **Trace:** how plain-language labels swap for technical terms in the UI; how the kill-chain "stamped stations" and timeline "reel" panels are pure SVG.
- **Write:** `learning-notes.md` § "Plain-language summary layer" — expand with the dual-track explainability contract (summary up front, technical detail behind expander).
- **Exit criterion:** you can explain why CyberCat doesn't use a graph library for the entity graph.
- **Commit:** `docs: learning-notes — expand plain-language layer with explainability contract`.

### Tue — Resilience primitives: safe_redis and EventBus supervisor

- **Read:** `backend/app/db/redis.py` (`init_redis` with bounded timeouts), `backend/app/streaming/bus.py:97-123` (the supervisor reconnect loop), wherever `safe_redis` is defined. `backend/tests/integration/test_redis_unavailable.py`. `docs/phase-19-plan.md` § A1.1.
- **Trace:** what happens to a request when Redis dies mid-flight. Why `safe_redis` returns `None` instead of raising. How `_supervisor` reconnects without a global retry storm.
- **Write:** `walkthroughs.md` § "Slice 9 — Redis dies; the system stays up."
- **Exit criterion:** you can explain what happens to in-flight detections during a Redis outage and why no events are lost.
- **Commit:** `docs: walkthrough slice 9 — Redis-down resilience (safe_redis + EventBus supervisor)`.

### Wed — Chaos testing harness

- **Read:** `labs/chaos/run_chaos.sh`, `labs/chaos/lib/evaluate.sh`, any *one* scenario script (recommend `restart_postgres.sh` — A2 — it's the cleanest). `docs/phase-19.5-plan.md`.
- **Trace:** orchestrator → scenario lifecycle (pre-warm → chaos action → measurement window → cleanup) → pass/fail evaluation. The four §A1 counters. Why the `00`/`0` counter bug from the calibration commits mattered.
- **Write:** `walkthroughs.md` § "Slice 10 — A chaos scenario runs end-to-end."
- **Exit criterion:** you can explain why the orchestrator measures `accept_pct` instead of `acceptance_passed`.
- **Commit:** `docs: walkthrough slice 10 — chaos orchestrator and one scenario lifecycle`.

### Thu — Audit and gap-fill

- **Read:** `docs/learning-notes.md` cold, start to finish, in one sitting. ~1.5 hours.
- **Trace:** which entries do you re-read smoothly? Which entries make you hesitate? Which entries reference concepts not yet in the file?
- **Write:** for each weak entry, ask the assistant to rewrite it. You read the rewrite, push back where it's still unclear, and commit the final version. This is the day the assistant works hardest.
- **Exit criterion:** every index entry in `learning-notes.md` is something you could explain to someone else from memory after one re-read.
- **Commit:** `docs: learning-notes — sweep audit (rewrote N entries for clarity)` (replace N with the actual count).

### Fri — Sprint close: the master walkthrough

- **Read:** `docs/walkthroughs.md` cold, start to finish.
- **Write:** `walkthroughs.md` § "Closing — What I now understand." A 500–1000 word operator-voice essay: what the project is, how it works end to end, what tradeoffs it makes, where you'd take it next. This is the artifact you can open six months from now to remind yourself.
- **Update `PROJECT_STATE.md`:** mark Phase 19.7 ✅ COMPLETE. Move the "what's next" pointer to Phase 20.
- **Exit criterion:** you can recite the closing essay's outline (not verbatim, but the structure) without looking.
- **Commit:** `docs: phase 19.7 close — sprint complete, walkthroughs and learning-notes consolidated`.

### Sat–Sun — Mini-project finish + reflect

- **Goal:** wrap the mini-project. Make sure its README is a clean re-readable artifact. Add it to your GitHub pinned repos.
- **Output:** a public, well-documented mini-project that demonstrates "I can build a FastAPI + Postgres + Redis app from scratch with no AI." This is your portable proof beyond CyberCat.

---

## Daily commit cadence — what counts, what doesn't

**Counts:**
- Walkthrough section in `docs/walkthroughs.md` (one commit per day's slice).
- Learning-notes entry expansion or new entry (one commit per entry, even small).
- WHY-comments added to code while tracing (one commit per file or logically grouped set).
- Tiny refactors surfaced during tracing — variable rename, extract-helper, dead-code removal (one commit per refactor).
- Mini-project commits (count toward your activity, separate repo).

**Doesn't count (don't game the streak):**
- Whitespace-only commits.
- Splitting one walkthrough across 5 commits to pad the count.
- Commit messages like `wip`, `update`, `fix`. Every message names what changed and why.
- Reverting then re-committing the same change.

**Rough commit budget for the sprint:**
- 20 weekday commits (one per day, sometimes two when a day produces both a walkthrough section *and* a code comment fix).
- 8 weekend mini-project commits.
- ~28–35 commits over 4 weeks, all signal, no noise.

That's stronger than "30 trivial commits" by a wide margin. Anyone reading the repo's commit log during the sprint sees thoughtful, deliberate engagement — which is exactly the recruiter signal you actually want.

---

## What the assistant does during the sprint

- **Answers questions** when you hit a concept you don't follow. No quizzes, no calibration checks (per CLAUDE.md §9 + your stated learning style).
- **Expands learning-notes entries** on request. Operator types the expansion into the file — friction stays with you.
- **Points at files and explains data flow** when the day's reading list is unclear, but does *not* pre-summarize what you're about to read.
- **Surfaces small refactors** ("the variable name `r` here is confusing, want to rename it?") as natural commit opportunities.
- **Stays out of the writing seat.** All prose in `walkthroughs.md` is operator-authored. The assistant can suggest a structure or paste a code snippet to anchor a paragraph, but the words are yours.

---

## What happens to the chaos work

Phase 19.5 is the only feature work still touching `main` during the sprint:

- **Wed 2026-05-06 remote agent draft PR** for `labs/chaos/scenarios/kill_redis.sh` — review when it lands, merge if clean. ~30-min interruption to the sprint.
- **Regression-injection sanity check** (gates on the above) — a one-time verification, ~30 min.
- **Optional CI workflow runs** — five button-clicks in the Actions tab, ~15 min.

Everything else holds until Phase 20.

---

## Sprint exit checklist

Before declaring Phase 19.7 complete:

- [ ] All 10 walkthrough slices written and committed.
- [ ] All weak entries in `learning-notes.md` rewritten in the Thursday-Week-4 sweep.
- [ ] Mini-project public on GitHub, with a README the operator wrote.
- [ ] Closing essay in `walkthroughs.md` reads clean cold.
- [ ] `PROJECT_STATE.md` header marks Phase 19.7 ✅ COMPLETE and points to Phase 20.
- [ ] Operator can answer the master question — *"what happens when an sshd login failure arrives at the agent until the analyst sees an incident in the UI"* — without looking.

When all six are checked, the sprint shipped. Resume Phase 20 (heavy-hitter scenarios) from a position of understanding.

---

*Plan created 2026-05-03. Phase 19.7 starts the next working day after Phase 19.5 closes (live A1 verification + regression-injection sanity check).*
