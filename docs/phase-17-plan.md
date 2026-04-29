# Phase 17 — Detective Console: Frontend Redesign for First-Time Users

## Context

CyberCat's frontend is **visually cohesive but assumes expert knowledge**. From the audit:

- `/` redirects straight to `/incidents` — there is no welcome surface; a fresh repo user lands on a list of jargon-coded cards with no orientation.
- Every domain term (`incident`, `detection`, `ATT&CK technique`, `confidence`, `reversible action`, `event kind`, `entity`, `correlator`) is rendered without explanation. The audit confirmed there is no glossary, no tooltips, no help page anywhere in the app.
- Empty states are generic ("No incidents") with no guidance on how to get data flowing.
- Nav links (`Lab`, `Actions`, `Detections`) are bare text — no icons, titles, or descriptions.
- The three flagship SVG visualizations (kill chain, timeline, entity graph) are polished but unlabeled — a non-security user sees colored dots and tactic IDs with no legend.
- Aesthetic is functional zinc dark mode — well-engineered, but anonymous. Doesn't match the project's "patient detective" narrative.

**Outcome we want:** A stranger who clones the repo and runs `./start.sh` should land on a page that *tells them what they are looking at*, *shows them real data immediately*, and *lets them learn the vocabulary by hovering* — without leaving the app.

**Aesthetic decision:** Pure **detective / case-file motif** across all views (user picked the case-file preview). Working views become "dossiers" with evidence-board layouts and typewriter accents on a warm-on-dark base. This honors the README's "patient detective" framing and gives the product a distinctive identity that is rare in security tooling.

**Dependency budget:** Add `framer-motion`, `@radix-ui/react-tooltip`, `@radix-ui/react-dialog`, `@radix-ui/react-popover`, `@radix-ui/react-dropdown-menu`. ~50–80 KB gzip total. We still own all visual styling — Radix only handles accessibility primitives.

**Phase numbering:** Becomes Phase 17. Existing optional Go rewrite shifts to Phase 18; existing optional token-rotation/dedup shifts to Phase 19. Detection-as-code pipeline takes the next slot after this phase ships.

---

## Hand-off notes (read before coding — these are easy to miss)

These four items are the gotchas most likely to bite an executor who reads only the relevant sub-phase. They are reinforced inline below; this section is the canonical list.

1. **Renumber `PROJECT_STATE.md` as part of 17.8, don't skip it.** `PROJECT_STATE.md:31-33` (and the "Order of work going forward" list above it) currently references the old Phase 17 (Go rewrite) and Phase 18 (token rotation/multi-source dedup). After this phase ships, those become Phase 18 and Phase 19 respectively. If the renumber is skipped, the project doc contradicts itself and future sessions will not know which Phase 17 is real. Also update the same numbers wherever they appear in `Project Brief.md`, `CyberCat-Explained.md`, and any `docs/phase-*-plan.md` cross-references.

