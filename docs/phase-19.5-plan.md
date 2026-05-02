# Phase 19.5 — Chaos Testing Plan

## Context

Phase 19 (hardening + CI/CD + detection-as-code) shipped at tag `v0.9` on 2026-05-02 with 8 of 9 verification items closed. **Item #2 (live Redis chaos verification on Linux) was deferred to this phase**, with the workflow file `.github/workflows/chaos-redis.yml` shipping as the regression gate. Phase 19.5 is the dedicated half-phase that takes that gate from "scaffolded" to "green," extends it to five more failure modes, and gives Phase 20 (heavy-hitter scenarios) a reliability floor.

The roadmap entry (`docs/roadmap-discussion-2026-04-30.md` lines 550–565) listed six scenarios; effort estimate ~3–5 days; done-criteria "all six pass on a clean stack." Two scenarios already have partial scaffolding (Redis kill, Postgres restart) from Phase 19. The other four are greenfield.

This plan models on `docs/phase-19-plan.md`'s structure — terse, code-cited, per-workstream Files/Acceptance/Test sub-headers; the only table is Risks. Scenarios are numbered A1–A6 inside Workstream A; orchestrator + shared eval helper are Workstream B.

## Calibration vs the roadmap

Two recipe revisions. Both forced by GitHub Actions sandbox constraints; both keep the *intent* of the original scenarios.

- **Scenario A3 (network partition):** roadmap calls for `iptables` to drop port 8000 from `cct-agent`. `iptables` requires `CAP_NET_ADMIN` which `ubuntu-latest` runners don't grant. **Substitute `docker network disconnect <net> compose-cct-agent-1` for the partition window**; functionally equivalent at the container level (TCP connection hangs cleanly, agent's HTTP client times out, retries fire as designed). Confirmed against `agent/cct_agent/shipper.py`.
- **Scenario A6 (slow disk → slow Postgres network):** roadmap calls for "200ms latency on Postgres volume via `tc`," but `tc` is network-only and disk-latency injection (`dm-delay`, blkdebug) needs `CAP_SYS_ADMIN` (also unavailable on GH Actions). **Redefine as 200ms network latency between backend and Postgres** via `tc qdisc add dev eth0 root netem delay 200ms` inside the Postgres container. Tests the more realistic failure mode anyway — CyberCat doesn't run Postgres on a slow shared filesystem; the realistic "slow Postgres" failure mode is a slow connection.

## Workstream A — Six chaos scenarios

Every scenario script lives under `labs/chaos/scenarios/<name>.sh`, sources the shared eval helper from `labs/chaos/lib/evaluate.sh`, and prints a final `PASS:` or `FAIL:` line with a structured reason. Each script also has a thin `.github/workflows/chaos-<name>.yml` that wraps `bash start.sh` + the script + a teardown step.

The four §A1 acceptance counters (sim_tracebacks, backend_tracebacks, event_count_5min, degraded_warnings) are the consistent shape across all six scenarios. Counters #1, #2, #3 apply to every scenario; counter #4 (degraded_warnings) is scenario-specific and named per scenario (`A1`: redis_degraded; `A2`: postgres-disconnect retry; `A3`: agent ship-failed; `A4`: cursor advance; `A5`: incident-dedupe-on-restart; `A6`: postgres-slow query log).

### A1 — Kill Redis (already shipped)

**Files:** `.github/workflows/chaos-redis.yml` already exists (commit `8a37227`). Promote its inline eval block into `labs/chaos/scenarios/kill_redis.sh` so the orchestrator can run it locally. The workflow keeps its current shape; the script becomes the single source of truth for the eval logic.

**Mechanism:** `docker compose kill redis` at t=4s, `docker compose up -d redis` at t=29s.

**Acceptance:** `sim_tracebacks=0`, `backend_tracebacks=0`, `event_count_5min>0`, `degraded_warnings>0` (matches `redis_degraded|redis_state=unavailable|degraded mode|EventBus consumer crashed`).

