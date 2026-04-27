# Phase 13 — Real-Time Streaming (SSE) Plan

> Replaces the 5s/10s polling on the analyst UI with a server-pushed event stream so incidents, detections, actions, evidence, and the Wazuh bridge badge update instantly. Roadmap candidate #7 from `project-explanation/CyberCat-Explained.md` §16, formalized as Phase 13.

---

## 1. Context

Today the analyst UI is "soft real time" via polling — `frontend/app/lib/usePolling.ts` reruns five GETs every 5–10s (`/v1/incidents`, `/v1/incidents/{id}`, `/v1/responses`, `/v1/detections`, `/v1/wazuh/status`). Two costs:

1. **Latency** — analysts see incidents up to 10s after they exist. For the flagship `credential_theft_chain` demo (which compresses to ~30s), that's ~30% of the run spent waiting for the next tick.
2. **Wasted work** — every browser tab issues five queries per minute regardless of whether anything changed. Most of the time the response is identical.

Phase 13 ships a **read-only Server-Sent Events (SSE) channel** at `GET /v1/stream` that pushes lightweight notifications when domain state changes; the frontend converts each notification into a targeted refetch (or, for the Wazuh badge, into a direct state replace). Polling stays as a 60s safety net so the UI degrades gracefully if the stream dies.

This is the highest-leverage of the "what would push it to 9 or 10" items in the explainer doc — it removes the single biggest "feels like a toy" tell of polling intervals.

---

## 2. Architecture & Key Decisions

### 2.1 SSE, not WebSocket

We need server→client only — no client→server messaging. SSE wins on every axis that matters here:

- **Auto-reconnect** is built into the browser `EventSource` (with `Last-Event-ID` resume support if we want it).
- **HTTP-native** — inherits CORS, proxying, and the existing CORSMiddleware setup at `backend/app/main.py:56-62` with no special upgrade handshake.
- **Trivially testable** with the existing `httpx.AsyncClient` + `ASGITransport` pattern in `backend/tests/conftest.py`.
- WebSocket buys us full-duplex we don't need and a worse failure mode (no built-in resume).

### 2.2 Redis Pub/Sub for fan-out, in-process queues for delivery

The backend runs **one uvicorn worker** today (`backend/start.sh:4`), so in-process fan-out would technically suffice. We use Redis Pub/Sub anyway because:

- It matches the project's architectural rule ("Redis is for ephemeral coordination — never the system of record" — `CLAUDE.md` §2).
- It future-proofs for `--workers 2+` or a second backend container with zero code change.
- Cost is one extra ~1ms hop on `localhost`, well under our latency budget.

**Topology (one running backend process):**

```
Domain action → db.commit() → publish(StreamEvent) → redis.publish(channel, json)
                                                        │
                                              ┌─────────┴──────────┐
                                              ▼                    ▼
                                       (one shared Redis subscriber task in lifespan)
                                                       │
                                          fan out via in-process asyncio.Queue
                                              │       │       │
                                              ▼       ▼       ▼
                                          SSE conn SSE conn SSE conn   (one per browser tab)
                                              │       │       │
                                              ▼       ▼       ▼
                                          EventSource in browser → useStream hook
```

One Redis subscriber per backend process — **not** one per SSE client. Per-client overhead is just one `asyncio.Queue` (~few KB).

### 2.3 Refetch-on-notify, not push-the-payload

Each event carries only `{type, resource_id, timestamp}`, **not** the full updated resource. The frontend reacts by refetching the affected resource via the existing typed REST client.

Trade-off accepted:

- **Pro:** Backend has one canonical place that serializes each resource (the existing GET endpoint). No duplicated serialization in the publisher. No risk of streamed payload diverging from polled payload.
- **Pro:** Eliminates a whole class of "list-mutation" bugs (insert vs upsert vs delete on the client).
- **Pro:** Auth/RBAC, when added in a future phase, applies automatically — the frontend refetch goes through the normal authorized API path.
- **Con:** One extra HTTP request per event. At our event rate (single-digit per minute on idle, single-digit per second during a `credential_theft_chain` run), this is a non-issue. Each refetch is a single small JSON payload.

