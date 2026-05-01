# PR: Phase 19: Hardening, CI/CD, Detection-as-Code

(Title above; body below — copy-paste into the GitHub PR form. Delete this file after the PR is open.)

---

## Summary

Phase 19 closes out the resilience, CI, and detection-fixture work and lands the heavy-hitting verification surface for the project.

**Resilience (A1–A6):**
- Redis: `safe_redis()` helper with circuit breaker + per-op timeout. Detector and publisher call sites wrapped. EventBus survives Redis blips with reconnect supervisor.
- Postgres: explicit pool config + `with_ingest_retry` wired into the Wazuh poller **and** the HTTP `/events/raw` route (A3.1).
- Wazuh poller: circuit breaker on transient errors.
- Asyncio default executor bumped to 64 workers so DNS spikes during outages don't starve the request loop.

**Validation + perf (A4, A7):**
- `RawEventIn` validators bound payload size and clock skew; new negative tests.
- N+1 fixes in incidents and detections list endpoints with a query-counting fixture.
- Perf baseline + load harness for repeatable load tests.

**CI/CD (B):**
- `.github/workflows/ci.yml` — pytest + ruff on every push.
- `.github/workflows/smoke.yml` — docker compose smoke chain on push to main.

**Detection-as-code (C):**
- `labs/fixtures/` with manifest, replayer, and curated JSONL fixtures for auth/process/network event kinds.
- Test asserts each fixture either fires or cleanly skips its expected rule.

**Docs (D):**
- `docs/phase-19-plan.md` and `docs/phase-19-handoff.md` (the latter is the source of truth for what's verified vs. deferred).
- Performance baseline + ADR-0014 (frontend detective redesign).

## Test results

- Backend pytest: **236/236** passing (174 baseline + 62 new).
- Ruff clean on `app/`.
- Smoke chain: **7/7** scripts passing (phase17 17/0 on fresh volume + 6/6 on post-wipe stack).
- Frontend typecheck: clean.

## Known residual gap (NOT blocking PR; blocks v0.9 tag)

The redis-kill chaos test (`docker compose kill redis` mid-simulator) still surfaces `httpx.ReadTimeout` on **Windows/WSL2 + Docker Desktop**. Diagnosed: `getaddrinfo("redis")` returns NXDOMAIN in ~3.6s on this platform, beyond what `socket_connect_timeout` can bound, and `asyncio.wait_for` cannot cancel the underlying thread. Strong indication this is platform-specific; full writeup in `docs/phase-19-handoff.md` under "A1.1 residual gap".

**Action item:** confirm chaos test passes on this PR's Linux CI runner before tagging v0.9. If it passes there, the gap is platform-only and shipping is fine.

## Test plan

- [ ] CI: `ci.yml` workflow green on this branch
- [ ] After merge: `smoke.yml` workflow green on `main`
- [ ] (Optional) Manually re-run the redis-kill chaos test on the Linux CI image to confirm platform diagnosis
- [ ] If all green, tag `v0.9` against the merge commit
