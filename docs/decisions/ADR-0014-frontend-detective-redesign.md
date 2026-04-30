# ADR-0014 — Frontend Detective Redesign (Phase 17)

**Date:** 2026-04-29
**Status:** Accepted
**Deciders:** Oziel (owner)
**Extends:** ADR-0001 (project scope), ADR-0002 (tech stack)

---

## Context

Through Phases 1–16.10 the frontend was visually cohesive but assumed
expert knowledge. A first-time visitor to `localhost:3000` was redirected
straight to `/incidents` and met a list of jargon-coded cards
(`identity_compromise`, `T1110.003`, `confidence 0.84`, classification
`reversible`) with no orientation, no glossary, no help affordance, and
no demo data on a clean install. Empty states said "No incidents."
Aesthetic was anonymous zinc dark mode — well-engineered, but indistinct.

The goal of Phase 17 was to make CyberCat *legible to a non-expert
visitor* without diluting the analyst-grade depth, and to give the
product a distinctive identity that matches its README framing
("patient detective").

This ADR records the durable decisions. Phase 18 layered a site-wide
plain-language pass on top (`labels.ts`, `PlainTerm`, `incident.summary`)
— see PROJECT_STATE.md for that scope. Phase 18.8 then revisited the
two flagship visualizations on the incident detail page; the visual
language established here is what those rewrites paint with.

---

## Decisions

### 1. Aesthetic: case-file dossier motif, dark-only

**Chosen:** A "detective / case-file" aesthetic across every working
view. Warm-paper dossier surfaces (`dossier.paper`, `dossier.paperEdge`,
`dossier.ink`, `dossier.evidenceTape`, `dossier.stamp`,
`dossier.redaction`) on a dark base; a typewriter/case-header font
(`Special Elite` via `next/font/google`) for headers and stamps; IBM
Plex Mono kept for IDs and code; soft inner-shadow `boxShadow.dossier`
mimicking a folder edge; a subtle `bg-foldermark` SVG watermark on
page chrome. Working pages are framed as "dossiers" and the app frame
is the "case board."

**Why this aesthetic:** Most security tooling looks like a Bloomberg
terminal or a generic admin panel. The case-file motif gives the
product an identity that reads as deliberate and non-generic, and it
directly maps to the analyst's mental model: every incident *is* a
case file with evidence, a timeline, suspects, and findings. The
aesthetic is functional, not decorative.

**Rejected alternatives:**
- *Light theme.* Out of scope. Operator runs the platform in a dark
  terminal-adjacent context; no light-theme audience identified.
- *Generic-prettier zinc/slate refresh.* Considered and rejected — the
  existing palette already worked at that level. The win was identity,
  not polish.
- *Skeuomorphic paper texture (full photo backgrounds, drop shadows,
  rotated cards).* Rejected as cute-not-serious. The dossier vocabulary
  is reduced to a few typographic and color cues that carry the motif
  without theatrics.

### 2. Dependencies: Radix primitives + framer-motion, nothing else

**Chosen:** Add four Radix primitives (`@radix-ui/react-tooltip`,
`@radix-ui/react-dialog`, `@radix-ui/react-popover`,
`@radix-ui/react-dropdown-menu`) plus `framer-motion`. We still own
all visual styling — Radix only handles accessibility primitives
(focus management, keyboard nav, ARIA, portaling, modal correctness).

**Why this set:** Each primitive has a recurring need across the app:
- Tooltip → glossary hover (`JargonTerm`, `PlainTerm`), nav link
  descriptions, badge explanations.
- Dialog → first-run tour modal, confirm-destructive prompts.
- Popover → header HelpMenu, action proposal forms.
- Dropdown-menu → status transitions, action-kind selectors.
- framer-motion → tour highlight ring, station-stamp tilt, playhead
  sweep, reveal animations under `prefers-reduced-motion` guards.

Combined gzip cost stayed well under the 100 KB budget defined in the
phase plan.

**Rejected alternatives:**
- *A full headless-UI library (Headless UI, Ariakit).* Either pulls in
  a wider surface than needed or pairs awkwardly with Tailwind tokens.
- *Hand-rolled accessibility primitives.* Hit-testing, focus trapping,
  and Escape/Tab/Arrow handling for a Dialog and Popover is a known
  way to ship subtle a11y bugs. Off-loading to Radix is the right
  build-vs-buy line.
- *A heavier animation library (gsap, motion.dev).* framer-motion's
  `motion` + `AnimatePresence` + `useReducedMotion` covers every
  animation in Phase 17 and Phase 18.8 with no remainder.

### 3. Glossary architecture: typed dictionary + tooltip wrapper, two layers

**Chosen:** A two-layer plain-language system, each with a single owner:

