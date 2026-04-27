# Phase 4 Execution Plan — Analyst Frontend

Scope: incident list + incident detail, read-only. Written 2026-04-20.

Read this first, then `PROJECT_STATE.md`, then `docs/api-contract.md` §3 (Incidents) and `docs/scenarios/identity-endpoint-chain.md` §"t = ~5 min — Analyst inspects". Those three define the contract, the pixels, and the data respectively.

---

## 0. Why this phase matters (don't skip this)

CyberCat's pitch is **explainable, threat-informed incident response**, not another alert list. The frontend is the first place a viewer decides whether this is a serious product or a student project. Phase 4 is where that judgment gets made.

The backend already stores every piece of evidence an incident is built from: events linked with roles, detections with `matched_fields`, ATT&CK rows with `source`, correlator `rationale`, action classifications, transitions. If the UI renders all of that honestly, CyberCat visibly does what most SOAR tools only claim.

### Design principles that make this stand out

1. **Explainability is the hero, not a footnote.** The rationale block is large and prominent. Timeline rows carry `role_in_incident` badges (trigger / supporting / context) so an analyst sees *why* each event is here. Detections expose `matched_fields` inline, not buried in a modal.
2. **ATT&CK is structured, not a tag cloud.** Render tactic → technique → subtechnique hierarchy with `source` badges (`rule_derived` vs `correlator_inferred`). Click a technique → deep link to MITRE.
3. **Every action advertises its blast radius.** Classification badges (`auto_safe` / `suggest_only` / `reversible` / `disruptive`) are visually distinct. No mystery buttons. Phase 4 is read-only so we only *render* these — Phase 5 wires the execute path, but the visual language ships now.
4. **Timeline is grouped by entity, not by time alone.** Per the scenario doc, the analyst thinks "what did alice do" and "what happened on this host" — the UI should reflect that mental model. Flat chronological fallback is available via toggle.
5. **Confidence math is auditable.** The detail panel shows the per-detection `severity_hint` / `confidence_hint` components that fed the incident's overall scores.
6. **Polling is invisible.** Data refreshes in place without spinners flashing. Analysts should never feel the network; they should feel the investigation.

These are the details that separate this from a generic CRUD admin panel. Hold the line on all six.

---

## 1. Pre-work (do this before writing any frontend code)

### 1a. Verify Phase 3 end-to-end

Per `PROJECT_STATE.md` §"What needs to happen next session". Without a real incident in the DB, the frontend is guessing.

```bash
cd infra/compose
docker compose build backend
docker compose up -d
```

Then POST 4× `auth.failed` + 1× `auth.succeeded` for `alice@corp.local` from `203.0.113.7`. Confirm:
- 4th failure → `detections_fired` non-empty.
- `auth.succeeded` → both `detections_fired` and `incident_touched` populated.
- `GET /v1/incidents` returns the incident (title, severity=high, kind=identity_compromise).
- `GET /v1/incidents/{id}` returns all junctions populated.

If any step fails, fix Phase 3 before continuing.

### 1b. Backend CORS

Add `CORSMiddleware` to `backend/app/main.py` allowing `http://localhost:3000`, credentials off, all methods/headers. Keep it env-driven so it doesn't ship permissive into any future non-lab build.

### 1c. Path reality check

PROJECT_STATE's old Phase 4 section referenced `frontend/src/app/...`. The actual tree is `frontend/app/...` (Next.js 15 default). Use `frontend/app/` throughout. Do not introduce `src/`.

### 1d. Env plumbing

