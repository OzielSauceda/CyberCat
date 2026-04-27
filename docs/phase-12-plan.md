# Phase 12 Plan — Analyst UX Polish

## Context

Phase 10 closed with the `identity_endpoint_chain` chain correlator and the `credential_theft_chain` attack simulator — the backend is now fully expressive. Phase 12 turns that expression into something visually compelling for a portfolio. All underlying data is already in the DB; this phase is purely presentation.

The goal: **screenshots become portfolio-grade.** An interviewer looking at a single incident detail page should immediately understand what happened, where in the ATT&CK kill chain it sits, and how the entities relate — without reading a word of prose.

**Status:** Implemented 2026-04-23 — awaiting owner browser verification.

---

## Deliverables

### 1. ATT&CK Kill Chain Strip (`AttackKillChainPanel.tsx`) ✅ implemented

**Replaces** the old list-based `AttackPanel`.

**What it shows:** The full ATT&CK Enterprise kill chain (all 14 tactics in canonical order: Reconnaissance → Impact) as a compact horizontal strip. Matched tactics are highlighted in indigo; unmatched are dim zinc. Below the strip, matched tactics expand to show their techniques with MITRE links and source badges.

**Design decisions:**
- 14 tactics in correct ATT&CK order — immediately readable as a kill-chain progression
- R badge (zinc) = rule-derived technique; C badge (violet) = correlator-inferred
- Technique count bubble on each matched tactic box
- `›` separator between boxes; adjacent matched boxes get an indigo separator
- Scrollable on narrow viewports (`overflow-x-auto`)
- Placed **full-width** between the rationale box and the two-column grid — first thing a reviewer sees after context

**Implementation notes:**
- Tactic slugs match the format stored in `AttackRef.tactic` (e.g. `"credential-access"`, `"initial-access"`)
- `AttackTagRow` local helper uses `useAttackEntry(id)` for MITRE name lookup (same pattern as the old `AttackTagWithName`)
- No backend changes; no new data required

---

### 2. Graphical Attack Timeline (`IncidentTimelineViz.tsx`) ✅ implemented

**What it shows:** A full-width SVG horizontal timeline. Events are plotted as dots at their exact timestamps on a time axis. Detection triangles appear above the baseline, connected to their triggering events by dashed lines.

**Visual encoding:**
- X axis: time (relative from first event, labeled +0s / +60s / etc.)
- Dot color by layer:
  - `auth.*` → indigo (identity layer)
  - `process.*` / `file.*` → lime (endpoint layer)
  - `network.*` → cyan
  - `session.*` → emerald
  - other → zinc
- Dot size/style by role:
  - `trigger` → large (r=9) with glow halo
  - `supporting` → medium (r=6) solid
  - `context` → small (r=4) hollow outline, 45% opacity
- Detection triangles (amber) with dashed connectors to triggering event via `DetectionRef.event_id`

**Design decisions:**
- Pure SVG, no external lib, responsive via `viewBox` + `width="100%"`
- Tooltip tracks actual mouse cursor position (container `onMouseMove` + absolute div) — avoids SVG→screen coordinate conversion complexity
- Tooltip clips to left of cursor when near right edge
- Skips render entirely when `events.length === 0` (no placeholder)
- Placed full-width immediately below the ATT&CK strip

---

### 3. Entity Relationship Graph (`EntityGraphPanel.tsx`) ✅ implemented

**What it shows:** A pure SVG graph with one node per incident entity and edges between entities that co-occur in timeline events.

**Layout:** Circular arrangement — N entities placed evenly on a circle. Works cleanly for 1–8 entities (typical incident has 2–5).

**Visual encoding:**
- Node color: same palette as `EntityChip` (indigo=user, violet=host, cyan=ip, lime=process, yellow=file, pink=observable)
- Node radius: proportional to event count (min 14, max 22)
- Kind abbreviation (USR/HST/IP/PRO/FIL/OBS) inside node circle
- Natural key label below node; role label in small muted text below that
- Edge: dashed line, weight = number of co-occurring events
- On hover: hovered node gets a glow ring; all other nodes and non-adjacent edges dim to 22% opacity; adjacent edges brighten + show weight label ("N×")
- Click: navigates to `/entities/{id}` via `useRouter`