- `frontend/app/lib/glossary.ts` — long-form `{ title, short, long }`
  entries keyed by slug. Renders the canonical definitions on `/help`
  and powers `JargonTerm` tooltip pop-ups.
- `frontend/app/lib/labels.ts` (added in Phase 18) — `{ label, plain,
  slug? }` enum-to-friendly-label maps. Powers `PlainTerm`, badge
  components, and filter-chip labels.

`<JargonTerm slug="incident">` (and the Phase 18 `<PlainTerm>`) wrap
any text node, render a dotted underline, and on hover open a Radix
Tooltip with the short definition + a "Read more →" link to
`/help#<slug>`. Adding a new domain term means adding one entry to
each file; the rendering surface is automatic.

**Why two files:** Long-form definitions and short labels have
different cadences of edit. Glossary entries change rarely; label maps
change every time a backend enum gains a value. Separating the two
files keeps each one focused and means a backend pydantic schema
extension only forces a `labels.ts` edit, not a glossary rewrite.

**Rejected alternatives:**
- *One mega-file.* Mixed concerns; harder to spot a missing label
  during code review.
- *Inline strings with no central source.* Was the pre-Phase-17 state
  and is exactly what this phase displaced.
- *i18n framework (next-intl, next-i18next).* Out of scope per phase
  plan §"Out of scope." English-only stays; the slug→entry pattern
  leaves a clean migration path if i18n ever lands.

### 4. First-run tour: localStorage flag, three steps, dialog overlay

**Chosen:** A `FirstRunTour` component (Radix Dialog, modal-less
variant + framer-motion highlight ring) auto-fires on first visit
when (a) `localStorage["cybercat:tour:completed"]` is unset and (b) at
least one incident exists. Three steps point at the first incident
card, the kill-chain panel, and the actions panel. "Skip" sets the
flag; "Re-run tour" in HelpMenu clears it.

**Why this shape:** The tour has to be present *and* unobtrusive. Auto
on first visit catches the cold-start audience; localStorage gating
prevents nagging on every reload; HelpMenu re-entry serves the user
who skipped or wants to revisit. Three steps is the maximum that fits
on one page without scrolling and matches the three working concepts
(incident, kill chain, response).

**Rejected alternatives:**
- *Full-screen onboarding wizard.* Heavy, gates the product behind a
  flow. Wrong answer for a tool the user already chose to run.
- *Server-stored "seen tour" flag.* Requires a user identity (auth-on
  mode) and a persistence migration. localStorage is correct for an
  ephemeral per-browser flag.
- *Tour fires before any incidents exist.* The pointed-at elements
  wouldn't render. Auto-seed (Decision 5) ensures incidents always
  exist on first visit, but the gating is still defensive.

### 5. Auto-seed contract: env flag + advisory lock + seed marker

**Chosen:** On FastAPI startup, if `CCT_AUTOSEED_DEMO=true` (default
`true` in dev compose, `false` for production-ish profiles) **and**
the `events` table is empty **and** no `seed_marker` row exists, the
backend runs `labs/simulator/scenarios/credential_theft_chain` at
`--speed 0.1`. The entire check-and-run is wrapped in a Postgres
advisory lock (`pg_try_advisory_lock(<stable int key>)`) so two
backend replicas can't race. A `seed_marker` row is written on
success; subsequent boots short-circuit on the marker.

`DELETE /v1/admin/demo-data` (gated by `require_admin`) truncates
every table touched by the seed scenario inside one transaction with
`TRUNCATE ... CASCADE`, preserves `users` and `api_tokens`, and clears
the marker.

A frontend `DemoDataBanner` reads the marker via a backend status
endpoint and surfaces "You're viewing seeded demo data. [Wipe and
start fresh →]" until the marker is gone.

**Why all three (env + lock + marker):** The env flag alone is
insufficient — a backend restart that crosses an hour boundary would
re-seed because `credential_theft_chain` dedup keys are Redis-bound
with a one-hour TTL. The advisory lock alone is insufficient — it
defends against concurrent races but not against repeated cold boots.
The marker alone is insufficient — two replicas can read "no marker"
simultaneously. All three together give the contract: "seed exactly
once per fresh-volume deployment, regardless of replica count or
restart cadence."

**Rejected alternatives:**
- *Trust Redis dedup alone.* Crosses hour boundaries; double-seeds.
- *Skip the advisory lock.* Multi-replica races silently double-seed.
- *Skip the marker, rely on `events` empty check.* `events` table is
  emptied by other tests; the check is non-monotonic. Marker row is
  monotonic per fresh volume.

### 6. Route ordering: Phase 17 smoke runs first

**Chosen:** `labs/smoke_test_phase17.sh` is intended to run *before*
every other smoke test in any aggregate runner. Each pre-existing
smoke either exports `CCT_AUTOSEED_DEMO=false` at start or calls
`DELETE /v1/admin/demo-data` before its first ingest.