- `frontend/.env.local` (dev, gitignored): `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
- `infra/compose/docker-compose.yml`: set the same env on the `frontend` service.
- No hardcoded URLs in code. Every fetch reads `process.env.NEXT_PUBLIC_API_BASE_URL`.

---

## 2. Decisions locked for Phase 4

| Decision | Choice | Reason |
|---|---|---|
| Styling | **Tailwind CSS** | Fast path to a polished, consistent look; ubiquitous; no bespoke CSS to maintain. Add via `npm install -D tailwindcss postcss autoprefixer` and `npx tailwindcss init -p`. |
| API client | **Hand-typed** in `frontend/app/lib/api.ts` | Schema surface is small and stable for v1. Defer OpenAPI codegen to Phase 5+. |
| Data fetching | **Client components + polling** | API contract §11 commits to polling over WebSocket/SSE in v1. Keeps the backend simple. |
| Poll intervals | List: 10s. Detail: 5s while visible, paused when tab hidden (`document.visibilityState`). | Balance of freshness and server load during a demo. |
| Routing | App Router, server layout, client pages | Next.js 15 default. Server layout for the shell, client components for the polling pages. |
| State | Local `useState` + custom `usePolling` hook | Avoid bringing in SWR/React Query for v1; if caching/dedup becomes painful, revisit in Phase 5. |
| Dependency budget | Tailwind, `clsx`, `date-fns`. No component library. | "No abstractions beyond what the task requires" — we can add shadcn/ui later if needed. |

---

## 3. Work plan

Numbered the way it should be built.

### 3.1 Styling scaffold

- Install Tailwind and wire `globals.css`.
- `app/layout.tsx`: replace the placeholder; add a top nav with CyberCat wordmark and a single `Incidents` link. Set dark-mode-friendly defaults — analysts live in dark UIs.
- Pick a base palette and stick to it. Suggested: neutral zinc background, accent indigo, semantic severity colors below.

Severity → Tailwind color (text / bg / border):
- `info`: zinc-400 / zinc-800 / zinc-700
- `low`: sky-300 / sky-900 / sky-700
- `medium`: amber-300 / amber-900 / amber-700
- `high`: orange-300 / orange-900 / orange-700
- `critical`: red-300 / red-900 / red-600

Status pill colors — use neutral for `new` / `triaged`, blue for `investigating`, amber for `contained`, green for `resolved`, zinc-muted for `closed`.

### 3.2 API client (`frontend/app/lib/api.ts`)

Mirror `backend/app/api/schemas/incidents.py` 1:1. Enum unions duplicated from `backend/app/enums.py`.

Types:
- `IncidentSummary`, `IncidentList`, `IncidentDetail`
- `EntityRef`, `DetectionRef`, `TimelineEvent`, `AttackRef`
- `ActionSummary`, `ActionLogSummary`, `TransitionRef`, `NoteRef`
- Enum unions: `IncidentStatus`, `Severity`, `IncidentKind`, `EntityKind`, `ActionKind`, `ActionClassification`, `ActionStatus`, `RoleInIncident`

Functions:
- `listIncidents(params: ListIncidentsParams): Promise<IncidentList>`
- `getIncident(id: string): Promise<IncidentDetail>`

Error handling:
- `ApiError extends Error` with `code`, `message`, `details`, `status`.
- Non-2xx → parse the problem envelope per `api-contract.md` §Conventions and throw `ApiError`.
- 404 on detail → caller distinguishes and renders a "not found" page.

Hard rule: **no `any`** in product code. `unknown` + narrowing when the shape is external.

### 3.3 Shared UI primitives (`frontend/app/components/`)

Small, composable, no state unless needed:

- `SeverityBadge({ severity }: { severity: Severity })`
- `StatusPill({ status }: { status: IncidentStatus })`
- `ConfidenceBar({ value }: { value: number })` — 0–1 decimal, shows percentage and a visual bar
- `RelativeTime({ at }: { at: string })` — refreshes every minute via `setInterval`
- `AttackTag({ id, name?, source }: ...)` — renders `T1059.001` with link to `https://attack.mitre.org/techniques/T1059/001/`; small badge for `rule_derived` vs `correlator_inferred`
- `ActionClassificationBadge({ kind })` — strong visual distinction between the four classifications
- `Panel({ title, children })` — consistent section wrapper
- `JsonBlock({ data })` — collapsible, monospaced, syntax-muted rendering for `matched_fields`, `normalized`, `attrs`, `params`
- `EntityChip({ entity })` — color by `EntityKind`, shows `natural_key` truncated with tooltip
- `EmptyState({ title, hint })`
- `ErrorState({ error, onRetry })`
- `SkeletonCard` / `SkeletonRow`

### 3.4 Polling hook (`frontend/app/lib/usePolling.ts`)

Small custom hook. Signature: `usePolling<T>(fetcher: () => Promise<T>, intervalMs: number): { data, error, loading, refetch }`.

