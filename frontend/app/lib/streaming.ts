"use client"

export type StreamTopic =
  | "incidents"
  | "detections"
  | "actions"
  | "evidence"
  | "wazuh"

export type StreamEvent =
  | { type: "incident.created"; data: { incident_id: string; kind: string; severity: string } }
  | { type: "incident.updated"; data: { incident_id: string; change: "extended" | "elevated" } }
  | { type: "incident.transitioned"; data: { incident_id: string; from_status: string; to_status: string } }
  | { type: "detection.fired"; data: { detection_id: string; rule_id: string; incident_id?: string | null; severity: string | null } }
  | { type: "action.proposed"; data: { action_id: string; incident_id: string; kind: string } }
  | { type: "action.executed"; data: { action_id: string; incident_id: string; kind: string; result: string } }
  | { type: "action.reverted"; data: { action_id: string; incident_id: string; kind: string } }
  | { type: "evidence.opened"; data: { evidence_request_id: string; incident_id: string; kind: string } }
  | { type: "evidence.collected"; data: { evidence_request_id: string; incident_id: string } }
  | { type: "evidence.dismissed"; data: { evidence_request_id: string; incident_id: string } }
  | { type: "wazuh.status_changed"; data: { enabled: boolean; reachable: boolean; last_error: string | null } }

export type StreamStatus = "connecting" | "open" | "reconnecting" | "failed"

const ALL_EVENT_TYPES: StreamEvent["type"][] = [
  "incident.created",
  "incident.updated",
  "incident.transitioned",
  "detection.fired",
  "action.proposed",
  "action.executed",
  "action.reverted",
  "evidence.opened",
  "evidence.collected",
  "evidence.dismissed",
  "wazuh.status_changed",
]

const MAX_FAILURES = 3
const FAILURE_WINDOW_MS = 30_000

interface ConnectOptions {
  topics: StreamTopic[]
  onEvent: (event: StreamEvent) => void
  onStatusChange: (status: StreamStatus) => void
}

interface Connection {
  close: () => void
}

export function connectStream(opts: ConnectOptions): Connection {
  const { topics, onEvent, onStatusChange } = opts
  const url =
    (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") +
    `/v1/stream?topics=${topics.join(",")}`

  let es: EventSource | null = null
  let closed = false
  let failureTimestamps: number[] = []

  function connect() {
    if (closed) return
    onStatusChange("connecting")
    es = new EventSource(url)

    es.onopen = () => {
      onStatusChange("open")
    }

    es.onerror = () => {
      if (closed) return
      const now = Date.now()
      failureTimestamps = failureTimestamps.filter((t) => now - t < FAILURE_WINDOW_MS)
      failureTimestamps.push(now)

      if (failureTimestamps.length >= MAX_FAILURES) {
        onStatusChange("failed")
        es?.close()
        es = null
        return
      }

      onStatusChange("reconnecting")
      // EventSource reconnects automatically; we only track failure count
    }

    for (const eventType of ALL_EVENT_TYPES) {
      es.addEventListener(eventType, (e: MessageEvent) => {
        if (closed) return
        try {
          const data = JSON.parse(e.data)
          onEvent({ type: eventType, data } as StreamEvent)
        } catch {
          // malformed event — skip
        }
      })
    }
  }

  connect()

  return {
    close() {
      closed = true
      es?.close()
      es = null
    },
  }
}
