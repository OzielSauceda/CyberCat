# Phase 19.5 — Plain-language summary

If you're coming back to the project and want to know what Phase 19.5 actually did, read this. The canonical engineering doc is `docs/phase-19.5-plan.md`; this is the "what landed and how to read it" map.

## 1. What Phase 19.5 actually does

Phase 19.5 is the **integration-level regression gate** for Phase 19's resilience primitives. Phase 19 wrote the code that makes the stack survive Redis blips, Postgres restarts, and similar disruptions — `safe_redis`, `with_ingest_retry`, `EventBus._supervisor`, the agent's shipper retry, the correlator's dedupe key, the explicit Postgres pool config. Phase 19.5 builds the **chaos test harness** that verifies those primitives still hold under live failure injection, and would catch the day a future commit weakens any of them.

It does not add a new product feature. The architecture diagram from `docs/architecture.md` is unchanged. It adds:

- A new directory `labs/chaos/` with six scenario scripts + a shared four-counter eval helper + an orchestrator.
- Six new `workflow_dispatch` GitHub Actions workflows under `.github/workflows/chaos-*.yml`, one per scenario.
- A few documentation updates (this file, runbook, PROJECT_STATE).

## 2. The six scenarios

Each scenario fires one specific disruption and asserts the system degrades gracefully. The shape is consistent: four §A1 counters (sim tracebacks, backend tracebacks, events landed in last 5 min, degraded-mode warnings) plus scenario-specific extras.

| # | Scenario | Disruption | Tests this Phase-19 primitive |
|---|---|---|---|
| A1 | Kill Redis | `docker compose kill redis` for ~25s mid-scenario | `safe_redis()` circuit breaker + `EventBus._supervisor()` reconnect loop |
| A2 | Restart Postgres | `docker compose restart postgres` mid-load at 100/s | `with_ingest_retry()` decorator + explicit pool config (`pool_pre_ping=True`) |
| A3 | Network-partition agent | `docker network disconnect cct-agent` for 60s | Agent shipper's bounded retry queue + drop-oldest overflow policy |
| A4 | SIGSTOP agent | `docker compose pause cct-agent` for 30s | Agent's atomic checkpoint + `tail.py` resume-from-offset behavior |
| A5 | OOM-kill backend | `docker compose kill -s SIGKILL backend` mid-correlation | Correlator's deterministic dedupe key (`identity_compromise:{user}:{hour}`) — prevents double-correlation on restart |
| A6 | Slow Postgres network | `tc netem 200ms` on postgres `eth0` for 30s | Explicit pool config (`pool_size=20, max_overflow=10, pool_timeout=10`) + the load harness's 90%-of-target rate floor |

For each scenario the script lives at `labs/chaos/scenarios/<name>.sh`, the matching CI workflow at `.github/workflows/chaos-<name>.yml`, and the orchestrator `labs/chaos/run_chaos.sh` runs all six locally in sequence.

## 3. Two recipe revisions vs the original roadmap

The roadmap entry (`docs/roadmap-discussion-2026-04-30.md` lines 550–565) listed `iptables` for scenario A3 and `tc` against the Postgres volume for A6. Both got re-cut during the Phase 19.5 plan because of GitHub Actions runner sandbox limits:

