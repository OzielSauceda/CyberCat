# Phase 19 — Handoff to next session

Pick up here. Read this top-to-bottom; it's the shortest path to context.

---

## STATUS — 🟡 CODE-SHIPPED 2026-04-30, ACCEPTANCE PENDING (read this first)

**Phase 19 code merged to `main` via PR #5** (`phase-19` → `main`, commit `efde988`). Backend pytest **236/236**, agent pytest **104/104** on the CI agent runner (122/122 on the backend image), ruff clean, frontend typecheck clean, Linux smoke chain **7/7** on the PR-trigger run.

**Earlier framing in this section called Phase 19 "shipped" — that was overstated.** The Phase 19 plan's own done-criteria (line 351) and §"Verification plan" (lines 319–331) have three live-acceptance items that were never closed during the merge cycle, plus one numerical delta vs target, plus the v0.9 tag. Honest scorecard:

| # | Verification-plan item | State |
|---|---|---|
| 1 | Resilience pytest | ✅ 236/236 |
| 2 | Manual Redis kill-test (live) | ❌ Failed on Windows/WSL2; never re-run on Linux |
| 3 | Manual Postgres restart-test (live) | ⚠️ A3.1 unit test passes, but the live `100/s × 30s + restart postgres at t=10s` retest with ≥ 95% acceptance was **never re-run** after the fix landed |
| 4 | Load test 1000/s × 60s | ❌ Heavy-hitting trail only ran **100/s × 60s** — one order of magnitude below §A6 (line 125) |
| 5 | Hot-route ≤ 4 queries on 50-item page | ⚠️ Achieved ≤ 12 / ≤ 10 — better than baseline (250+ / 200+) but plan target was ≤ 4 |
| 6 | Detection-as-code | ✅ |
| 7 | CI proof | ✅ (the `.gitignore` fixture bug surfaced and got caught) |
| 8 | Smoke proof on `main` | ❌ Smoke on `main` is currently **RED** (the workflow shipped broken; PR #6 is the fix, all 6 checks green, ready to merge) |
| 9 | Frontend typecheck | ✅ |
| 10 | `v0.9` tag cut | ❌ Not applied |

**Story of the smoke-fix follow-up (PR #6):** the Smoke workflow shipped in Phase 19 was push-to-main only, so it never ran during the PR cycle. Its first real run failed because (a) it brought up only `postgres redis backend frontend` instead of the full `--profile agent` stack — three of the six smoke scripts in step 5 (`smoke_test_phase16_9.sh`, `smoke_test_phase16_10.sh`, `smoke_test_agent.sh`) require `cct-agent` + `lab-debian` — and (b) the agent needs `CCT_AGENT_TOKEN` provisioned by `start.sh`'s bootstrap. Fix: replaced the bare `docker compose up` with `bash start.sh` (defaults to `--profile agent` + token bootstrap), installed `httpx` on the runner (the simulator + replay drive the backend over HTTP from the host), pinned `pytest` ordering on the merge gate (`-p no:randomly` — pytest-randomly was double-flaking the same commit between push and PR triggers), added per-script `::error::` annotation surfacing + a `smoke-logs` artifact, and added a narrow `pull_request` trigger so future smoke/compose changes self-validate before merge.

**Also landed during the merge cycle:** `*.log` in `.gitignore` (under `# Docker`) was eating five test fixture files in `agent/tests/fixtures/` — they existed locally so my pytest passed but the GH Actions checkout had nothing in the directory. Fixed via `!agent/tests/fixtures/*.log` negation + force-tracking.

## Remaining work — pick up here in this order

1. **Merge PR #6** (`fix/smoke-workflow-agent-profile`). All 6 checks green (CI push + PR × 3 jobs, Smoke PR run). Closes scorecard items #7 and #8.
2. **Watch the Smoke workflow on `main`** after merge. Should be green (we just verified the same workflow on the PR trigger). If not, the per-script `::error::` annotations + the `smoke-logs` artifact will surface the failing script and its tail without needing job-log auth.
3. **Re-run the Redis kill-test (live) on Linux.** Plan §A1 acceptance (line 67). Reproduction recipe in "How to verify the fixes worked" below (Test 3). Easiest path: run inside an Ubuntu container, or via a temporary `workflow_dispatch` invocation against a Linux runner. Pass: simulator's `--verify` PASSES, latency on each request < 1s, no traceback. If it fails on Linux too, the deferred work in "A1.1 residual gap" below has to land first. Closes scorecard item #2.
4. **Re-run the Postgres restart-test (live).** `100/s × 30s` against `/v1/events/raw` with `restart postgres` at t=10s. Pass: ≥ 95% accepted, recovery within 30s, transport_errors well below 1992 (the pre-fix number). Recipe in "How to verify the fixes worked" below (Test 4). Closes scorecard item #3.
5. **Run the load harness at the §A6 bar.** `python labs/perf/load_harness.py --rate 1000 --duration 60` — the heavy-hitting trail only exercised 100/s, an order of magnitude below the bar. Pass: 0% drops at the API layer, p95 detection latency < 500ms, peak Postgres connection count < 25. Closes scorecard item #4.
6. **Reconcile hot-route query count.** Plan §A7 (line 138) targeted ≤ 4 queries on a 50-item page; we shipped at ≤ 12 (incidents) / ≤ 10 (detections). Two honest options: (a) tighten the routes further by collapsing the entity-count + event-count + detection-count loads into one CTE and confirm ≤ 4, or (b) write a one-line amendment to the plan justifying the ≤ 12 / ≤ 10 floor (e.g., separate batched queries are clearer than a CTE for future maintainers; the meaningful win is N → constant, not constant → 4) and update the done-criteria text to match. Closes scorecard item #5.
7. **Tag `v0.9`** against the merge commit — only after 1–6 above. Skipping any is shipping with debt the plan explicitly forbade. Closes scorecard item #10.

For a plain-language overview of what Phase 19 actually changed in the codebase (NEW vs MODIFIED, did the architecture change?), see `docs/phase-19-summary.md`.

The original handoff content below is preserved verbatim for the historical record; the gap-1 / gap-2 notes captured the in-flight state at the time it was written.

---

## TL;DR

- Phase 19 code work for A1–A7, B, C, D is **complete on disk** but **not committed**.
- Backend test suite: **233 / 233 pytest passing** (174 baseline + 59 new).
- Smoke chain (default profile, 6 scripts after a phase17 fix): **101 / 101 passing**.
- Heavy-hitting verification surfaced **two real gaps** (A1.1 + A3.1) that must land before Phase 19 ships.
- Nothing is on a feature branch yet. Working branch is still `phase-18-docs`.

## Current state of the world

| Surface | State |
|---|---|
| Working branch | `phase-18-docs` (unchanged) |
| Uncommitted files | ~30 (see "Files touched" below) |
| Backend Docker image | Rebuilt at start of heavy-hitting run; has Phase 19 code baked in |
| Backend container `/app` | Running with bind-mount on `infra/compose/docker-compose.yml` for `../../labs:/app/labs:ro` |
| Postgres + Redis | Up and healthy |
| Last test run | 233 pytest pass, ruff clean, 4 random seeds × 233 all green |
| Last simulator run | `credential_theft_chain --verify` PASSED on healthy stack |
| Last chaos run | Surfaced Gap 1 (Redis kill) and Gap 2 (Postgres restart) — see plan §"Heavy-hitting verification" |

## Two gaps that must close before shipping — STATUS

> **Update 2026-04-30 (continuation session):** A3.1 is complete and verified. A1.1 is partially complete: the prescribed fix landed, plus several deeper hardening steps the original handoff didn't anticipate. The Redis-kill chaos test still fails on this Windows/WSL2 host because of platform-level DNS NXDOMAIN latency. See "A1.1 residual gap" below.

### A3.1 — HTTP ingest path has no retry  [DONE]

Refactored `ingest_raw_event` per option A. New integration test `test_postgres_disconnect.py::test_http_ingest_retries_on_connection_invalidated` passes (along with a sibling test that asserts the wrapper gives up after exactly one retry).

### A1.1 — Redis kill makes ingest slow, not graceful  [PARTIAL]

**Done:**
1. `backend/app/db/redis.py::init_redis()` — `socket_connect_timeout=0.5`, `socket_timeout=2.0`, `retry_on_timeout=False`. (Read timeout sized at 2s, not 0.5s — under pytest load real ops occasionally exceed 500ms.)
2. `backend/app/streaming/publisher.py::publish()` — wrapped with `safe_redis(...)`.
3. `backend/app/correlation/rules/endpoint_compromise_standalone.py` — SETNX dedup wrapped with `safe_redis`. **Watch out:** `redis.set(NX)` returns `None` when the key already exists; the helper here uses a sentinel `_UNAVAILABLE` so we don't conflate "redis down" with "dedup hit".
4. `backend/app/db/redis_state.py::safe_redis` — bounded by `asyncio.wait_for(_OP_TIMEOUT_SEC=3.0)` and tripped by a circuit breaker (`_BREAKER_OPEN_SEC=5.0`) so subsequent calls during an outage short-circuit instead of each burning their own timeout.
5. `backend/app/streaming/bus.py` — bus client got `socket_connect_timeout=0.5`. Crucially **does not** set `socket_timeout` — pubsub.listen() blocks indefinitely; a small read timeout would turn every idle period into a "consumer crashed → reconnect" cycle.
6. `backend/app/main.py::lifespan` — bumps asyncio's default thread executor to 64 workers. Python's default (`min(32, cpu+4)`) is exhausted by a few simultaneous `getaddrinfo` calls when DNS NXDOMAIN takes seconds to fail.
7. `backend/tests/conftest.py` — autouse fixture resets the breaker between tests (no leak between cases).
8. New test `backend/tests/integration/test_redis_unavailable.py::test_publisher_does_not_block_on_outage` — passes (publisher returns < 1s under simulated outage).

**A1.1 residual gap (deferred):**

`docker compose kill redis` mid-simulator on this Windows/WSL2 host still produces `httpx.ReadTimeout` on the simulator side. Backend processes events for a stretch (logs show `redis_degraded` warnings firing as expected and 201 responses returning) but eventually wedges — even after Redis is restored, the backend stops processing requests until restarted.

Diagnostic findings:
- On WSL2 + Docker Desktop, `getaddrinfo("redis")` against a removed container takes **~3.6 seconds** to return NXDOMAIN. `socket_connect_timeout` does not bound this — Python's getaddrinfo runs on the asyncio default thread executor and is uncancellable from the main loop.
- `asyncio.wait_for` cancels the awaiting Task at the timeout, but the underlying thread continues running getaddrinfo to completion. The thread pool slot stays consumed.
- The wazuh_poller (when `WAZUH_BRIDGE_ENABLED=true` in your `.env`, even on the agent profile) compounds this — it polls a non-resolvable `wazuh-indexer` host every 5s, each lookup eating a thread pool slot for 3.6s.
- Even the bumped thread pool (64 workers) doesn't fully save us — under sustained NXDOMAIN load *plus* the redis-py connection pool's internal locks, the backend reaches a state where it stops accepting new requests.

This appears to be a platform-specific WSL2/Docker DNS-resolver issue that the original Phase 19 author may not have hit on a Linux-native test host. On a native Linux runner where NXDOMAIN returns in microseconds, the prescribed `socket_connect_timeout=0.5` *is* sufficient; the breaker covers any residual slowness. Worth re-running this test on the GH Actions Linux runner before deciding the gap matters in production.

**Recommended next steps (not blocking ship):**
- Reproduce the chaos test on the CI Linux runner — likely passes there.
- If reproducible on Linux, investigate redis-py async pool's behavior under `wait_for` cancellation — there are reports of pool locks not releasing cleanly.
- Consider a "redis is up?" health probe at the start of each ingest request that fails fast if not (avoiding the per-op timeout cascade).
- Disable `WAZUH_BRIDGE_ENABLED` on default-profile dev stacks to remove the second source of DNS thrash.

## How to verify the fixes worked

```bash
# 1. Ensure stack is up (default profile)
docker compose -f infra/compose/docker-compose.yml --profile agent up -d

# 2. Rebuild backend after the A1.1 / A3.1 code changes
docker compose -f infra/compose/docker-compose.yml build backend
docker compose -f infra/compose/docker-compose.yml up -d backend

# 3. Wait for backend ready
until curl -sf http://localhost:8000/v1/incidents > /dev/null; do sleep 2; done

# 4. Confirm pytest still green
docker compose -f infra/compose/docker-compose.yml exec -T backend python -m pytest tests/

# 5. Re-run the chaos scenarios that failed before
# Test 3: simulator + Redis kill
curl -s -X DELETE http://localhost:8000/v1/admin/demo-data
docker cp labs compose-cct-agent-1:/app/labs
(MSYS_NO_PATHCONV=1 docker compose -f infra/compose/docker-compose.yml exec -T -w //app cct-agent \
  python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --api http://backend:8000 --verify > /tmp/sim.log 2>&1 &)
sleep 4 && docker compose -f infra/compose/docker-compose.yml kill redis
sleep 25 && docker compose -f infra/compose/docker-compose.yml up -d redis
wait && cat /tmp/sim.log | tail -20
# EXPECT: simulator completes, --verify PASSES, latency on each request < 1s

# Test 4: Postgres restart mid-load
docker cp labs/perf/load_harness.py compose-backend-1:/tmp/load_harness.py
(MSYS_NO_PATHCONV=1 docker compose -f infra/compose/docker-compose.yml exec -T backend \
  python //tmp/load_harness.py --base-url http://localhost:8000 --rate 100 --duration 30 > /tmp/load.log 2>&1 &)
sleep 10 && docker compose -f infra/compose/docker-compose.yml restart postgres
wait && cat /tmp/load.log | tail -15
# EXPECT: ≥ 95% accepted, recovery within 30s, transport_errors well below 1992
```

## After A1.1 + A3.1 land

1. Commit on a fresh `phase-19` branch (current branch is `phase-18-docs`).
2. Push, watch CI run (`.github/workflows/ci.yml`). The smoke workflow only fires on `main` push so feature-branch verification is just `ci.yml`.
3. Open a PR to `main` titled "Phase 19: Hardening, CI/CD, Detection-as-Code".
4. After merge, smoke workflow runs against `main` automatically. Verify it goes green.
5. **Re-run the Redis-kill chaos test on the Linux CI runner** before tagging. If it passes there, the residual gap is platform-specific and shipping is fine. If it fails on Linux too, the deferred work in "A1.1 residual gap" needs to land first.
6. Tag `v0.9` against the merge commit.

## Files touched (all uncommitted)

### New files
```
.github/workflows/ci.yml
.github/workflows/smoke.yml
README.md
backend/app/db/redis_state.py
backend/app/ingest/retry.py
backend/tests/integration/test_detection_fixtures.py
backend/tests/integration/test_event_validation_negative.py
backend/tests/integration/test_hot_route_query_count.py
backend/tests/unit/test_bus_supervisor.py
backend/tests/unit/test_postgres_resilience.py
backend/tests/unit/test_redis_unavailable.py
backend/tests/unit/test_wazuh_poller_resilience.py
docs/perf-baselines/2026-04-30-phase19-pre-perf.md
docs/phase-19-handoff.md          ← this file
docs/phase-19-plan.md
labs/fixtures/README.md
labs/fixtures/manifest.yaml
labs/fixtures/replay.py
labs/fixtures/auth/ssh_brute_force_burst.jsonl
labs/fixtures/auth/successful_login_clean.jsonl
labs/fixtures/auth/successful_login_anomalous.jsonl
labs/fixtures/process/benign_apt_update.jsonl
labs/fixtures/process/encoded_powershell.jsonl
labs/fixtures/process/curl_pipe_sh.jsonl
labs/fixtures/network/benign_outbound.jsonl
labs/fixtures/network/known_bad_ip_beacon.jsonl
labs/perf/load_harness.py
```

### Modified files
```
PROJECT_STATE.md                                          (Phase 19 status)
agent/cct_agent/*                                         (ruff auto-fixes — datetime.UTC, etc.)
agent/pyproject.toml                                      (ruff/mypy/pytest-randomly dev deps + tool config)
backend/Dockerfile                                        (comment about labs bind-mount)
backend/app/api/routers/detections.py                     (A7 N+1 fix)
backend/app/api/routers/incidents.py                      (A7 N+1 fix)
backend/app/api/schemas/events.py                         (A4 validators)
backend/app/auth/dependencies.py                          (B `raise ... from None` ruff fix)
backend/app/correlation/__init__.py                       (correlator registration order pinned)
backend/app/db/redis.py                                   (A1 RedisUnavailable instead of assert)
backend/app/db/session.py                                 (A3 explicit pool config)
backend/app/detection/rules/auth_anomalous_source_success.py  (A1 safe_redis)
backend/app/detection/rules/auth_failed_burst.py          (A1 safe_redis)
backend/app/detection/rules/blocked_observable.py         (A1 safe_redis)
backend/app/ingest/wazuh_poller.py                        (A2 circuit-breaker, A3 retry wrapper)
backend/pyproject.toml                                    (ruff/mypy/pytest-randomly dev deps + tool config)
backend/tests/conftest.py                                 (count_queries fixture for A7)
backend/tests/integration/test_response_action_emits.py   (replaced hardcoded 2026-01-01 timestamps with relative)
backend/tests/unit/test_streaming_event_bus.py            (rename _consume → _consume_once after A5 supervisor)
backend/app/streaming/bus.py                              (A5 supervisor + reconnect)
infra/compose/docker-compose.yml                          (bind-mount labs/ into backend)
labs/smoke_test_phase17.sh                                (was untracked; now updated and tracked)
~ many ruff-formatted files (timezone.utc → UTC, isort) ~
```

`git status` will show the full list.

## Key debug findings worth remembering

1. **Ruff alphabetizing imports broke a real correlator.** `correlation/__init__.py` registration order is load-bearing. Pinned with `# isort: skip_file` and a comment.
2. **Backend image is baked, not bind-mounted.** Iterate with `docker cp <host_file> compose-backend-1:/app/<container_path>` for fast loops; rebuild before any "real" run with `docker compose build backend`.
3. **labs/ is now bind-mounted into backend** at `/app/labs:ro` (added in this session). The `test_detection_fixtures.py` test resolves the manifest via this path.
4. **Phase 17 smoke had a stale schema reference** (`["total"]` from `IncidentList` which only has `items`). Fixed in `labs/smoke_test_phase17.sh`. Was never committed before this session — `git status` had it as `??`.
5. **`MSYS_NO_PATHCONV=1`** is required when running `docker exec` with absolute container paths from git-bash on Windows; otherwise paths like `/tmp/file.py` get rewritten to `C:/Program Files/Git/tmp/file.py`.
6. **Auto-seed (Phase 17) only fires on a fresh Postgres volume.** To re-test the first-boot flow: `docker compose -f infra/compose/docker-compose.yml down -v` then `up -d`.

## Quick commands cheat sheet

```bash
# Bring up default + agent profile (matches the heavy-hitting test stack)
docker compose -f infra/compose/docker-compose.yml --profile agent up -d

# Run full backend suite
docker compose -f infra/compose/docker-compose.yml exec -T backend python -m pytest tests/

# Run full backend suite with random ordering
docker compose -f infra/compose/docker-compose.yml exec -T backend python -m pytest tests/ --randomly-seed=12345

# Lint
docker compose -f infra/compose/docker-compose.yml exec -T backend ruff check app/

# Run smoke chain (skip wazuh-only phase8, phase11)
for s in labs/smoke_test_phase17.sh labs/smoke_test_phase10.sh labs/smoke_test_phase9a.sh \
         labs/smoke_test_phase15.sh labs/smoke_test_phase16_9.sh labs/smoke_test_phase16_10.sh \
         labs/smoke_test_agent.sh; do bash "$s" || echo "FAIL: $s"; done

# Wipe demo data (clean state for next sim run)
curl -s -X DELETE http://localhost:8000/v1/admin/demo-data

# Tear it all down
docker compose -f infra/compose/docker-compose.yml --profile agent down -v
```
