# labs/chaos — Phase 19.5 chaos testing harness

Six failure-injection scenarios that exercise the resilience primitives shipped in Phase 19. Each scenario fires one specific disruption against a running stack and asserts the system degrades gracefully (events keep landing, no traceback, the resilience layer's degraded-mode log line fires).

**Plan:** `docs/phase-19.5-plan.md`
**Status:** in progress (started 2026-05-02). See `PROJECT_STATE.md` for the live scorecard.

## Layout

```
labs/chaos/
├── README.md           — this file
├── run_chaos.sh        — orchestrator: runs all six scenarios sequentially
├── lib/
│   └── evaluate.sh     — shared helpers (four-counter eval, cleanup trap, log capture)
└── scenarios/
    ├── kill_redis.sh        — A1: docker compose kill redis
    ├── restart_postgres.sh  — A2: docker compose restart postgres
    ├── partition_agent.sh   — A3: docker network disconnect cct-agent (substitute for iptables)
    ├── pause_agent.sh       — A4: docker compose pause cct-agent
    ├── oom_backend.sh       — A5: docker compose kill -s SIGKILL backend
    └── slow_postgres.sh     — A6: tc qdisc add ... netem delay 200ms (network, not disk)
```

## Running locally

The chaos scenarios assume the stack is **already up**. Bring it up with `bash start.sh` first (it provisions `CCT_AGENT_TOKEN` and brings up the agent profile). Then:

```bash
# Run one scenario
bash labs/chaos/scenarios/kill_redis.sh

# Run all six sequentially
bash labs/chaos/run_chaos.sh
```

Each scenario script sources `lib/evaluate.sh` for the shared four-counter evaluation, sets a trap to call `cleanup_chaos_state` on exit (so partial failures don't leave the stack with leftover `tc` rules / disconnected networks / paused containers), and prints a final `PASS:` or `FAIL:` line with a structured reason.

## Running in CI

Each scenario also has a `.github/workflows/chaos-<name>.yml` workflow_dispatch file. Trigger from the Actions tab → "Run workflow" on the workflow you want. The CI workflow brings up the stack via `bash start.sh`, runs the matching scenario script, and tears the stack down on completion.

The four §A1 acceptance counters (sim_tracebacks, backend_tracebacks, event_count_5min, degraded_warnings) are the consistent shape across all six scenarios. Counter #4's pattern is scenario-specific — see each script's header comment.

## Two recipe revisions vs the original roadmap

The original roadmap (`docs/roadmap-discussion-2026-04-30.md` lines 550–565) listed `iptables` for scenario A3 and `tc` against the Postgres volume for scenario A6. Both were re-cut during the Phase 19.5 plan because of `ubuntu-latest` GitHub Actions runner sandbox limits:

- **A3:** `iptables` requires `CAP_NET_ADMIN`, unavailable on GH Actions. Substituted `docker network disconnect` — functionally equivalent at the container level (TCP hangs, agent's HTTP client times out cleanly, retries fire as designed).
- **A6:** `tc` is for network packets, not disk I/O; real disk-latency injection (`dm-delay`, blkdebug) needs `CAP_SYS_ADMIN`, also unavailable on GH Actions. Redefined as 200ms network latency between backend and Postgres via `tc qdisc add dev eth0 root netem delay 200ms` *inside* the Postgres container — tests the more realistic failure mode anyway (slow Postgres connection, not slow disk).

Both substitutions are documented in `docs/phase-19.5-plan.md` § "Calibration vs the roadmap".