- **A3:** `iptables` requires `CAP_NET_ADMIN`, unavailable on `ubuntu-latest`. **Substituted `docker network disconnect`** — functionally equivalent at the container level (the agent's HTTP client gets connection-refused/hangs, its bounded retry fires, the partition heals when we reconnect).
- **A6:** `tc` is for network packets, not disk I/O. Real disk-latency injection (`dm-delay`, blkdebug) needs `CAP_SYS_ADMIN`, also unavailable. **Redefined as 200ms network latency between backend and Postgres** via `tc netem` injected by a `nicolaka/netshoot` sidecar (`--net container:<postgres>` + `--cap-add NET_ADMIN` on the sidecar, NOT on postgres itself — keeps postgres's security posture untouched). Same observable failure mode (slow Postgres from backend's POV) without the sandbox limitation.

Both substitutions are technical wins in disguise — they avoid coupling the test to host capabilities while still exercising the same resilience primitive. Documented in `docs/phase-19.5-plan.md` § "Calibration".

## 4. The four §A1 counters — why they're consistent across scenarios

Every chaos scenario evaluates the same four counters before declaring pass/fail:

1. **`sim_tracebacks`** — count of `Traceback (most recent call last)` lines in the simulator/harness/emitter log. Must be `0`. If the test driver itself crashes, the chaos didn't actually fire on the system under test.
2. **`backend_tracebacks`** — same in the backend container's logs (last 250 lines). Must be `0`. The whole point of the resilience layer is to convert exceptions into degraded-mode behavior, not propagate them.
3. **`event_count_5min`** — count of rows in the `events` table from the last 5 minutes. Must be `> 0`. Proves the ingest path stayed alive through the chaos.
4. **`degraded_warnings`** — count of scenario-specific log lines that prove the resilience layer actually fired (e.g. `redis_degraded`, `with_ingest_retry`, `ship queue full`, `EventBus consumer crashed`). Must be `> 0`. If this is `0`, either the chaos got lucky timing and missed the right code path, or our pattern needs widening — both are signals to investigate, not pass.

Plus scenario-specific extras: A2 checks for orphan incidents and harness acceptance, A3 checks ≥80% of partition-window events landed, A4 checks the agent's sshd cursor offset strictly advanced, A5 checks exactly one of each incident kind exists for `alice`, A6 checks p99 < 5s and achieved_rate ≥ 90% of target.

The shared evaluation helper at `labs/chaos/lib/evaluate.sh` exports the four-counter functions so every script computes them the same way.

## 5. What's pending

> **Status update 2026-05-04: Phase 19.5 ✅ FULLY VERIFIED LOCALLY.** All six scenarios green + regression-injection sanity check passed both directions. Items previously listed as pending are now resolved (A1 ✅, regression check ✅) — see ✅ markers below. The CI per-workflow runs and `v0.95` tag remain optional, deferred to operator preference.

- **Live verification on operator's stack: ✅ DONE 2026-05-03 (A2-A6) + 2026-05-04 (A1).** All six scenarios verified locally on Windows + Docker Desktop + WSL2. The orchestrator (`labs/chaos/run_chaos.sh`) returned `OVERALL: PASS` on round 2 (round 1 caught one A4 integration regression — the agent's startup log lines roll out of the 250-line capture window after earlier scenarios run, so the degraded_warnings pattern matched 0 in sequential runs; fix in commit `7cb67ae` made the cursor-advance assertion the real proof and demoted degraded_warnings to informational). First-run findings produced eight concrete calibration improvements, all on `main` (commits `cc0e8bb` + `7cb67ae`):
  1. `lib/evaluate.sh`: `count_traceback_lines` and `count_degraded_warnings` were emitting `"00"` instead of `"0"` (the `|| echo 0` fallback fired on top of grep+tr's already-printed "0" because pipefail inherited from the caller). Fixed by capturing into a local first.
  2. `lib/evaluate.sh`: `cleanup_chaos_state` leaked "OCI runtime exec failed: tc" because postgres-alpine has no tc. Now redirects both stdout and stderr.
  3. A2 (`restart_postgres.sh`): was gating on the load_harness's `acceptance_passed` flag (perf criteria, p95<500ms) — that's wrong for a chaos test where elevated latency during the restart window IS the expected behavior. Replaced with plan §A2 chaos criteria: ≥95% accept, transport_errors < 10 (vs 1992 pre-fix), no orphans, plus a `chaos_proof` signal (failed_5xx > 0 OR p95 > 1s).
  4. A4 (`pause_agent.sh`): the `docker compose exec cct-agent cat /var/lib/...` call was getting path-mangled by Git Bash on Windows to `C:/Program Files/Git/var/lib/...`. Same workaround Phase 19's perf script uses: prepend `MSYS_NO_PATHCONV=1`.
  5. A4 + A3: emitter timestamp via `date '+%b %_d %H:%M:%S'` produces local-CDT time, but the agent's sshd parser stores `occurred_at` as UTC. Events looked 5 hours old and fell outside the 5-min counting window. Switched to `date -u`.
  6. A5 (`oom_backend.sh`): originally ran the simulator from the host, but operator's host has no httpx (Python 3.13 without httpx installed; smoke workflow installs it via `pip` in CI but locally there's none). Switched to `docker cp labs/` into cct-agent + `docker exec` from there — matches the 2026-05-01 chaos pattern in `docs/phase-19-handoff.md` "Test 3".
  7. A6 (`slow_postgres.sh`): at the original RATE=50/s, sustained 200ms postgres latency × ~6 queries per event burned through the 30-connection pool in ~4s. Backend hit `sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached, timeout 10.00`. Plan §A6 risk row predicted exactly this: "Either tighten the harness rate ... or document the new ceiling." Lowered RATE default to 20 (25% headroom). Also demoted `failed_5xx` and `transport_errors` from hard gates to informational — at the pool ceiling there are always transient saturation artifacts that aren't crashes.
  8. A4: degraded_warnings was matching agent startup log lines that age out of the 250-line capture window during the orchestrator's earlier scenarios. The cursor-advance assertion (`sshd_offset_after > sshd_offset_before`) plus events-landed are the real proof; degraded_warnings is now informational with an inline note explaining why 0 is acceptable.

