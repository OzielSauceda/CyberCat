# Phase 11 — Wazuh Active Response Dispatch

## Context

Phase 9A (verified 2026-04-22) shipped five response handlers as **DB-state only** per ADR-0005: `quarantine_host_lab` writes a marker to `LabAsset.notes`; `kill_process_lab` annotates the process entity and auto-creates an evidence request. Neither actually drops network traffic or terminates a process. The DB state was always intended as Phase 9A's scope; real OS/network side-effects were deferred.

Phase 11 closes that gap. The two `disruptive`-classified handlers will, after writing their DB state, dispatch a real Wazuh Active Response command to the agent on the target host so the action produces the physical effect it claims — iptables DROP for quarantine, process termination for kill — on the `lab-debian` (and future `lab-windows`) machines.

Why it matters for the product story: every portfolio review question of the form "does this thing actually *do* anything?" currently has a caveat answer. Phase 11 removes the caveat. Combined with Phase 10's attack simulator and Phase 12's visuals, this makes the end-to-end demo — "simulator fires → detection → incident → analyst clicks Execute → agent-side iptables rule lands within 5s" — complete and showable.

## Decisions

1. **Both handlers in scope.** `quarantine_host` uses Wazuh's built-in `firewall-drop` AR (no agent work). `kill_process` uses a new custom `kill-process` AR script installed on the lab agents via Dockerfile — small, self-contained, and the payoff (demoable process termination) is worth the ~40 lines of shell + config.
2. **`ActionResult.partial`** is added. If DB state commits but AR dispatch fails (manager unreachable, 5xx, timeout, agent not enrolled), the action resolves as `partial` with a readable reason. DB rollback is NOT used — the audit trail of *what was attempted* is load-bearing for "every incident explainable."
3. **Separate `wazuh_ar_enabled` flag** (default `false`). Independent of `wazuh_bridge_enabled` so telemetry-only demos remain safe.
4. **AR metadata stored in existing `ActionLog.reversal_info` JSONB.** No schema migration for metadata. The JSONB shape: `{ar_dispatch_status: "dispatched"|"failed"|"skipped"|"disabled", wazuh_command_id: str|null, ar_response: dict|null, ar_dispatched_at: iso8601, error: str|null}`.
5. **Idempotency: dispatch anyway.** `firewall-drop` is idempotent against existing iptables rules; killing a dead PID is a benign no-op. Handler doesn't pre-check.
6. **Disruptive actions remain non-revertible.** Phase 11 does not add a revert path. Demo cleanup uses a documented out-of-band unquarantine step in the smoke test's `--cleanup` mode.

## File-by-file changes

### Backend — new files

- **`backend/app/response/dispatchers/__init__.py`** — package marker.
- **`backend/app/response/dispatchers/wazuh_ar.py`** — the dispatcher.
  - Module-level `httpx.AsyncClient` reusing the SSL pattern from `backend/app/ingest/wazuh_poller.py:60-65` (CA bundle pinned, hostname verify off).
  - `async def authenticate() -> str` — POST `/security/user/authenticate`, returns JWT. Cached in a module-level dict with expiry; re-auth on 401.
  - `async def dispatch_ar(command: str, agent_id: str, arguments: list[str], alert: dict | None) -> DispatchResult` — POST `/active-response` on the manager. Single attempt, 5s connect / 10s read timeout. Returns a `DispatchResult` dataclass: `{status, wazuh_command_id, response, error}`.
  - Short-circuit: if `settings.wazuh_ar_enabled` is False → returns `status="disabled"` without any network call.
  - Never logs the Authorization header.
- **`backend/app/response/dispatchers/agent_lookup.py`** — resolves host natural_key → Wazuh agent_id.
  - `async def agent_id_for_host(host: str) -> str | None` — query `/agents?name=<host>` on the manager, cache result in Redis with 60s TTL. Returns `None` if not enrolled; dispatcher maps that to `status="skipped"` with reason `agent_not_enrolled`.

### Backend — modified files

- **`backend/app/enums.py`** — add `ActionResult.partial`.
- **`backend/app/config.py`** — add:
  - `wazuh_ar_enabled: bool = False`
  - `wazuh_manager_url: str = "https://wazuh-manager:55000"`
  - `wazuh_manager_user: str = "wazuh-wui"`
  - `wazuh_manager_password: str = ""`
  - `wazuh_ar_timeout_seconds: int = 10`
  - Reuses existing `wazuh_ca_bundle_path`.