**Exception** — the `wazuh.status_changed` event embeds its full `WazuhStatus` payload because (a) it's tiny, (b) the badge has no meaningful "fetch detail" endpoint beyond what's in the event. A clean special-case, not a slippery slope.

### 2.4 One multiplexed endpoint with topic filter

A single `GET /v1/stream?topics=incidents,actions,detections,evidence,wazuh` per browser tab. The server filters the stream to the requested topics before sending. Default (no `topics` param) = all topics.

**Why one endpoint, not five:**

- One TCP/HTTP connection per tab (instead of five).
- Simpler client code (one hook, not one per resource).
- No coordinated reconnect across multiple streams.

### 2.5 Heartbeat + reconnect

- Server emits an SSE comment line `: hb\n\n` every 20s on each connection. Keeps idle connections from being dropped by intermediate proxies, the OS, or browser timeouts.
- `EventSource` auto-reconnects on transport error. Server respects standard `Last-Event-ID` header on reconnect — but **resume is not implemented in Phase 13**: on reconnect, the client just refetches all visible resources (same as a page load). This is honest and avoids a ring-buffer or persisted event log.

### 2.6 Polling as a safety net

The frontend hook keeps a **slow 60s background poll** running while SSE is connected. If the stream silently stalls (no events for some pathological reason — e.g., publisher crash after commit), the slow poll catches it within a minute. If SSE fails to connect after 3 attempts in 30s, the hook falls back to the existing 5s/10s polling cadence and shows a small "Live updates unavailable — polling" indicator.

### 2.7 No auth gate (current scope)

CyberCat is single-operator lab-only (`CLAUDE.md` §4). No auth middleware exists today (`backend/app/main.py`). The SSE endpoint inherits this posture. When multi-operator auth lands (separate future phase), the SSE endpoint gets the same `Depends(current_user)` as everything else.

---

## 3. Event Taxonomy (the streaming contract)

All events share this envelope:

```json
{
  "id": "01HV4XZK...",          // ULID — for Last-Event-ID, monotonic per process
  "type": "incident.created",    // dot-namespaced, see table below
  "topic": "incidents",          // routing key, used for ?topics= filter
  "ts": "2026-04-24T17:32:14.812Z",
  "data": { ... }                // shape depends on type — see below
}
```

### 3.1 Topic / type matrix

| Topic        | Event type                       | `data` payload                                                                | Emitted from                                                        |
|--------------|----------------------------------|------------------------------------------------------------------------------|---------------------------------------------------------------------|
| `incidents`  | `incident.created`               | `{incident_id, kind, severity}`                                              | `backend/app/ingest/pipeline.py` after `await db.commit()`         |
| `incidents`  | `incident.updated`               | `{incident_id, change: "extended" \| "elevated"}`                            | `backend/app/ingest/pipeline.py` (extended), `elevate_severity.py` |
| `incidents`  | `incident.transitioned`          | `{incident_id, from_status, to_status}`                                      | `backend/app/api/routers/incidents.py:transition_incident`         |
| `detections` | `detection.fired`                | `{detection_id, rule_id, incident_id?, severity}`                            | `backend/app/ingest/pipeline.py` (after detection batch)            |
| `actions`    | `action.proposed`                | `{action_id, incident_id, kind}`                                             | `backend/app/api/routers/responses.py:propose_response`            |
| `actions`    | `action.executed`                | `{action_id, incident_id, kind, result}` (`result` may be `partial`)         | `backend/app/api/routers/responses.py:execute_response`            |
| `actions`    | `action.reverted`                | `{action_id, incident_id, kind}`                                             | `backend/app/api/routers/responses.py:revert_response`             |
| `evidence`   | `evidence.opened`                | `{evidence_request_id, incident_id, kind}`                                   | via `action.executed` of `request_evidence` (also explicit emit)    |
| `evidence`   | `evidence.collected`             | `{evidence_request_id, incident_id}`                                         | `backend/app/api/routers/evidence_requests.py:collect_evidence_request` |
| `evidence`   | `evidence.dismissed`             | `{evidence_request_id, incident_id}`                                         | `backend/app/api/routers/evidence_requests.py:dismiss_evidence_request` |
| `wazuh`      | `wazuh.status_changed`           | full `WazuhStatus` shape (`{enabled, reachable, lag_seconds, ...}`)          | `backend/app/ingest/wazuh_poller.py` on transition only             |

