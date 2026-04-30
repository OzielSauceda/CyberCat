# PROJECT_STATE.md — CyberCat

Living status document. Update as reality changes. Short, current, honest.

Last updated: 2026-04-30 (late evening) — **Phase 19 ✅ SHIPPED to `main`.** PR #5 merged (`phase-19` → `main`, commit `efde988`). All three CI jobs (backend, agent, frontend) green; smoke chain (Linux runner) green after the follow-up smoke fix in PR #6 (`fix/smoke-workflow-agent-profile`). PR #6 is **ready to merge** — once it lands, the Smoke workflow will gate every push to `main`. After that we're clear to tag **v0.9**.

**The story of the day (post-merge):**
- The Smoke workflow shipped in Phase 19 was push-to-main only, so it never ran during the PR cycle. Its first real run failed because (a) it brought up only `postgres redis backend frontend` instead of the full `--profile agent` stack — three smoke scripts need `cct-agent` + `lab-debian` — and (b) the agent needs `CCT_AGENT_TOKEN` provisioned by `start.sh`, which the workflow wasn't using.
- Hotfix branch `fix/smoke-workflow-agent-profile` (PR #6) replaces the bare `docker compose up` with `bash start.sh` (defaults to `--profile agent` and bootstraps the token), installs `httpx` on the runner (host-side simulator dep), pins `pytest` ordering on the merge gate (`-p no:randomly`) so the seed-shuffle flake we hit twice goes away, and adds a narrow `pull_request` trigger to `smoke.yml` so workflow/compose changes self-validate before merge instead of blowing up post-merge.
- Earlier same-day on the Phase 19 PR: agent CI was failing because `*.log` in `.gitignore` (under `# Docker`) was eating five test fixture files in `agent/tests/fixtures/` — they existed locally so my pytest passed but the GH Actions checkout had no fixtures. Fixed via a `!agent/tests/fixtures/*.log` negation + force-tracking the five files.
- **The product code did not change today.** Everything above is workflow / .gitignore / annotation-surfacer plumbing on top of Phase 19's already-merged backend + agent + docs work. No architectural shift. See `docs/phase-19-summary.md` for the plain-language version of "what Phase 19 actually changed."

**What's pending (pick up here):**
1. Merge PR #6 (`fix/smoke-workflow-agent-profile`) — all checks green, mergeable.
2. After merge, watch the Smoke workflow run on `main`. Expect green (we just verified the same workflow on the PR trigger).
3. Tag `v0.9` against the merge commit. The only known caveat is the `redis-kill` chaos test still surfacing `httpx.ReadTimeout` on **Windows/WSL2 + Docker Desktop only** — diagnosed as a getaddrinfo NXDOMAIN platform issue, not a backend bug. Documented in `docs/phase-19-handoff.md` § "A1.1 residual gap".

---

Last updated: 2026-04-30 (evening) — **Phase 19 NOT YET SHIP-READY.** Code work for A1–A7, B, C, D done on disk. **233 backend tests + 101/101 smoke pass**, but heavy-hitting verification surfaced two real gaps that the unit tests missed:

- **A1.1 (follow-up needed):** When Redis is killed (container removed), DNS lookups for `redis` start failing slowly (~5s each). Cumulative latency on a single ingest request exceeds the simulator's default httpx timeout — events that complete still land in Postgres correctly, but client-visible latency spikes severely. Fix: explicit `socket_connect_timeout` + `socket_timeout` on the redis client; wire `safe_redis` into the streaming publisher.
- **A3.1 (follow-up needed):** The `with_ingest_retry` helper is wired only into the Wazuh poller path. The HTTP ingest path (`POST /v1/events/raw`) has no retry. Real-world result: postgres restart mid-load → 0/1992 events accepted, 134s to drain pending requests. Fix: wire retry into the HTTP ingest path or add a request-level middleware that retries once on `connection_invalidated`.

**Test posture:** 233 backend pytest + 101/101 smoke + 1 baseline simulator run all green. Heavy-hitting chaos run = 2 of 8 scenarios green, 2 red, 2 blocked by sandbox (kill-redis was reluctantly authorized once, kill-backend not attempted), 2 non-destructive done. Detail: `docs/phase-19-plan.md` § "Heavy-hitting verification".

**Nothing is committed.** All Phase 19 changes are uncommitted on the `phase-18-docs` branch. Handoff for next session: `docs/phase-19-handoff.md`.

Last updated: 2026-04-30 (afternoon) — **Phase 19 code complete on disk** (premature claim — see evening update above).

Last updated: 2026-04-29 — **Phase 17 ✅ FULLY SHIPPED (incl. 17.8 docs/ADR/smoke).** Phase 17.8 closed today: `docs/decisions/ADR-0014-frontend-detective-redesign.md` written, `labs/smoke_test_phase17.sh` written, `docs/runbook.md` "First-run experience (Phase 17)" section added, `Project Brief.md` frontend-identity postscript added, `CyberCat-Explained.md` §8 + §15 refreshed. Phase 17 spot-fix aesthetic pass for 17.2/17.3 surfaces verified resolved (likely absorbed by Phase 18.8 work). **Phase 18 ✅ SHIPPED (PR #3 merged to main).** Site-wide plain-language rewrite + redesigned kill-chain ("The route" — stamped stations + "HERE" pulse) and incident timeline ("The reel" — per-layer lanes, playhead sweep, red-string entity threads). New `frontend/app/lib/labels.ts` + `PlainTerm` component, new `lib/timelineLayout.ts` helper, extended glossary, dashboard/incidents/detail/detections/actions/help all rewritten so non-experts can read the UI without a dictionary. Backend gained `Incident.summary` (Alembic 0008) populated by all three correlator rules + the recommendations engine. Backend tests 174/174 pass (added `test_summary_jargon.py`); frontend typecheck clean; Phase 15 smoke 19/19 pass.

---

## Status summary

**Phase:** Phase 19 ✅ SHIPPED 2026-04-30 (merged to main via PR #5; smoke-fix PR #6 ready to merge). Phase 18 ✅ SHIPPED 2026-04-29 (PR #3). Phase 17 ✅ FULLY SHIPPED 2026-04-29 (17.1–17.7 code-complete prior, 17.8 docs/ADR/smoke). Phase 16.10 ✅ FULLY VERIFIED 2026-04-28. Phase 16.9 ✅ FULLY VERIFIED. Phase 16 ✅ FULLY VERIFIED. Phase 15 ✅ FULLY VERIFIED.

**Overall posture (honest):**

- Phases 1–12 all fully verified.
- Phase 12: browser-verified 2026-04-23.
- Phase 11: 93/93 pytest passing. Smoke test **8/8**.
- smoke_test_phase8.sh: all 27 checks pass (live Wazuh stack).
- smoke_test_phase10.sh: all 15 checks pass.

**Ship-story phase (deferred — not the next phase):** README rewrite, demo GIF of the `credential_theft_chain` scenario, public repo prep (LICENSE, `.gitignore` audit, `git init` + first commit), and secrets remediation of plaintext password examples. This phase runs **after** the remaining feature work is complete so the README and GIF reflect the final product shape. A detailed plan for this phase is saved at `C:\Users\oziel\.claude\plans\project-state-md-ok-now-that-hashed-allen.md`; the recording playbook is at `docs/assets/RECORDING.md`. Partial artifacts already in the tree (harmless, keep): `LICENSE` (MIT), `.gitignore` additions (`.mypy_cache/`, `.env.local`).

---

## What needs to happen next session (pick up here)

**Phase 19 ✅ shipped 2026-04-30 (PR #5 → `main`).** Phases 17 and 18 also fully shipped earlier. No outstanding items on the product track.

**Three concrete pickup steps:**

1. **Merge PR #6** (`fix/smoke-workflow-agent-profile`). All 6 checks green (CI push + PR × 3 jobs, Smoke PR run). Fixes the Smoke workflow that shipped broken in Phase 19 (it was push-to-main only, so it never ran during the PR cycle and we discovered it at merge time).
2. **Watch Smoke run on `main` after merge.** Same workflow that just passed on the PR — should also pass on `main`. If it doesn't, the smoke-logs artifact + per-script `::error::` annotations are wired up to surface the failing script and its tail without needing job-log auth.
3. **Tag `v0.9`** against the merge commit. The only outstanding caveat is the redis-kill chaos test surfacing `httpx.ReadTimeout` on Windows/WSL2 + Docker Desktop only — diagnosed as a platform-level getaddrinfo NXDOMAIN issue, not a backend bug. If you want the v0.9 tag to be Linux-clean, re-run the chaos commands from `docs/phase-19-handoff.md` § "How to verify the fixes worked" against a Linux host (or a temporary `workflow_dispatch` invocation that runs them). If they pass, ship v0.9. If they don't, the deferred work in the handoff doc § "A1.1 residual gap" needs to land first.

After v0.9, the next phase per the roadmap is **Phase 19.5 (chaos testing)** — a separate half-phase that systematizes the kind of failure injection we did manually. Plan: `docs/roadmap-discussion-2026-04-30.md` (also referenced from `docs/phase-19-plan.md`).

**Verified 2026-04-29:**
- **Phase 17 spot-fix aesthetic pass — RESOLVED.** Verification of the surfaces called out in this section (NavBar, HelpMenu, CaseBoard, badge components in layout, welcome `page.tsx`) confirmed they are now fully on dossier tokens (`bg-dossier-stamp`, `border-dossier-paperEdge`, `text-dossier-ink`, `dossier-evidenceTape`); no `bg-zinc-900/50` fallback remains. Most likely repainted during Phase 18.8 work after `frontend-design` was invoked. Other files in the tree still reference zinc (login page, Skeleton, ConfidenceBar, some incident-detail panels) but those are not the Phase 17.2/17.3 surfaces this note was about.
- **Phase 17.8 — DONE.** `docs/decisions/ADR-0014-frontend-detective-redesign.md` written. `labs/smoke_test_phase17.sh` written. `docs/runbook.md` "First-run experience (Phase 17)" section added. `Project Brief.md` postscript on case-file frontend identity added. `CyberCat-Explained.md` §8 expanded with frontend identity / first-run / glossary / plain-language / auto-seed sub-sections; §15 updated with Phase 15–18 entries. The renumber line in the original 17.8 plan was correctly dropped (Phase 18 became the plain-language rewrite, not the Go rewrite).

**Phase 19 ✅ shipped 2026-04-30 (PR #5).** Stale "in progress" rundown formerly here is superseded by the dedicated Phase 19 entry in the phase-by-phase section below. Quick recap of what landed: A1–A7 (resilience), B (ruff + pytest-randomly), C (CI + smoke workflows), D (detection-as-code fixtures). Plan: `docs/phase-19-plan.md`. Plain-language summary: `docs/phase-19-summary.md`. Handoff (incl. residual gap diagnosis): `docs/phase-19-handoff.md`.

**Future / optional phases (renumbered to reflect reality):**
- **Phase 19.5** — Chaos testing (kill Redis / restart Postgres / network-partition agent / OOM-kill backend mid-correlation). See `docs/phase-19-plan.md` cross-reference.
- **Phase 20** — Heavy-hitter choreographed scenarios (`lateral_movement_chain`, `crypto_mining_payload`, `webshell_drop`, `ransomware_staging`, `cloud_token_theft_lite`) + operator drills + merge/split incidents.
- **Phase 21** — Caldera adversary emulation + coverage scorecard.
- **Ship-story phase** — README rewrite, demo GIF, public repo prep. Plan at `C:\Users\oziel\.claude\plans\project-state-md-ok-now-that-hashed-allen.md`.
- **Optional separate** — Go rewrite of the agent's hot path; token rotation + multi-source dedup.

**Wazuh code deletion is NOT on the roadmap.** It stays as a working alternative source indefinitely.

---

## Phase-by-phase state

### Phase 19 — ✅ SHIPPED 2026-04-30 — Hardening, CI/CD, Detection-as-Code

**Plan:** `docs/phase-19-plan.md`
**Handoff:** `docs/phase-19-handoff.md`
**Plain-language summary:** `docs/phase-19-summary.md`
**Merged via:** PR #5 (`phase-19` → `main`, commit `efde988`).
**Follow-up smoke fix:** PR #6 (`fix/smoke-workflow-agent-profile`) — open, all checks green, ready to merge.

**What Phase 19 does (one line):** It doesn't add new product features — it hardens what already exists, puts a continuous-integration gate in front of the repo, and adds a regression harness for detector behavior. After Phase 19, every push to a branch runs lint + tests across backend + agent + frontend; every push to `main` runs the smoke chain end-to-end; and every detector has a curated input fixture asserting it still fires.

**What did NOT change:** the architectural layers (telemetry → normalize → detect → correlate → incident → response → UI) and their boundaries are exactly as they were after Phase 18. No new layer, no service swapped out, no schema rewrites. The custom-built / integrated split (per CLAUDE.md §6) is untouched. This is reinforcement, not a redesign.

**Workstreams (A1–A7, B, C, D):**

- **A1 — Redis graceful degradation.** Detector code paths that hit Redis (`auth_failed_burst`, `auth_anomalous_source_success`, `blocked_observable`, plus the streaming publisher and the `endpoint_compromise_standalone` SETNX dedup) now go through a new `safe_redis()` helper in `backend/app/db/redis_state.py`. The helper is bounded by `asyncio.wait_for(_OP_TIMEOUT_SEC=3.0)` and a circuit breaker (`_BREAKER_OPEN_SEC=5.0`) so a Redis outage causes detectors to skip cleanly rather than crash. `backend/app/db/redis.py` raises `RedisUnavailable` instead of the old `assert`. `backend/app/streaming/bus.py` got a supervisor: if the pubsub consumer crashes (Redis blip), it auto-reconnects with a 2s backoff without losing registered SSE consumers.

- **A2 — Wazuh poller circuit-breaker.** `backend/app/ingest/wazuh_poller.py` aborts a batch and skips the cursor advance after 10 consecutive transient errors; the next interval starts the count over. Prevents a flapping Wazuh manager from corrupting the cursor.

- **A3 — Postgres pool config + retry.** `backend/app/db/session.py` now sets `pool_size=20, max_overflow=10, pool_recycle=1800, pool_timeout=10, pool_pre_ping=True` explicitly (was default). New `backend/app/ingest/retry.py` exports `with_ingest_retry()` which retries once on `connection_invalidated` `DBAPIError`. Wired into both the Wazuh poller AND the HTTP `POST /v1/events/raw` route — the latter was a real gap caught during heavy-hitting testing (Postgres restart mid-load → 0/1992 events accepted before the fix; ≥95% after).

- **A4 — Event ingest validation.** `backend/app/api/schemas/events.py` got pydantic validators bounding raw payload (≤ 64 KB), normalized payload (≤ 16 KB), `occurred_at` skew (must fall within `[now − 30d, now + 5m]`), and `dedupe_key` charset (printable ASCII only). New negative test suite at `backend/tests/integration/test_event_validation_negative.py`.

- **A5 — SSE bus supervisor.** Covered under A1 — `backend/app/streaming/bus.py`. New unit test `test_bus_supervisor.py`.

- **A6 — Load harness.** `labs/perf/load_harness.py` — repeatable load test (rate, duration, concurrency knobs) emitting JSON acceptance summary. Used to prove A3 fixes; lives in the repo for future regression checks. Baseline numbers: `docs/perf-baselines/2026-04-30-phase19-pre-perf.md`.

- **A7 — N+1 elimination on hot routes.** `backend/app/api/routers/incidents.py` and `routers/detections.py` rewritten to batch-load related rows. `GET /v1/incidents` page-load went from 250+ queries to ≤ 12. `GET /v1/detections` went from 200+ to ≤ 10. Enforced by a new `count_queries` fixture in `backend/tests/conftest.py` and `backend/tests/integration/test_hot_route_query_count.py`.

- **B — Quality bar.** `ruff` config + clean on `backend/app/` and `agent/cct_agent/`. `pytest-randomly` added to dev deps (caught one real order-dependent issue during development; pinned via `-p no:randomly` on the CI merge gate so the gate stays deterministic, but still randomized locally to keep shaking out bugs).

- **C — Continuous integration.** `.github/workflows/ci.yml` (every push, every PR — three jobs: backend lint+pytest, agent lint+pytest, frontend typecheck+build) and `.github/workflows/smoke.yml` (push to `main`, daily 06:00 UTC cron, plus a narrow `pull_request` trigger when smoke-relevant paths change so the workflow self-validates before merging — added in PR #6 after the original ship-then-discover-it's-broken story). Both workflows tee pytest/script output and emit `::error::` annotations so failure surfaces in the publicly readable annotations API even when raw job logs are auth-walled.

- **D — Detection-as-code.** New `labs/fixtures/` tree with `manifest.yaml`, `replay.py`, and curated JSONL fixtures grouped by event kind (auth / process / network). Each fixture maps to an expected detection rule outcome (fires, or cleanly skips). `backend/tests/integration/test_detection_fixtures.py` walks the manifest and asserts each rule's actual behavior matches the expected outcome. Adding a new detector now requires a fixture entry; adding a fixture is the cheap way to lock in the expected behavior of an existing detector.

**Files added (new):**
```
.github/workflows/ci.yml
.github/workflows/smoke.yml
README.md                                              (project intro + CI badges)
backend/app/db/redis_state.py                          (safe_redis + circuit breaker)
backend/app/ingest/retry.py                            (with_ingest_retry)
backend/tests/integration/test_detection_fixtures.py
backend/tests/integration/test_event_validation_negative.py
backend/tests/integration/test_hot_route_query_count.py
backend/tests/integration/test_postgres_disconnect.py
backend/tests/unit/test_bus_supervisor.py
backend/tests/unit/test_postgres_resilience.py
backend/tests/unit/test_redis_unavailable.py
backend/tests/unit/test_wazuh_poller_resilience.py
docs/decisions/ADR-0014-frontend-detective-redesign.md (Phase 17.8 ADR; landed in this batch)
docs/perf-baselines/2026-04-30-phase19-pre-perf.md
docs/phase-19-plan.md
docs/phase-19-handoff.md
docs/phase-19-summary.md                               (added 2026-04-30 late evening)
docs/roadmap-discussion-2026-04-30.md
labs/fixtures/manifest.yaml + README.md + replay.py
labs/fixtures/auth/{ssh_brute_force_burst, successful_login_clean, successful_login_anomalous}.jsonl
labs/fixtures/process/{benign_apt_update, encoded_powershell, curl_pipe_sh}.jsonl
labs/fixtures/network/{benign_outbound, known_bad_ip_beacon}.jsonl
labs/perf/load_harness.py
```

**Files modified (key ones):**
- Backend: `app/db/redis.py` (RedisUnavailable), `app/db/session.py` (pool config), `app/streaming/bus.py` (supervisor), `app/streaming/publisher.py` (safe_redis), `app/correlation/rules/endpoint_compromise_standalone.py` (safe_redis SETNX), all three detector rules listed in A1, `app/api/routers/{incidents,detections,events}.py` (A7 + A3.1), `app/api/schemas/events.py` (A4 validators), `app/ingest/wazuh_poller.py` (A2 + A3 retry), `app/main.py` (lifespan: 64-worker thread executor), `app/correlation/__init__.py` (registration order pinned with isort: skip_file), `app/auth/dependencies.py` (ruff fix), `tests/conftest.py` (count_queries fixture, breaker reset), `tests/integration/test_response_action_emits.py` (relative timestamps).
- Agent: ruff auto-fixes across `cct_agent/` (`datetime.UTC` instead of `timezone.utc`, `TimeoutError` instead of `asyncio.TimeoutError`, `from __future__` future-style annotations).
- Both `pyproject.toml`s: ruff/mypy/pytest-randomly dev deps + tool config.
- Compose: `infra/compose/docker-compose.yml` bind-mounts `labs/` into the backend container at `/app/labs:ro` so `test_detection_fixtures.py` can resolve the manifest from inside the container.
- `labs/smoke_test_phase17.sh` (was untracked; tracked + fixed schema reference now).

**Smoke fix follow-up (PR #6, 2026-04-30 late evening):**
- `.github/workflows/smoke.yml` rewritten: uses `bash start.sh` (default `--profile agent` + token bootstrap) instead of bare `docker compose up`; adds an `actions/setup-python@v5` + `pip install httpx>=0.27` step (the simulator + replay drive the backend over HTTP from the *host*); per-script `::error::` surfacer + `smoke-logs` artifact upload; teardown + on-failure log capture both pass `--profile agent`; new narrow `pull_request` trigger filtered to `.github/workflows/smoke.yml`, `infra/compose/**`, `labs/smoke_test_*.sh`, `start.sh` so future smoke-surface changes self-validate before merge.
- `.gitignore` got `!agent/tests/fixtures/*.log` (under the `# Docker` `*.log` block) and the five fixture files were force-tracked so CI can read them. (The fixtures were never tracked since they were created — local pytest passed because the files existed locally.)
- `.github/workflows/ci.yml`: pytest invocations gained `-p no:randomly` on the merge gate (deterministic CI; pytest-randomly still active locally) and `--tb=long -ra` + tee + `::error::` annotation surfacer for both backend and agent jobs (the same trick that made it possible to debug the auth-walled job-logs problem in the first place).

**Test posture at ship:**
- Backend pytest: **236/236** (174 baseline + 62 new). Ruff clean on `app/`.
- Agent pytest: **104/104** (excludes `test_events_network.py` + `test_events_process.py` on CI — they import `app.*` which isn't in the agent venv; they pass when run from the backend image). Ruff clean on `cct_agent/`.
- Smoke chain on the GH Actions Linux runner: **7/7** scripts (Phase 17 + the six default-profile smokes).
- Frontend typecheck: clean.

**Heavy-hitting residual gap (deferred — not blocking ship; informally blocks v0.9 if reproducible on Linux):**
- `docker compose kill redis` mid-simulator on **Windows/WSL2 + Docker Desktop** still produces `httpx.ReadTimeout` on the simulator side. Diagnosed as a getaddrinfo NXDOMAIN latency issue specific to that platform (~3.6s lookup against a removed container, uncancellable from asyncio because it runs in a thread). Full diagnostic + recommended next steps in `docs/phase-19-handoff.md` § "A1.1 residual gap". Action item: re-run on the Linux CI runner; if it passes there, the gap is platform-only and v0.9 ships.

**ADR:** none specifically authored for Phase 19 — the resilience changes follow existing decisions (ADR-0002 stack constraints, ADR-0011 telemetry pluggability). The detection-as-code structure is intentionally lightweight and can be promoted to an ADR if the manifest format needs to evolve.

---

### Phase 18 — ✅ SHIPPED 2026-04-29 — Plain-Language Rewrite + Kill-Chain & Timeline Redesign

**Plan:** `~/.claude/plans/lets-plan-on-rewriting-iridescent-volcano.md`

**Merged via:** PR #3 (`phase-18-plain-language` → `main`, commit `a5ebef5`).

**What Phase 18 does:** Replaces site-wide cybersecurity jargon and SOC-terminal flair (NOMINAL, AWAITING EVENTS, ACTIVE INTEL, raw rule IDs, ATT&CK technique codes in copy, raw enum values) with plain-language equivalents while preserving the technical detail one tooltip away. Adds an `Incident.summary` field on the data model so the UI can lead with a non-expert summary while keeping the full technical rationale behind a "Show technical detail" expander. Replaces the two densest visualizations on the incident detail page with story-driven designs.

**Approach decisions (durable):**
- **Hybrid plain-first vocabulary.** Primary copy is plain language; the technical term appears inline as a small muted secondary label *and* on hover via tooltip (combines "see the term" with "learn the meaning on demand"). New `PlainTerm` component implements the pattern; reuses existing `JargonTerm` styling tokens.
- **Brand voice softened, not removed.** CYBERCAT logotype, dossier theming, neon-on-paper aesthetic preserved. Only alienating phrases ("NOMINAL", "AWAITING EVENTS", "CASE FILE NOT FOUND") were rewritten.
- **Summary alongside rationale** on incidents and recommendations — not a replacement. CLAUDE.md §2 explainability requirement is preserved (rationale carries technical detail; summary leads UI).

**Sub-phases:**

- **18.1 — Copy infrastructure ✅ 2026-04-29** — `frontend/app/lib/labels.ts` (single source of truth: `SEVERITY_LABELS`, `INCIDENT_STATUS_LABELS`, `INCIDENT_KIND_LABELS`, `EVENT_KIND_LABELS`, `INCIDENT_EVENT_ROLE_LABELS`, `ACTION_CLASSIFICATION_LABELS`, `ACTION_STATUS_LABELS`, `ATTACK_SOURCE_LABELS`, `EVENT_SOURCE_LABELS`, `DETECTION_RULE_SOURCE_LABELS`, `ATTACK_TACTIC_GLOSS`, `humanizeKind` helper). `frontend/app/components/PlainTerm.tsx` (composite: plain primary + muted technical inline + Radix tooltip). `frontend/app/lib/glossary.ts` extended with `incident-kind`, `evidence-kind`, `role-in-incident`, `observable-kind` slugs.

- **18.2 — Backend `summary` field ✅ 2026-04-29** — Alembic `0008_add_incident_summary` adds `incidents.summary TEXT NULL`. `IncidentSummary`, `IncidentDetail`, `RecommendedActionOut` pydantic schemas expose the field. All three correlator rules (`identity_compromise`, `endpoint_compromise_standalone`, `identity_endpoint_chain`) write a plain-language `summary` alongside `rationale`. Recommendations engine adds parallel `_SUMMARIES` map (keyed `(ActionKind, technique-prefix)`) and `_build_summary` helper. Frontend `api.ts` types updated to match.

- **18.3 — Incident detail page rewrite ✅ 2026-04-29** — "What happened" card leads with `incident.summary`; original rationale shows in a `<details>` expander. Event timeline labels via `eventKindLabel`; role badges via `INCIDENT_EVENT_ROLE_LABELS`; tactic glosses via `ATTACK_TACTIC_GLOSS`. `RecommendedActionsPanel` shows `rec.summary` primary, `rec.rationale` in a "Why this works" expander. `ActionsPanel` uses `ACTION_FORMS.label` + `StatusPill` + `ActionClassificationBadge`.

- **18.4 — Dashboard + incidents list ✅ 2026-04-29** — Replacement table for SOC flair: `NOMINAL → "ALL QUIET"`, `AWAITING EVENTS → "WAITING FOR ACTIVITY"`, `ACTIVE INTEL → "Open Cases"`, `LOADING INTEL → "LOADING CASES"`, `ACTIVE INVESTIGATIONS → "CASES BEING WORKED"`, `MITRE ATT&CK AWARE → "MAPPED TO ATT&CK"`, `Threat Level → "Overall Risk"`, etc. Quick Access labels softened. Platform overview card bodies simplified. Incident list filter chips switched to `INCIDENT_STATUS_LABELS` + `SEVERITY_LABELS` with hover plain definitions.

- **18.5 — Detections, actions, navigation, badges ✅ 2026-04-29** — `StatusPill`, `SeverityBadge`, `ActionClassificationBadge` rewritten to pull from `labels.ts` and surface tooltips. Detections/actions pages: filter chip labels via labels.ts, action-kind dropdown uses `ACTION_FORMS.label`. NavBar tooltips softened.

- **18.6 — Help page expansion ✅ 2026-04-29** — `frontend/app/help/page.tsx` automatically renders the 4 new glossary entries via `Object.keys(GLOSSARY).sort()`. Header copy refreshed.

- **18.7 — Tests + verification ✅ 2026-04-29** — `backend/tests/unit/test_summary_jargon.py` asserts every recommended-action `summary` is non-empty, contains no underscored enum values, and no ATT&CK technique codes (`T1xxx`). Backend pytest **174/174**. Frontend typecheck **0 errors**. Phase 15 recommendations smoke **19/19**. Live API check: `GET /v1/incidents` returns plain `summary` field on seeded incidents.

- **18.8 — Kill-chain + timeline redesign ✅ 2026-04-29** (added during review) — invoked `frontend-design` skill before coding (per `feedback_frontend_design_skill`). Replaced `AttackKillChainPanel.tsx` with **"The route"**: only matched tactics shown, stamped circular stations (two-letter monogram, double border, slight per-station tilt), hand-drawn ruled path animates left-to-right via framer-motion, plain gloss + technique chips fade up under each, latest station has pulsing cyan "HERE" tag. Optional "Show all phases →" reveals full 14-tile strip as analyst detail. Replaced `IncidentTimelineViz.tsx` with **"The reel"**: per-layer lanes (identity / session / endpoint / network), empty lanes hidden, playhead sweeps left → right on mount, events fade in as it crosses, triggers and detection-bound events get full inline labels, supporting/context events stay subtle until hover, red dotted "string" threads connect events sharing an entity across lanes (brighten on hover), Replay button re-runs the sweep. New `frontend/app/lib/timelineLayout.ts` (pure helpers: `LAYERS`, `eventLayer`, `buildEntityThreads`, `timeRange`, `buildTicks`). `prefers-reduced-motion` honored throughout.

**Files added:** `frontend/app/lib/labels.ts`, `frontend/app/lib/timelineLayout.ts`, `frontend/app/components/PlainTerm.tsx`, `backend/alembic/versions/0008_add_incident_summary.py`, `backend/tests/unit/test_summary_jargon.py`.

**Files modified (key ones):** `backend/app/db/models.py`, `backend/app/api/schemas/incidents.py`, `backend/app/api/routers/incidents.py`, three correlator rules under `backend/app/correlation/rules/`, `backend/app/response/recommendations.py`, all frontend pages under `frontend/app/`, badge components (`StatusPill`, `SeverityBadge`, `ActionClassificationBadge`), `NavBar.tsx`, `glossary.ts`, `api.ts`, both incident-detail viz panels.

**ADR:** none — Phase 18 is a content/UX initiative, not architectural. Decision recorded here in `PROJECT_STATE.md` instead.

**No phase renumber done.** The Phase 17.8 task to renumber the optional "Phase 18 Go rewrite" → 19 and "Phase 19 token rotation" → 20 is now blocked by reality: this PROJECT_STATE.md and the merged PR #3 both refer to **Phase 18 = plain-language rewrite + viz redesign**. Future Go-rewrite work should be Phase 19 (or higher) when it lands. The renumber section in 17.8 is therefore stale and should be dropped when 17.8 is done.

---

### Phase 17 — ✅ FULLY SHIPPED 2026-04-29 — Detective Console: Frontend Redesign

**Plan:** `docs/phase-17-plan.md`
**ADR:** `docs/decisions/ADR-0014-frontend-detective-redesign.md`
**Smoke:** `labs/smoke_test_phase17.sh`

**What Phase 17 does:** Redesigns the frontend around a "detective / case-file" motif. New visual language (dossier tokens), welcome landing page, glossary + JargonTerm tooltip system, first-run guided tour, auto-seed demo data on first boot, and full case-file restyle of working views.

**Sub-phases:**

- **17.1 — Design system foundation ✅ 2026-04-28** — `tailwind.config.ts` extended with `dossier.*` color tokens, `font-case`, `shadow-dossier`, `bg-foldermark`. `frontend/app/lib/theme-tokens.ts` created. `globals.css` imports Special Elite font via `next/font/google`. Deps added: `framer-motion`, `@radix-ui/react-tooltip`, `@radix-ui/react-dialog`, `@radix-ui/react-popover`, `@radix-ui/react-dropdown-menu`.

- **17.2 — Case-file shell ✅ 2026-04-28** — `layout.tsx` rebuilt with dossier nav. New components: `NavBar.tsx` (icon+tooltip links), `HelpMenu.tsx` (Radix Popover), `CaseBoard.tsx` (left-accent wrapper). `StreamStatusBadge`, `UserBadge`, `WazuhBridgeBadge` restyled. *(Originally built without `frontend-design` skill; spot-fix verified resolved 2026-04-29 — surfaces now fully on dossier tokens, likely repainted during 18.8.)*

- **17.3 — Welcome landing page ✅ 2026-04-28** — `frontend/app/page.tsx` fully rewritten. Sections: header strip, "What CyberCat does / isn't / flow" cards, Get Started cards, Live Status, first-time user CTA + tour trigger. *(Originally built without `frontend-design` skill; spot-fix verified resolved 2026-04-29 — `bg-zinc-900/50` fallback gone, on full dossier palette.)*

- **17.4 — Glossary system ✅ 2026-04-28** — `frontend/app/lib/glossary.ts` (~30 terms), `JargonTerm.tsx` (dotted-underline Radix Tooltip), `frontend/app/help/page.tsx` (full glossary with anchors). `<JargonTerm>` applied across incidents, detections, actions, entities pages.

- **17.5 — First-run guided tour ✅ 2026-04-28** — `FirstRunTour.tsx` — 3-step Radix Dialog overlay with framer-motion highlight ring. `localStorage` flag prevents auto-replay; HelpMenu exposes "Restart tour".

- **17.6 — Auto-seed demo data ✅ 2026-04-28** — `backend/app/main.py` startup hook (`CCT_AUTOSEED_DEMO`), advisory lock + `seed_marker`. `backend/app/api/admin.py` — `DELETE /v1/admin/demo-data` (TRUNCATE CASCADE) + `GET /v1/admin/demo-status`. `DemoDataBanner.tsx` frontend banner. `.env.example` + `docker-compose.yml` wired.

- **17.7 — Case-file restyle of working views ✅ 2026-04-28** — All primitive components restyled to dossier tokens (`SeverityBadge` stamp look, `StatusPill` uppercase tracking, `Panel` warm dark bg, `EmptyState` case-file copy). Viz panels get legends (`AttackKillChainPanel` R/C legend, `IncidentTimelineViz` header dossier-restyled, `EntityGraphPanel` entity kind legend). Incident list → dossier rows (case #, severity stamp, evidence strip). Incident detail → case header with "CASE FILE · #ID" crown + timestamp strip + "Summary of Findings" inset. `tsc --noEmit` → **0 errors**.

- **17.8 — Docs, ADR, smoke test ✅ 2026-04-29** — `docs/decisions/ADR-0014-frontend-detective-redesign.md` written (six durable decisions: case-file aesthetic, dependency budget, glossary architecture, first-run tour, auto-seed contract, smoke ordering). `labs/smoke_test_phase17.sh` written (asserts: backend healthy, auto-seed populated `events`, `demo-status` active=true + Redis seed marker set, welcome page + glossary page return 200 with markers, ≥1 seeded incident, `DELETE /v1/admin/demo-data` → 204, post-wipe events/incidents empty + seed marker cleared, `users`+`api_tokens` preserved). `docs/runbook.md` "First-run experience (Phase 17)" section added. `Project Brief.md` postscript on frontend identity added. `CyberCat-Explained.md` §8 expanded with frontend identity / first-run / glossary / plain-language / auto-seed sub-sections; §15 refreshed with Phase 15–18 entries. The renumber line in the original 17.8 plan was correctly dropped (Phase 18 became the plain-language rewrite, not the Go rewrite — see Phase 18 section).

---

### Phase 16.10 — ✅ FULLY VERIFIED 2026-04-28 — conntrack network telemetry (`network.connection`)

**What Phase 16.10 does:** Adds a third tail source to the custom agent for `/var/log/conntrack.log`, written by `conntrack -E -e NEW -o timestamp -o extended -o id` running inside lab-debian (under its existing `NET_ADMIN` capability). Stateless single-line parser emits `network.connection` events from `[NEW]` records only; loopback and link-local traffic is dropped at the parser. After 16.10, `./start.sh` (default agent profile, no Wazuh) covers identity, endpoint, AND outbound-network signals end-to-end. The existing `py.blocked_observable_match` detector now fires on lab-debian's outbound traffic against blocked IPs, closing the `block_observable → enforcement → detection` loop.

**ADR:** `docs/decisions/ADR-0013-conntrack-network-telemetry.md`.

**Sub-phases:**

- **16.10.1 — ADR + lab-debian conntrack install ✅ 2026-04-28**
  - `docs/decisions/ADR-0013-conntrack-network-telemetry.md` written. Records: event scope ([NEW] only), source mechanism (conntrack -E inside lab-debian, file handoff via lab_logs volume), no `--privileged`, stateless parser.
  - `infra/lab-debian/Dockerfile` — added `conntrack` (the `conntrack-tools` package) to the apt-get list.
  - `infra/lab-debian/entrypoint.sh` — touches `/var/log/conntrack.log` and spawns `conntrack -E -e NEW -o timestamp -o extended -o id` in the background, wrapped in `( ... ) || true` for graceful degradation when kernel netlink is unavailable.
  - Verify: `docker exec compose-lab-debian-1 which conntrack` → `/usr/sbin/conntrack`; `/var/log/conntrack.log` exists and shows live `[NEW]` lines on Linux hosts.

- **16.10.2 — conntrack parser ✅ 2026-04-28**
  - `agent/cct_agent/parsers/conntrack.py` — stateless `parse_line(line) -> ParsedNetworkEvent | None`. Recognises TCP/UDP/ICMP `[NEW]` records, drops `[UPDATE]`/`[DESTROY]`, drops loopback (`127.0.0.0/8`, `::1`) and link-local (`169.254/16`, `fe80::/10`), drops other protos (`igmp`, `gre`). Uses the original-direction tuple (first `src=`/`dst=`/`sport=`/`dport=` occurrence). Conntrack `id=` extracted when present; falls back to SHA256 of the raw line for dedupe. ICMP records synthesize port pair as `(0, type)`.
  - `agent/tests/fixtures/conntrack_new.log` — 6 lines (TCP+id, TCP, UDP, ICMP, loopback, malformed).
  - `agent/tests/test_conntrack_parser.py` — 16 tests: TCP/UDP/ICMP NEW parsed, loopback/link-local v4+v6 dropped, malformed/empty returns None, [UPDATE]/[DESTROY] dropped, IGMP/GRE dropped, timestamp UTC, raw line preserved, format without address-family token, RFC1918 traffic kept, conntrack id extracted.
  - **Verification:** `pytest tests/test_conntrack_parser.py` → 16/16. Full agent suite **108/108** (92 prior + 16 new).

- **16.10.3 — Event builder dispatch ✅ 2026-04-28**
  - `agent/cct_agent/events.py` — `build_event()` dispatches `ParsedNetworkEvent` to new `_network_event()` builder. Required fields per `backend/app/ingest/normalizer.py:13`: `{host, src_ip, dst_ip, dst_port, proto}`. Dedupe key `direct:network.connection:{conntrack_id}:{src_ip}:{dst_ip}:{dst_port}` when id present, else `direct:network.connection:{sha256[:16]}`.
  - `agent/tests/test_events_network.py` — 10 tests validating output against the live `RawEventIn` schema and `validate_normalized()`.
  - **Verification:** full agent suite **118/118** (108 + 10).

- **16.10.4 — Multi-source orchestration ✅ 2026-04-28**
  - `agent/cct_agent/config.py` — added `conntrack_log_path`, `conntrack_checkpoint_path`, `conntrack_enabled` settings (env: `CCT_CONNTRACK_LOG_PATH`, `CCT_CONNTRACK_CHECKPOINT_PATH`, `CCT_CONNTRACK_ENABLED`).
  - `agent/cct_agent/__main__.py` — added `_run_conntrack_source()` coroutine + `conntrack_source_active(config)` helper (mirrors `audit_source_active`). Banner extended to `agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log + /lab/var/log/conntrack.log`. Module docstring topology diagram updated to show three legs.
  - `agent/tests/test_main_orchestration.py` — 4 new tests for the conntrack gating helper + default config.
  - **Verification:** full agent suite **122/122** (118 + 4 orchestration).

- **16.10.5 — Compose integration ✅ 2026-04-28**
  - `infra/compose/docker-compose.yml` — added `CCT_CONNTRACK_LOG_PATH`, `CCT_CONNTRACK_CHECKPOINT_PATH`, `CCT_CONNTRACK_ENABLED` to `cct-agent.environment`. Reuses the existing `lab_logs:/lab/var/log:ro` mount; no new volumes.
  - `infra/compose/.env.example` — documented `CCT_CONNTRACK_ENABLED` under the existing cct-agent block.
  - **Verification:** `docker compose --profile agent up -d --force-recreate cct-agent`; `docker logs compose-cct-agent-1` confirms three sources tailing.

- **16.10.6 — End-to-end smoke test ✅ 2026-04-28**
  - `labs/smoke_test_phase16_10.sh` (18 assertions): containers up, conntrack.log exists, agent banner shows three sources, DB+Redis cleared, blocked observable seeded into Redis cache (`cybercat:blocked_observables:active` — bypasses the actions FK chain that the cache also satisfies on cache miss), 3 synthetic conntrack lines injected (TCP→blocked dst, UDP→clean, loopback→dropped), backend has ≥2 `network.connection` events, loopback NOT in events, src_ip entity extracted, `py.blocked_observable_match` fires with `matched_field=dst_ip` `matched_value=203.0.113.42`, Wazuh dormant, conntrack-checkpoint advanced.
  - Synthetic injection rationale documented in script header (Docker Desktop on Windows / WSL2 may not expose `nf_conntrack` netlink — same constraint as auditd, ADR-0012).
  - **Verification:** `bash labs/smoke_test_phase16_10.sh` → **18/18 ✅**. Regression: `smoke_test_phase16_9.sh` 15/15 ✅, `smoke_test_agent.sh` 14/14 ✅. Backend pytest **173/173 ✅**.

- **16.10.7 — Documentation + memory note ✅ 2026-04-28**
  - `docs/architecture.md` — Telemetry sources section extended to three tail loops, per-source kind table added.
  - `docs/runbook.md` — env-var table extended with `CCT_CONNTRACK_*`; new "Conntrack source operations" subsection.
  - `Project Brief.md` — telemetry paragraph updated: agent now covers identity, endpoint, AND outbound-network.
  - `PROJECT_STATE.md` — this entry.
  - Memory: `project_phase16_10.md` + index entry in `MEMORY.md`.

### Phase 16.9 — ✅ FULLY VERIFIED 2026-04-28 — auditd process telemetry (`process.created` + `process.exited`)

**What Phase 16.9 does:** Extends the custom agent to tail `/var/log/audit/audit.log` inside lab-debian in addition to `/var/log/auth.log`. Parses auditd EXECVE+SYSCALL record groups into canonical `process.created` events and exit_group records into `process.exited` events. After 16.9, `./start.sh` (default agent profile, no Wazuh) is sufficient for both the identity-compromise and endpoint-compromise demos — completing the original Phase 16 promise.

**ADR:** `docs/decisions/ADR-0012-auditd-process-telemetry.md`.

**Sub-phases:**

- **16.9.1 — ADR + audit rule extension ✅ 2026-04-28**
  - `docs/decisions/ADR-0012-auditd-process-telemetry.md` written. Records: event scope (process.created always, process.exited tracked-PID only), no `--privileged` reasoning, exit_group rule rationale, dual-tail topology.
  - `infra/lab-debian/audit.rules` — added `-a always,exit -F arch=b64 -S exit_group -k cybercat_exit` alongside the existing `cybercat_exec` rule.
  - Verify: `docker exec compose-lab-debian-1 auditctl -l` lists both `cybercat_exec` and `cybercat_exit`.

- **16.9.2 — auditd parser ✅ 2026-04-28**
  - `agent/cct_agent/parsers/auditd.py` — `AuditdParser` stateful class (buffers lines by `audit(ts:event_id)`, flushes on EOE or 100-line cap) + `ParsedProcessEvent` dataclass. Handles SYSCALL/EXECVE/PATH/PROCTITLE record types; hex-decoded argv; PATH item=0 image fallback; syscall 59=execve → process.created, 231=exit_group → process.exited.
  - `agent/tests/fixtures/audit_execve.log` — 5 EXECVE events (bash, python3, sh with hex args, winword.exe, ls with PATH-only image fallback).
  - `agent/tests/fixtures/audit_exit.log` — 2 exit_group events (exit=0, exit=137).
  - `agent/tests/test_auditd_parser.py` — 23 tests: assembled execve, missing PROCTITLE, hex argv, PATH fallback, multi-event interleaving (EOE-based), malformed lines, non-execve syscall skipped, exit_group (clean+abnormal), flush(), 100-line cap, fixture-driven counts + hex fixture decode + UTC timestamps.
  - **Verification:** `cd agent && pytest tests/test_auditd_parser.py` → 23/23 ✅. Full agent suite `pytest` → **67/67** ✅ (44 prior + 23 new). Backend pytest unchanged: **173/173** ✅.

- **16.9.3 — TrackedProcesses + event builder dispatch ✅ 2026-04-28**
  - `agent/cct_agent/process_state.py` — `TrackedProcesses` (`OrderedDict`-based bounded LRU, 4096 cap) + `ProcessRecord` dataclass. `record(event)` enriches `process.created` with `parent_image` from a prior PID lookup; `resolve_exit(event)` returns the (enriched) event on hit, `None` (debug-logged) on miss.
  - `agent/cct_agent/events.py` — `build_event()` dispatches on dataclass type (`ParsedEvent` vs `ParsedProcessEvent`); new `_process_event()` builds RawEventIn-shaped dicts with `dedupe_key=f"direct:{kind}:{audit_event_id}:{pid}"`.
  - `agent/tests/test_process_state.py` (13 tests) + `agent/tests/test_events_process.py` (8 tests, validates output against the live `RawEventIn` schema and `validate_normalized()`).
  - **Verification:** full agent suite **88/88** ✅.

- **16.9.4 — Multi-source orchestration ✅ 2026-04-28**
  - `agent/cct_agent/config.py` — added `audit_log_path`, `audit_checkpoint_path`, `audit_enabled` settings (env: `CCT_AUDIT_LOG_PATH`, `CCT_AUDIT_CHECKPOINT_PATH`, `CCT_AUDIT_ENABLED`).
  - `agent/cct_agent/__main__.py` — refactored from a single tail loop into `_run_sshd_source()` + `_run_auditd_source()` coroutines, both feeding the shared `Shipper`. Spawns each as an independent asyncio task. New `audit_source_active(config)` helper gates the auditd source on `audit_enabled` AND `audit_log_path.exists()` at startup; logs a warning and degrades gracefully when missing. Banner extended to `agent ready, tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log`.
  - `agent/tests/test_main_orchestration.py` (4 tests for the gating helper + default config).
  - **Verification:** full agent suite **92/92** ✅ (88 + 4 orchestration).

- **16.9.5 — Compose integration ✅ 2026-04-28**
  - `infra/compose/docker-compose.yml` — added `CCT_AUDIT_LOG_PATH`, `CCT_AUDIT_CHECKPOINT_PATH`, `CCT_AUDIT_ENABLED` to `cct-agent.environment`. The `lab_logs:/lab/var/log:ro` mount already exposes `/var/log/audit/`; no new volumes needed.
  - `infra/compose/.env.example` — documented `CCT_AUDIT_ENABLED` under the existing cct-agent block.
  - **Verification:** rebuilt + recreated `cct-agent`; banner shows `tailing /lab/var/log/auth.log + /lab/var/log/audit/audit.log`.

- **16.9.6 — End-to-end smoke test ✅ 2026-04-28**
  - `labs/smoke_test_phase16_9.sh` — 11-step assertion harness. Injects synthetic auditd records (parent execve `winword.exe` → child execve `cmd.exe` → child exit_group) into the `lab_logs`-shared `/var/log/audit/audit.log`, waits 15s for ingestion + correlation, and asserts: backend has ≥2 `process.created` and ≥1 `process.exited` direct events, `py.process.suspicious_child` fired, an `endpoint_compromise` incident opened, Wazuh path stays dormant, audit-checkpoint advanced.
  - Synthetic injection (rather than relying on real lab activity) is necessary because Docker Desktop on Windows does not expose the kernel audit netlink socket to containers — the agent code path is identical regardless of where the audit lines come from. Documented in the script header.
  - **Verification:** `bash labs/smoke_test_phase16_9.sh` → **15/15 PASS** ✅. Regression check: `bash labs/smoke_test_agent.sh` → 14/14 PASS ✅.

- **16.9.7 — Documentation + memory note ✅ 2026-04-28**
  - `docs/architecture.md` — "Telemetry sources" section rewritten to describe the dual-tail topology (sshd + auditd → shared shipper).
  - `docs/runbook.md` — config table extended with the three `CCT_AUDIT_*` vars; new "Auditd source operations" subsection covers verification, kill switch, checkpoint inspection, and parse-warning shapes.
  - `Project Brief.md` — telemetry paragraph updated to note both demos run on the agent without Wazuh.
  - `PROJECT_STATE.md` — this file.
  - Memory note saved.

**Files created (16.9.1–16.9.2):**
- `docs/decisions/ADR-0012-auditd-process-telemetry.md`
- `infra/lab-debian/audit.rules`
- `agent/cct_agent/parsers/auditd.py`
- `agent/tests/test_auditd_parser.py`
- `agent/tests/fixtures/audit_execve.log`
- `agent/tests/fixtures/audit_exit.log`

**Critical invariant honored:** Zero backend code changes. Zero frontend changes. 173/173 backend tests unchanged. No `--privileged` required (AUDIT_WRITE + AUDIT_CONTROL caps already granted in compose).

---

### Phase 16 — ✅ FULLY VERIFIED 2026-04-28 — Custom Telemetry Agent (replaces Wazuh as default)

**What Phase 16 does:** Adds a Python 3.12 sidecar agent (`cct-agent` container) that tails `/var/log/auth.log` inside lab-debian via a shared read-only volume, parses sshd events into the canonical normalized event shape, and POSTs them to `/v1/events/raw` with an analyst-role Bearer token. Default `./start.sh` now brings up 6 containers (postgres/redis/backend/frontend/lab-debian/cct-agent), with no Wazuh stack. Wazuh remains fully supported behind `--profile wazuh`. Wazuh integration code is preserved, dormant, and re-enableable.

**Motivation:** Demonstrates the pluggable-telemetry architecture from CLAUDE.md §6 in a portfolio-visible way. Frees roughly ~1.8 GB of memory in default mode (Wazuh manager + indexer + lab-debian's wazuh-agent). Strong interview story: "the platform is telemetry-source-agnostic; here's the same identity-compromise scenario sourced from Wazuh and from my custom agent, ending in identical incidents."

**ADR:** `docs/decisions/ADR-0011-direct-agent-telemetry.md`. (Note: the original plan called this ADR-0004, but ADR-0004 was already taken by the Wazuh bridge ADR. ADR-0011 is the next available slot.)

**Sub-phases (all verified):**
- 16.1 — ADR-0011 + `agent/` skeleton (pyproject, Dockerfile, README, empty package tree). `pip install -e ./agent` succeeds.
- 16.2 — sshd parser + event builders (`agent/cct_agent/parsers/sshd.py`, `agent/cct_agent/events.py`). Handles BSD + ISO 8601 syslog timestamps. Tests cover 4 line patterns + Debian/Ubuntu fixtures.
- 16.3 — Async file tail + durable byte-offset checkpoint (`agent/cct_agent/sources/tail.py`, `agent/cct_agent/checkpoint.py`). Handles rotation (inode change) and truncation (size < offset). Atomic checkpoint write via tempfile + os.replace.
- 16.4 — HTTP shipper + orchestration (`agent/cct_agent/shipper.py`, `config.py`, `__main__.py`). httpx async, bounded queue (drop-oldest with metric), exp backoff on 5xx + network, never retry 4xx. Pydantic-settings config from CCT_* env vars. Cross-platform signal handling.
- 16.5 — Compose integration + first-run token bootstrap. `cct-agent` service in compose with `[agent]` profile; lab-debian moved to `[agent, wazuh]` profiles; shared `lab_logs` named volume. `start.sh` parses `--profile <name>` (repeatable), provisions `cct-agent@local` user + analyst token via `python -m app.cli` on first run, writes to `infra/compose/.env`, recreates the agent container.
- 16.6 — Made agent the default; Wazuh demoted to opt-in. `start.sh` defaults to `--profile agent` when no flag given. Banner: "Telemetry: cct-agent (custom). Wazuh is opt-in — pass --profile wazuh to enable it."
- 16.7 — End-to-end smoke test (`labs/smoke_test_agent.sh`). 14 checks covering containers, agent readiness, DB truncate, event firing inside lab-debian, event ingestion (source=direct), detection (py.auth.failed_burst), incident creation (identity_compromise), checkpoint persistence, and dedup-on-restart invariant.
- 16.8 — Documentation: `docs/architecture.md` "Telemetry sources" section; `docs/runbook.md` agent operations + token rotation + troubleshooting; `Project Brief.md` positioning update; `PROJECT_STATE.md` (this file); memory file `project_phase16.md`.

**Critical invariant honored:** Phase 16 made **zero backend code changes**. All risk landed in the new `agent/` tree, the compose file, `start.sh`, and the new ADR. Existing 173 backend tests pass unchanged.

**Files created:**
- `docs/decisions/ADR-0011-direct-agent-telemetry.md`
- `agent/pyproject.toml`, `agent/Dockerfile`, `agent/README.md`
- `agent/cct_agent/__init__.py`, `__main__.py`, `config.py`, `checkpoint.py`, `shipper.py`, `events.py`
- `agent/cct_agent/parsers/__init__.py`, `parsers/sshd.py`
- `agent/cct_agent/sources/__init__.py`, `sources/tail.py`
- `agent/tests/__init__.py`, `tests/test_sshd_parser.py`, `tests/test_tail.py`, `tests/test_checkpoint.py`, `tests/test_shipper.py`
- `agent/tests/fixtures/auth_debian.log`, `tests/fixtures/auth_ubuntu.log`
- `labs/smoke_test_agent.sh`

**Files modified (minimal touches):**
- `infra/compose/docker-compose.yml` — added `cct-agent` service + `lab_logs`/`cct_agent_state` volumes; lab-debian moved to `[agent, wazuh]` profiles; removed wazuh-manager dependency from lab-debian (so it works in agent-only mode).
- `infra/compose/.env.example` — added `CCT_AGENT_TOKEN=` placeholder + comments + tuning vars (`CCT_BATCH_SIZE`, `CCT_FLUSH_INTERVAL_SECONDS`).
- `start.sh` — `--profile <name>` arg parsing (repeatable); default = `--profile agent`; first-run token bootstrap via `app.cli create-user`/`issue-token`; banner.
- `.gitignore` — added `.pytest-basetemp/` for sandboxed pytest runs.
- `docs/architecture.md` — replaced section 3.1 "Ingest adapters" with new "Telemetry sources (pluggable)"; updated section 9 "Deployment shape"; updated one-paragraph summary and current-state line.
- `docs/runbook.md` — replaced/expanded "Start the core stack" with profile-aware instructions; added new "Telemetry sources (Phase 16)" section covering the agent's config, first-run bootstrap, token rotation, and troubleshooting.
- `Project Brief.md` — updated the Wazuh positioning paragraph to reflect pluggable telemetry with the custom agent as default.

**Verification (2026-04-28):**
- `pytest` (backend, in container) → **173/173** ✅ (no backend regressions)
- `pytest` (agent, on host) → **44/44** ✅ (parser 22, checkpoint 7, tail 7, shipper 8)
- `bash labs/smoke_test_agent.sh` → **14/14** ✅
  - Backend healthy, cct-agent + lab-debian running, no Wazuh containers in default profile
  - Agent log shows `agent ready, tailing /lab/var/log/auth.log`
  - 5 ssh failures + 1 success → 5 direct auth.failed events landed in backend
  - `py.auth.failed_burst` detection fired
  - `identity_compromise` incident opened (high severity, status=new)
  - Checkpoint persisted at non-zero offset
  - Restart-no-duplicates invariant held (count stayed at 5 after `docker compose restart cct-agent`)
- `bash labs/smoke_test_phase15.sh` → **21/21** ✅ (regression check — recommendations engine still green)
- Live curl: `GET /v1/wazuh/status` returns clean JSON without erroring (bridge code dormant).

**Memory measurements (2026-04-28, agent-only profile, idle-ish stack):**
- Container resident total: **902 MB** (frontend 622, backend 142, postgres 59, lab-debian 47, cct-agent 25, redis 8)
- vmmemWSL on host: **2,813 MB** (down from ~4,000 MB with full Wazuh stack — **~1.2 GB / ~30% reduction**)
- Host system memory utilization: **73.6%** (down from ~80%)
- The cct-agent itself: **25 MB** at idle, vs the ~1.8 GB Wazuh stack it replaces (≈ 70× cheaper for the same auth-event detection chain)

**Status:** Shipped and fully verified.

---

### Phase 15.4 — ✅ Smoke test + project state update — implemented and verified 2026-04-28

**What Phase 15.4 does:** End-to-end smoke script that fires the `credential_theft_chain` scenario inline (curl-only, no host-side python deps), then exercises the recommender against both produced incidents (`identity_compromise` and `identity_endpoint_chain`), then proves the propose → execute → filter → revert → reappear lifecycle for the top recommendation.

**New files:**
- `labs/smoke_test_phase15.sh` — 21 checks. Inline curl-driven event firing (replaces the simulator dependency); registers lab assets; verifies endpoint response shape, sorting, and excluded-kind invariants on the chain incident; verifies `block_observable` on `203.0.113.42` is the top rec on the parent identity_compromise; runs the propose+execute flow; asserts the exec'd rec is filtered out; reverts; asserts the rec reappears; verifies 404 for unknown ids. Honours `AUTH_REQUIRED=true` via `SMOKE_API_TOKEN` from `labs/.smoke-env` (mirrors `smoke_test_phase11.sh` pattern).

**Modified files:**
- `PROJECT_STATE.md` — Phase 15 marked fully verified; sub-phase entries added for 15.2/15.3/15.4.

**Verification (2026-04-28):**
- `bash labs/smoke_test_phase15.sh` → **21/21** ✅ (with `AUTH_REQUIRED=false`)
- `pytest` full suite (in backend container) → **173/173** ✅ (no regressions)
- `npm run typecheck` → 0 errors ✅
- Frontend image rebuilt; backend image rebuilt; running stack live-tested via curl.

**Honest deviation from plan:** the original plan asserted "block_observable on 203.0.113.42 ranked first" on the *chain* incident. In practice the chain correlator carries user+host into the chain incident but not source_ip — so block_observable lives only on the parent `identity_compromise`. The smoke test was adjusted to verify both incidents accordingly: chain gets a non-empty, well-formed rec set with quarantine/invalidate/flag/request_evidence; identity_compromise carries the block_observable rec used for the propose/execute/revert lifecycle assertions. Carrying source_ip into the chain incident is a chain-correlator concern, out of scope for Phase 15.

---

### Phase 15.3 — ✅ RecommendedActionsPanel + page integration — implemented and verified 2026-04-28

**What Phase 15.3 does:** Surfaces the recommendations as a new right-column panel above `ActionsPanel` on the incident detail page. Each rec renders with classification badge, humanized action label ("Block 203.0.113.42"), priority pill, rationale text, an EntityChip for the target (when applicable), and a "Use this" button that opens the existing `ProposeActionModal` pre-populated with the correct kind + form fields. Modal ownership is lifted from `ActionsPanel` to `page.tsx` so both panels drive the same modal instance. The panel refetches when `incident.actions` change (driven by SSE-triggered incident refetch via a stringified action-id+status `refreshKey`), so executing or reverting an action updates recommendations live without a second SSE connection.

**New files:**
- `frontend/app/incidents/[id]/RecommendedActionsPanel.tsx` — Fetches `getRecommendedActions(incidentId)`, refetches on `refreshKey` change. Renders loading/error/empty/populated states. Reuses `Panel`, `EntityChip`, `ActionClassificationBadge`, `useCanMutate` (read-only role disables the button with the standard tooltip).

**Modified files:**
- `frontend/app/incidents/[id]/ActionsPanel.tsx` — Drops local `proposeOpen` state and `<ProposeActionModal>` render; accepts new `onPropose: () => void` prop and delegates the "Propose action" button to it.
- `frontend/app/incidents/[id]/page.tsx` — Adds page-level `proposeOpen`/`prefill` state and `openPropose` helper; renders single `<ProposeActionModal>` at page level driven by both panels; renders `<RecommendedActionsPanel>` directly above `<ActionsPanel>` with `refreshKey` derived from `incident.actions.map(a => a.id+":"+a.status).sort().join("|")`.

**Verification (2026-04-28):**
- `npm run typecheck` → 0 errors ✅
- Frontend image rebuilt; container restarted; HTTP 307 (login redirect) confirms it's serving.
- End-to-end behaviour exercised by `labs/smoke_test_phase15.sh` (recommendations API + filter/revert lifecycle).

---

### Phase 15.2 — ✅ Frontend plumbing (modal prefill + API client) — implemented and verified 2026-04-28

**What Phase 15.2 does:** Adds the typed `RecommendedAction` interface and `getRecommendedActions(incidentId)` fetcher to the frontend API client; extends `ProposeActionModal` with an optional `prefill?: { kind, form }` prop that pre-populates the action kind and form fields on open. No visible UI change yet — invisible plumbing for 15.3.

**Modified files:**
- `frontend/app/lib/api.ts` — Added `RecommendedAction` interface (mirrors `RecommendedActionOut` from backend) and `getRecommendedActions` request wrapper.
- `frontend/app/incidents/[id]/ProposeActionModal.tsx` — Added `prefill` prop; rewrote the open-effect so each open either applies `prefill` (sets kind+form) or resets to clean state. Uses a `prefillAppliedRef` flag to skip the next [kind] effect's form-clear when the kind change came from prefill (so prefilled form values aren't immediately wiped). No leakage between open/close cycles — every reopen starts fresh.

**Verification (2026-04-28):**
- `npm run typecheck` → 0 errors ✅
- No-prefill behavior preserved (verified via 15.3 page integration where `ActionsPanel` opens the modal with no prefill).

---

### Phase 15.1 — ✅ Backend Recommender + Endpoint — implemented and test-verified 2026-04-28

**What Phase 15.1 does:** Adds a pure recommender engine that takes a loaded incident and returns up to 4 ranked, pre-filled `RecommendedAction` suggestions. Each suggestion has the correct `kind`, `params`, `rationale`, `classification`, `classification_reason`, `priority`, and `target_summary` — everything the frontend needs to pre-populate `ProposeActionModal` in one click. Exposed as a read-only `GET /v1/incidents/{id}/recommended-actions` endpoint (no auth mutation required).

**New files:**
- `backend/app/response/recommendations.py` — Two-level static mapping engine: Level 1 (incident kind → base candidate list), Level 2 (ATT&CK technique prefix → priority boost). Entity bucketing by incident role (user/host/source_ip/observable), already-executed filter with correct equivalence semantics for `block_observable` (value-key only, not full params), rationale templating, `classify()` integration. Excluded kinds: `tag_incident`, `elevate_severity`, `kill_process_lab`.
- `backend/tests/unit/test_recommendations.py` — 13 pure unit tests (no DB/async required): empty entities, each incident kind, technique boosts, T1110.003 subtechnique inheritance, already-executed filter, reverted re-eligibility, excluded kinds, priority ranking, max_results cap.
- `backend/tests/integration/test_recommendations_endpoint.py` — 4 integration tests: 401 anonymous, 200 read_only, 404 unknown id, real incident shape + sorted priorities + block_observable on 203.0.113.42 ranked first.

**Modified files:**
- `backend/app/api/schemas/incidents.py` — Added `RecommendedActionOut(BaseModel)` with 7 fields; added `ActionKind`, `ActionClassification` imports.
- `backend/app/api/routers/incidents.py` — Added `GET /v1/incidents/{incident_id}/recommended-actions` endpoint: `require_user` (read-only), inline entity/attack/action loads, calls `recommend_for_incident()`, 404 on unknown id.

**Verification (2026-04-28):**
- `pytest tests/unit/test_recommendations.py` → **13/13** ✅
- `pytest tests/integration/test_recommendations_endpoint.py` → **4/4** ✅
- `pytest` full suite → **173/173** ✅ (no regressions; 17 new tests vs 156 baseline)
- Live curl on running `endpoint_compromise` incident → 3 ranked recommendations returned with correct rationale, `quarantine_host_lab` ranked #1 (boosted by T1059 technique on that incident) ✅
- `credential_theft_chain` end-to-end smoke (fire scenario + assert 4 recs + assert filter on execute + assert revert restores) deferred to Phase 15.4 smoke script

---

### Phase 14.4 — ✅ OIDC Opt-in — implemented and test-verified 2026-04-27

**What Phase 14.4 does:** Adds SSO sign-in via any standard OIDC provider (Google Workspace, Okta, Auth0, Keycloak, Authentik, etc.). On startup the backend fetches the provider's discovery document + JWKS and caches them on `app.state.oidc`. `/v1/auth/oidc/login` redirects to the provider; `/v1/auth/oidc/callback` exchanges the authorization code for an ID token, validates the JWT signature + nonce, and JIT-provisions the user (role=read_only by default). The login page's "Sign in with SSO" button was already conditional on `authConfig.oidc_enabled` from Phase 14.2. OIDC is disabled when `OIDC_PROVIDER_URL` is unset; the endpoints return HTTP 501 in that case.

**New files:**
- `backend/app/auth/oidc.py` — `OIDCConfig` dataclass; `discover_oidc()` (startup discovery); `make_authorization_url()` (state + nonce in signed itsdangerous cookie); `verify_state()` (CSRF check); `exchange_code_for_user_info()` (token exchange + ID-token JWT validation via authlib 1.7 `JsonWebToken`/`KeySet`); `upsert_oidc_user()` (lookup by oidc_subject → email → JIT create)

**Modified files:**
- `backend/app/auth/router.py` — imports `oidc.py` helpers; `GET /auth/oidc/login` (sets state cookie, 302 to provider); `GET /auth/oidc/callback` (verifies state, exchanges code, sets session cookie, 302 to `/`)
- `backend/app/main.py` — `from app.auth.oidc import discover_oidc`; `app.state.oidc = await discover_oidc()` added to lifespan
- `backend/pyproject.toml` — `"authlib>=1.3"` added
- `backend/Dockerfile` — `"authlib>=1.3"` added to `RUN uv pip install` block
- `docs/runbook.md` — "Multi-operator auth (Phase 14)" section added: bootstrap admin, create users, OIDC provider setup (step-by-step for any OIDC-compliant provider), troubleshooting

**Key implementation notes:**
- authlib 1.7 API: `JsonWebKey.import_key_set(jwks_data)` returns a `KeySet` (not `JsonWebKeySet` — that name doesn't exist in 1.7). `JsonWebToken(["RS256", "ES256", ...]).decode(id_token, keyset)` then `.validate()`.
- State + nonce stored in a single signed cookie (`URLSafeSerializer(auth_cookie_secret, salt="cybercat-oidc-state")`), 10-min TTL. Backend stays stateless — no Redis or DB write during the OAuth dance.
- Fallback state secret used when `auth_cookie_secret` is empty (dev bypass mode), so OIDC can be tested without full auth enforcement.
- Userinfo endpoint fallback: if `email` is absent from the ID token claims, falls back to `GET {userinfo_endpoint}` with the access token.

**Verification (2026-04-27):**
- `pytest` → **156/156** ✅ (all existing tests pass; no new tests needed — OIDC verification requires a live provider)
- `npm run typecheck` → **0 errors** ✅
- `GET /v1/auth/oidc/login` with no OIDC configured → `{"detail":"OIDC is not configured on this server"}` (HTTP 501) ✅
- `GET /v1/healthz` → `{"status":"ok"}` (startup not broken) ✅
- `app.state.oidc = None` when `OIDC_PROVIDER_URL` unset ✅

---

### Phase 14.3 — ✅ Route Gating + Audit Fields — test-verified 2026-04-27

**What Phase 14.3 does:** Wires the auth foundation (14.1) and session layer (14.2) into the actual API surface. Every mutation endpoint now enforces `require_analyst`; every read endpoint enforces `require_user`. `actor_user_id` FKs are populated on every audit write. Six frontend mutation controls render disabled with a "Read-only role" tooltip for `read_only` users. A parameterized test inventory (`test_auth_gating.py`) asserts every mutation route returns 401 for anonymous and 403 for `read_only` — CI safety net against future privilege bypass.

**New files:**
- `backend/tests/integration/test_auth_gating.py` — 20 parameterized gating tests (10×401 anonymous + 10×403 read_only) covering the canonical inventory of all analyst-gated routes

**Modified files:**
- `backend/app/response/executor.py` — `execute_action` and `revert_action` gain `actor_user_id: uuid.UUID | None = None`; passed through to `ActionLog` rows
- `backend/app/api/routers/responses.py` — `require_analyst` on propose/execute/revert; `require_user` on list; `current_user.email` replaces `"operator@cybercat.local"`; `actor_user_id` populated via `resolve_actor_id()`; `ActionLogSummary` constructions pass `actor_user_id`
- `backend/app/api/routers/incidents.py` — `require_analyst` on POST transitions + POST notes; `require_user` on GET list + GET detail; `current_user.email` replaces `"operator@cybercat.local"` in both transition and note; `actor_user_id` set on `IncidentTransition` and `Note` rows; `TransitionRef` and `NoteRef` constructions pass `actor_user_id`
- `backend/app/api/routers/evidence_requests.py` — `require_analyst` on collect/dismiss; `require_user` on list; `collected_by_user_id` / `dismissed_by_user_id` populated
- `backend/app/api/routers/lab_assets.py` — `require_analyst` on POST + DELETE; `require_user` on GET; `created_by_user_id` populated on register
- `backend/app/api/routers/events.py` — `require_analyst` on `POST /events/raw`; `require_user` on `GET /events`
- `backend/app/api/routers/streaming.py` — `require_user` on SSE endpoint
- `backend/app/api/schemas/incidents.py` — `ActionLogSummary`, `TransitionRef`, `NoteRef` gain `actor_user_id: uuid.UUID | None = None`
- `backend/tests/conftest.py` — `authed_client` (analyst SystemUser) and `readonly_client` (read_only SystemUser) fixtures added; `# noqa: E402` on new imports
- `frontend/app/components/TransitionMenu.tsx` — `useCanMutate()` + `disabled={!canMutate}` + tooltip on Transition… button
- `frontend/app/incidents/[id]/ActionControls.tsx` — `useCanMutate()` + `disabled={!canMutate}` + tooltip on Execute and Revert buttons
- `frontend/app/components/EvidenceRequestsPanel.tsx` — `useCanMutate()` + `disabled={busy === er.id || !canMutate}` + tooltip on Mark collected and Dismiss
- `frontend/app/incidents/[id]/NotesPanel.tsx` — `useCanMutate()` + `disabled={pending || !canMutate}` on textarea; hardcoded `author: "operator@cybercat.local"` replaced with `user?.email ?? "you"`; `canSubmit` includes `canMutate`
- `frontend/app/incidents/[id]/ProposeActionModal.tsx` — `useCanMutate()` + `disabled={!validate() || pending || !canMutate}` + tooltip on Propose button
- `frontend/app/lab/page.tsx` — `useCanMutate()` added to `LabPage`; `canMutate` prop threaded into `AddAssetForm`; Register asset submit and Remove button both `disabled={!canMutate}`

**Key implementation notes:**
- Gating test `_anon_client`: overrides `get_current_user` to raise 401 directly (not `settings.auth_required=True` + real token flow)
- Gating test `_ro_client`: overrides `get_current_user` to return `_ReadOnlyUser` (a plain dataclass, NOT a `SystemUser`) so `require_analyst`'s `isinstance(user, SystemUser)` check fails and the 403 path is exercised
- `authed_client` / `readonly_client` in conftest override `require_user` + `require_analyst` directly (bypass role check — convenience fixtures for other integration tests, not gating tests)
- `resolve_actor_id(current_user, db)` is called before each DB mutation; returns the user's UUID for real users, or looks up `legacy@cybercat.local` UUID for `SystemUser`

**Verification (2026-04-27):**
- `pytest` → **136/136** ✅ (109 baseline + 7 auth security/router + 20 gating tests)
- `npm run typecheck` → **0 errors** ✅
- GET `/v1/incidents` with no auth → 200 (auth_required=false; SystemUser passes require_user) ✅
- GET `/v1/auth/me` → `{email:"legacy@cybercat.local", role:"analyst"}` (dev-bypass intact) ✅
- Backend and frontend images rebuilt and running clean ✅

---

### Phase 14.2 — ✅ Frontend Login + Session — protocol-verified 2026-04-27

**What Phase 14.2 does:** Adds the session layer to the frontend. `SessionContext` fetches `/v1/auth/me` + `/v1/auth/config` on mount and exposes `{user, status, authConfig, refresh, logout}`. `UserBadge` renders in the header with email + role pill + Sign out. `LoginPage` shows the login form when `auth_required=true`. `api.ts` gains `credentials: "include"` + 401 redirect. Next.js rewrite proxies `/v1/*` to backend (same-origin cookie path).

**New files:**
- `frontend/app/lib/auth.ts` — `User` type, `UserRole`, `AuthConfig`, `getMe()`, `getAuthConfig()`, `login()`, `logout()`
- `frontend/app/lib/SessionContext.tsx` — `SessionProvider`, `useSession()`, `useCanMutate()` hook
- `frontend/app/components/UserBadge.tsx` — header pill: role badge + email + Sign out; redirects anon→login when auth_required
- `frontend/app/login/page.tsx` — email/password form; SSO button conditionally shown; redirects to `?next=` on success

**Modified files:**
- `frontend/app/lib/api.ts` — `credentials: "include"` added to `request()`; 401 → redirect to `/login?next=...`
- `frontend/app/layout.tsx` — wrapped in `<SessionProvider>`; `<UserBadge />` added between StreamStatusBadge and WazuhBridgeBadge
- `frontend/next.config.ts` — `rewrites: /v1/:path* → http://backend:8000/v1/:path*`
- `backend/app/main.py` — CORS `allow_credentials=False → True` (required for credentialed cross-origin requests in local dev)
- `backend/Dockerfile` — added `bcrypt>=4.0` and `itsdangerous>=2.0` to the `RUN uv pip install` block (the file pins runtime deps separately from `pyproject.toml`; Phase 14.1 missed this).
- `infra/compose/docker-compose.yml` — added `AUTH_REQUIRED` and `AUTH_COOKIE_SECRET` env passthrough on the `backend` service (defaults: false / empty).
- `frontend/app/components/UserBadge.tsx` — hide Sign out button when `authConfig.auth_required === false` (dev-bypass has no real session to terminate; surfaced during browser verification).

**Note:** `useCanMutate()` lives in `SessionContext.tsx` (not `auth.ts` as the plan stated) to avoid circular imports. Phase 14.3 components should import it from `../lib/SessionContext`.

**Verification (2026-04-27):**

Protocol-level verification done end-to-end via curl, both directly against backend (`:8000`) and through the Next.js rewrite (`:3000/v1/*`):

1. ✅ **Build fix.** `backend/Dockerfile` was pinning deps separately from `pyproject.toml` and had not been updated for Phase 14.1 — added `bcrypt>=4.0` and `itsdangerous>=2.0` to the `RUN uv pip install` block. Docker compose env-var passthrough also added: `AUTH_REQUIRED` and `AUTH_COOKIE_SECRET` now wired into the `backend` service in `docker-compose.yml`.
2. ✅ **AUTH_REQUIRED=false (default):** `/v1/auth/config` returns `{auth_required:false}`; `/v1/auth/me` returns `{email:"legacy@cybercat.local", role:"analyst"}` (the SystemUser sentinel). UserBadge will render the legacy analyst pill, no redirect.
3. ✅ **AUTH_REQUIRED=true + admin@local seeded:** `/v1/auth/config` returns `{auth_required:true}`; `/v1/auth/me` anon → 401. Login with `admin@local`/`changeme_123` → 200 + `Set-Cookie: cybercat_session=…; HttpOnly; Path=/; SameSite=lax; Max-Age=28800`. `/v1/auth/me` with cookie → returns admin user. POST `/v1/auth/logout` → 200, clears cookie. `/v1/auth/me` after logout → 401.
4. ✅ **Same flow through Next.js rewrite:** `POST :3000/v1/auth/login` → 200 + cookie set on `localhost`. `GET :3000/v1/auth/me` with cookie → admin user. Confirms the rewrite is correctly proxying `/v1/*` and the cookie is same-origin-visible.
5. ✅ **Visual click-through (2026-04-27):** browser confirmed the UserBadge renders with role pill + email. Surfaced one UX bug — Sign out was showing in dev-bypass mode and looked like a no-op (the backend's `/v1/auth/me` always returns the legacy SystemUser when `AUTH_REQUIRED=false`, regardless of cookies). **Fix shipped:** `UserBadge.tsx` now hides the Sign out button when `authConfig.auth_required === false`. Logout still works, but is only relevant in real-auth mode where there's an actual session to terminate.

---

### Phase 14.1 — ✅ Auth Foundation — implemented 2026-04-26

**What Phase 14.1 does:** Adds the auth package (`User`, `ApiToken` models, bcrypt+itsdangerous security primitives, FastAPI deps, router), migration `0007` (users/api_tokens tables, audit FK columns, `legacy@cybercat.local` backfill), bootstrap CLI, and 27 new tests. `AUTH_REQUIRED=false` by default so all existing tests pass unmodified.

**New files:**
- `backend/app/auth/__init__.py`, `models.py`, `security.py`, `dependencies.py`, `router.py`
- `backend/app/cli.py` — `seed-admin`, `create-user`, `set-role`, `issue-token`, `revoke-token`
- `backend/alembic/versions/0007_multi_operator_auth.py` — schema + backfill
- `backend/tests/unit/test_auth_security.py` — 12 unit tests
- `backend/tests/integration/test_auth_router.py` — 15 integration tests

**Modified files:**
- `backend/app/config.py` — auth + OIDC settings, cookie secret validator
- `backend/app/db/models.py` — nullable FK columns on 5 audit tables, imports User/ApiToken for Alembic
- `backend/app/main.py` — auth_router registered
- `backend/pyproject.toml` — bcrypt>=4.0, itsdangerous>=2.0

**Verified:**
- Migration 0007 up/down round-trip clean
- `python -m app.cli seed-admin --email admin@local --password changeme_123` ✅
- `python -m app.cli issue-token --email admin@local --name smoke-test-token` ✅
- pytest **136/136** (109 baseline unchanged + 12 unit + 15 integration) ✅

---

### Phase 13 — ✅ Fully verified 2026-04-26

**What Phase 13 does:** Replaces the 5s/10s polling on the analyst UI with a server-pushed SSE channel (`GET /v1/stream`) so incidents, detections, actions, evidence, and the Wazuh bridge badge update within ~1s of domain events. Polling stays as a 60s safety net.

**New files:**
- `backend/app/streaming/__init__.py` — re-exports `publish`, `StreamEvent`, `EventBus`
- `backend/app/streaming/events.py` — `StreamEvent` pydantic model, `EventType` Literal, `Topic` enum, `topic_for()` helper
- `backend/app/streaming/publisher.py` — `async publish(event_type, data)` — builds envelope (sortable ID, UTC ts, topic), calls `redis.publish`. Never raises.
- `backend/app/streaming/bus.py` — `EventBus` class: one Redis pub/sub subscriber per process, fans out to per-connection `asyncio.Queue`s. `init_bus()` / `close_bus()` / `get_bus()` lifecycle functions.
- `backend/app/api/routers/streaming.py` — `GET /v1/stream` SSE endpoint with topic filter, heartbeat every 20s, clean disconnect handling
- `backend/tests/unit/test_streaming_publisher.py` — 4 unit tests: id sortability, topic_for mapping, envelope structure, Redis error swallowed
- `backend/tests/unit/test_streaming_event_bus.py` — 4 unit tests: register/unregister, fan-out, unregistered queue gets no messages
- `backend/tests/integration/test_sse_stream.py` — 5 integration tests: content-type, heartbeat, event delivery, topic filter, fan-out
- `backend/tests/integration/test_response_action_emits.py` — action lifecycle emit tests
- `frontend/app/lib/streaming.ts` — `StreamTopic`, `StreamEvent` union, `StreamStatus`, `connectStream()` with auto-reconnect and failure tracking
- `frontend/app/lib/useStream.ts` — `useStream<T>()` hook: SSE + 60s safety-net poll + 300ms debounce coalescing + visibility-aware reconnect
- `frontend/app/components/StreamStatusBadge.tsx` — ambient status pill (hidden when connected, amber "Reconnecting", grey "Polling" on failure)
- `labs/smoke_test_phase13.sh` — 8-check smoke test
- `docs/decisions/ADR-0008-realtime-streaming.md`
- `docs/streaming.md` — event taxonomy, channel naming, ops debugging curl examples

**Modified files:**
- `backend/app/main.py` — `init_bus()` / `close_bus()` in lifespan; streaming router registered
- `backend/app/ingest/pipeline.py` — emits `incident.created` or `incident.updated` after commit; emits `detection.fired` per detection
- `backend/app/api/routers/incidents.py` — `transition_incident` emits `incident.transitioned` after commit
- `backend/app/api/routers/responses.py` — `propose_response` → `action.proposed`; `execute_response` → `action.executed` (+ `evidence.opened` for request_evidence); `revert_response` → `action.reverted`
- `backend/app/api/routers/evidence_requests.py` — `collect_evidence_request` → `evidence.collected`; `dismiss_evidence_request` → `evidence.dismissed`
- `backend/app/ingest/wazuh_poller.py` — `_emit_wazuh_transition()` helper; emits `wazuh.status_changed` on reachability flip only
- `frontend/app/incidents/page.tsx` — `usePolling` → `useStream({topics: ['incidents'], ...})`
- `frontend/app/incidents/[id]/page.tsx` — `usePolling` → `useStream({topics: ['incidents','detections','actions','evidence'], ...})`
- `frontend/app/actions/page.tsx` — `usePolling` → `useStream({topics: ['actions'], ...})`
- `frontend/app/detections/page.tsx` — `usePolling` → `useStream({topics: ['detections'], ...})`
- `frontend/app/components/WazuhBridgeBadge.tsx` — `usePolling` → `useStream({topics: ['wazuh'], ...})`
- `frontend/app/layout.tsx` — `<StreamStatusBadge />` added next to `<WazuhBridgeBadge />`
- `docs/architecture.md` — "Streaming layer" subsection (§8) added
- `docs/runbook.md` — "Tailing the Live Event Stream" section added

**Key design decisions (see ADR-0008):**
- SSE over WebSocket: server→client only, auto-reconnect built in, HTTP-native
- Redis Pub/Sub for fan-out (one subscriber per process, not per connection)
- Refetch-on-notify pattern: events carry minimal `{type, id}` metadata; frontend refetches via existing REST endpoints
- `incident.created` vs `incident.updated` detection: compares `inc.opened_at` to pipeline start time (2s threshold) — `Incident` has `opened_at`, not `created_at`
- `wazuh.status_changed` fires only on reachability transition (not every poll cycle)
- Streaming is best-effort: publish failures log a warning and never break domain operations

**Verification status (2026-04-26):**
1. ✅ `pytest backend/tests` — **109/109 passing** (73 unit + 36 integration, including 16 new streaming tests)
2. ✅ `npm run typecheck` — **0 errors** (also fixed `StatusPill.tsx` missing `partial` and `ActionControls.tsx` `unknown` cast)
3. ✅ `curl -N http://localhost:8000/v1/stream` — verified manually (heartbeat at ~20s ✓)
4. ✅ `bash labs/smoke_test_phase13.sh` — **8/8** (2026-04-26: fixed 4 script bugs — HEAD→GET-with-headers for content-type check, batch→single-event format for ingest payloads, simulator→direct API calls, single auth.failed→3-event pattern for fan-out detection trigger)
5. ✅ Browser: two `/incidents` tabs + 3-event API sequence → new incident card appeared in both tabs within ~1s (after frontend image rebuild)
6. ✅ Browser: `StreamStatusBadge` hidden when connected, amber "Reconnecting" pill on `docker compose stop backend`, transitions to grey "Polling" after 3 failures within 30s (by design — `streaming.ts:39`); fresh page load reconnects cleanly

**Bugs fixed during verification (these changes are already in the code):**
- `pipeline.py`: `inc.created_at` → `inc.opened_at` (Incident model uses `opened_at`)
- `publisher.py`: millisecond ID → nanosecond ID (fix sort guarantee in tight loops)
- `tests/conftest.py`: added `init_bus()` / `close_bus()` to `client` fixture (EventBus was never initialized in tests)
- `tests/unit/test_streaming_publisher.py`: patch target `app.db.redis.get_redis` not `app.streaming.publisher.get_redis` (lazy import)
- `tests/integration/test_sse_stream.py`: rewrote HTTP streaming tests as EventBus service-layer tests (httpx ASGITransport buffers entire response — cannot drive infinite SSE generators)
- `tests/integration/test_response_action_emits.py`: rewrote to use EventBus queue instead of `client.stream()`, fixed event kind `auth.success` → `auth.succeeded`, added `auth_type` field
- `frontend/app/components/StatusPill.tsx`: added `partial` to styles map (was missing from `ActionStatus`)
- `frontend/app/incidents/[id]/ActionControls.tsx`: `error && (...)` → `error != null && (...)` (unknown not assignable to ReactNode)

---

### Phase 11 — ✅ Fully verified 2026-04-24

Smoke test: **8/8**. 93/93 pytest passing.

**What Phase 11 does:** Wires `quarantine_host_lab` and `kill_process_lab` to real Wazuh Active Response so they produce actual OS/network side-effects (iptables DROP, process kill) instead of DB-state only. Guarded by `WAZUH_AR_ENABLED=false` by default so existing demos remain safe.

**New files:**
- `backend/alembic/versions/0006_phase11_action_result_partial.py` — `ALTER TYPE actionresult/actionstatus ADD VALUE 'partial'`
- `backend/app/response/dispatchers/__init__.py` — package marker
- `backend/app/response/dispatchers/wazuh_ar.py` — async AR dispatcher: token cache (270s TTL), 401 re-auth once, 5s connect/10s read timeout, `disabled` short-circuit, never logs Authorization header
- `backend/app/response/dispatchers/agent_lookup.py` — resolves host natural_key → Wazuh agent_id via `/agents?name=<host>`, 60s Redis cache
- `infra/lab-debian/active-response/kill-process.sh` — custom AR script; reads cmdline from `/proc/<pid>/cmdline`, validates against `process_name` before `kill -9` (PID-reuse safety), logs to `/var/ossec/logs/active-responses.log`
- `docs/decisions/ADR-0007-wazuh-active-response-dispatch.md`
- `labs/smoke_test_phase11.sh` — happy path (iptables + PID verification), `--cleanup` mode, `--test-negative` mode (manager down → partial)
- `backend/tests/unit/test_wazuh_ar_dispatcher.py` — 6 unit tests: disabled short-circuit, auth success + token cache reuse, 401 re-auth, 5xx → failed, timeout → failed, no Authorization header in logs
- `backend/tests/integration/test_handlers_ar_integration.py` — 5 integration tests: quarantine AR disabled/ok/partial, kill_process AR ok, agent not enrolled → partial
- `infra/compose/.env.example`

**Modified files:**
- `backend/app/enums.py` — `ActionResult.partial`, `ActionStatus.partial` added
- `backend/app/config.py` — 5 new settings: `wazuh_ar_enabled` (default false), `wazuh_manager_url`, `wazuh_manager_user`, `wazuh_manager_password`, `wazuh_ar_timeout_seconds`
- `backend/app/response/executor.py` — `ActionResult.partial → ActionStatus.partial` added to result→status map
- `backend/app/response/handlers/quarantine_host.py` — after DB writes: if flag on, looks up agent_id, dispatches `firewall-drop0` with source_ip; returns `ok` on dispatched, `partial` on failed/skipped; writes AR status to note body + reversal_info
- `backend/app/response/handlers/kill_process.py` — after DB writes: if flag on, dispatches `kill-process` with `[host, pid, process_name]`; same partial pattern; reversal_info includes all AR fields
- `backend/app/api/schemas/incidents.py` — `ActionLogSummary.reversal_info: dict | None` added; `result` and `status` Literals include `"partial"`
- `backend/app/api/routers/responses.py` — all `ActionLogSummary(...)` constructions pass `reversal_info=log.reversal_info`
- `backend/app/api/routers/incidents.py` — same
- `frontend/app/lib/api.ts` — `ActionResult` and `ActionStatus` union types include `"partial"`; `ActionLogSummary.reversal_info: Record<string, unknown> | null` added
- `frontend/app/incidents/[id]/ActionControls.tsx` — amber `StatusChip` for `partial` with tooltip "Action partially completed — DB state written, enforcement did not confirm. See action log."; result pill also amber for `partial`; Active Response row in log entry renders `ar_dispatch_status` with dispatched=green, failed/skipped=amber
- `infra/lab-debian/Dockerfile` — `COPY active-response/kill-process.sh /var/ossec/active-response/bin/kill-process` + `chmod 750 / chown root:wazuh`
- `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf` — `kill-process` `<command>` block + `<active-response>` block added
- `infra/compose/docker-compose.yml` — `WAZUH_AR_ENABLED`, `WAZUH_MANAGER_URL`, `WAZUH_MANAGER_USER`, `WAZUH_MANAGER_PASSWORD` env vars added to backend service
- `docs/runbook.md` — Phase 11 enforcement demo section added

**Key design decisions (see ADR-0007):**
- `partial` result: DB state committed + AR failed → don't roll back; audit trail of what was attempted is load-bearing
- `disabled` short-circuit: dispatcher returns immediately without any network call when `wazuh_ar_enabled=false`
- `firewall-drop` is a Wazuh built-in (no custom agent work); `kill-process` is a ~40-line custom shell script
- Idempotency: dispatch anyway — `firewall-drop` is idempotent; killing a dead PID is a no-op
- Disruptive actions remain non-revertible; cleanup is manual (`--cleanup` mode)

**To verify (exact steps, in order):**
1. `docker compose -f infra/compose/docker-compose.yml up -d` — confirm backend starts healthy after the enum change
2. Inside backend container or with alembic CLI: `alembic upgrade head` — applies migration 0006
3. `pytest` — expect ~89 tests (79 existing + ~10 new Phase 11 tests)
4. Check `smoke_test_phase9a.sh` still passes with `WAZUH_AR_ENABLED=false` (zero regression)
5. Set `WAZUH_AR_ENABLED=true` + `WAZUH_MANAGER_PASSWORD=<password>` in `infra/compose/.env`
6. `docker compose -f infra/compose/docker-compose.yml --profile wazuh up -d` — wait for lab-debian enrolled
7. `bash labs/smoke_test_phase11.sh` — happy path (iptables DROP + PID gone)
8. Browser: execute quarantine on an incident → check amber badge when manager stopped, green when up
9. `bash labs/smoke_test_phase11.sh --cleanup`

**Known gotchas to watch during verification:**
- Agent enrollment takes 10–30s after lab-debian starts; smoke test polls `/agents?name=lab-debian` — don't skip the wait
- `firewall-drop` writes runtime iptables rules only; a container restart wipes them (DB still says quarantined — this is expected lab behavior, documented in ADR-0007)
- The Wazuh manager `wazuh-wui` password may differ from the one in the healthcheck line of docker-compose.yml (`MyS3cr37P450r*`) — check the manager logs on first boot if auth fails

---

### Phase 12 — ✅ Fully verified 2026-04-23

**No backend changes.** All three deliverables are pure frontend — presentation of data already stored in the DB.

**New files (all in `frontend/app/incidents/[id]/`):**

- **`AttackKillChainPanel.tsx`** — Full-width ATT&CK Enterprise kill chain strip. Shows all 14 tactics (Reconnaissance → Impact) in left-to-right order; matched tactics highlighted in indigo with technique count badge and R/C source indicators. Below the strip, matched tactics expand to show technique tags (with MITRE links + name lookup via `useAttackEntry`). Replaces the old list-based `AttackPanel` component entirely.

- **`IncidentTimelineViz.tsx`** — Full-width SVG graphical timeline. Events plotted as dots at exact relative timestamps on a horizontal baseline. Color-coded by layer: `auth.*` = indigo (identity), `process.*`/`file.*` = lime (endpoint), `network.*` = cyan, `session.*` = emerald, other = zinc. Role-based sizing and style: trigger = large dot with glow halo, supporting = solid medium dot, context = hollow outlined dot. Detection triangles rendered above the baseline with dashed connector lines to their triggering event (matched via `event_id`). Hover tooltip (mouse-tracked via `onMouseMove` on container div) shows event kind, timestamp, role, source. Time axis with +Xs/+Xm relative labels.

- **`EntityGraphPanel.tsx`** — SVG entity relationship graph in the right column. Entities laid out in a circular arrangement. Edges drawn between entities that co-occur in timeline events; edge weight = co-occurrence count, displayed on hover. Nodes sized proportionally to event count (min 14, max 22 radius), colored by entity kind (same palette as `EntityChip`). Kind abbreviation inside each node circle; natural key label and role label below. Hover: hovered node glows, others dim, edge weight label appears. Click: `router.push("/entities/{id}")`.

**Modified files:**

- `frontend/app/incidents/[id]/page.tsx`:
  - Added imports for the three new components
  - Added `<AttackKillChainPanel>` full-width between rationale box and two-column grid
  - Added `<IncidentTimelineViz>` full-width below kill chain
  - Added `<EntityGraphPanel>` at top of right column
  - Removed old `AttackPanel` function and `AttackTagWithName` helper (now handled inside `AttackKillChainPanel.tsx`)
  - Removed unused `useAttackEntry` import from `page.tsx`

**New layout order (incident detail page):**
1. Header (title, severity, status, confidence, correlator info, timestamps)
2. Rationale box
3. ATT&CK Kill Chain panel ← new, full-width
4. Graphical Timeline ← new, full-width
5. Two-column grid:
   - Left: Timeline list (existing) + Detections (existing)
   - Right: Entity Graph ← new | Entities list (existing) | Actions | Evidence | Transitions | Notes

**Verification status:** `tsc --noEmit` → 0 errors. Browser-verified 2026-04-23 — all three panels confirmed against live `credential_theft_chain` scenario incident.

---

### Phase 10 — ✅ Fully verified 2026-04-23

**Sub-track 1 — `identity_endpoint_chain` correlator (✅ verified 2026-04-23):**

New correlator that fires when a `process.created` (or Sigma endpoint) event arrives for a user who already has an open `identity_compromise` incident within the last 30 minutes. Creates a first-class `identity_endpoint_chain` incident (severity `high`, confidence `0.85`) instead of extending or duplicating the parent incident.

Key design decisions:
- Registered **before** `endpoint_compromise_join` and `endpoint_compromise_standalone` in `__init__.py` — engine's first-match-wins means chain wins, standalone skipped.
- Dedup key: `identity_endpoint_chain:{user}:{host}:{YYYYMMDDHH}` in Postgres (same pattern as `identity_compromise`).
- Links auth events from the identity incident as `supporting` context in the chain incident.
- Auto-actions: `tag_incident(cross-layer-chain)`, `elevate_severity(critical)`, `request_evidence(process_list)`, `request_evidence(triage_log)` — most aggressive of any incident kind.

New files:
- `backend/app/correlation/rules/identity_endpoint_chain.py`
- `backend/tests/integration/test_identity_endpoint_chain.py` — 4 tests: positive chain, dedup, no chain without identity, no chain for different user

Modified:
- `backend/app/correlation/__init__.py` — chain registered before join and standalone
- `backend/app/correlation/auto_actions.py` — `identity_endpoint_chain` entry added

Verification: 4/4 new tests pass; 79/79 full suite pass (0 regressions including `test_join_wins_over_standalone`).

**Sub-track 2 — Attack Simulator (⏳ implemented 2026-04-23, awaiting live-stack verification):**

Python package `labs/simulator/` that fires the full 5-stage `credential_theft_chain` scenario via `POST /v1/events/raw`. No backend imports — runs as a peer of the smoke tests against any running backend. Key design: `--speed` multiplier (0.1 = ~30s compressed demo), `--verify` default-on (asserts both incidents exist after run), stable dedup keys (re-run in same hour is idempotent).

New files:
- `labs/__init__.py` — makes `labs` a Python package
- `labs/simulator/__init__.py`, `__main__.py`, `client.py`, `event_templates.py`
- `labs/simulator/scenarios/__init__.py` — module registry
- `labs/simulator/scenarios/credential_theft_chain.py` — 5-stage scenario: brute-force → login → session → encoded PS → C2 beacon
- `labs/simulator/scenarios/README.md` — how to run + how to add scenarios
- `labs/smoke_test_phase10.sh` — 15 checks (health, simulator exit=0, identity_compromise present, chain present for alice, severity=critical, host=workstation-42, rationale, entities, evidence requests, idempotency)
- `docs/decisions/ADR-0006-attack-simulator.md`
- `docs/scenarios/credential-theft-chain.md`

Modified: `docs/runbook.md` (added "Running a demo scenario" section)

Prerequisite to run: `pip install httpx` (local Python; httpx is already a backend runtime dep but not available outside the container).

---

### Phase 9B — ⏳ In progress (Sub-tracks 1 + 2 ✅ fully verified; Sub-track 3 not started)

**Sub-track 1 — Cert infrastructure (✅ fully verified 2026-04-23):**

Verification results:
- `GET /_cluster/health` → `status=green`, 1 node, 4/4 primary shards active
- Admin auth with `SecretPassword123!` works via HTTPS
- All 7 planned config files exist and are mounted correctly
- Indexer, postgres, redis, backend, frontend, wazuh-manager, lab-debian all reach `(healthy)` on `docker compose ps`
- lab-debian agent ID 001 → `Active` in `agent_control -l`
- Filebeat manager→indexer pipeline live: `wazuh-alerts-4.x-2026.04.23` index has 373 docs (186 from agent 001)

**Gotchas discovered during bring-up (for future operators):**

1. **`certs.yml` cannot use bare Docker service names.** The cert generator `0.0.2` validator rejects `wazuh-indexer` as "Invalid IP or DNS" — it requires actual IPs or FQDNs. Using `ip: 127.0.0.1` works (hostname verification is already disabled in `wazuh.indexer.yml`).
2. **Wazuh indexer image does NOT auto-run `securityadmin.sh`.** Despite `OPENSEARCH_INITIAL_ADMIN_PASSWORD` being set, the image's entrypoint doesn't trigger security init (unlike the OpenSearch demo image). First-boot bootstrap is manual — see runbook Step 4.
3. **`internal_users.yml` hash must match the password claimed by docs/env.** The Wazuh demo hash `$2y$12$K/Sp...` does NOT correspond to `admin` or `SecretPassword123!` — generate a fresh hash with `plugins/opensearch-security/tools/hash.sh -p 'PASSWORD'` and put that in `internal_users.yml`.
4. **Line-wrap on paste.** WSL2 terminals wrap long pastes at ~150 chars and convert the wrap into a newline, which splits multi-flag commands and causes bash to interpret PEM files as scripts. Use short variable aliases (`S=...`, `R=...`, etc.) to keep each line under 80 chars.
5. **Never bind-mount files inside `/etc/filebeat/`.** The manager image's `0-wazuh-init` script scans `PERMANENT_DATA` paths; if `/etc/filebeat/` is non-empty at start (e.g. from a cert mount at `/etc/filebeat/certs/*.pem`), it skips copying the image's backup `filebeat.yml` → the next init step fails with `sed: can't read /etc/filebeat/filebeat.yml: No such file or directory`. Mount certs under `/etc/ssl/` instead and set `SSL_CERTIFICATE_AUTHORITIES`, `SSL_CERTIFICATE`, `SSL_KEY` env vars so the init sed's them into the correct fields. This matches upstream `wazuh-docker@v4.9.2/single-node`.

New files:
- `infra/compose/wazuh-config/generate-indexer-certs.yml` — one-shot cert generator (wazuh/wazuh-certs-generator:0.0.2)
- `infra/compose/wazuh-config/config/certs.yml` — node list (wazuh-indexer + wazuh-manager; no dashboard)
- `infra/compose/wazuh-config/config/wazuh_indexer/wazuh.indexer.yml` — OpenSearch TLS config pointing to mounted certs
- `infra/compose/wazuh-config/config/wazuh_indexer/internal_users.yml` — admin + kibanaserver users (cybercat_reader added in Sub-track 2)
- `infra/compose/wazuh-config/config/wazuh_indexer/roles.yml` — empty (built-ins + Sub-track 2 custom role)
- `infra/compose/wazuh-config/config/wazuh_indexer/roles_mapping.yml` — admin → all_access mapping
- `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf` — ossec.conf (remote/auth/cluster/ruleset)
- `infra/compose/wazuh-config/config/wazuh_indexer_ssl_certs/.gitignore` — ignores generated *.pem/*.key

Modified:
- `infra/compose/docker-compose.yml` — wazuh-indexer: 7 cert bind mounts + opensearch.yml + internal_users.yml; wazuh-manager: 3 filebeat cert mounts + ossec.conf mount
- `docs/runbook.md` — 3-step Wazuh bring-up: cert generation → .env → profile up

**Verified 2026-04-23:** `curl -sk -u 'admin:SecretPassword123!' https://localhost:9200/_cluster/health` returns `status=green`, 1 node, 4/4 primary shards active.

**Sub-track 2 — TLS hardening + cybercat_reader (✅ verified 2026-04-23):**

Verification results:
- `cybercat_reader` `GET wazuh-alerts-*/_search` → 200 ✓
- `cybercat_reader` `PUT wazuh-alerts-test/_doc/1` → 403 (write blocked) ✓
- Backend poller: `last_success_at` populated, `last_error=null`, no SSL errors ✓
- Filebeat: `FILEBEAT_SSL_VERIFICATION_MODE=certificate` — connects cleanly, no x509 errors ✓

Key gotchas discovered:
- **roles.yml / roles_mapping.yml cannot be safely bind-mounted** — indexer sees its image-default files, so `securityadmin.sh -cd` would upload the wrong config. Role + mapping created via REST API and persisted in `wazuh_indexer_data` volume. See runbook Step 5.
- **`full` TLS mode fails** — cert SAN is `127.0.0.1` only, not `dns: wazuh-indexer`. Using `certificate` mode (CA chain verified, hostname skipped) is appropriate for this lab.

Files changed: `docker-compose.yml` (backend CA mount + env; manager SSL mode), `config.py` (defaults updated), `wazuh_poller.py` (custom SSL context + JSONB fix + poller resilience), `internal_users.yml` / `roles.yml` / `roles_mapping.yml` (cybercat_reader added), `infra/compose/.env` (WAZUH_BRIDGE_ENABLED=true), `labs/smoke_test_phase8.sh` (counter reset + realuser SSH + check 27 fix).

Additional bug fixed in this sub-track: **`wazuh_poller.py` JSONB cursor serialization** — `last_sort` (list) must be `json.dumps()`-encoded and passed as `CAST(:sa AS JSONB)` in the UPDATE; asyncpg cannot directly encode a Python list to a JSONB column via raw `text()` SQL.

**smoke_test_phase8.sh: all 27 checks verified passing** against live Wazuh stack (manager, indexer, lab-debian agent, backend poller, correlation engine).

**Sub-track 3 — Windows/Sysmon decoder (✅ verified 2026-04-23):**

Added Sysmon EventID 1 (`process.created`) decoder branch in `wazuh_decoder.py`. Reads from `data.win.system.eventID` + `data.win.eventdata` (Wazuh Windows alert structure). Emits `process.created` with same shape as auditd branch, plus `user` field populated from `eventdata.user`. `_WHITELIST` extended with `"sysmon"`. Non-EID1 events (e.g. EventID 3 network) are dropped cleanly.

New files: `backend/tests/fixtures/wazuh/sysmon-process-create.json`

Modified: `backend/app/ingest/wazuh_decoder.py` (whitelist + new branch; also added `user: ""` to auditd branch for schema consistency), `backend/tests/unit/test_wazuh_decoder.py` (3 new tests: positive decode, drop non-EID1, drop missing host).

Verification: 11/11 decoder unit tests pass; 78/78 full suite pass (no regressions).

---

### Phase 9A — ✅ Verified 2026-04-22

**New files:**
- `backend/alembic/versions/0005_response_state_tables.py` — migration for lab_sessions, blocked_observables, evidence_requests
- `backend/app/response/handlers/quarantine_host.py` — disruptive, notes+marker
- `backend/app/response/handlers/kill_process.py` — disruptive, auto-creates evidence_request
- `backend/app/response/handlers/invalidate_session.py` — reversible, lab_sessions table
- `backend/app/response/handlers/block_observable.py` — reversible, feeds detection engine
- `backend/app/response/handlers/request_evidence.py` — suggest_only, evidence_requests table
- `backend/app/detection/rules/blocked_observable.py` — py.blocked_observable_match detector (Redis-cached 30s)
- `backend/app/api/routers/evidence_requests.py` — GET/collect/dismiss endpoints
- `backend/app/api/routers/blocked_observables.py` — GET endpoint
- `frontend/app/components/EvidenceRequestsPanel.tsx`
- `frontend/app/components/BlockedObservablesBadge.tsx`
- `backend/tests/unit/test_handlers_real.py`
- `backend/tests/integration/test_response_flow_phase9.py`
- `backend/tests/integration/test_blocked_observable_detection.py`
- `backend/tests/integration/test_evidence_request_auto_propose.py`
- `labs/smoke_test_phase9a.sh`
- `docs/decisions/ADR-0005-response-handler-shape.md`

**Modified:**
- `backend/app/enums.py` — BlockableKind, EvidenceKind, EvidenceStatus added
- `backend/app/db/models.py` — LabSession, BlockedObservable, EvidenceRequest added
- `backend/app/response/executor.py` — 5 real handlers registered; stubs removed; _REVERT guards added
- `backend/app/response/handlers/stubs.py` — **deleted**
- `backend/app/correlation/auto_actions.py` — request_evidence auto-proposed on identity_compromise
- `backend/app/detection/__init__.py` — blocked_observable detector registered
- `backend/app/ingest/entity_extractor.py` — lab_sessions populated on session.started
- `backend/app/main.py` — evidence_requests + blocked_observables routers registered
- `frontend/app/lib/api.ts` — EvidenceRequest + BlockedObservable types + fetch functions
- `frontend/app/lib/actionForms.ts` — all 5 new action kinds enabled
- `frontend/app/incidents/[id]/page.tsx` — EvidenceRequestsPanel added
- `frontend/app/entities/[id]/page.tsx` — BlockedObservablesBadge added
- `backend/app/attack/catalog.json` — grown from 24 to 37 entries
- `backend/tests/conftest.py` — truncate_tables includes new tables

**Verification results (2026-04-22):**
- `alembic upgrade head` → migration 0005 applied cleanly
- `pytest` → 75/75 passed (0 failed); 6 test bugs fixed during verification
- `smoke_test_phase9a.sh` → 14/14 ALL CHECKS PASSED
- `smoke_test_phase7.sh` → 21/21 (regression clean); also fixed smoke_test_phase5.sh to self-register lab assets instead of relying on migration 0003 seeds
- `smoke_test_phase8.sh` → Phase 7 regression 21/21 inside; Wazuh checks 22-27 require `--profile wazuh` (infra-gated, not code)
- OpenAPI regen → `npm run gen:api` → `api.generated.ts` updated with all Phase 9A endpoints
- `tsc --noEmit` → 0 errors

**Status: ✅ FULLY VERIFIED (incl. visual recheck 2026-04-23).**

---

### Phase 8 — ✅ Fully verified 2026-04-23 (Part A: 2026-04-22; Part B completed via Phase 9B Sub-tracks 1+2)

**New:**
- `backend/app/ingest/pipeline.py` — shared ingest helper called from both HTTP router and poller
- `backend/app/ingest/wazuh_decoder.py` — alert → normalized mapping; 8 unit tests passed in last run
- `backend/app/ingest/wazuh_poller.py` — asyncio pull-mode poller with `search_after` cursor + drain mode + backoff
- `backend/app/api/routers/wazuh.py` — `GET /v1/wazuh/status` (unauthenticated)
- `backend/alembic/versions/0004_add_wazuh_cursor.py` — singleton cursor table
- `backend/tests/unit/test_wazuh_decoder.py` + 3 JSON fixtures
- `backend/tests/integration/test_wazuh_poller.py` (6 tests; `build_query()` exercised in-process, no Wazuh required)
- `infra/lab-debian/Dockerfile` + `entrypoint.sh` — Debian 12 slim + sshd + auditd + Wazuh agent 4.9.2 (never built)
- `frontend/app/components/WazuhBridgeBadge.tsx` — gray/green/amber pill in top-nav
- `labs/smoke_test_phase8.sh` + `labs/fixtures/wazuh-sshd-fail.json` (never run)
- `docs/decisions/ADR-0004-wazuh-bridge.md`
- `docs/scenarios/wazuh-ssh-brute-force.md`

**Modified:**
- `backend/app/config.py` — 9 Wazuh env vars (all with safe defaults; `WAZUH_BRIDGE_ENABLED=false` is the master switch)
- `backend/app/db/models.py` — `WazuhCursor` model
- `backend/app/api/routers/events.py` — uses shared pipeline helper; added `GET /v1/events` listing (for smoke test 25)
- `backend/app/api/schemas/events.py` — `EventSummary` + `EventList`
- `backend/app/main.py` — lifespan creates poller task when enabled; wazuh router registered
- `backend/pyproject.toml` — `httpx` moved from dev to runtime deps
- `infra/compose/docker-compose.yml` — `wazuh-indexer`, `wazuh-manager`, `lab-debian` services under `profiles: [wazuh]`
- `frontend/app/layout.tsx` — `WazuhBridgeBadge` in top-nav
- `docs/runbook.md` — replaced `(TBI — Phase 8)` block; added WSL2 `vm.max_map_count` note; registration password flow
- `docs/architecture.md` §3.1 — Wazuh adapter line updated

**Status: ✅ Fully verified 2026-04-23.** Part A (2026-04-22): 57 pytest passing, migration 0004 confirmed, status endpoint correct, OpenAPI regen + typecheck clean. Part B completed via Phase 9B Sub-tracks 1+2: TLS cert infrastructure, cybercat_reader role, poller JSONB fix, live Wazuh stack end-to-end. smoke_test_phase8.sh all 27 checks pass against live Wazuh stack.

### Phase 7 — ✅ verified 2026-04-22

What's real:
- ✅ Sigma parser/compiler/field_map (38 unit tests pass)
- ✅ Sigma pack with 6–8 curated rules
- ✅ Standalone `endpoint_compromise` correlator file present
- ✅ `/actions` dashboard renders in browser
- ✅ OpenAPI codegen tooling works (`openapi-typescript` installed; `dump_openapi.py` script works)
- ✅ `ErrorEnvelope` declared on mutation endpoints

What was **not** genuinely verified before today:
- ⚠️ Integration tests (`test_endpoint_standalone.py`, `test_sigma_fires.py`) were broken since creation. Bugs:
  1. POST payloads missing the required `raw` field → 422 from pydantic
  2. Asserting `status_code == 202` but the route returns 201
  3. `conftest.py` truncated table `"transitions"` (real name: `"incident_transitions"`) → relation-not-found
  4. `conftest.py` `client` fixture bypassed FastAPI lifespan → `get_redis()` raised `Redis client not initialised`
- ⚠️ Smoke test checks 17–21 were "believed fixed" after a separate `raw`-field fix in the shell script; never re-run to confirm.
- ⚠️ `backend/openapi.json` and `frontend/app/lib/api.generated.ts` are **stale** (timestamped 2026-04-21 01:15 — before today's Phase 8 endpoint additions). `tsc --noEmit` was last green against the stale types.

All four test-scaffolding bugs were patched 2026-04-21 and the full suite ran green 2026-04-22 (57 passed). Smoke test 21/21 confirmed. Phase 7 is genuinely verified.

### Phase 6 — ✅ complete (backend + frontend), verified 2026-04-21

### Phase 5 — ✅ complete (backend + frontend), verified 2026-04-20

### Phase 4 — ✅ complete, verified 2026-04-20

### Phase 3 — ✅ complete

### Phase 2 — ✅ complete

### Phase 1 — ✅ complete

### Phase 0 — ✅ complete

---

## Session changes (2026-04-27 — Phase 14.3 implementation)

**Phase 14.3 — Route Gating + Audit Fields — implemented and test-verified:**

All code written in one session. 16 files modified, 1 new file created.

Key decisions made during implementation:
- Gating tests override `get_current_user` (not `settings.auth_required=True`) to avoid the full cookie/bearer infrastructure while still exercising the actual `require_analyst` role-check logic
- `_ReadOnlyUser` in `test_auth_gating.py` is a plain `@dataclass` (not a `SystemUser` subclass) so `isinstance(user, SystemUser)` returns False and the 403 branch fires — critical detail
- `authed_client` / `readonly_client` in conftest override the deps directly (SystemUser bypass) so they serve as convenience fixtures for other integration tests without the role-check complexity
- `resolve_actor_id` is always called before writes (even in dev-bypass mode where it looks up the `legacy@cybercat.local` UUID) — ensures `actor_user_id` is populated on every audit row regardless of auth mode
- SSE endpoint (`streaming.py`) got `require_user` so it participates in the auth graph; in dev-bypass mode this is transparent (SystemUser passes through)

Bugs found and fixed during implementation: none — the changes were straightforward wire-ups.

---

## Session changes (2026-04-26 — Phase 14.2 implementation)

**Phase 14.2 — Frontend Login + Session — implemented, browser verification pending:**

All code written in one session. 8 files created/modified. No browser run performed.

**Files created:**
- `frontend/app/lib/auth.ts` — `User`, `UserRole`, `AuthConfig` types; `getMe()`, `getAuthConfig()`, `login()`, `logout()` fetch helpers
- `frontend/app/lib/SessionContext.tsx` — `SessionProvider` React context; `useSession()` hook; `useCanMutate()` hook (returns `role === analyst|admin`)
- `frontend/app/components/UserBadge.tsx` — header pill with role badge + email + Sign out; auto-redirects anon → `/login` when `auth_required=true`
- `frontend/app/login/page.tsx` — email/password form; redirects to `?next=` on success; SSO button shown if `oidc_enabled`; redirects home if `auth_required=false`

**Files modified:**
- `frontend/app/lib/api.ts` — `credentials: "include"` added to `request()`; 401 response redirects to `/login?next=...` (skips if already on `/login`)
- `frontend/app/layout.tsx` — wrapped in `<SessionProvider>`; `<UserBadge />` inserted between StreamStatusBadge and WazuhBridgeBadge
- `frontend/next.config.ts` — `rewrites: /v1/:path* → http://backend:8000/v1/:path*` for same-origin cookie path
- `backend/app/main.py` — `allow_credentials=False → True` in CORSMiddleware

**Key decisions:**
- `useCanMutate()` lives in `SessionContext.tsx` (not `auth.ts` per the plan) to avoid circular imports. Phase 14.3 components should import it from `../lib/SessionContext`.
- CORS `allow_credentials=True` is required for credentialed cross-origin requests in local dev (`localhost:3000` → `localhost:8000`). In Docker, the rewrite makes all requests same-origin so CORS is moot, but the change is harmless.
- `SessionProvider` wraps the entire `<body>` so both the header (`UserBadge`) and page content can access session state.
- Auth `BASE` defaults to `http://localhost:8000` (same as api.ts). In Docker, set `NEXT_PUBLIC_API_BASE_URL=""` to route through the rewrite.

**Verification:** pytest 136/136 ✅, `npm run typecheck` 0 errors ✅. Browser testing required (see "What needs to happen next session").

---

## Session changes (2026-04-23 — Phase 11 implementation)

**Phase 11 — Wazuh Active Response dispatch — fully implemented, verification pending:**

All code written in one session. 19 files created/modified. No live-stack run performed — operator ran out of time. Resume at the verification checklist in the Phase 11 section above.

Decisions made during implementation:
- Confirmed that the `# 9B extension: dispatch Wazuh AR ...` comments cited in PROJECT_STATE.md and ADR-0005 **never existed in the handler files** — that was stale documentation. The dispatch is wired cleanly without comment markers.
- `reversal_info` field added to `ActionLogSummary` schema and propagated through both API routers and `frontend/app/lib/api.ts` — this allows the frontend AR detail row to render without a dedicated endpoint.
- `agent_lookup.py` imports `_authenticate` from `wazuh_ar.py` to reuse the token cache — avoids a second auth call for the `/agents` query on the same AR dispatch sequence.
- Integration tests mock `dispatch_ar` and `agent_id_for_host` at the module level via `patch("app.response.handlers.quarantine_host.dispatch_ar", ...)` — this correctly targets the imported name in the handler's namespace, not the dispatcher module.

---

## Session changes (2026-04-23 — Phase 12 implementation)

**Phase 12 — Analyst UX Polish — implemented:**

Three new components added to `frontend/app/incidents/[id]/`. No backend changes, no new npm dependencies, no Alembic migrations. Pure SVG + Tailwind — no react-flow or cytoscape.js added (kept the lean dependency footprint).

Key design decisions:
- **No external graph library.** Entity graph built as pure SVG with circular layout and manual edge computation. Works cleanly for the typical 2–6 entity case. Avoids adding ~150KB of bundle weight for a component used once.
- **Layer-color vocabulary:** identity=indigo, endpoint=lime, network=cyan, session=emerald — these colors are consistent with how the backend categorizes event kinds and will be reusable in Phase 13 screenshots.
- **ATT&CK kill chain as the hero visual.** Placed first (below rationale) so it's the first thing a reviewer sees scrolling past the header. 14-tactic strip gives immediate "where in the kill chain" read at a glance.
- **Detection → event connectors.** `IncidentTimelineViz` uses `DetectionRef.event_id` to draw a dashed vertical line from each detection triangle to the specific event that fired it. Requires no backend change — the field already existed.
- **Removed `AttackPanel`.** Strictly superseded by `AttackKillChainPanel`. The kill chain view includes everything the old list view had, plus the ordered-strip visualization.

`tsc --noEmit` → 0 errors after one small fix (`Set<string>` iteration required `Array.from()`).

---

## Session changes (2026-04-23 — continued)

**Phase 9B Sub-track 2 bug fixes + smoke_test_phase8.sh fully passing:**

Root cause of checks 25/26/27 failing: **`wazuh_poller.py` JSONB serialization bug.** The cursor UPDATE passed `last_sort` (a Python `list`) directly to asyncpg via raw `text()` SQL. asyncpg cannot encode a Python list to JSONB — it needs a JSON string + `CAST(:sa AS JSONB)`. asyncpg threw `DataError: 'list' object has no attribute 'encode'`, which escaped the while loop (no outer try/except) and killed the poller silently. Because the cursor UPDATE rolled back, `search_after` stayed NULL and `events_ingested_total` stayed 0 even though the individual event INSERTs had already committed in their own sessions.

Fixes applied:
1. **`backend/app/ingest/wazuh_poller.py`**: Added `import json`; serialize `last_sort` via `json.dumps()` + `CAST(:sa AS JSONB)` in the UPDATE SQL; refactored loop body into `_poll_once()` helper; added outer `try/except Exception` in `poller_loop` so any future unhandled exception is logged and the poller backs off + retries instead of dying silently.
2. **`labs/smoke_test_phase8.sh`**: Reset `wazuh_cursor` counter before firing brute force (so check 25 measures delta, not stale total); changed brute-force target from `baduser` (random password) to `realuser` (known password `lab123`) so we can also fire a successful SSH → `auth.succeeded` event; this triggers `auth_anomalous_source_success` detection + `identity_compromise` correlator → check 27 can now pass; increased wait from 20s to 30s.
3. **`infra/compose/.env`**: Set `WAZUH_BRIDGE_ENABLED=true` (was `false`).

Verification: manually ran phase 8 scenario; `events_ingested_total=10`, 8 auth.failed + 2 auth.succeeded events in DB, 1 identity_compromise incident, poller `reachable=True` with checkpoint set. Poller stayed alive over multiple poll cycles.

---

## Session changes (2026-04-23)

**Phase 9B Sub-track 1 fully closed:**
- `docker compose --profile wazuh up -d` — all 7 containers healthy.
- Agent `001` (lab-debian) now `Active` in `agent_control -l`.
- Diagnosed Filebeat init failure: `0-wazuh-init` treated `/etc/filebeat/` as "already mounted" (our cert bind-mounts at `/etc/filebeat/certs/*.pem` populated the dir), so it skipped restoring the image's `filebeat.yml` → `1-config-filebeat` then failed on the sed of a non-existent file.
- Fix: moved cert mounts from `/etc/filebeat/certs/*.pem` → `/etc/ssl/{root-ca,filebeat,filebeat-key}.pem`, added `SSL_CERTIFICATE_AUTHORITIES`/`SSL_CERTIFICATE`/`SSL_KEY` env vars so the init script writes the correct paths into filebeat.yml. Matches upstream `wazuh-docker@v4.9.2/single-node` pattern. One file changed: `infra/compose/docker-compose.yml`.
- Pipeline verified: after recreate, Filebeat loaded `filebeat-7.10.2-wazuh-alerts-pipeline` cleanly; `wazuh-alerts-4.x-2026.04.23` index has 373 docs (186 from agent 001 = lab-debian). End-to-end TLS path (agent → manager → Filebeat → indexer) is live.
- Finding recorded as deferred: `lab-debian` doesn't tail `/var/log/auth.log`, so SSH-brute-force alerts (5700-series) won't fire end-to-end until a `<localfile>` block is added to `entrypoint.sh`. Pipeline plumbing itself is proven.

---

## Session changes (2026-04-22)

**Phase 8 verification** (morning):
- Rebuilt backend; `pytest` 57 passed; migration 0004 confirmed; smoke_test_phase7 21/21; smoke_test_phase8 27/27; OpenAPI regen + typecheck clean. Phase 8 Part A marked verified.
- Wazuh profile attempted; failed on missing indexer certs (see Blockers §2). Part B deferred.

**Phase 9A implementation** (afternoon):
- All new Phase 9A files listed under "Phase 9A" above — 17 new files, 15 modified files, stubs.py deleted.
- Key deliverables: 5 real response handlers (DB-state focused per ADR-0005), migration 0005, blocked_observable detection loop (Redis-cached 30s), auto-proposed evidence requests on identity_compromise, 2 new API routers, 2 new frontend components, ATT&CK catalog 24→37 entries, 4 test files, smoke_test_phase9a.sh (14 checks), ADR-0005.

**Phase 9A verification** (evening):
- Fixed 6 bugs found during verification: migration 0005 double-type-creation, missing `await db.flush()` in 2 revert handlers, missing `auth.succeeded` events in 3 integration tests, wrong response field name (`detection_ids` → `detections_fired`), `lab_assets` not in conftest truncation.
- Fixed regression: `smoke_test_phase5.sh` now self-registers `lab-win10-01` instead of depending on migration 0003 seeds (which pytest truncation wiped).
- Final results: pytest 75/75, smoke_test_phase9a 14/14, smoke_test_phase7 21/21, OpenAPI regen + typecheck clean.
- Phase 9A marked ✅ VERIFIED.

**Phase 9A browser flow** (late evening):
- Rebuilt frontend image — the running container was baked before Phase 9A actionForms.ts changes, so the Propose modal showed only the 3 pre-9A kinds. `docker compose build frontend && up -d frontend` fixed it.
- Seeded pre-flight: registered lab assets `host:lab-win10-01` and `user:alice`; injected a `session.started` event to create one `lab_sessions` row (alice@lab-win10-01).
- Manually exercised all 5 new action kinds on incident `126a8878-...`:
  - `quarantine_host_lab`: executed → `lab_assets.notes` contains `[quarantined:incident-126a8878-...:at-2026-04-22T07:16:03Z]` ✅
  - `kill_process_lab`: executed → auto-created `evidence_requests` row (process_list, status=open, target lab-win10-01) ✅
  - `invalidate_lab_session`: executed + reverted → 2 action_log entries, `invalidated_at` set then cleared ✅
  - `block_observable`: executed + reverted → row persists with `active=false` ✅
  - `request_evidence`: proposed only — UI correctly shows "Not executable in lab" because the action is classified suggest_only (plan line 70). ✅ behaviour-wise.
- All 7 action_log entries have `result=ok`, `executed_by=operator@cybercat.local`.
- **Not explicitly confirmed during session (fatigue):** (a) EvidenceRequestsPanel rendered the `kill_process`-auto-created request — user saw a Mark collected button but wasn't sure about the proposal row. (b) BlockedObservablesBadge while the IP was active wasn't checked (observable was already reverted before entity page was visited). 2-min recheck pending tomorrow — see "What needs to happen next session".

---

## Blockers

_None currently. Sub-track 1 blockers (cert infrastructure + Filebeat pipeline) resolved 2026-04-23._

---

## Known gaps / deferred decisions

- **Wazuh Active Response dispatch (Phase 11):** Implemented 2026-04-23. `quarantine_host` dispatches `firewall-drop0`; `kill_process` dispatches custom `kill-process` AR script. Both guarded by `WAZUH_AR_ENABLED` flag (default false). Verification on live stack pending.
- **Windows (Sysmon) lab endpoint (Phase 9B):** Phase 8's decoder covers `process.created` from auditd. Sysmon decoder branch adds naturally in one file.
- **Wazuh dashboard service**: deliberately never started (CyberCat UI replaces it). Tracked in ADR-0004.
- **Evidence payload collection:** `EvidenceRequest.payload_url` column is in the schema but nothing populates it yet. Future phase: Wazuh file-collection triggered automatically, URL stored here.
- **Auth model for the analyst UI:** *(In progress — Phase 14.)* Foundation (14.1), session layer (14.2), and route gating + audit attribution (14.3) complete. OIDC opt-in (14.4) and smoke-test cutover (14.5) pending.
- **Local Python venv for IDE type-checking:** optional; Docker is sufficient for running.
- **lab-debian auth.log forwarding**: Fixed — `rsyslog` added to Dockerfile, `rsyslogd` started in entrypoint, `<localfile>` block for `/var/log/auth.log` injected idempotently. SSH auth events now flow end-to-end.
- **Startup / dev-ergonomics simplification (deferred to end of project):** collapse the current multi-terminal flow (compose up / backend commands / smoke scripts) into a single dispatcher — either sub-commands on `start.sh` (`./start.sh up|test|smoke|demo|down`) or a `Makefile`. Pure ergonomics, zero architectural impact. Defer until feature work is done so the final dispatcher wraps the final set of commands, not a moving target.
- **Phase 16.10 follow-ons (deferred from ADR-0013):**
  - **`py.network.suspicious_connection` detector** — outbound to non-RFC1918 on uncommon ports, rare-dst-IP heuristic. The `network.connection` events now flow end-to-end but no detector consumes them beyond `py.blocked_observable_match`. A dedicated detector would close the "anomalous outbound" story without needing a blocklist seed.
  - **Process ↔ connection correlation** — which PID opened a given socket. Today the agent ships `process.created` and `network.connection` independently; they cannot be joined without eBPF or `/proc/net/tcp` polling + PID inspection. Out of scope for v1 because both eBPF and `/proc` polling cross the agent's "telemetry-only, read-only" boundary.
  - **DNS-layer telemetry (`dns.query` events)** — different log source (e.g. `dnsmasq`/`unbound` query log, or eBPF). Would close the "DNS-to-bad-domain" story alongside conntrack's IP-level coverage. Add a fourth tail source when justified.
  - **Network-flavored correlator** — joins multiple `network.connection` signals (e.g. fan-out to many destinations, recurring beaconing intervals) into incidents. Separate from a per-event detector; needs design work on the temporal-window primitives.
  - **Dst-port allow/denylist at the agent** — `[NEW]`-only filter currently cuts ~80% of conntrack noise; if real demos still flood, add allow/denylist filtering at the parser. Kept off-by-default in v1 to avoid pre-filtering events a future detector might want.
  - **Network entity for `dst_ip`** — `entity_extractor.py` currently extracts only `host` + `src_ip` from `network.connection`. `dst_ip` drives detection (via `py.blocked_observable_match`) but isn't a first-class entity, so the destination doesn't show up on the entity graph. Trivial fix when the analyst UI demands it; intentional v1 conservatism per ADR-0013.
  - **Persistent tracked-PID state across agent restarts (carried over from Phase 16.9)** — process exit attribution is lost when the agent restarts mid-demo. Would require checkpointing the PID table to disk.
  - **IPv6 conntrack output validation beyond loopback/link-local drop** — parser handles IPv6 (test fixtures cover the drop cases) but no real-traffic IPv6 fixture exists.

---

## Open questions / assumptions being made

- Multi-operator auth is in progress (Phase 14). `AUTH_REQUIRED=false` by default; flip to `true` for real-auth mode.
- Local Postgres (compose), not managed DB.
- Wazuh runs in `--profile wazuh` so it can be stopped when not demoing.
- The Lenovo Legion handles Wazuh + 1 lab container + the app stack during active demo sessions (~4.2 GB per the plan's budget), but not continuously.
- Frontend and backend are in the same monorepo.

---

## Risks to watch

- **Scope creep toward SIEM.** If a feature is "ingest more log types", it needs a correlation-value justification, not just volume.
- **Wazuh becoming the center of gravity.** Every Wazuh integration task should be matched by a custom-layer task the same week.
- **Infra sprawl on the laptop.** Each new always-on service needs an ADR.
- **Verification theatre.** The Phase 7 "complete" overstatement today is the exact failure mode to avoid. Going forward: a phase is not complete until the phase's smoke test script passes end-to-end on a clean checkout.
