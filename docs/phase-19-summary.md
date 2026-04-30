# Phase 19 — Plain-language summary

If you're coming back to the project and feel a little lost, read this. It answers four questions in plain terms:

1. What did Phase 19 actually do?
2. Did the core architecture change?
3. What's new in the tree vs what was just modified?
4. Where are we now and what's the next concrete step?

For the precise plan, the engineering rationale, and the heavy-hitting verification trail, the canonical sources are still `docs/phase-19-plan.md` (what we said we'd do) and `docs/phase-19-handoff.md` (what we found while doing it). This file is the human-readable map.

---

## 1. What Phase 19 actually did

Phase 19 is **not a feature phase**. It doesn't add a new detector, a new event source, a new UI page, or a new workflow stage. The product surface a user sees in the browser after Phase 19 is the same as the product surface they saw after Phase 18 (the plain-language rewrite + kill-chain/timeline redesign).

What Phase 19 did is **make the existing thing more trustworthy**, in four lanes:

| Lane | Plain-English | Where it shows up in code |
|---|---|---|
| **Resilience** | Kill Redis or restart Postgres mid-run, the backend doesn't crash and doesn't lose events. Detectors that *want* Redis skip cleanly when Redis is down instead of throwing. The streaming consumer reconnects on its own after a Redis blip. The Wazuh poller backs off gracefully when transient errors stack up. | `backend/app/db/redis_state.py` (new), `backend/app/db/redis.py`, `backend/app/db/session.py`, `backend/app/streaming/bus.py`, `backend/app/streaming/publisher.py`, `backend/app/correlation/rules/endpoint_compromise_standalone.py`, the four files under `backend/app/detection/rules/`, `backend/app/ingest/wazuh_poller.py`, `backend/app/ingest/retry.py` (new) |
| **Validation + perf** | Hot routes (`GET /v1/incidents`, `GET /v1/detections`) used to fire 200+ database queries per page load. Now ≤ 12 and ≤ 10 respectively. Event ingest now rejects oversized payloads, far-past/far-future timestamps, and weird dedupe keys at the API boundary instead of letting them pollute the DB. | `backend/app/api/routers/incidents.py`, `routers/detections.py`, `app/api/schemas/events.py`, plus a load-testing harness at `labs/perf/load_harness.py` |
| **Continuous integration** | Every push to a branch now runs lint + tests on backend, agent, and frontend. Every push to `main` runs the smoke chain (full stack, all six default-profile smoke scripts) end-to-end. We can't accidentally merge a regression any more — the gate is automatic. | `.github/workflows/ci.yml` (new), `.github/workflows/smoke.yml` (new) |
| **Detection-as-code** | Every detector now has a curated input fixture asserting it still fires (or cleanly skips) on known-good and known-bad sample events. Adding a detector requires adding a fixture; adding a fixture is the cheap way to lock in current behavior so it can't silently regress. | `labs/fixtures/` (new tree: `manifest.yaml`, `replay.py`, JSONL files for auth/process/network), `backend/tests/integration/test_detection_fixtures.py` (new) |

That's the whole story. **No layer was added, no service was swapped, no schema was rewritten.** The custom-built / integrated split (per `CLAUDE.md` §6) is exactly what it was — Wazuh is still optional telemetry, the cct-agent is still the default, the canonical event/incident model is unchanged.

> **One honest caveat:** the four lanes above describe what Phase 19 *coded*. Several of those bullets were **never live-verified to the bar the plan committed to** during the merge cycle — Redis kill on Linux, live Postgres restart re-verification, load harness at 1000/s. The code is in `main`, but the acceptance bars from `docs/phase-19-plan.md` § "Verification plan" still have open items. See § 4 below for the seven concrete steps to actually close the phase.

---

## 2. Did the core architecture change?

**No.** The architecture diagram from `docs/architecture.md` is still accurate. The seven layers from `CLAUDE.md` §2 still apply:

```
1. Telemetry intake          (Wazuh + cct-agent, both still supported)
2. Normalization             (raw events → canonical event/entity model)
3. Detection interpretation  (Sigma + custom detectors)
4. Correlation               (signals → incidents)
5. Incident state + evidence (Postgres-owned truth)
6. Response policy + actions (guarded, auditable, lab-scoped)
7. Analyst frontend          (Next.js)
```

What Phase 19 did is **harden the boundaries between those layers without redrawing them**. The Redis safe-helper sits inside layer 3 (detection) and layer 4 (correlation) — it doesn't introduce a new "resilience layer". The Postgres pool config sits inside layer 5 (storage) — it doesn't introduce a new "persistence layer". The CI workflows live outside the runtime stack entirely.

If the runtime stack was a physical building, Phase 19 didn't add or remove a room — it reinforced load-bearing walls, added smoke detectors, and wrote the building inspection up as a checklist that runs every time someone modifies the blueprints.

---

## 3. What's new in the tree vs what was just modified?

For the exact line-item list, see the "Files added" + "Files modified" sections in `PROJECT_STATE.md`'s Phase 19 entry. Briefly:

**New top-level surfaces** (these are things that did not exist before Phase 19):
- `.github/workflows/` — the CI + Smoke GitHub Actions workflows.
- `README.md` — a small project intro with CI badges. (The repo had no top-level README before; the substantive narrative still lives in `Project Brief.md`, `CyberCat-Explained.md`, and `docs/`.)
- `backend/app/db/redis_state.py` — `safe_redis(...)` helper + circuit breaker.
- `backend/app/ingest/retry.py` — `with_ingest_retry()` decorator.
- `labs/fixtures/` — detection-as-code fixtures (manifest, replay tool, JSONL events).
- `labs/perf/load_harness.py` — repeatable load harness.
- `docs/phase-19-plan.md`, `docs/phase-19-handoff.md`, this file (`docs/phase-19-summary.md`), `docs/perf-baselines/2026-04-30-phase19-pre-perf.md`, `docs/roadmap-discussion-2026-04-30.md` — Phase 19 documentation set.
- A handful of new test modules under `backend/tests/` covering the resilience surfaces, the N+1 query budgets, the negative validation cases, and the detection fixtures.

**Modified surfaces** (these existed before; Phase 19 changed *how* they behave, not *what* they are):
- The four detector rules under `backend/app/detection/rules/`. Same input → same output → same incident outcomes. The only difference is they no longer crash when Redis is unavailable.
- `backend/app/streaming/bus.py` and `streaming/publisher.py`. SSE consumers behave the same; they just survive Redis blips now.
- `backend/app/api/routers/{incidents, detections, events}.py`. Same response shapes. Faster page loads (A7) and a single-retry safety net on `POST /v1/events/raw` (A3.1).
- `backend/app/api/schemas/events.py`. Same fields. Adds rejection for oversized payloads, bad timestamps, and weird dedupe keys.
- `backend/app/db/{redis, session}.py`. Same connection handles. Explicit pool config and `RedisUnavailable` instead of `assert`.
- `backend/app/ingest/wazuh_poller.py`. Same polling loop. Now circuit-breaks on consecutive failures.
- `backend/app/main.py`. Same lifespan shape. Bumps asyncio's default thread executor to 64 workers (DNS lookups during outages were starving the request loop).
- `agent/cct_agent/*` — purely stylistic ruff auto-fixes (`datetime.UTC`, `TimeoutError`, future-style annotations). Behavior is identical.
- `infra/compose/docker-compose.yml` — bind-mounts `labs/` into the backend container at `/app/labs:ro` so `test_detection_fixtures.py` can resolve the manifest.
- Both `pyproject.toml` files — added ruff/mypy/pytest-randomly dev deps + tool config.

**Touched-but-not-functionally-changed:**
- `labs/smoke_test_phase17.sh` was promoted from untracked to tracked, with a stale schema reference fixed.
- A few test-suite files got the new `count_queries` fixture or had hard-coded timestamps switched to relative ones so they don't go stale.

If you `git log --stat` the Phase 19 commit (`f68232d`), about half the diff is documentation and half is code. The code half is heavily weighted toward tests and the resilience helpers; the four detector files only got "wrap this Redis call in `safe_redis(...)`" three-line edits.

---

## 4. Where are we now and what's the next step?

**Status (honest revision):** Phase 19 is **code-shipped to `main`, acceptance pending.** Backend, agent, and frontend CI all gate every push. The smoke chain runs on push-to-main and ran clean on the PR-trigger validation. The smoke fix that closes the structural bug from the original Phase 19 ship is sitting open as PR #6, all checks green, ready to merge.

**But Phase 19 is not formally complete by its own done-criteria.** The plan at `docs/phase-19-plan.md` line 351 + §"Verification plan" (lines 319–331) call for live acceptance on three items that were never closed during the merge cycle:

- **Plan §A1 acceptance (line 67):** `docker compose kill redis` mid-`credential_theft_chain --speed 0.1` — must pass with no traceback. Failed on Windows/WSL2; never re-run on Linux.
- **Plan §A3 + Gap 2 (line 405):** live `100/s × 30s` against `/v1/events/raw` with `restart postgres` at t=10s — must hit ≥ 95% acceptance + 30s recovery. Unit test for the fix passes; the live retest was never re-run.
- **Plan §A6 (line 125):** load harness at **1000/s × 60s** — must hit 0% drops + p95 < 500ms + peak Postgres conns < 25. The heavy-hitting trail only ran 100/s.

Plus one numerical delta: §A7 targeted ≤ 4 queries on a 50-item page; we shipped at ≤ 12 / ≤ 10 (still a 95%+ reduction from the 250+ baseline, but not the planned floor). And the `v0.9` tag is not cut.

**Next concrete steps — pick up here in this order:**

1. Merge PR #6 (`fix/smoke-workflow-agent-profile`) → `main`. URL: https://github.com/OzielSauceda/CyberCat/pull/6
2. After merge, the Smoke workflow fires on `main`. Watch it. Expect green. If it fails, the per-script `::error::` annotations (visible in the public check-runs annotations API even without auth) and the `smoke-logs` artifact will tell you which script and why.
3. **Re-run Redis kill-test on Linux.** Reproduction recipe in `docs/phase-19-handoff.md` § "How to verify the fixes worked" (Test 3). Easiest paths: an Ubuntu Docker container, or a temporary `workflow_dispatch` GH Actions workflow against a Linux runner. If it passes, the §A1 acceptance bar is met. If it fails on Linux too, the deferred work in the handoff's "A1.1 residual gap" needs to land first.
4. **Re-run live Postgres restart-test.** Recipe in the same handoff section (Test 4). Pass: ≥ 95% accepted, recovery within 30s, transport_errors well below 1992 (the pre-fix number).
5. **Run load harness at 1000/s.** `python labs/perf/load_harness.py --rate 1000 --duration 60`. Pass: 0% drops, p95 < 500ms, peak Postgres conns < 25.
6. **Reconcile hot-route ≤ 4 vs achieved ≤ 12.** Either tighten the routes further (one CTE per route should get to ≤ 4) or write a one-line amendment to the plan justifying the ≤ 12 / ≤ 10 floor and update the done-criteria text. Either is defensible; both close the gap honestly.
7. **Tag `v0.9`** against the merge commit — only after 1–6 above.

The single source of truth for this list is the top-of-file header in `PROJECT_STATE.md` ("What's pending — pick up here in this order"). This file and `docs/phase-19-handoff.md` § "Remaining work" mirror it verbatim.

**Beyond v0.9:** Phase 19.5 (chaos testing) is the next phase per the roadmap — it systematizes the kind of failure injection we did manually here. After that, Phase 20 layers in heavy-hitter choreographed scenarios. See `PROJECT_STATE.md` § "Future / optional phases" for the full roadmap and `docs/roadmap-discussion-2026-04-30.md` for the long-form discussion.

---

## Reading order if you have 10 minutes

1. **This file** — the map.
2. **`PROJECT_STATE.md` § "Phase 19" entry** — line-item list of what's in the tree.
3. **`docs/phase-19-handoff.md`** — full diagnostic context, including the residual gap. The TL;DR + STATUS sections at the top are enough.

If you have an extra 30 minutes and want to understand the engineering rationale behind each workstream (A1–A7, B, C, D), `docs/phase-19-plan.md` is the canonical "why we made the choices we made" doc.
