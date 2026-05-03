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

- **Live verification.** All scripts pass `bash -n` syntax check and all workflow YAMLs parse with PyYAML. **None have been executed against a live stack yet.** The first real run of each scenario will probably surface small calibration tweaks (degraded-warnings patterns that need widening, timing windows that need adjustment, maybe one or two scenarios that fail in ways we'll have to triage). That's the "verification phase" still to come.
- **Regression-injection sanity check.** Once the six scenarios all pass green, the final test is to deliberately break one Phase-19 primitive (e.g. remove `safe_redis(...)` from one detector) and confirm the relevant chaos scenario fails red. If it doesn't, the harness isn't strict enough.
- **CI nightly cron.** Per `docs/phase-19.5-plan.md` § "Verification plan #5", we may opt the chaos workflows into a daily 06:00 UTC cron once they're stable. Costs GH Actions minutes; trade-off is continuous regression coverage. Not done yet.
- **`v0.95` tag.** Optional, per the plan. Could also fold into Phase 20's `v1.0` tag.

## 6. Where things are right now

`main` carries:
- The plan (`docs/phase-19.5-plan.md`).
- Foundation (`labs/chaos/lib/evaluate.sh`, `labs/chaos/README.md`, `labs/chaos/run_chaos.sh`).
- Five of six scenario scripts (`restart_postgres.sh`, `partition_agent.sh`, `pause_agent.sh`, `oom_backend.sh`, `slow_postgres.sh`) + their matching workflows.
- A1 (`kill_redis.sh`) is queued — a remote agent scheduled for **Wed 2026-05-06 at 10:00 CDT** is set to land it as a draft PR (routine `trig_01NDdyh6syXyAiY9Lz9rjaxd`, retargeted from an earlier path to match the Phase 19.5 plan's structure).

When A1 lands, all six scenarios are present and the orchestrator's `SKIP` entry for it goes away automatically.

## 7. Reading order if you have 10 minutes

1. **This file** — the map.
2. **`docs/phase-19.5-plan.md` § Workstream A** — the per-scenario engineering rationale.
3. **`labs/chaos/scenarios/restart_postgres.sh`** — the cleanest scenario script to read first; the others follow the same shape.
4. **`labs/chaos/lib/evaluate.sh`** — the shared helpers that make the scripts terse.

If you have an extra 30 minutes and want the full design rationale, the recipe revisions, and the risk/mitigation table, `docs/phase-19.5-plan.md` is the canonical source.