Behavior:
- First fetch on mount; background refetch on interval.
- Pause when `document.visibilityState === "hidden"`.
- Abort in-flight requests on unmount.
- Never replace `data` with `undefined` on refetch error — keep last-good and surface error separately so the UI doesn't blank.

### 3.5 Incident list (`frontend/app/incidents/page.tsx`)

Client component. Polls `listIncidents()` every 10s.

Layout:
- Filter bar (top): status multi-select, severity_gte select, Clear button. Filters encode in URL search params so links are shareable.
- Incident cards grid (1 column mobile, 2 column tablet, 3 column desktop).

Card contents:
- Top row: `SeverityBadge`, `StatusPill`, `RelativeTime` on `opened_at`.
- Title (truncated to 2 lines with `line-clamp-2`).
- Primary entities line: user chip, host chip (if present).
- Counts row: events, detections, entities (icons + numbers).
- Click anywhere on card → `/incidents/{id}` via Next `<Link>`.

Pagination:
- "Load more" button using `next_cursor`. Appends to existing list. Keep state simple — a `useState<IncidentSummary[]>` that grows.

States:
- Loading (initial): 6 skeleton cards.
- Empty: `"No incidents yet. Seed one via POST /v1/events/raw — see docs/runbook.md."`
- Error: `ErrorState` with retry.
- Filter returns zero: `"No incidents match these filters."` with a Clear action.

### 3.6 Incident detail (`frontend/app/incidents/[id]/page.tsx`)

Client component. `params.id` → `getIncident(id)` every 5s.

Layout (desktop, two-column where useful):

**Header (full width):**
- Title (large).
- Meta row: `SeverityBadge`, `StatusPill`, `ConfidenceBar`, `kind`, `correlator_rule@correlator_version`, `opened_at` + `updated_at` + `closed_at` (if set) as `RelativeTime`.

**Rationale panel (full width, visually prominent):**
- Large typographic block, monospace-comfortable line length (~80ch max).
- Label: "Why this is one incident" so the intent is obvious to non-analysts viewing a demo.

**Two-column grid below:**

Left column — the evidence:
- **Timeline panel.** Toggle: "By entity" (default) / "Chronological". Each event row shows `occurred_at`, `kind`, source badge, `role_in_incident` badge, a compact summary pulled from `normalized` (kind-specific — auth events show user+source_ip, process events show image+pid, session events show user+host+session_id), and entity chips. Row expands to show full `normalized` JSON.
- **Detections panel.** One row per `DetectionRef`: `rule_id`, `rule_source` (`sigma` | `py`), `severity_hint`, `confidence_hint`, ATT&CK tag list, `matched_fields` in a collapsible `JsonBlock`.

Right column — the shape and response:
- **Entities panel.** Grouped by `EntityKind`. Each entity shows `natural_key`, `role_in_incident`, `first_seen`/`last_seen`, and `attrs` in a collapsible `JsonBlock`.
- **ATT&CK panel.** Grouped by tactic. Inside each tactic, technique and subtechnique rows. Each row has `AttackTag` + `source` badge.
- **Actions panel.** One row per action: `kind`, `ActionClassificationBadge`, `status`, `proposed_by`, `proposed_at`, `last_log` summary if present. Params in `JsonBlock`. **No execute/revert buttons in Phase 4** — these land in Phase 5 once the backend endpoints exist. Leave space in the component for them so it's a small diff later.
- **Transitions panel.** Vertical timeline of `TransitionRef`: `from_status → to_status`, actor, reason, at.
- **Notes panel.** List only for Phase 4.

States:
- Loading: skeleton header + 4 skeleton panels.
- 404: full-page "Incident not found" + link back to list.
- Error: `ErrorState` above the content; keep showing last-good data if available.

### 3.7 Layout shell touch-ups