**Reused from Phase 19:** `safe_redis()` (`backend/app/db/redis_state.py`), `EventBus._supervisor()` (`backend/app/streaming/bus.py:97-123`), `redis_degraded` log emitter (`backend/app/db/redis_state.py:61`).

### A2 — Restart Postgres

**Files:** `labs/chaos/scenarios/restart_postgres.sh` (port from `labs/perf/run_postgres_restart_test.sh` + add the four-counter eval block); `.github/workflows/chaos-postgres.yml`.

**Mechanism:** start `load_harness.py --rate 100 --duration 30`; at t=10s, `docker compose restart postgres`. Wait for completion.

**Acceptance:** ≥95% acceptance rate (operator already verified 99.2% on 2026-05-01 via the perf script); `transport_errors=0`; recovery within 30s; **no orphan rows** — `SELECT id FROM incidents WHERE id NOT IN (SELECT incident_id FROM incident_events)` returns 0.

**Reused from Phase 19:** `with_ingest_retry()` (`backend/app/ingest/retry.py`); explicit pool config `pool_size=20, max_overflow=10, pool_recycle=1800, pool_timeout=10, pool_pre_ping=True` (`backend/app/db/session.py`).

### A3 — Network-partition agent → backend

**Files:** `labs/chaos/scenarios/partition_agent.sh`; `.github/workflows/chaos-partition.yml`.

**Mechanism:** start simulator running scenario events through cct-agent; at t=4s, `docker network disconnect compose_default compose-cct-agent-1` (or whichever bridge name the project uses — script auto-detects via `docker compose ls`). Hold for 60s. `docker network connect ...` to heal.

**Acceptance:**
- Agent does NOT crash (process still running after partition lift; no traceback in agent logs).
- Agent's bounded retry queue (5 retries × exponential backoff capped ~61s, per `agent/cct_agent/shipper.py:178`) replays buffered events post-heal.
- **≥80%** of partition-window events arrive in `events` table after heal — NOT 100%, since shipper documents drop-oldest on queue overflow + drop-on-max-retries. The plan acknowledges this; ≥80% is the floor.
- Backend has no traceback during partition.
- `degraded_warnings`: count of `agent ship failed` log lines > 0 (proves the chaos actually fired).

**Reused from Phase 19:** None directly; this exercises the agent's pre-existing shipper resilience (Phase 16 work).

### A4 — SIGSTOP agent for 30s

**Files:** `labs/chaos/scenarios/pause_agent.sh`; `.github/workflows/chaos-pause.yml`.

**Mechanism:** start lab-debian generating sshd events at a steady rate (replay-style harness — events into `/var/log/auth.log` inside lab-debian, e.g. via `printf` redirected). At t=4s, `docker compose pause cct-agent`. Sleep 30s. `docker compose unpause cct-agent`.

**Acceptance:**
- Read all three checkpoint files inside the agent container (`/var/lib/cct-agent/checkpoint.json`, `audit-checkpoint.json`, `conntrack-checkpoint.json`) before pause and after unpause + 10s settle. Assert each `offset` field is **strictly greater** post-unpause than pre-pause.
- Events generated during the 30s pause window are present in `events` table (proves the agent re-tailed from cursor, not from current EOF) — verified by counting events with `occurred_at` inside the pause window.
- `degraded_warnings`: count of "checkpoint advance" / "tail resumed" log lines > 0.
- Zero duplicate events (assert COUNT vs DISTINCT on `dedupe_key` for the pause window).

**Reused from Phase 16/16.9/16.10:** atomic checkpoint write via tempfile + `os.replace` (`agent/cct_agent/checkpoint.py:49-72`); `tail_lines()` resume-from-offset behavior (`agent/cct_agent/tail.py:40-111`); `dedupe_key`-based idempotent ingest at `POST /v1/events/raw`.

### A5 — OOM-kill backend mid-correlation

**Files:** `labs/chaos/scenarios/oom_backend.sh`; `.github/workflows/chaos-oom-backend.yml`.