- **A1 (`kill_redis.sh`) ✅ DONE 2026-05-04.** Operator wrote it directly rather than waiting for the queued Wed remote agent. Modeled on `restart_postgres.sh` (cleanest sibling), uses `load_harness.py` inside the backend container as the driver, mechanism is `docker compose kill redis` at t=10s + `up -d redis` at t=25s. Standalone result: `sim_tracebacks=0`, `backend_tracebacks=0`, `event_count_5min=1228`, `degraded_warnings=2` → **PASS**. Two calibration findings landed during verification (commit `6be162f`): time-window log capture (`--since 2m`) replaces the 250-line tail (which was burying resilience signals under SQLAlchemy echo at ~12k lines per run); accept_pct/transport_errors demoted to informational (not gated) because Windows+WSL2 has a documented 3.6s `getaddrinfo("redis")` NXDOMAIN quirk that doesn't apply on `ubuntu-latest`.

- **Regression-injection sanity check ✅ DONE 2026-05-04.** Bypassed `safe_redis()` on `auth_failed_burst.py:41` (replaced with raw `redis.incr()`), rebuilt backend, re-ran kill_redis.sh — **FAILED with `degraded_warnings=0` exactly as plan §"Verification plan #4" predicted**. The harness IS strict enough to catch missing-resilience regressions. File restored via `git checkout`, backend rebuilt clean.

- **Per-scenario CI workflows on `ubuntu-latest` (optional, deferred).** Five workflow_dispatch files for A2-A6 are on `main` and likely pass on Linux (same scripts that pass locally). `chaos-redis.yml` would need a refactor to source `lib/evaluate.sh` and adopt the calibrated logic from `kill_redis.sh` before triggering — its current inline eval is the original Phase-19 version that failed three times on 2026-05-02. Phase 19.5 done-criteria are met without this; operator can tackle the refactor in a future session if cross-platform Linux verification of A1 is wanted for a recruiter-facing story.

- **CI nightly cron (optional, deferred).** Same trade-off as before: daily 06:00 UTC cron costs GH Actions minutes, buys continuous regression coverage. Not blocking Phase 19.5 closure.

- **`v0.95` tag (optional, deferred).** Could tag now or roll into Phase 20's `v1.0`.

## 6. Where things are right now

`main` carries (as of commit `72d467d`, end of 2026-05-04 session — Phase 19.5 closed):
- The plan (`docs/phase-19.5-plan.md`).
- Foundation (`labs/chaos/lib/evaluate.sh`, `labs/chaos/README.md`, `labs/chaos/run_chaos.sh`).
- **All six** scenario scripts, all calibrated against live runs (`kill_redis.sh`, `restart_postgres.sh`, `partition_agent.sh`, `pause_agent.sh`, `oom_backend.sh`, `slow_postgres.sh`) + their matching workflows.
- Regression-injection sanity check verified — bypassing `safe_redis` makes `kill_redis.sh` FAIL red, proving the harness catches the regression it's designed to catch.

The orchestrator now reports `OVERALL: PASS — all 6 scenarios green` instead of the previous `5 green, 1 skipped`. Phase 20 (heavy-hitter choreographed scenarios) is the next phase whenever the operator is ready to start it.

## 7. Reading order if you have 10 minutes

1. **This file** — the map.
2. **`docs/phase-19.5-plan.md` § Workstream A** — the per-scenario engineering rationale.
3. **`labs/chaos/scenarios/restart_postgres.sh`** — the cleanest scenario script to read first; the others follow the same shape.
4. **`labs/chaos/lib/evaluate.sh`** — the shared helpers that make the scripts terse.

If you have an extra 30 minutes and want the full design rationale, the recipe revisions, and the risk/mitigation table, `docs/phase-19.5-plan.md` is the canonical source.