- **`backend/app/response/executor.py`** — extend the `ActionResult → ActionStatus` map to include `partial`. Signature of handlers is unchanged.
- **`backend/app/db/models.py`** — `ActionResult` and `ActionStatus` PG enum types gain `partial`.
- **`backend/app/response/handlers/quarantine_host.py`** — after existing DB writes, if `wazuh_ar_enabled`:
  - Look up `source_ip` from the incident's entities (best-effort; if none, use `host` as target).
  - `agent_id = await agent_id_for_host(host)`; if `None` → return `(partial, "wazuh agent not enrolled", reversal_info)`.
  - `result = await dispatch_ar("firewall-drop0", agent_id, [source_ip or "0.0.0.0"], alert_payload)`.
  - Map `DispatchResult.status` → ActionResult: `dispatched→ok`, `failed→partial`, `skipped→partial`, `disabled→ok`.
  - Append AR status to the Note body and to `reversal_info`.
- **`backend/app/response/handlers/kill_process.py`** — same pattern: after existing DB writes, dispatch `kill-process` command with arguments `[host, pid, process_name]`.
- **`backend/alembic/versions/0006_phase11_action_result_partial.py`** — `ALTER TYPE actionresult ADD VALUE 'partial'` + same for `actionstatus`. Downgrade is a no-op with a documented comment (Postgres does not support enum value removal without table rewrite).

### Frontend — modified files

- **`frontend/app/lib/api.ts`** (regenerated via `npm run gen:api` after backend changes) — `ActionResult` / `ActionStatus` unions include `"partial"`.
- **Action badge component** (the component that renders the result pill on `/actions` and `/incidents/[id]`) — add amber styling for `partial`, tooltip `"Action partially completed — DB state written, enforcement did not confirm. See action log."`
- **Action detail/row** — if `reversal_info.ar_dispatch_status` is present, render a labeled row: `Active Response: dispatched | failed (reason) | skipped (reason) | disabled`.

### Infra — new / modified files

- **`infra/lab-debian/active-response/kill-process.sh`** *(new)* — custom AR script. Reads the Wazuh AR JSON from stdin, extracts `host`, `pid`, `process_name`, runs `kill -9 <pid>` with a safety check that the process cmdline matches `process_name` (prevents cross-host PID collisions). Exit 0 on success, nonzero on failure (logged to `/var/ossec/logs/active-responses.log`).
- **`infra/lab-debian/Dockerfile`** — `COPY active-response/kill-process.sh /var/ossec/active-response/bin/kill-process`, `chmod 750`, `chown root:wazuh`. One layer.
- **`infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf`** — add:
  - `<command name="kill-process"><executable>kill-process</executable><extra_args>...</extra_args></command>`
  - `<active-response><command>kill-process</command><location>local</location></active-response>`
  - `firewall-drop` is already a default command — no config needed for quarantine.
- **`infra/compose/docker-compose.yml`** — add `WAZUH_AR_ENABLED`, `WAZUH_MANAGER_URL`, `WAZUH_MANAGER_USER`, `WAZUH_MANAGER_PASSWORD` to the backend service env block (sourced from `.env`). Port 55000 already published.
- **`infra/compose/.env.example`** — document the four new variables.

### Docs

- **`docs/decisions/ADR-0007-wazuh-active-response-dispatch.md`** *(new)* — Context (ADR-0005 split recap), Decision (the six numbered points above), Rationale (portfolio/operator framing), Consequences (iptables non-persistence is a known lab limitation, documented operator cleanup).
- **`docs/runbook.md`** — new section "Running a Phase 11 enforcement demo": `.env` flags to set, expected iptables rule, manual cleanup.
- **`PROJECT_STATE.md`** — Phase 11 entry (move from "Next" to "Verified" after smoke test passes). Also fix the stale `# 9B extension:` claim on line 30 and in ADR-0005 — those markers never existed in code.

### Tests

- **`backend/tests/unit/test_wazuh_ar_dispatcher.py`** *(new)* — mocked `httpx`: auth success + token cache reuse, auth 401 → re-auth once, dispatch success, dispatch 5xx, dispatch timeout, `wazuh_ar_enabled=False` short-circuit, unknown agent → skipped. Assert Authorization header never appears in log output.
- **`backend/tests/integration/test_handlers_ar_integration.py`** *(new)* — with dispatcher mocked: quarantine handler returns `partial` on dispatch failure (DB state still persisted), returns `ok` on dispatch success, `reversal_info` shaped correctly. Same for kill_process.
- **`labs/smoke_test_phase11.sh`** *(new)* — requires `--profile wazuh`. Steps:
  1. Wait for `wazuh-manager` healthy AND `lab-debian` enrolled (`curl -sk https://localhost:55000/agents?name=lab-debian` retry loop, 30s cap).
  2. POST an event that creates an `identity_compromise` incident for alice@lab-debian.
  3. Propose + execute `quarantine_host_lab` on that incident.
  4. `docker compose exec lab-debian iptables -S | grep DROP` → asserts the rule landed.
  5. Assert `ActionLog.reversal_info.ar_dispatch_status == "dispatched"` and `Action.status == "executed"`.
  6. Start `sleep 120` in `lab-debian`; propose + execute `kill_process_lab` with that PID.
  7. `docker compose exec lab-debian ps -p <pid>` → asserts process gone.
  8. `--cleanup` mode: flush iptables, restart lab-debian, confirm clean state.
  9. Negative path (optional, `--test-negative`): stop `wazuh-manager`, retry execute, assert `Action.status == "partial"` and reason readable.