**Mechanism:** start `python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --no-verify` in background. At t=10s (mid-scenario, after stage-2 success but before stage-5 C2 beacon), `docker compose kill -s SIGKILL backend`. Wait 5s. `docker compose up -d backend`. Wait for backend `/healthz` to return 200. Continue waiting until simulator finishes.

**Acceptance:**
- After backend recovers, count incidents with `kind='identity_compromise'` AND `kind='identity_endpoint_chain'` for `primary_user='alice'` — each must be ≥1 AND ≤1 (no duplicate, no missing).
- The dedupe_key `identity_compromise:alice:<hour_bucket>` lookup must succeed exactly once per scenario run.
- No orphan rows: same SQL as A2.
- `backend_tracebacks=0` after recovery (during the kill window itself, the kill IS a traceback-style termination, but the freshly-started backend should produce zero tracebacks in *its* logs).
- `degraded_warnings`: count of "incident dedupe hit on restart" log line > 0 (proves the dedupe path actually fired — if it's 0, we got lucky and the chaos didn't actually overlap a correlation window; re-run with adjusted timing).

**Reused from Phase 4–6:** correlator dedupe key construction (`backend/app/correlation/rules/identity_compromise.py:55`); `SELECT incident WHERE dedupe_key=...` lookup (`backend/app/correlation/rules/identity_compromise.py:57-62`). Phase 19's `with_ingest_retry()` covers the ingest path during the brief Postgres-pool-warmup window after backend restart.

### A6 — Slow Postgres network (redefined from "slow disk")

**Files:** `labs/chaos/scenarios/slow_postgres.sh`; `.github/workflows/chaos-slow-postgres.yml`.

**Mechanism:** install `iproute2` inside Postgres container if not already present (one-time `apt install` with `--no-install-recommends`; cache in image if reused often). Run `docker compose exec -T postgres tc qdisc add dev eth0 root netem delay 200ms`. Run `python labs/perf/load_harness.py --rate 50 --duration 30` (lower rate than A2 because every query now adds 200ms; 50/s is sustainable headroom). Cleanup: `docker compose exec -T postgres tc qdisc del dev eth0 root`.

**Acceptance:**
- `p99` detection latency < 5s (per roadmap; latency-bounded chaos test).
- `achieved_rate` ≥ 90% of target (i.e. ≥45/s sustained out of 50/s requested).
- `transport_errors=0`.
- `failed_5xx=0`.
- `backend_tracebacks=0` and `sim_tracebacks=0`.
- `degraded_warnings`: count of slow-query log lines (`statement_timeout` warnings, or rows from `pg_stat_statements` with mean_exec_time > 100ms) > 0.

**Reused from Phase 19:** `load_harness.py` acceptance summary block (`labs/perf/load_harness.py:166-183`), pool config (above).

## Workstream B — Orchestrator + shared eval helper

### B1 — Shared evaluation helper

**File:** `labs/chaos/lib/evaluate.sh`.

**Functions exported via shell:**
- `count_traceback_lines <log_file>` — `grep -c "Traceback (most recent call last)"`, defaulting empty to 0.
- `count_postgres_events_5min` — `psql -t -A -c "SELECT count(*) FROM events WHERE occurred_at > now() - interval '5 minutes';"` against the `cybercat`/`cybercat` user/db inside the postgres container.
- `count_degraded_warnings <log_file> <pattern>` — `grep -cE "$pattern"` with default-zero handling.
- `print_acceptance_summary` — prints the four-counter block in the same format as `chaos-redis.yml` so output is consistent across scenarios.
- `cleanup_chaos_state` — defensive teardown: removes any leftover tc qdisc, reconnects networks, unpauses any paused container, restarts any stopped service. Called from a trap on EXIT in every scenario script.

### B2 — Orchestrator

**File:** `labs/chaos/run_chaos.sh`.