**Design decisions:**
- No react-flow or cytoscape — pure SVG with O(N²) edge computation. Keeps the bundle lean; works perfectly for small N.
- Edges computed from `timeline.entity_ids` pairwise co-occurrence — no new API endpoint needed
- Placed in the right column, above the existing Entities list panel, so there's visual context before the raw entity cards

---

## File map

```
frontend/app/incidents/[id]/
├── AttackKillChainPanel.tsx    ← NEW
├── EntityGraphPanel.tsx        ← NEW
├── IncidentTimelineViz.tsx     ← NEW
├── page.tsx                    ← MODIFIED (3 imports, 3 new usages, AttackPanel removed)
├── ActionsPanel.tsx            (unchanged)
├── ActionControls.tsx          (unchanged)
├── NotesPanel.tsx              (unchanged)
└── ProposeActionModal.tsx      (unchanged)
```

**Deleted (logically):** The inline `AttackPanel` function and `AttackTagWithName` helper from `page.tsx` — fully superseded by `AttackKillChainPanel.tsx`.

---

## New incident detail page layout

```
[Header: title, severity, status, confidence, correlator, timestamps]
[Rationale box]
[ATT&CK Kill Chain — full width]         ← Phase 12
[Graphical Timeline — full width]        ← Phase 12
[Two-column grid]
  ├── Left:
  │     TimelinePanel (list view, existing)
  │     DetectionsPanel (existing)
  └── Right:
        EntityGraphPanel                  ← Phase 12
        EntitiesPanel (existing)
        ActionsPanel (existing)
        EvidenceRequestsPanel (existing)
        TransitionsPanel (existing)
        NotesPanel (existing)
```

---

## Verification checklist (owner to complete)

Run the frontend dev server (`cd frontend && npm run dev`) and open an incident seeded by the `credential_theft_chain` simulator (`python -m labs.simulator --scenario credential_theft_chain --speed 0.1`) for maximum data coverage.

### ATT&CK Kill Chain
- [ ] 14 tactic boxes render in correct order left-to-right
- [ ] Matched tactics (credential-access, initial-access, execution likely) highlight in indigo
- [ ] Technique count badge visible on matched tactics
- [ ] R / C source badges visible
- [ ] Matched technique rows with MITRE names appear below strip
- [ ] No overflow / clipping on standard viewport

### Graphical Timeline
- [ ] Events appear as dots at correct relative positions
- [ ] Layer colors correct (auth=indigo, process=lime, network=cyan)
- [ ] Trigger events have visible glow; context events are hollow
- [ ] Detection triangles (amber) appear above baseline
- [ ] Dashed connectors from detections to their triggering events
- [ ] Hover tooltip shows kind, time, role, source
- [ ] Time axis labels readable

### Entity Graph
- [ ] Nodes render with correct kind colors
- [ ] Kind abbreviation visible inside each node
- [ ] Natural key + role label below each node
- [ ] Edges drawn between co-occurring entities
- [ ] Hover dims non-adjacent nodes/edges, shows weight label
- [ ] Click on node navigates to entity detail page

### Regressions
- [ ] Timeline list, Detections, Entities list, Actions, Evidence, Transitions, Notes panels all intact
- [ ] No JS errors in browser console

---

## Dependencies and risks

- **No new npm dependencies added.** The graph and timeline are pure SVG. Bundle size unchanged.
- **No backend changes.** All data comes from `IncidentDetail` already fetched by the page's `usePolling` hook.
- **SVG tooltip pixel coords.** The timeline tooltip uses `onMouseMove` on the container div for absolute pixel tracking — tested to work with responsive SVG `viewBox`. If container padding changes, tooltip may need offset adjustment.
- **Circular layout crowding.** With more than 8 entities the circular layout may crowd node labels. Acceptable for current incident scale; can add a force-directed fallback in a future phase.
- **Tactic slug format.** `AttackKillChainPanel` assumes `AttackRef.tactic` is stored as a slug (e.g. `"credential-access"`). This matches how all existing correlators write the field. If a new correlator writes a different format, the strip won't highlight that tactic.

---

## Future phases (not Phase 12)

See `docs/phase-10-plan&more.md` for the full roadmap. After Phase 12 verification:

- **Phase 11** — Wazuh Active Response dispatch (real OS side-effects on quarantine/kill)
- **Phase 13** — Ship story (README rewrite, demo GIF, public repo, case study write-up)
