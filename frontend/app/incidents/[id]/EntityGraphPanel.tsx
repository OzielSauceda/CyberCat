"use client"

import { useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Panel } from "../../components/Panel"
import { EmptyState } from "../../components/EmptyState"
import type { EntityRef, TimelineEvent, EntityKind } from "../../lib/api"

const NODE_COLORS: Record<EntityKind, { fill: string; stroke: string; text: string }> = {
  user:       { fill: "#1e1b4b", stroke: "#6366f1", text: "#a5b4fc" },
  host:       { fill: "#2e1065", stroke: "#7c3aed", text: "#c4b5fd" },
  ip:         { fill: "#083344", stroke: "#0891b2", text: "#67e8f9" },
  process:    { fill: "#1a2e05", stroke: "#65a30d", text: "#bef264" },
  file:       { fill: "#422006", stroke: "#d97706", text: "#fde68a" },
  observable: { fill: "#500724", stroke: "#db2777", text: "#f9a8d4" },
}

const SVG_W = 560
const SVG_H = 260
const CX = SVG_W / 2
const CY = SVG_H / 2

interface GraphNode {
  entity: EntityRef
  x: number
  y: number
  eventCount: number
}

interface GraphEdge {
  source: string
  target: string
  weight: number
}

function computeLayout(
  entities: EntityRef[],
  events: TimelineEvent[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const eventsByEntity = new Map<string, number>()
  for (const e of entities) eventsByEntity.set(e.id, 0)

  for (const ev of events) {
    for (const eid of ev.entity_ids) {
      if (eventsByEntity.has(eid)) {
        eventsByEntity.set(eid, (eventsByEntity.get(eid) ?? 0) + 1)
      }
    }
  }

  const edgeMap = new Map<string, number>()
  for (const ev of events) {
    const linked = ev.entity_ids.filter((id) => eventsByEntity.has(id))
    for (let i = 0; i < linked.length; i++) {
      for (let j = i + 1; j < linked.length; j++) {
        const key = [linked[i], linked[j]].sort().join("|")
        edgeMap.set(key, (edgeMap.get(key) ?? 0) + 1)
      }
    }
  }

  const n = entities.length
  const R = n <= 1 ? 0 : Math.min(CX, CY) * (n <= 4 ? 0.52 : 0.62)

  const nodes: GraphNode[] = entities.map((entity, i) => {
    const angle = n <= 1 ? 0 : (2 * Math.PI * i) / n - Math.PI / 2
    return {
      entity,
      x: CX + R * Math.cos(angle),
      y: CY + R * Math.sin(angle),
      eventCount: eventsByEntity.get(entity.id) ?? 0,
    }
  })

  const edges: GraphEdge[] = Array.from(edgeMap.entries()).map(([key, weight]) => {
    const [source, target] = key.split("|")
    return { source, target, weight }
  })

  return { nodes, edges }
}

export function EntityGraphPanel({
  entities,
  events,
}: {
  entities: EntityRef[]
  events: TimelineEvent[]
}) {
  const router = useRouter()
  const [hovered, setHovered] = useState<string | null>(null)
  const { nodes, edges } = useMemo(() => computeLayout(entities, events), [entities, events])

  if (entities.length === 0) {
    return (
      <Panel title="Entity graph">
        <EmptyState title="No entities linked" />
      </Panel>
    )
  }

  const nodeMap = new Map(nodes.map((n) => [n.entity.id, n]))

  return (
    <Panel title="Entity graph" count={entities.length}>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        width="100%"
        style={{ display: "block", maxHeight: SVG_H }}
        role="img"
        aria-label="Entity relationship graph"
      >
        {/* Edges */}
        {edges.map((edge) => {
          const src = nodeMap.get(edge.source)
          const tgt = nodeMap.get(edge.target)
          if (!src || !tgt) return null
          const highlighted = hovered === edge.source || hovered === edge.target
          const dimmed = hovered !== null && !highlighted

          return (
            <g key={`edge-${edge.source}-${edge.target}`} opacity={dimmed ? 0.12 : 1}>
              <line
                x1={src.x} y1={src.y}
                x2={tgt.x} y2={tgt.y}
                stroke={highlighted ? "#6366f1" : "#3f3f46"}
                strokeWidth={highlighted ? Math.min(edge.weight + 1, 5) : 1.5}
                strokeDasharray={highlighted ? undefined : "5 4"}
              />
              {highlighted && (
                <text
                  x={(src.x + tgt.x) / 2}
                  y={(src.y + tgt.y) / 2 - 6}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#a1a1aa"
                  fontFamily="ui-monospace, monospace"
                >
                  {edge.weight}×
                </text>
              )}
            </g>
          )
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const colors = NODE_COLORS[node.entity.kind as EntityKind] ?? NODE_COLORS.observable
          const r = Math.min(Math.max(14, 10 + node.eventCount * 1.5), 22)
          const isHov = hovered === node.entity.id
          const dimmed = hovered !== null && !isHov
          const label =
            node.entity.natural_key.length > 18
              ? node.entity.natural_key.slice(0, 16) + "…"
              : node.entity.natural_key

          return (
            <g
              key={node.entity.id}
              transform={`translate(${node.x},${node.y})`}
              onMouseEnter={() => setHovered(node.entity.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => router.push(`/entities/${node.entity.id}`)}
              style={{ cursor: "pointer" }}
              opacity={dimmed ? 0.22 : 1}
            >
              {isHov && (
                <circle r={r + 7} fill={colors.stroke} opacity={0.12} />
              )}
              <circle
                r={r}
                fill={colors.fill}
                stroke={colors.stroke}
                strokeWidth={isHov ? 2.5 : 1.5}
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={9}
                fill={colors.stroke}
                fontFamily="ui-monospace, monospace"
                fontWeight="bold"
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {node.entity.kind.slice(0, 3).toUpperCase()}
              </text>
              <text
                y={r + 12}
                textAnchor="middle"
                fontSize={10}
                fill={isHov ? colors.text : "#a1a1aa"}
                fontFamily="ui-monospace, monospace"
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {label}
              </text>
              {node.entity.role_in_incident && (
                <text
                  y={r + 24}
                  textAnchor="middle"
                  fontSize={8}
                  fill={isHov ? "#71717a" : "#3f3f46"}
                  fontFamily="ui-monospace, monospace"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {node.entity.role_in_incident}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </Panel>
  )
}