**Notes:**

- `blocked_observable.added/reverted` is intentionally **not** its own topic — those events are observable through `action.executed`/`action.reverted` of kind `block_observable`. The dedicated `BlockedObservablesBadge` re-fetches on `action.*` events affecting that kind. Keeps the taxonomy minimal.
- `wazuh.status_changed` fires **only on transition** (e.g., `reachable: true → false`, or `enabled` flip), not every poll cycle. Avoids a once-per-second event flood from the poller.
- All `incident_id` / `action_id` fields are UUID strings (matches existing schemas).

### 3.2 Redis channel naming

- Pattern: `cybercat:stream:<topic>` — e.g. `cybercat:stream:incidents`.
- Subscriber uses `PSUBSCRIBE cybercat:stream:*` so adding a topic is a one-line publisher change.
- These channels do **not** collide with existing dedup/cooldown keys (those use `correlator:`, `dedup:`, etc. — different namespace).

---

## 4. Backend Changes

### 4.1 New module: `backend/app/streaming/`

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `publish`, `StreamEvent`, `EventBus` |
| `events.py`   | Pydantic `StreamEvent` model + `EventType` Literal union + `Topic` enum + `topic_for(event_type)` helper. **Single source of truth for the event taxonomy in §3.** |
| `publisher.py` | `async def publish(event_type: EventType, data: dict) -> None` — builds the envelope (assigns ULID `id`, sets `ts`, derives `topic`), serializes to JSON, calls `redis.publish(channel, payload)`. Never raises — wraps Redis errors in a `logger.warning` so domain operations are never broken by streaming failures. |
| `bus.py`     | `EventBus` class. On `start()`: opens a Redis pub/sub connection, runs `psubscribe("cybercat:stream:*")`, spawns a consumer task that reads messages and pushes them onto every registered `asyncio.Queue`. Provides `register() -> Queue`, `unregister(queue)`. On `stop()`: cancels consumer task, closes pubsub. Singleton, accessed via `get_bus()`. |

### 4.2 New router: `backend/app/api/routers/streaming.py`

- `GET /v1/stream` — Returns a `StreamingResponse` with media type `text/event-stream`.
- Query param: `topics` — optional comma-separated topic filter (e.g. `?topics=incidents,actions`). Default = all topics.
- Per-connection lifecycle:
  1. Parse + validate `topics` against the `Topic` enum (400 if bogus).
  2. `queue = bus.register()`.
  3. Async generator yields:
     - On every event from queue → if event's topic in filter → format as `id: <ulid>\nevent: <type>\ndata: <json>\n\n`.
     - Every 20s with no event → yield `: hb\n\n` (heartbeat comment).
  4. On client disconnect (or any exception in the generator) → `bus.unregister(queue)` in a `finally`.
- Response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (proxy hint), `Connection: keep-alive`.

### 4.3 Modifications to existing files