- `app/layout.tsx`: top nav with wordmark + Incidents link; dark theme; sets `lang="en"` and a sensible font stack. Keep it minimal.
- `app/page.tsx`: change the Phase 0 placeholder to redirect to `/incidents` (Next's `redirect('/incidents')` from `next/navigation`).

### 3.8 Nice-to-have polish (only if core is done and tested)

- **Tab title badge.** Show the open-incident count in the browser tab title when on `/incidents`. Subtle but makes the product feel alive.
- **Keyboard shortcut.** `g i` → go to incidents (from detail page). Small, but signals "made for analysts".
- **Copy-to-clipboard** on incident ID and entity natural keys.
- **Entity chip hover card** showing recent events count.

Cut any of these if they slip the phase.

---

## 4. Verification gate (Phase 4 is not "done" until all of these pass)

Concrete checks. Each must be exercised manually; don't claim any without running it.

1. `npm run typecheck` in `frontend/` is clean. Zero `any` in product code.
2. `docker compose build frontend && docker compose up -d` builds and serves without errors.
3. Empty-state list: visit `/incidents` against an empty DB → empty state renders, not a blank page or crash.
4. Replay the Phase 3 smoke test (`POST` 4× `auth.failed` + 1× `auth.succeeded` for alice). List updates within one poll cycle (≤10s).
5. Card renders: severity badge `high`, status `new`, primary user `alice@corp.local`, primary host empty at this stage, counts correct (events=5, detections=2, entities=2).
6. Click into detail — all seven panels render with real data:
   - Header + rationale present
   - Timeline shows 5 events with correct roles
   - Entities shows alice + 203.0.113.7
   - Detections shows both detection records with `matched_fields`
   - ATT&CK shows at least T1110, T1110.003, T1078
   - Actions panel shows proposed + executed auto-tag actions (if Phase 3 creates them; if not, shows empty state for actions — still a pass)
   - Transitions shows the initial `null → new` transition
7. Tab switch: hide the tab → polling pauses (verify via browser devtools network panel). Show the tab → polling resumes and UI re-syncs within 5s.
8. Kill backend (`docker compose stop backend`) while the detail page is open: UI shows error banner, does not blank out, keeps last-good data.
9. Browser dark mode default works; light mode is not broken.
10. Load a bogus detail URL `/incidents/00000000-0000-0000-0000-000000000000` → 404 state with back link.

Only when 1–10 pass, update `PROJECT_STATE.md` to flip Phase 4 to complete and move to Phase 5.

---

## 5. Out of scope for Phase 4 (deferred, with the phase they belong to)

| Feature | Deferred to |
|---|---|
| `POST /v1/incidents/{id}/transitions` backend route + UI action | Phase 5 |
| `POST /v1/incidents/{id}/notes` backend + UI | Phase 5 |
| `POST /v1/responses/{id}/execute` + `/revert` backend + UI | Phase 5 |
| Entity detail page (`/entities/{id}`) | Phase 5 |
| `GET /v1/entities` search, entity cross-links in timeline | Phase 5 |
| OpenAPI → TS codegen pipeline | Phase 5 if surface grows, else Phase 6 |
| Auth / login | Post-v1 (per ADR-0001 / CLAUDE.md §4) |
| SSE / WebSocket push | Post-v1 (per `api-contract.md` §11) |
| Wazuh integration | Phase 8 (ADR-0004) |
| Lab seeder script | Phase 6 |

---

## 6. Risks and mitigations

- **Backend read-only means the scenario demo can't complete in-browser.** Analysts can't transition or execute. Mitigation: Phase 5 is next; until then, document that the Phase 4 demo ends at "analyst opens the incident and inspects evidence".
- **Incident detail payload size.** Fat incidents with many events and detections may push detail GET latency up. Mitigation: measure in Phase 4 verification; if P95 > 300ms on an incident with 20+ events, lower detail poll to 10s and note in PROJECT_STATE.
- **Polling-over-WebSocket means visible lag.** At 10s list poll, a freshly-created incident takes up to 10s to appear. Acceptable for v1; called out in api-contract.md §11.
- **Turbopack + Docker on Windows.** Hot reload is sometimes flaky. Mitigation: runbook already documents the local `npm run dev` fallback.
- **Color palette accessibility.** Severity colors must stay WCAG AA at minimum against dark background. Verify contrast before closing the phase.

---

## 7. Handoff note for Phase 5

Things Phase 5 will want from us:
- The action panel should have dedicated space reserved for the execute / revert buttons — design it now, wire later.
- The transition panel should have space for a "transition incident" affordance next to the current status in the header — design now, wire later.
- The notes panel should have space for "add note" — design now, wire later.

Leaving visual placeholders makes Phase 5 a small diff instead of a layout shuffle.