**Why first, not last:** A broken auto-seed poisons every existing
smoke (they all assume control over event ingestion). Running the
Phase 17 smoke first asserts the seed contract before downstream
tests rely on a clean slate.

**Rejected alternative:**
- *Run Phase 17 last like other phase smokes.* Incorrect ordering;
  every prior smoke would already have failed by the time it ran.

---

## Consequences

**Positive:**
- A first-time visitor lands on a populated welcome page, hovers any
  jargon term to learn it, and has a guided tour available — without
  leaving the app.
- The product has a distinctive visual identity (case-file dossier)
  that no other security project in this category uses.
- Glossary + label files are single-source-of-truth and are touched
  every time a domain term lands. Code-review checklist: "did this
  PR introduce a new domain term? add it to glossary.ts and labels.ts."
- All Radix primitives bring real a11y guarantees the project would
  otherwise have to maintain by hand.
- The auto-seed contract makes the demo experience deterministic on a
  fresh clone.

**Negative / accepted trade-offs:**
- Frontend bundle grew (Radix + framer-motion). Tracked in the phase
  plan budget; stayed under 100 KB gzip.
- Two label-files (`labels.ts`, `glossary.ts`) is mild duplication
  surface; mitigated by review discipline. The two-file split is
  intentional per Decision 3.
- The auto-seed contract requires three coordinated mechanisms (env +
  advisory lock + marker). Each is justified in Decision 5; none are
  removable.
- The case-file aesthetic is dark-only. A future light theme would
  require palette duplication. No light-theme audience identified.

**Deferred to future phases:**
- Full restyle of `/detections`, `/actions`, `/lab`, `/entities/[id]`
  interiors (they inherit the shell + glossary + chrome but keep
  existing list/table layouts). Tracked as the Phase 17 spot-fix pass
  and absorbed by Phase 18.8 work.
- i18n / non-English glossary entries.
- Mobile / responsive polish below tablet width.
- Storybook / component library scaffolding.

---

## Files affected

**New (frontend):**
- `frontend/tailwind.config.ts` — extended (dossier tokens, font-case,
  shadow-dossier, bg-foldermark).
- `frontend/app/lib/theme-tokens.ts` — token re-exports.
- `frontend/app/lib/glossary.ts` — ~30 typed glossary entries.
- `frontend/app/components/JargonTerm.tsx` — tooltip wrapper.
- `frontend/app/components/CaseBoard.tsx` — dossier-edge frame.
- `frontend/app/components/HelpMenu.tsx` — header (?) Popover.
- `frontend/app/components/FirstRunTour.tsx` — tour overlay.
- `frontend/app/components/DemoDataBanner.tsx` — seeded-data banner.
- `frontend/app/help/page.tsx` — full glossary page.

**New (backend / infra):**
- `backend/app/api/admin.py` — `DELETE /v1/admin/demo-data`.
- `infra/compose/docker-compose.yml` — `CCT_AUTOSEED_DEMO` env var.
- `infra/compose/.env.example` — document env var.
- `labs/smoke_test_phase17.sh` — first-run + welcome-page smoke.

**Modified (frontend):**
- `frontend/package.json` — Radix + framer-motion deps.
- `frontend/app/globals.css` — Special Elite font import.
- `frontend/app/layout.tsx` — case-file shell.
- `frontend/app/page.tsx` — full welcome rewrite (was a redirect).
- `frontend/app/incidents/page.tsx`, `incidents/[id]/page.tsx` —
  case-file restyle, `<JargonTerm>` wrapping.
- Reusable components: `SeverityBadge`, `StatusPill`, `EntityChip`,
  `Panel`, `EmptyState`, `AttackKillChainPanel`, `IncidentTimelineViz`,
  `EntityGraphPanel`, `ActionClassificationBadge`, `ConfidenceBar`,
  `AttackTag`, `StreamStatusBadge`, `UserBadge`, `WazuhBridgeBadge` —
  internal Tailwind classes only; props/APIs preserved.

**Modified (backend):**
- `backend/app/main.py` — autoseed startup hook (env + advisory lock
  + seed_marker).

**Modified (docs):**
- `docs/runbook.md` — new "First-run experience" section.
- `Project Brief.md` — case-file frontend identity addendum.
- `CyberCat-Explained.md` — §8/§9 + §15 updated.
- `PROJECT_STATE.md` — Phase 17 status entry.

**Explicitly NOT touched:**
- Routing, auth, SSE, polling logic — unchanged.
- Database schema — no migrations beyond what Phase 17.6 / 18 already
  shipped.
- API contracts — only `DELETE /v1/admin/demo-data` added.
- Existing component prop signatures — preserved to avoid touching
  call sites during restyle.