| File | Change |
|------|--------|
| `backend/app/main.py` (lifespan, around `:30-44`) | Construct `EventBus`, `await bus.start()` after `init_redis()`, store on `app.state.event_bus`. On shutdown, `await bus.stop()` before `close_redis()`. |
| `backend/app/main.py` (router registration) | Register the new streaming router (`app.include_router(streaming.router)`). |
| `backend/app/ingest/pipeline.py` (after the commit at `:69` and after correlator/auto-action commit at `:74`) | Emit `incident.created` for fresh incidents returned from `run_correlators()`; emit `incident.updated` for ones touched but not created; emit one `detection.fired` per row from `run_detectors()`. All emits happen **after the commit succeeds**. Wrap in `try/except` so a Redis hiccup does not break ingest. |
| `backend/app/api/routers/incidents.py` (`transition_incident`, `:383-441`) | After `await db.commit()` at `:434`: `await publish("incident.transitioned", {incident_id, from_status, to_status})`. |
| `backend/app/api/routers/responses.py` (`propose_response`, `:115`) | After commit: `await publish("action.proposed", {action_id, incident_id, kind})`. |
| `backend/app/api/routers/responses.py` (`execute_response`, `:137`) | After commit: `await publish("action.executed", {action_id, incident_id, kind, result})`. If `kind == "request_evidence"` and result was `ok`, also emit `evidence.opened`. |
| `backend/app/api/routers/responses.py` (`revert_response`, `:163`) | After commit: `await publish("action.reverted", {action_id, incident_id, kind})`. |
| `backend/app/api/routers/evidence_requests.py` (`collect_evidence_request`, `:65-78`) | After commit at `:77`: `await publish("evidence.collected", {evidence_request_id, incident_id})`. |
| `backend/app/api/routers/evidence_requests.py` (`dismiss_evidence_request`, `:81-93`) | After commit at `:92`: `await publish("evidence.dismissed", {evidence_request_id, incident_id})`. |
| `backend/app/response/handlers/elevate_severity.py` (after the in-handler severity write) | After the calling router commits — coordinate via emit-after-commit at the executor level instead. **Implementation note:** add a single emit point in `backend/app/response/executor.py` *or* keep it at the router. Prefer router-level (already touched above) — `execute_response` checks if the executed action was `elevate_severity` and emits an additional `incident.updated` with `change: "elevated"`. |
| `backend/app/ingest/wazuh_poller.py` (around the cursor commit at `:209`) | Track previous `(reachable, enabled)` tuple in module-level state. On a transition only, emit `wazuh.status_changed` with the full status payload. No emit on every cycle. |

**Critical convention:** every `await publish(...)` call sits **after** the relevant `await db.commit()` and is wrapped so that a publish failure is logged but never raised. The DB is the source of truth; streaming is best-effort.

### 4.4 Tests

| File | Cases |
|------|-------|
| `backend/tests/unit/test_streaming_publisher.py` (new) | (1) `publish` builds correct envelope (id is ULID, ts is ISO8601 UTC, topic derived from type). (2) `publish` calls `redis.publish` with the right channel + JSON payload. (3) Redis raise → `publish` logs and returns (no raise). |
| `backend/tests/unit/test_streaming_event_bus.py` (new) | (1) `register` returns a fresh queue and adds to internal set. (2) Subscriber task forwards a message to all registered queues. (3) `unregister` removes the queue and a subsequent message does not block. |
| `backend/tests/integration/test_sse_stream.py` (new) | (1) `GET /v1/stream` opens, receives heartbeat within 25s. (2) `POST /v1/events/raw` (synthetic auth-failed burst that fires `identity_compromise`) → SSE client receives `incident.created`. (3) Topic filter: `?topics=actions` does not deliver `incident.*` events. (4) Multiple concurrent SSE clients all receive the same event. (5) Client disconnect → `bus.unregister` is called (verify via internal queue count). |
| `backend/tests/integration/test_response_action_emits.py` (new) | (1) Propose action → `action.proposed` event. (2) Execute → `action.executed`. (3) Revert (where reversible) → `action.reverted`. (4) Execute `request_evidence` → both `action.executed` AND `evidence.opened`. |

All integration tests use the existing `AsyncClient(transport=ASGITransport(app=app))` pattern from `backend/tests/conftest.py` and the real Redis from compose. SSE tests use `client.stream("GET", "/v1/stream", ...)` and read the stream line by line with a per-test 5s timeout.

### 4.5 Dependencies

- **No new Python packages.** `redis` (already a dep) supports pub/sub. `ulid-py` is small but optional — if we want zero new deps, generate sortable IDs with `time.time_ns()` + 4 random bytes hex-encoded (sufficient for `Last-Event-ID`).

---

## 5. Frontend Changes

### 5.1 New module: `frontend/app/lib/streaming.ts`

Hand-written types and a low-level `EventSource` wrapper.