2. **Auto-seed needs the advisory lock + seed marker, not just the env var.** `credential_theft_chain` is idempotent within an hour via Redis dedup keys, but a backend restart that crosses an hour boundary will re-seed and produce duplicate incidents. The safety net is **both**: a Postgres advisory lock (so concurrent backend replicas don't race) **and** a `seed_marker` row (or `cybercat:demo_active` Redis key) the seeder writes once and the startup hook checks before re-running. `CCT_AUTOSEED_DEMO=true` alone is insufficient.

3. **`DELETE /v1/admin/demo-data` must truncate every table touched by the seed scenario.** Plan currently lists `events`, `incidents`, `detections`, `actions` but the live model graph is wider — check `backend/app/models/` before coding. At minimum confirm: `event_entities`, `entities`, `incident_events`, `incident_detections`, `incident_entities`, `incident_attack`, `incident_transitions`, `action_logs`, `evidence_requests`, `blocked_observables`, `lab_sessions`, `lab_assets`, `wazuh_cursor`. Anything missed leaves orphan FK rows or stale cursor state. **Preserve** `users` and `api_tokens` always. Use `TRUNCATE ... CASCADE` inside a single transaction; do not delete table-by-table.

4. **`labs/smoke_test_phase17.sh` runs first, not last.** A broken auto-seed will poison every existing smoke (they all assume control over event ingestion). Phase 17 smoke must run before `smoke_test_agent.sh`, `smoke_test_phase16_9.sh`, `smoke_test_phase16_10.sh`, etc. Either rename the file with a leading `00_` prefix, or update whatever runner script orders the suite. Each pre-existing smoke must also `CCT_AUTOSEED_DEMO=false` in its env or call the demo-wipe endpoint at start, otherwise a stray restart mid-suite will silently re-seed.

---

## Sub-phase plan

### 17.1 — Design system foundation (case-file tokens)

Establish the visual vocabulary before touching pages.

**Files:**
- `frontend/package.json` — add `framer-motion`, `@radix-ui/react-tooltip`, `@radix-ui/react-dialog`, `@radix-ui/react-popover`, `@radix-ui/react-dropdown-menu`.
- `frontend/tailwind.config.ts` — extend theme with case-file tokens:
  - `colors.dossier.{paper, paperEdge, ink, redaction, evidenceTape, stamp}`
  - `fontFamily.case` (typewriter / monospace serif hybrid for case headers)
  - `boxShadow.dossier` (soft inner shadow mimicking folder edge)
  - `backgroundImage.foldermark` (subtle SVG pattern for page chrome)
- `frontend/app/globals.css` — import case-header font (e.g., `Special Elite` or `Courier Prime` via next/font/google), keep `IBM Plex Mono` for IDs/code.
- **NEW** `frontend/app/lib/theme-tokens.ts` — central export of the named token strings so components don't hardcode hex.

**Verification:** `npm run typecheck` clean; visual smoke by rendering one example component in a Storybook-less ad-hoc preview page (`/_design`) that we delete at end of phase.

---

### 17.2 — Case-file shell (top nav, chrome, help affordance)

Reframe the app frame as a "case board." This is the chrome every page inherits.

**Files:**
- `frontend/app/layout.tsx` — new top nav: each link gets an icon (incidents=folder-open, detections=magnifier, actions=stamp, lab=flask, help=question-circle) + Radix Tooltip with one-line description. Right side: existing status badges (`StreamStatusBadge`, `WazuhBridgeBadge`, `UserBadge`) restyled as "operator credentials."
- **NEW** `frontend/app/components/CaseBoard.tsx` — wrapper component giving every page the dossier-edge frame (warm border on the left, foldermark watermark, case number in the corner).
- **NEW** `frontend/app/components/HelpMenu.tsx` — header (?) button opening a Radix Popover with: "What is this app?", "Open glossary", "Restart tour", "Read the runbook."
- `frontend/app/components/StreamStatusBadge.tsx`, `UserBadge.tsx`, `WazuhBridgeBadge.tsx` — restyle to match the case-file token palette; preserve all behavior.

**Verification:** Every existing page renders inside the new shell without functional regression; nav tooltips appear; help popover opens.

---

### 17.3 — Welcome landing page at `/`

Replace `app/page.tsx` (currently a redirect) with a real home.

**Files:**
- `frontend/app/page.tsx` — full rewrite. Sections:
  1. **Header strip** — "CYBERCAT // CASE BOARD" with current operator name + open-case count.
  2. **What is this?** — three-card row: *"What CyberCat does"*, *"What it isn't"* (lifted from CyberCat-Explained.md §3), *"How an investigation flows"* (mini diagram).
  3. **Get started** — three action cards: *"See an investigation in progress"* (links to first open incident, or runs the demo scenario if empty), *"Browse rules"* (links to /detections), *"Try a response action"* (links to a pre-loaded incident with the actions panel highlighted).
  4. **Live system status** — open incidents, detections fired today, agent + Wazuh source health, last event ingested.
  5. **For first-time users** — "Take the 3-minute tour" button (triggers the guided tour from 17.5) and a link to the glossary.
- Update `frontend/app/lib/api.ts` if needed to support a single "home dashboard" GET that bundles the counts (or compose existing endpoints client-side — prefer the latter to avoid backend churn).

**Verification:** Cold load with empty DB shows the auto-seeded demo data (17.6) and the welcome page; cold load with existing data shows real numbers.

---

### 17.4 — Glossary system (jargon → plain English)

Make every domain term hover-explainable. Touches every page.

**Files:**
- **NEW** `frontend/app/lib/glossary.ts` — typed dictionary keyed by term slug:
  ```ts
  export const GLOSSARY = {
    incident: { title: "Incident", short: "A grouped story...", long: "..." },
    detection: { ... },
    "attack-technique": { ... },
    confidence: { ... },
    "reversible-action": { ... },
    // ...~30 terms
  } satisfies Record<string, GlossaryEntry>;
  ```
- **NEW** `frontend/app/components/JargonTerm.tsx` — wraps any text node: `<JargonTerm slug="incident">incident</JargonTerm>`. Renders dotted underline + Radix Tooltip with `short` + "Read more →" linking to `/help#incident`.
- **NEW** `frontend/app/help/page.tsx` — renders the full glossary as a single scrollable page with anchored sections, sample screenshots (small inline SVGs), and a "How an investigation works" walkthrough.
- Apply `<JargonTerm>` across:
  - `frontend/app/incidents/page.tsx` — wrap "incident", "severity", "status", "kind" labels.
  - `frontend/app/incidents/[id]/page.tsx` — wrap correlator name, "confidence," "ATT&CK kill chain," "tactic," "technique."
  - `frontend/app/components/AttackKillChainPanel.tsx` — wrap "tactic" / "technique" labels and add an inline legend.
  - `frontend/app/components/IncidentTimelineViz.tsx` — wrap "event," "detection," and add a layer-color legend (identity / endpoint / network / session).
  - `frontend/app/components/EntityGraphPanel.tsx` — wrap "entity," "co-occurrence," and add a legend.
  - `frontend/app/components/ActionClassificationBadge.tsx` — wrap each classification.
  - `frontend/app/detections/page.tsx`, `frontend/app/actions/page.tsx`, `frontend/app/lab/page.tsx`, `frontend/app/entities/[id]/page.tsx` — wrap their respective domain terms.

**Verification:** Every jargon term shows a tooltip on hover; `/help` page lists all terms; click-through from tooltip lands on the right anchor.

---

### 17.5 — First-run guided tour

Three-step overlay that introduces the working concepts on first use.

**Files:**
- **NEW** `frontend/app/components/FirstRunTour.tsx` — Radix Dialog (modal-less variant) + framer-motion highlight ring. Steps:
  1. *"This is an incident."* — points at the first incident card on `/incidents`.
  2. *"This is the kill chain."* — points at the AttackKillChainPanel on `/incidents/[id]`.
  3. *"These are your response buttons."* — points at the ActionsPanel on `/incidents/[id]`.
  Each step: short paragraph + "Next" / "Skip tour" / "Re-run from Help."
- `localStorage.setItem("cybercat:tour:completed", "1")` flag prevents auto-replay; `HelpMenu` exposes a "Re-run tour" entry that clears the flag.
- Triggered from the welcome page CTA *and* automatically on first load if flag is unset and at least one incident exists.

**Verification:** Fresh browser profile auto-shows the tour; tour navigates correctly; "Skip" persists; "Re-run from Help" resets and replays.

---

### 17.6 — Auto-seed demo data on first boot

Without this, even the redesigned empty states leave a fresh repo user staring at nothing.

> **⚠ Hand-off note 2 applies here.** The advisory lock + `seed_marker` are non-optional. See "Hand-off notes" above for the full reasoning — `CCT_AUTOSEED_DEMO=true` alone will double-seed across hour boundaries.
>
> **⚠ Hand-off note 3 applies here.** The wipe-endpoint table list below is incomplete on purpose — verify against `backend/app/models/` before coding. Missing tables = orphan FK rows.

**Files:**
- `backend/app/main.py` (or the existing startup hook) — on FastAPI startup, if `CCT_AUTOSEED_DEMO=true` (default `true` for dev compose, `false` for production-ish profiles) AND `events` table is empty AND no `seed_marker` row exists, run `labs/simulator/scenarios/credential_theft_chain` in-process (or spawn a one-shot subprocess) at `--speed 0.1`. **Wrap the entire check + run in a Postgres advisory lock** (`pg_try_advisory_lock(<stable int key>)`) so concurrent backend replicas don't race. Write a `seed_marker` row (or set Redis key `cybercat:demo_active=1`) on success — the startup hook short-circuits on subsequent boots when it sees the marker.
- `infra/compose/.env.example` — document `CCT_AUTOSEED_DEMO`.
- `infra/compose/docker-compose.yml` — wire the env var into the `backend` service.
- **NEW** `frontend/app/components/DemoDataBanner.tsx` — slim header banner: "You're viewing seeded demo data. [Wipe and start fresh →]". The "Wipe" action calls a new admin-gated endpoint `DELETE /v1/admin/demo-data`. Hidden once the `seed_marker` is cleared (either by the wipe endpoint or by a future "first real ingestion" hook).
- **NEW** `backend/app/api/admin.py` (if absent — otherwise extend) — `DELETE /v1/admin/demo-data` gated by `require_admin`. Truncates **every table touched by the seed scenario** in a single transaction with `TRUNCATE ... CASCADE`. Verify the full list against `backend/app/models/` before coding; the seed scenario writes far more than `events`/`incidents`/`detections`/`actions` (it also fans out into `event_entities`, `entities`, the four incident junction tables, `incident_transitions`, `action_logs`, `evidence_requests`, `blocked_observables`, `lab_sessions`, `lab_assets`, and the `wazuh_cursor` row). **Preserve** `users` and `api_tokens` always. Clear the `seed_marker` row at the end of the same transaction.

**Verification:** Spin up clean stack with empty volumes → backend logs `seeding demo data...` → frontend lands on populated welcome page → banner shows → "Wipe" button clears + reverts to true empty state with onboarding empty-state copy.

---

### 17.7 — Case-file restyle of working views

Apply the new visual language to the pages users spend the most time on. Defer the long tail.

**Priority order:**
1. **Incident detail page** (`frontend/app/incidents/[id]/page.tsx`) — most visited. Header becomes a "case header" with case number, opened/updated stamps, status pill restyled as a stamp impression. Rationale box becomes a "summary of findings" inset. Right column reframed as "evidence panels."
2. **Incident list** (`frontend/app/incidents/page.tsx`) — cards become dossier rows: case number left, primary suspect/location middle, severity stamp right, evidence count strip at bottom.
3. **Empty states** (`frontend/app/components/EmptyState.tsx`) — case-file empty copy: *"The board is clear. No open cases."* with a "Run the demo scenario" CTA when in dev.
4. **SVG legends** added to `AttackKillChainPanel`, `IncidentTimelineViz`, `EntityGraphPanel`.
5. **Restyle** `SeverityBadge`, `StatusPill`, `EntityChip`, `Panel`, `ConfidenceBar`, `AttackTag`, `ActionClassificationBadge` to use case-file tokens — preserve all props/APIs to avoid touching call sites.
6. Out of scope this sub-phase: full restyle of `/detections`, `/actions`, `/lab`, `/entities/[id]` interiors. They inherit the new shell + glossary + chrome from 17.2/17.4 but keep their existing list/table layouts. They become a Phase 17.b candidate if the user wants polish parity.

**Verification:** Visual sweep with browser; `tsc --noEmit` clean; existing component tests pass.

---

### 17.8 — Documentation, ADR, verification

> **⚠ Hand-off note 1 applies here.** The renumber is the single most likely thing to be skipped. Do it as the *first* doc edit in this sub-phase, before writing the new ADR — otherwise the new docs will reference numbers that don't match `PROJECT_STATE.md`.
>
> **⚠ Hand-off note 4 applies here.** Phase 17 smoke runs *first*, not last. See ordering instructions below.

**Files:**
- **NEW** `docs/decisions/ADR-0014-frontend-detective-redesign.md` — records: case-file aesthetic decision, dependency choices (framer-motion + Radix), glossary system architecture, first-run tour mechanics, auto-seed contract.
- `docs/runbook.md` — new "First-run experience" section explaining `CCT_AUTOSEED_DEMO`, how to re-run the tour, where the glossary lives, how to wipe demo data.
- `Project Brief.md` — update vision-document language to mention the case-file frontend identity. **Also update any "Phase 17/18" references to the new numbering** (Go rewrite → 18, token rotation → 19).
- `CyberCat-Explained.md` — update §8/§9 to describe the welcome page, glossary, tour, and case-file styling. **Also sweep for stale phase numbers** — §15/§16 reference Phase 17/18 in the roadmap section.
- `PROJECT_STATE.md` — **do this first.** Add Phase 17 entry; renumber existing optional Phase 17 (Go rewrite) → Phase 18, and Phase 18 (token rotation/dedup) → Phase 19; update the "Order of work going forward" list at the top of the file (currently `PROJECT_STATE.md:31-33`).
- **Sweep** `docs/phase-*-plan.md` for any cross-references to the old Phase 17/18 numbers.
- **NEW** `labs/smoke_test_phase17.sh` — assertions: backend up, autoseed populated `events` table on empty start, `seed_marker` row present, `GET /` (frontend) returns 200 with welcome-page markers, `GET /help` returns 200 with glossary content, `DELETE /v1/admin/demo-data` clears every seeded table, post-wipe `events` count is 0 and `seed_marker` is gone, then every existing smoke test still passes.
- **Smoke ordering:** name the new file `labs/smoke_test_phase17.sh` but run it *first* in any aggregate runner. Either (a) prefix `00_` to the filename, (b) update whatever shell loop or CI step currently iterates `labs/smoke_test_*.sh` to put `phase17` first, or (c) add an explicit ordering list. Each pre-existing smoke (`smoke_test_agent.sh`, `smoke_test_phase15.sh`, `smoke_test_phase16_9.sh`, `smoke_test_phase16_10.sh`) must export `CCT_AUTOSEED_DEMO=false` at start, OR call `DELETE /v1/admin/demo-data` before its first ingest, otherwise a backend restart mid-suite silently re-seeds and pollutes assertions.

**Verification:**
- `cd backend && pytest` — should remain 173/173 (no backend logic change beyond the seed hook).
- `cd frontend && npm run typecheck` — 0 errors.
- All existing smoke tests pass: `smoke_test_agent.sh` 14/14, `smoke_test_phase16_9.sh` 15/15, `smoke_test_phase16_10.sh` 18/18.
- New smoke `labs/smoke_test_phase17.sh` passes.
- Manual browser verification on the operator's Lenovo: cold start with wiped volumes → welcome page → tour fires → glossary tooltip works on every term → wipe demo button clears state → empty state shows the "run demo scenario" CTA.

---

## Critical files to modify (quick index)

**Frontend (new):**
- `frontend/app/page.tsx` (rewrite)
- `frontend/app/help/page.tsx`
- `frontend/app/lib/glossary.ts`
- `frontend/app/lib/theme-tokens.ts`
- `frontend/app/components/JargonTerm.tsx`
- `frontend/app/components/CaseBoard.tsx`
- `frontend/app/components/HelpMenu.tsx`
- `frontend/app/components/FirstRunTour.tsx`
- `frontend/app/components/DemoDataBanner.tsx`

**Frontend (modify):**
- `frontend/package.json`, `frontend/tailwind.config.ts`, `frontend/app/globals.css`, `frontend/app/layout.tsx`
- `frontend/app/incidents/page.tsx`, `frontend/app/incidents/[id]/page.tsx`
- `frontend/app/components/{SeverityBadge,StatusPill,EntityChip,Panel,EmptyState,AttackKillChainPanel,IncidentTimelineViz,EntityGraphPanel,ActionClassificationBadge,ConfidenceBar,AttackTag,StreamStatusBadge,UserBadge,WazuhBridgeBadge}.tsx`
- All non-detail pages get `<JargonTerm>` wrapping only — no layout rewrite.

**Backend (modify, minimal):**
- `backend/app/main.py` — autoseed startup hook.
- `backend/app/api/admin.py` — `DELETE /v1/admin/demo-data` endpoint.
- `infra/compose/docker-compose.yml`, `infra/compose/.env.example` — `CCT_AUTOSEED_DEMO` plumbing.

**Docs:**
- `docs/decisions/ADR-0014-frontend-detective-redesign.md` (new)
- `docs/runbook.md`, `Project Brief.md`, `CyberCat-Explained.md`, `PROJECT_STATE.md` (update)
- `labs/smoke_test_phase17.sh` (new)

---

## Reuse / preserve

- **All existing reusable components keep their props and APIs.** SeverityBadge/StatusPill/etc. only change their internal Tailwind classes — call sites untouched.
- **All three SVG visualizations** (`AttackKillChainPanel`, `IncidentTimelineViz`, `EntityGraphPanel`) keep their data-binding logic — we only add legends + glossary wrapping.
- **All routing, auth, SSE, polling logic** unchanged.
- **`labs/simulator/scenarios/credential_theft_chain`** is reused as the auto-seed source — no new fixture authoring.
- **Existing `EmptyState` and `ErrorState` components** are restyled, not replaced.
- **Existing `frontend/app/lib/api.ts`** stays the typed client; we add no new endpoints beyond `DELETE /v1/admin/demo-data`.

---

## Out of scope (deliberately)

- Light theme. Dark-only stays.
- Mobile / responsive polish below tablet width — desktop-first remains.
- Full restyle of `/detections`, `/actions`, `/lab`, `/entities/[id]` interiors — those inherit the shell + glossary + chrome only. A follow-up "Phase 17.b" can do interior restyles if the user wants visual parity.
- New backend endpoints beyond the demo-wipe admin route.
- Internationalization. English-only.
- Storybook / component library scaffolding.
- Detection-as-code pipeline (deferred to next phase as agreed).

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Visual restyle accidentally breaks an SVG visualization | Restyle each viz in its own commit; keep a side-by-side `/lab/preview` page during the phase that renders before/after for QA. Delete at end. |
| Auto-seeding masks real ingestion bugs in dev | Banner is loud; `CCT_AUTOSEED_DEMO=false` is honored; the seed marker prevents re-seed once disabled. |
| Radix bundle size creep | Only import the four primitives listed; track `dist/` size in the verification step and abort if the JS bundle grows >100 KB gzip total from baseline. |
| Glossary terms drift from product reality | Glossary is one file (`lib/glossary.ts`) — code review checklist item: "did this PR introduce a new domain term? add it to glossary." |
| First-run tour interferes with E2E tests | Tour is gated by `localStorage` flag; smoke tests set the flag at start. |
