# Streaming Reference

CyberCat exposes a Server-Sent Events (SSE) endpoint that pushes lightweight notifications when domain state changes.

## Endpoint

```
GET /v1/stream
```

Optional query parameter `topics`: comma-separated filter. Default = all topics.

```
GET /v1/stream?topics=incidents,actions
GET /v1/stream?topics=wazuh
```

Valid topics: `incidents`, `detections`, `actions`, `evidence`, `wazuh`.

An invalid topic value returns HTTP 400.

## Event Envelope

Every event has this shape:

```json
{
  "id": "0195f3a2b4e800008a1f",
  "type": "incident.created",
  "topic": "incidents",
  "ts": "2026-04-24T17:32:14.812Z",
  "data": { ... }
}
```

The SSE wire format wraps the envelope as:

```
id: 0195f3a2b4e800008a1f
event: incident.created
data: {"incident_id": "...", "kind": "identity_compromise", "severity": "high"}

```

## Event Taxonomy

| Topic        | Event type                | `data` payload                                                                |
|--------------|---------------------------|------------------------------------------------------------------------------|
| `incidents`  | `incident.created`        | `{incident_id, kind, severity}`                                              |
| `incidents`  | `incident.updated`        | `{incident_id, change: "extended" \| "elevated"}`                            |
| `incidents`  | `incident.transitioned`   | `{incident_id, from_status, to_status}`                                      |
| `detections` | `detection.fired`         | `{detection_id, rule_id, incident_id?, severity}`                            |
| `actions`    | `action.proposed`         | `{action_id, incident_id, kind}`                                             |
| `actions`    | `action.executed`         | `{action_id, incident_id, kind, result}`                                     |
| `actions`    | `action.reverted`         | `{action_id, incident_id, kind}`                                             |
| `evidence`   | `evidence.opened`         | `{evidence_request_id, incident_id, kind}`                                   |
| `evidence`   | `evidence.collected`      | `{evidence_request_id, incident_id}`                                         |
| `evidence`   | `evidence.dismissed`      | `{evidence_request_id, incident_id}`                                         |
| `wazuh`      | `wazuh.status_changed`    | `{enabled, reachable, last_error}`                                           |

## Redis Channel Naming

Pattern: `cybercat:stream:<topic>` — e.g. `cybercat:stream:incidents`.

The subscriber uses `PSUBSCRIBE cybercat:stream:*`. These channels do not collide with existing correlation/dedup keys (`correlator:`, `dedup:`, etc.).

## Heartbeat

The server emits an SSE comment every 20 seconds when no events are flowing:

```
: hb

```

This keeps idle connections alive through proxies and browser timeouts.

## Ops Debugging

Tail the live stream with curl:

```bash
curl -N http://localhost:8000/v1/stream
```

Filter to a single topic:

```bash
curl -N "http://localhost:8000/v1/stream?topics=incidents"
```

Observe heartbeats only (no events expected):

```bash
curl -N "http://localhost:8000/v1/stream?topics=wazuh"
```