```ts
export type StreamTopic = 'incidents' | 'detections' | 'actions' | 'evidence' | 'wazuh';

export type StreamEvent =
  | { type: 'incident.created';      data: { incident_id: string; kind: string; severity: string } }
  | { type: 'incident.updated';      data: { incident_id: string; change: 'extended' | 'elevated' } }
  | { type: 'incident.transitioned'; data: { incident_id: string; from_status: string; to_status: string } }
  | { type: 'detection.fired';       data: { detection_id: string; rule_id: string; incident_id?: string; severity: string } }
  | { type: 'action.proposed';       data: { action_id: string; incident_id: string; kind: string } }
  | { type: 'action.executed';       data: { action_id: string; incident_id: string; kind: string; result: string } }
  | { type: 'action.reverted';       data: { action_id: string; incident_id: string; kind: string } }
  | { type: 'evidence.opened';       data: { evidence_request_id: string; incident_id: string; kind: string } }
  | { type: 'evidence.collected';    data: { evidence_request_id: string; incident_id: string } }
  | { type: 'evidence.dismissed';    data: { evidence_request_id: string; incident_id: string } }
  | { type: 'wazuh.status_changed';  data: WazuhStatus };
```

Plus `connectStream(topics, onEvent, onStatusChange)` which:

- Opens an `EventSource` to `${API_BASE_URL}/v1/stream?topics=${topics.join(',')}`.
- Calls `onEvent(parsedEvent)` for every `MessageEvent`.
- Reports connection state (`'connecting' | 'open' | 'reconnecting' | 'failed'`) via `onStatusChange`.
- After 3 connection failures within 30s, marks state `'failed'` and stops; consumers fall back to polling.
- Returns `{ close }` for cleanup.

### 5.2 New hook: `frontend/app/lib/useStream.ts`

Drop-in replacement for `usePolling.ts`'s shape — same `{ data, error, isLoading }` return — but driven by SSE.

```ts
useStream<T>({
  topics: StreamTopic[],
  fetcher: () => Promise<T>,
  shouldRefetch: (event: StreamEvent) => boolean,  // filter callback
  fallbackPollMs?: number,                          // safety-net poll, default 60_000
})
```

Behavior:

1. Initial `fetcher()` call to populate `data`.
2. Open SSE via `connectStream`.
3. For each event where `shouldRefetch(event) === true`, debounce-and-refetch (300ms coalescing window so a burst of 5 detections fires one refetch, not 5).
4. Slow background poll every `fallbackPollMs` regardless (safety net).
5. On `'failed'` connection state, fall back to fast polling at the original interval (5s for detail, 10s for lists) and show a passive `<StreamStatusBadge>` indicator.
6. Visibility-aware: on tab hidden, close the SSE; on visible, reopen + refetch (mirrors current `usePolling` behavior).

### 5.3 New component: `frontend/app/components/StreamStatusBadge.tsx`

Tiny pill in the top-nav next to `WazuhBridgeBadge`:

- Green dot + "Live" → SSE connected.
- Amber dot + "Reconnecting" → mid-reconnect.
- Grey dot + "Polling" → fallback mode.

Hidden by default; shown only when state is non-green (avoids visual noise).

### 5.4 Modifications to existing pages

| File | Change |
|------|--------|
| `frontend/app/incidents/page.tsx` (`:102`) | Replace `usePolling(fetchIncidents, 10_000)` with `useStream({ topics: ['incidents'], fetcher: fetchIncidents, shouldRefetch: e => e.type.startsWith('incident.') })`. |
| `frontend/app/incidents/[id]/page.tsx` (`:406`) | Replace `usePolling(fetchIncident, 5_000)` with `useStream({ topics: ['incidents','detections','actions','evidence'], fetcher, shouldRefetch: e => 'incident_id' in e.data && e.data.incident_id === id })`. |
| `frontend/app/actions/page.tsx` (`:176`) | `useStream({ topics: ['actions'], fetcher, shouldRefetch: e => e.type.startsWith('action.') })`. |
| `frontend/app/detections/page.tsx` (`:130`) | `useStream({ topics: ['detections'], fetcher, shouldRefetch: e => e.type === 'detection.fired' })`. |
| `frontend/app/components/WazuhBridgeBadge.tsx` (`:24`) | `useStream({ topics: ['wazuh'], fetcher: fetchWazuhStatus, shouldRefetch: () => false })` plus a direct subscription to `wazuh.status_changed` events that **replaces state in-place** from the embedded payload (no refetch). The only special-case payload-carrying event. |
| `frontend/app/layout.tsx` | Add `<StreamStatusBadge />` adjacent to existing `<WazuhBridgeBadge />`. |
| `frontend/app/lib/usePolling.ts` | Keep as-is — `useStream` uses it internally as the fallback polling mechanism. Add a one-line `// Used by useStream as fallback; do not delete.` comment. |

