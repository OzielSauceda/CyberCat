# ADR-0008 — Real-Time Streaming via SSE

**Status:** Accepted  
**Date:** 2026-04-24  
**Deciders:** Oziel (owner)

---

## Context

The analyst UI was "soft real-time" via polling — five GETs every 5–10 seconds per browser tab. Two costs:

1. **Latency** — analysts see incidents up to 10s after they exist. For the `credential_theft_chain` demo (~30s), that is ~30% of run time wasted waiting.
2. **Wasted work** — every tab issues five queries per minute regardless of whether anything changed.

The goal of Phase 13 is to replace polling with a server-pushed event stream so incidents, detections, actions, evidence, and Wazuh bridge state update instantly.

---

## Decisions

### 1. SSE, not WebSocket

CyberCat needs server→client only — no client→server messages over the stream. SSE wins:

- Auto-reconnect is built into `EventSource` (no application logic needed).
- HTTP-native — inherits CORS and the existing `CORSMiddleware` setup with no upgrade handshake.
- Trivially testable via `httpx.AsyncClient` + `ASGITransport`.
- WebSocket requires a custom reconnect loop and carries full-duplex complexity we do not need.

### 2. Redis Pub/Sub for fan-out, in-process queues for delivery

The backend runs one uvicorn worker. In-process fan-out would technically suffice, but Redis Pub/Sub is used because:

- It matches the architecture rule: "Redis is for ephemeral coordination — never the system of record" (`CLAUDE.md` §2).
- It future-proofs for `--workers 2+` with zero code change.
- Cost is one ~1ms hop on localhost, well within the latency budget.

One Redis subscriber per backend process — not one per SSE connection. Per-connection overhead is one `asyncio.Queue` (~a few KB).

### 3. Refetch-on-notify, not push-the-payload

Each event carries only `{type, resource_id, timestamp}` metadata. The frontend reacts by refetching the affected resource via the existing typed REST client.

- Pro: One canonical serialization path (the existing GET endpoints). No duplicated serialization in the publisher.
- Pro: Eliminates list-mutation bugs (insert vs upsert vs delete on the client).
- Pro: Auth/RBAC (future phase) applies automatically — refetch goes through the authorized API path.
- Con: One extra HTTP request per event. At lab-scale event rates this is a non-issue.

**Exception:** `wazuh.status_changed` triggers a refetch of `/v1/wazuh/status` (same refetch-on-notify pattern — no embedded payload in Phase 13).

### 4. Single multiplexed endpoint with topic filter

`GET /v1/stream?topics=incidents,actions,detections,evidence,wazuh` — one connection per tab.

- One TCP/HTTP connection per tab instead of five polling timers.
- Simpler client code (one hook, one filter callback).

### 5. Polling as safety net

The frontend `useStream` hook keeps a slow 60s background poll even while SSE is connected. If SSE fails after 3 attempts in 30s, the hook falls back to faster polling and shows a `StreamStatusBadge` indicator.

### 6. Auth deferred

CyberCat is single-operator lab-only. No auth middleware exists. The SSE endpoint inherits this posture. When multi-operator auth lands, `/v1/stream` gets the same `Depends(current_user)` as every other endpoint.

### 7. Event resume not implemented

On reconnect the frontend refetches all visible resources (same as a page load). No ring-buffer or persisted event log is maintained. This is honest about the trade-off and avoids persistent storage complexity. Add `Last-Event-ID` resume later if a real demo gap is observed.

---

## Consequences

- Analyst UI updates within ~1s of domain events instead of up to 10s.
- One SSE connection replaces five polling intervals per tab.
- No new Python packages required (`redis` asyncio pub/sub already a dep).
- The streaming layer is entirely best-effort — a Redis failure logs a warning but never breaks a domain operation.