**Behavior:** assumes the operator already ran `bash start.sh` (does NOT bring up the stack itself; that's the operator's job — matches the convention of the head-start agent's `run_chaos_redis_local.sh`). Runs all six scenarios sequentially. Collects PASS/FAIL from each. Prints a final summary table (scenario name, result, duration, key counter values). Exits 0 only if all six green.

The orchestrator is the local equivalent of "trigger six workflow_dispatch jobs in CI." The CI workflows stay independently triggerable from the Actions tab.

### B3 — Existing chaos-redis.yml refactor (non-breaking)

`.github/workflows/chaos-redis.yml` already has its own evaluation block inline. Once `labs/chaos/lib/evaluate.sh` lands, the workflow can optionally be tightened to source the shared helper (saves ~30 lines), but this is a polish step — not required for done-criteria. Do this only if it reads cleaner; otherwise leave it alone.

## Out of scope

- New simulator scenarios (`lateral_movement_chain`, `crypto_mining_payload`, etc.) — Phase 20.
- Caldera / Atomic Red Team integration — Phase 21.
- Multi-worker uvicorn — Phase 21 (the §A6 1000/s ceiling is architectural, not a chaos finding).
- Real disk-latency injection (`dm-delay`, blkdebug) — defer until/unless the operator has a privileged Linux box outside GH Actions.
- LotL detection (Phase 22), UEBA-lite baselining (Phase 23).
- Production-grade chaos infra (Chaos Mesh, Litmus, Gremlin, Pumba) — overkill for laptop-scale lab.

## Verification plan

End-to-end sequence to declare Phase 19.5 done:

1. **Each scenario runs locally, individually**, on the operator's Windows + Docker Desktop + WSL2 stack. Expected: each script prints `PASS: ...` and exits 0. (Note: scenario A3's `docker network disconnect` works on Docker Desktop; A4's `docker compose pause` works on Docker Desktop; A6's `tc` runs inside the container so doesn't depend on host `iproute2`.)
2. **Each `chaos-<name>.yml` workflow runs on `ubuntu-latest`**, triggered manually from the Actions tab. Expected: green check + four-counter summary visible inline in the step log (matches the chaos-redis pattern).
3. **`bash labs/chaos/run_chaos.sh` runs all six locally** in one command after `bash start.sh`. Expected: green summary table at the end.
4. **Regression-injection sanity check** — temporarily remove the `safe_redis(...)` decorator from one detector, re-run scenario A1. Expected: A1 fails red with `degraded_warnings=0` (proves the harness actually catches missing-resilience regressions; if A1 still passes after the regression, the harness isn't strict enough).
5. **CI nightly** — wire the six chaos workflows into a daily 06:00 UTC cron (or weekly, operator's call) so chaos becomes a continuous regression gate, not a one-off ceremony.

## Risks + mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scenario A3 (partition) silently loses more events than expected because `agent/cct_agent/shipper.py` queue overflow drops oldest. | Phase 19.5 fails done-criteria with no clean fix path. | Set acceptance bar at ≥80%, not 100%. Document the shipper's `queue_max` + drop-oldest behavior in the scenario script header. If the partition window stretches past the 5-retry cap (~61s), reduce window to 45s. If still <80%, file as a Phase 19.5 finding for shipper hardening (could land an on-disk spool but that's likely Phase 20+ scope). |
| Scenario A5 (OOM) fails because correlator state turns out to leak between events via in-memory caching that wasn't visible in the engine code. | Phase 19.5 done-criteria slips. | Phase 1 exploration confirmed `correlation/engine.py` is stateless and `identity_compromise.py` queries Postgres for state. If a hidden cache turns up, add a Postgres-backed dedupe guard or drop the in-memory cache before declaring done. Worst case: ADR for a correlator state model that survives crashes. |
| Scenario A6 fails because pool-acquisition under sustained 200ms latency burns through `pool_size + max_overflow = 30` connections. | Backend hits `pool_timeout=10s` → 5xx. | Either tighten the harness rate (e.g., 30/s instead of 50/s) or document the new ceiling in the perf-baselines doc. The 50→30 reduction is acceptable; this is a chaos test, not a perf bench. |
| GH Actions runner heterogeneity flakes one of the six. | False-red CI gate; operator loses trust. | Run each workflow 3 consecutive times on first pass before declaring it green. If any flake, investigate (likely candidates: timing windows in A3 / A5 too tight, `start.sh` token bootstrap race). Tighten timing or add retries before claiming the scenario stable. |
| Reused chaos-redis.yml + new chaos-*.yml workflows quintuple GH Actions minutes consumed. | Bill anxiety. | Workflows are `workflow_dispatch` only by default — manual trigger, no automatic minutes. The optional cron from §"Verification plan #5" is a cost trade-off the operator opts into separately. |

## Done-criteria

All six chaos scenarios pass on a clean stack — measured both as **6/6 individual `chaos-*.yml` workflow_dispatch runs green on `ubuntu-latest`** AND **6/6 in `labs/chaos/run_chaos.sh` locally**. Plus the regression-injection sanity check (verification step 4) confirms the harness fails red when a Phase-19 resilience primitive is removed.

After done-criteria is hit, tag `v0.95` against the merge commit (optional — operator's call; could also fold into Phase 20's `v1.0` tag).

## What this unblocks

- **Phase 20 (heavy-hitter scenarios + UX drills):** chaos provides the reliability floor that scenarios run on top of. New simulator scenarios (`lateral_movement_chain`, `crypto_mining_payload`, etc.) can assume Redis blips and Postgres restarts won't break the run.
- **Phase 21 (Caldera + coverage scorecard):** Caldera operations implicitly create network turbulence and process churn. Phase 19.5's chaos tests are the regression gate that proves the stack survives that kind of disruption automatically.
- **Continuous regression coverage:** every Phase-19 resilience primitive (`safe_redis`, `with_ingest_retry`, `EventBus._supervisor`, the agent's shipper retry, the correlator's dedupe key) gets a chaos test that fails red if the primitive is later removed or weakened. Pure Phase-19 win, made durable.

## Files to be created (summary)

**Greenfield directory + scripts:**
- `labs/chaos/run_chaos.sh` — orchestrator
- `labs/chaos/lib/evaluate.sh` — shared four-counter eval helper
- `labs/chaos/scenarios/kill_redis.sh` — A1 (port from chaos-redis.yml inline block)
- `labs/chaos/scenarios/restart_postgres.sh` — A2 (port from `labs/perf/run_postgres_restart_test.sh`)
- `labs/chaos/scenarios/partition_agent.sh` — A3 (greenfield)
- `labs/chaos/scenarios/pause_agent.sh` — A4 (greenfield)
- `labs/chaos/scenarios/oom_backend.sh` — A5 (greenfield)
- `labs/chaos/scenarios/slow_postgres.sh` — A6 (greenfield, redefined from disk-latency)

**New CI workflows:**
- `.github/workflows/chaos-postgres.yml`
- `.github/workflows/chaos-partition.yml`
- `.github/workflows/chaos-pause.yml`
- `.github/workflows/chaos-oom-backend.yml`
- `.github/workflows/chaos-slow-postgres.yml`

**Existing (no change required for done-criteria):**
- `.github/workflows/chaos-redis.yml` (Phase 19 deliverable; optional refactor to source `evaluate.sh` after B1 lands)

**Doc updates after implementation lands:**
- `PROJECT_STATE.md` — Phase 19.5 entry: pending → in-progress → ✅ shipped
- `docs/runbook.md` — § "CI / chaos workflows" expanded with the six new workflows
- New file: `docs/phase-19.5-summary.md` — plain-language summary modeled on `docs/phase-19-summary.md`
- `CyberCat-Explained.md` §15 — bullet 24 added for Phase 19.5
- (conditional) `docs/decisions/ADR-NNNN-chaos-harness-shape.md` if any architectural choice surfaces during implementation that warrants durable record (e.g. Postgres-backed correlator dedupe, on-disk shipper spool)

**Estimated effort:** ~3–5 days of focused work per the roadmap. Scenarios A1+A2 are mostly port-the-existing-thing; A4+A5 are easy per the technical-viability investigation; A3 needs careful tuning of the partition window vs the shipper's 5-retry cap; A6 needs a one-time apt install inside the postgres container (or could ship via a small Dockerfile delta on the postgres service).