### 5.5 Tests

- `frontend/app/lib/__tests__/useStream.test.tsx` — using a `MockEventSource` (a small in-test class that exposes `dispatchEvent`), assert: (a) initial fetch fires; (b) matching event triggers refetch; (c) non-matching event does not; (d) burst of events coalesces to one refetch within debounce window; (e) connection failure after 3 attempts triggers polling fallback.

---

## 6. Documentation

| File | Change |
|------|--------|
| `docs/decisions/ADR-0008-realtime-streaming.md` (new) | Records: SSE over WebSocket; Redis Pub/Sub for fan-out; refetch-on-notify (not push-the-payload); single multiplexed `/v1/stream`; polling as safety net; auth deferred. |
| `docs/streaming.md` (new) | The contract — full event taxonomy table from §3 of this plan, channel naming, envelope shape, examples of `curl -N http://localhost:8000/v1/stream` for ops debugging. |
| `docs/architecture.md` | Add a "Streaming layer" subsection between "Response policy" and "Analyst frontend" describing the EventBus + publisher pattern. |
| `docs/runbook.md` | Add "Tailing the live event stream" section: `curl -N http://localhost:8000/v1/stream`. |
| `PROJECT_STATE.md` | New "Phase 13" section using the same shape as Phase 11/12 (status, new files, modified files, key design decisions, verification steps). Update header date and "Status summary". Move Phase 14 ship-story note down — Phase 13 is now the next phase. |
| `project-explanation/CyberCat-Explained.md` | Add a Phase 13 entry to §15 ("Where the project stands today") and remove item #7 from §16 (now shipped). |

---

## 7. Smoke Test

`labs/smoke_test_phase13.sh` (new, ~20 checks). Mirrors the structure of `labs/smoke_test_phase10.sh`.

1. Verify `/v1/stream` responds with `text/event-stream` content type and the connection stays open >2s.
2. Open SSE in background (`curl -N -m 30 ... > /tmp/stream.log &`), capture PID.
3. Run `python -m labs.simulator credential_theft_chain --speed 0.1 --verify`.
4. Wait 5s after simulator completes.
5. `kill $SSE_PID` to flush.
6. Grep `/tmp/stream.log` and assert presence of:
   - At least one `event: incident.created`
   - At least one `event: detection.fired`
   - At least one `event: incident.updated` (chain elevation)
   - The `incident_id` from the resulting identity_compromise incident appears in at least one event.
7. Topic filter test: open `?topics=actions`, fire scenario, assert log contains zero `incident.*` events.
8. Heartbeat test: open stream with no traffic for 25s, assert at least one `: hb` line received.
9. Multi-client fan-out: open two parallel `curl` streams, fire one event, assert both logs contain it.
10. Reconnect test: open stream, kill backend (`docker compose restart backend`), wait for backend healthy, fire event, assert frontend's `EventSource`-equivalent (a fresh `curl -N`) reconnects and receives.

---

## 8. Implementation Order

Each step is independently mergeable and verifiable. Follow in order.

1. **Backend skeleton** — create `backend/app/streaming/{__init__,events,publisher,bus}.py` with no callers yet. Unit-test publisher and bus in isolation (no SSE endpoint, no emit calls).
2. **SSE endpoint** — add `backend/app/api/routers/streaming.py`. Wire bus into lifespan in `main.py`. Verify `curl -N http://localhost:8000/v1/stream` returns event-stream and a heartbeat.
3. **Wire emit calls one router at a time**, in this order (each a small, testable diff):
   - `pipeline.py` — incidents + detections (highest-value events).
   - `responses.py` — actions.
   - `incidents.py` — transitions.
   - `evidence_requests.py` — evidence.
   - `wazuh_poller.py` — status (with transition detection).
   After each: run the matching integration test from §4.4, then `pytest` (full suite) for zero regressions.