## Implementation order

Each step merge-safe on its own; each step gated by its own tests passing. Do not start step N+1 until step N is green.

1. Enum + Alembic migration 0006 — smallest merge-safe unit. Existing tests must still pass unchanged.
2. Config additions (flag off by default). Start backend, confirm `/health` clean.
3. Dispatcher + agent lookup, with unit tests. No handler wiring yet.
4. `quarantine_host` wiring, guarded on `wazuh_ar_enabled`. Phase 9A smoke test must still pass with flag off.
5. Frontend enum + badge + action detail row. Regenerate `api.generated.ts`. `tsc --noEmit` clean.
6. `kill-process.sh` + Dockerfile + `wazuh_manager.conf`. Rebuild lab-debian image. Agent re-enrolls on recreate.
7. `kill_process` wiring.
8. `smoke_test_phase11.sh` happy path — iptables + PID verification end-to-end.
9. Negative path (manager down) verification.
10. ADR-0007 written, PROJECT_STATE.md updated, README note about AR being opt-in.

## Verification

- `pytest` all green (dispatcher unit + handler integration).
- `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` round-trip clean.
- `labs/smoke_test_phase9a.sh` — all 14 checks still pass with `WAZUH_AR_ENABLED=false` (zero regression).
- `labs/smoke_test_phase11.sh` — all checks pass end-to-end against live `--profile wazuh` stack.
- Manual browser check: execute a quarantine action on an incident; UI shows amber `partial` badge when manager is intentionally down, green `ok` when up. `reversal_info` visible in action detail.
- `docker compose exec wazuh-manager tail /var/ossec/logs/active-responses.log` shows the dispatched commands with correct agent_id.
- `npm run gen:api && tsc --noEmit` → 0 errors.

## Critical files

- `backend/app/response/dispatchers/wazuh_ar.py` *(new)*
- `backend/app/response/dispatchers/agent_lookup.py` *(new)*
- `backend/app/response/handlers/quarantine_host.py`
- `backend/app/response/handlers/kill_process.py`
- `backend/app/response/executor.py`
- `backend/app/enums.py`
- `backend/app/config.py`
- `backend/app/db/models.py`
- `backend/alembic/versions/0006_phase11_action_result_partial.py` *(new)*
- `infra/lab-debian/active-response/kill-process.sh` *(new)*
- `infra/lab-debian/Dockerfile`
- `infra/compose/wazuh-config/config/wazuh_cluster/wazuh_manager.conf`
- `infra/compose/docker-compose.yml`
- `labs/smoke_test_phase11.sh` *(new)*
- `docs/decisions/ADR-0007-wazuh-active-response-dispatch.md` *(new)*

## Risks / gotchas

- **Agent enrollment race.** Fresh `lab-debian` takes 10–30s to enroll. Smoke test must poll `/agents?name=lab-debian` before the first quarantine, not just wait on `docker compose ps --health`.
- **iptables non-persistence.** `firewall-drop` writes runtime rules only; a container restart wipes them while the DB still says "quarantined." Acceptable for lab; documented in ADR-0007 Consequences.
- **Wazuh manager password is long-lived.** Stays in `infra/compose/.env` (gitignored). Token cache in dispatcher invalidates on 401 and re-auths once.
- **Custom `kill-process.sh` safety.** Must validate cmdline against `process_name` before `kill -9` to avoid PID reuse accidents. Runs as root on the agent — review carefully.
- **Stale doc claim.** PROJECT_STATE.md:30 and ADR-0005:37 both claim `# 9B extension: dispatch Wazuh AR` comments already mark the extension points in the two handlers. They don't. Fix in the same PR that adds the real dispatch.
- **Executor commit boundary.** Executor holds one session across handler + ActionLog write. Dispatch call happens inside the handler — a raised exception would roll back the handler's DB writes too. Dispatcher must catch its own exceptions and return a `DispatchResult`, never raise.
- **Password leak in logs.** Enforce with a unit test: any dispatcher log line containing `Authorization` is a test failure.

## Explicitly out of scope (deferred)

- Revert path for disruptive actions (manual unquarantine remains the smoke-test `--cleanup` job).
- Windows/Sysmon agent AR (lab-debian only in Phase 11; Windows agent tracked in Phase 9B Sub-track 3 deferred notes).
- Persistent iptables rules across agent restart.
- Rate limiting / circuit breaking on AR dispatch (Phase 14+).
- AR command audit dashboard — the existing action_log UI suffices for v1.