4. **Frontend low-level wiring** — `streaming.ts` types + `connectStream()`; manual smoke via dev tools (no UI changes yet).
5. **`useStream` hook** + unit tests with `MockEventSource`.
6. **Migrate UI sites in this order** (smallest blast radius first):
   - `WazuhBridgeBadge.tsx` (single small pill).
   - `actions/page.tsx`.
   - `detections/page.tsx`.
   - `incidents/page.tsx`.
   - `incidents/[id]/page.tsx` (most complex — multi-topic filter).
   After each: browser-verify the page updates without a manual refresh on a triggered event.
7. **`StreamStatusBadge`** + layout integration.
8. **Smoke test script** (`smoke_test_phase13.sh`) — run end-to-end.
9. **Docs** — ADR-0008, `streaming.md`, architecture/runbook updates.
10. **PROJECT_STATE.md** — mark Phase 13 verified with date.

---

## 9. Verification

Phase 13 is **done** when all of the following are true:

- `pytest backend/tests` — green (existing 93 tests + ~15 new = ~108).
- `npm run typecheck` (`tsc --noEmit`) in `frontend/` — 0 errors.
- `bash labs/smoke_test_phase13.sh` — all checks pass.
- All existing smoke tests (`smoke_test_phase{3,5,6,7,8,9a,10,11}.sh`) — still pass (zero regressions).
- Manual browser check: open `/incidents` in two tabs, fire `python -m labs.simulator credential_theft_chain --speed 0.1`, observe new incident appearing in **both** tabs within ~1s of the simulator finishing (vs. up to 10s on polling).
- Manual browser check: stop backend container; UI shows `StreamStatusBadge: Reconnecting` then `Polling`; restart backend; badge returns to green.
- `curl -N http://localhost:8000/v1/stream` from the runbook works as documented.

---

## 10. Critical Files Reference

For the agent implementing this — these are the load-bearing files to read first before editing:

- `backend/app/main.py:30-44` — lifespan pattern; the `EventBus.start()` slots in here.
- `backend/app/ingest/pipeline.py:30-80` — the chokepoint for incident/detection events.
- `backend/app/api/routers/responses.py:107-211` (and the executor it calls) — action lifecycle commits.
- `backend/app/api/routers/incidents.py:383-441` — `transition_incident` is the single place status changes commit.
- `backend/app/db/redis.py:10-24` — Redis client shape; the bus uses the same `get_redis()` pattern but opens its own pubsub connection (a `redis.client.PubSub` cannot be shared across consumers).
- `backend/tests/conftest.py` — `AsyncClient` test pattern + Redis flush; copy-paste-friendly for the new SSE tests.
- `frontend/app/lib/usePolling.ts` — the abstraction `useStream` mirrors and reuses for fallback.
- `docs/decisions/ADR-0007-wazuh-active-response-dispatch.md` — formatting template for ADR-0008.
- `docs/phase-11-plan.md` (or whichever exists) and `PROJECT_STATE.md`'s Phase 11 section — formatting template for the Phase 13 entry.

---

## 11. Out of Scope (deliberately deferred)

- **Auth on the stream** — comes with the multi-operator phase (roadmap #10). Whatever auth wraps `/v1/incidents` will trivially wrap `/v1/stream`.
- **Event resume via `Last-Event-ID`** — frontend refetches on reconnect; no ring buffer or persistent event log. Add later only if the demo shows a real gap.
- **Push-the-payload events** — only `wazuh.status_changed` carries data today. Convert other events later if profiling shows refetch overhead matters (it won't at lab scale).
- **Per-event filtering by entity / severity** — topic-level filter only. Add `?incident_id=...` later if a use case appears.
- **Browser notifications / desktop alerts** — UI polish, separate phase.
- **Rate limiting / backpressure** — at lab scale (≤5 connected tabs, ≤100 events/min), not needed. If a real SOC use ever happens, add a per-connection token bucket on the bus.
