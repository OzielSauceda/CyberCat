# CyberCat — The Whole Project, Explained Simply

*A plain-language, top-to-bottom walkthrough of what CyberCat is, what it does, how it's built, and what every piece means. Written so that someone with zero computer-science background can follow, but with the real technical names included so that it's still accurate.*

---

## 1. The One-Paragraph Summary

CyberCat is a **security investigation tool**. When bad things happen on computers — someone trying to break into an account, a suspicious program starting up, a weird login from another country — those events normally show up as a noisy pile of separate alarms. CyberCat's job is to **watch those alarms, group the related ones together into one "incident," explain in plain language why they look suspicious, and give a human analyst safe buttons to respond** (like "block that IP" or "collect evidence"). Think of it as a very patient detective that reads every alarm, stitches the story together, and hands you a clean case file.

---

## 2. The Problem It Solves (no jargon)

Imagine you run an office building's security cameras.

- Camera 1 sees someone jiggling a door handle five times.
- Camera 2 sees someone walk inside two minutes later.
- Camera 3 sees a window open on the third floor.

Individually, each camera clip looks like nothing. Together, it's a break-in.

In the digital world, the "cameras" are **Wazuh agents** (tiny programs that watch computers). They produce thousands of separate alarms every day. A human can't read them all. Most tools just dump the alarms into a giant list.

**CyberCat does the stitching.** It reads the alarms, notices when they belong to the same story, and shows the story — not just the noise.

---

## 3. What CyberCat Is *Not*

To keep the project honest and focused, CyberCat deliberately does **not** try to be:

- A **SIEM** (the giant log-search platforms like Splunk). We don't try to store and search all logs ever.
- An **EDR** (endpoint protection like CrowdStrike). We don't install our own agents; we use Wazuh.
- A **Wazuh dashboard**. Wazuh is only our eyes — the product is the investigation layer above it.
- A **threat-intel portal** or a **CTF toy**. It's a real (lab-safe) incident-response slice.
- An **offensive / hacking tool**. Purely defensive, only on systems the user owns.

This restraint is written into `CLAUDE.md` at the project root as a hard rule.

---

## 4. The Big Picture (one diagram in words)

```
  Computers being watched          (Linux / Windows lab machines)
          │
          ▼
  Wazuh agents + Wazuh manager     (collect raw events, forward them)
          │
          ▼
  CyberCat Backend (FastAPI)       ← the "brain"
    ├── Ingest       (receive raw events)
    ├── Normalize    (turn vendor gibberish into a clean shape)
    ├── Detect       (apply rules: "this looks suspicious")
    ├── Correlate    (group related detections into one Incident)
    ├── Respond      (tag, block, quarantine, request evidence…)
    │
    ├── PostgreSQL   ← the durable memory (the "filing cabinet")
    └── Redis        ← the short-term memory (sticky notes)
          │
          ▼
  CyberCat Frontend (Next.js)      ← the analyst's screen
    Incidents list, Incident detail, Timeline, ATT&CK chain,
    Entity graph, Response action buttons, Evidence requests…
```

Every arrow here is a **custom layer we built**. Wazuh is upstream equipment; **the CyberCat app layer is the actual product**.

---

## 5. The Technology Stack, Piece by Piece

Each of these names sounds intimidating, but below is **what they do in real life** and **why we picked them**.

### 5.1 Python

- **What it is:** A programming language. Easy to read, very popular for security and data work.
- **What it does here:** The entire **backend brain** (everything that thinks, decides, correlates, and responds) is written in Python.
- **Why:** Fast to write, giant ecosystem, natural fit for parsing data and writing rules.

### 5.2 FastAPI

- **What it is:** A Python "framework" — basically a set of tools that makes it easy to build a web API (the backend that the frontend talks to).
- **What it does here:** Exposes all the URLs the frontend calls, like `/v1/incidents`, `/v1/events/raw`, `/v1/responses`.
- **Why:** It's modern, very fast, and it automatically generates documentation (OpenAPI) so our frontend can have **type-safe** generated API clients.

### 5.3 Pydantic

- **What it is:** A Python library that enforces "this piece of data must have these exact fields of these exact types."
- **What it does here:** Every API request and response has a Pydantic model. If the frontend sends the wrong shape of data, Pydantic rejects it instantly with a clear error.
- **Why:** Prevents bugs and bad data from ever reaching the database.

### 5.4 SQLAlchemy + asyncpg

- **What it is:** SQLAlchemy is the Python "ORM" — it lets us treat database rows as Python objects instead of writing raw SQL everywhere. asyncpg is the high-performance Postgres driver.
- **What it does here:** All reads and writes to the database go through it.
- **Why:** Type-safe, async (many operations at once), battle-tested.

### 5.5 Alembic

- **What it is:** A "migrations" tool — it manages changes to the database schema over time.
- **What it does here:** Every time we add a new column or table, we record the change in an Alembic migration file. Running the migration upgrades the database safely. We have **seven migrations** so far: initial schema, classification fields, lab asset preseed, Wazuh cursor table, response state tables, Phase 11's `partial` result enum value for Active Response, and Phase 14's multi-operator auth tables (`users`, `api_tokens`, audit FK columns, `legacy@cybercat.local` backfill).
- **Why:** So we can change the database without losing data or causing drift between development and production.

### 5.6 PostgreSQL (often just "Postgres")

- **What it is:** A relational database — a highly reliable, permanent filing cabinet.
- **What it does here:** **Stores durable truth.** All incidents, events, entities, detections, response actions, evidence requests, blocked observables — everything that matters long-term — lives here.
- **Why:** Proven reliability, rich data types (like JSONB for semi-structured fields), perfect for an incident history we must never lose.

### 5.7 Redis

- **What it is:** A fast, in-memory data store. Much faster than Postgres, but data is temporary.
- **What it does here:** Short-term **sticky notes** the detection/correlation engines use:
  - "I've seen this exact event already — don't process it twice" (dedup)
  - "5 failed logins for alice in the last 10 minutes" (sliding windows)
  - "I fired this rule 30 seconds ago, don't fire it again" (cooldowns)
  - Caches.
- **Why:** Speed. But critically — **if Redis dies, the system recovers**; if Postgres dies, we've lost real incidents. That split is a core architectural rule.

### 5.8 Wazuh

- **What it is:** An open-source security monitoring platform. Has "agents" (little programs installed on each machine), a "manager" that receives their reports, and an "indexer" (based on OpenSearch) that stores alerts.
- **What it does here:** **The eyes.** Wazuh watches the lab computers — it notices failed logins, suspicious processes, file changes, etc. — and forwards its alerts to CyberCat.
- **Why:** Industry-standard, open, free, already capable of collecting rich telemetry. We don't want to reinvent agents; we want to focus on the investigation layer.
- **How we plug in:** Our backend has a **Wazuh poller** (`wazuh_poller.py`) that regularly asks the Wazuh indexer "any new alerts since my last cursor?" using a dedicated least-privilege user (`cybercat_reader`). The cursor is saved in a Postgres table so we never lose our place.

### 5.9 Sigma

- **What it is:** A vendor-neutral language for writing security detection rules (basically YAML files that say "if you see X and Y, that's suspicious").
- **What it does here:** Lets us write detection rules once in a portable format, and our backend interprets them against incoming events. We also have hand-written Python detectors for cases Sigma can't express cleanly. **Both engines run in parallel** and their results converge on the same incident.
- **Why:** Standard format used by the security community → lots of pre-written rules available.

### 5.10 MITRE ATT&CK

- **What it is:** A free, public catalog from MITRE describing all the known **tactics** (the "why": e.g., Initial Access, Credential Access, Lateral Movement) and **techniques** (the "how") that real attackers use.
- **What it does here:** Every detection and incident is tagged with the relevant ATT&CK technique IDs. The incident page shows a full **kill chain strip** with all 14 tactics, highlighting the ones this incident touched.
- **Why:** So analysts immediately see "this incident covers credential access → lateral movement → impact" — the universal shared language of defense.

### 5.11 Next.js

- **What it is:** A popular React-based framework for building modern web applications.
- **What it does here:** The entire **frontend** (the pages the analyst looks at: incidents list, incident detail, entity pages, actions page, lab page) is a Next.js 15 app using the App Router.
- **Why:** Industry standard, great developer experience, fast pages, typed routing.

### 5.12 React 19

- **What it is:** The underlying UI library Next.js uses. Builds screens out of reusable components.
- **What it does here:** Every button, badge, card, chart on the frontend is a React component.

### 5.13 TypeScript

- **What it is:** JavaScript with type checking added. If you try to read a property that doesn't exist, the compiler catches it **before** it runs.
- **What it does here:** Everything in `frontend/` is typed. We also auto-generate a typed client (`openapi-typescript`) from the backend's OpenAPI spec, so the frontend literally cannot call a non-existent endpoint or misuse a field.
- **Why:** Kills entire categories of bugs.

### 5.14 Tailwind CSS

- **What it is:** A utility-first styling framework — instead of writing separate CSS files, you put short class names directly on elements (`class="rounded-md bg-red-600 px-3 py-1"`).
- **What it does here:** All the visual styling — colors, spacing, badges, pills, panels.
- **Why:** Fast to iterate on, consistent look, small final bundle.

### 5.15 Docker / Podman + Docker Compose

- **What it is:** "Containers" are lightweight, isolated boxes that package an app with all its dependencies so it runs the same on any machine. Docker Compose starts a set of them together with one command.
- **What it does here:** Every service in our stack (Postgres, Redis, backend, frontend, Wazuh manager, Wazuh indexer, the Debian lab VM) runs as a container. One `docker compose up` spins up the whole environment. The Wazuh parts are behind a `--profile wazuh` flag so they only start on demand.
- **Why:** Clean, reproducible, laptop-friendly. The whole platform runs on the operator's Lenovo Legion Slim 5 without touching the host OS.

### 5.16 httpx, redis-py, PyYAML, date-fns

- **httpx:** Python async HTTP client — how we talk to the Wazuh API.
- **redis-py (async):** How the backend talks to Redis.
- **PyYAML:** How we parse Sigma rule files (which are YAML).
- **date-fns:** How the frontend formats timestamps as "2 minutes ago."

---

## 6. The Data Flow — Follow One Event End to End

Let's trace a real example: **an attacker fails to log in five times, then succeeds, then runs a suspicious PowerShell command.**

1. **Wazuh agent** on the lab Windows box sees the failed logons (Windows Event ID 4625) and the successful logon (4624) and the PowerShell process creation (Sysmon Event ID 1). It forwards them to the Wazuh manager.
2. **Wazuh manager + indexer** store these as alerts in the `wazuh-alerts-*` index.
3. **CyberCat's Wazuh poller** (running inside the backend) asks the indexer every few seconds "any new alerts?" The poller pages through using a cursor saved in the `wazuh_cursor` Postgres table, so it never misses or double-reads.
4. **Normalizer** (`app/ingest/`) takes Wazuh's messy alert shape and turns it into our **canonical event**: `{ kind: "auth.failed", actor: alice, target_host: lab-win10-01, occurred_at: ..., raw: {...}, normalized: {...} }`. Entities (user alice, host lab-win10-01) are upserted in the `entities` table.
5. The event row is written to the `events` table. Junction row added to `event_entities`.
6. **Detection engine** runs all registered detectors against the new event:
   - A Python detector notices "this is the 5th auth.failed for alice in 10 minutes" → fires **brute-force detection**.
   - Later, the success logon fires the **anomalous login** detector.
   - The PowerShell event matches a **Sigma rule** for encoded PowerShell → fires a separate detection.
   - Each fire is written to the `detections` table, tagged with ATT&CK technique IDs.
7. **Correlation engine** looks at the detections and applies correlator rules:
   - `identity_compromise` correlator groups the brute-force + successful login → one incident.
   - `identity_endpoint_chain` correlator sees that the successful login + suspicious PowerShell happened on the same host within a short window and ties them together into a chained incident.
   - Result: one row in `incidents`, plus junction rows in `incident_events`, `incident_detections`, `incident_entities`, `incident_attack`.
8. **Auto-response**: for identity compromise, the policy engine auto-proposes a `request_evidence` action (safe, just asks the analyst to collect forensic data). `auto_safe` actions run immediately; `disruptive` ones wait for analyst approval.
9. **Frontend** polls `/v1/incidents` every 10 seconds → the new incident pops up. The analyst clicks in → the detail page shows the full story.

This whole chain takes seconds.

---

## 7. Where Data Is Stored (the honest answer)

- **Postgres** (inside a Docker volume named `postgres_data`):
  - `events` — every normalized event (with the raw Wazuh payload kept in a JSONB column)
  - `entities` — every user, host, IP, process, file, observable we've seen
  - `event_entities` — which entities appear in which events
  - `detections` — every rule fire
  - `incidents` — the correlated stories
  - `incident_events`, `incident_detections`, `incident_entities`, `incident_attack` — the junction tables that say "incident X contains these events / detections / entities / ATT&CK techniques"
  - `incident_transitions` — every status change (audit trail)
  - `actions`, `action_logs` — every response action and what happened when we ran it
  - `blocked_observables` — currently-blocked IPs/hashes (checked by the detection engine as a feedback loop)
  - `evidence_requests` — open/collected/dismissed evidence asks
  - `lab_sessions`, `lab_assets` — simulated lab-side state for response actions
  - `wazuh_cursor` — one row, holds the poller's place
- **Redis** (inside a Docker volume named `redis_data`):
  - Sliding-window counters, dedup keys, cooldowns, caches. **No source of truth — ever.**
- **Wazuh indexer** (inside `wazuh_indexer_data`): raw alerts; we only *read* from it, we don't rewrite it.
- **Source code + migrations + docs**: on disk in the project folder.

---

## 8. The Incidents Page — Every Feature Explained

> **Frontend identity (Phase 17):** Every working view sits inside a **detective / case-file** shell. The app frame is a "case board" with a top-nav of icon-plus-tooltip links (`Incidents`, `Detections`, `Actions`, `Lab`), an operator-credentials strip on the right (stream status, Wazuh bridge status, your role + email), and a (?) HelpMenu Popover that opens "What is this app?", the glossary, and a "Restart tour" entry. Pages are framed as dossiers — warm-paper edges, typewriter case headers (Special Elite font), and stamp/seal accents. The visual language is established in `tailwind.config.ts` (`dossier.paper`, `dossier.paperEdge`, `dossier.ink`, `dossier.evidenceTape`, `dossier.stamp`) and applied across `app/layout.tsx`, `CaseBoard.tsx`, `NavBar.tsx`, `HelpMenu.tsx`. ADR-0014 records the design.
>
> **First-run experience (Phase 17):** Visiting `localhost:3000` on a clean `./start.sh` no longer redirects to `/incidents` — `frontend/app/page.tsx` is a real welcome landing page with operator handle + open-case count, a hero stat bar (open cases, detections today, critical so far, overall risk), a live event ticker, an active-cases list, a platform-overview strip (Detection / Correlation / Response), and a "Take the tour" CTA. A 3-step guided tour (`FirstRunTour.tsx`) auto-fires on first visit and points at the first incident card → kill-chain panel → actions panel. `localStorage["cybercat:tour:completed"]` prevents auto-replay; HelpMenu exposes "Restart tour" to clear the flag.
>
> **Glossary (Phase 17):** Every domain term in the UI is hover-explainable. `frontend/app/lib/glossary.ts` is the single source of truth (~30 entries, each `{ title, short, long }`); `<JargonTerm slug="...">` renders a dotted underline that opens a Radix tooltip with the short definition and a "Read more →" link to `/help#<slug>`. `frontend/app/help/page.tsx` renders the full glossary as a single scrollable page with anchored sections.
>
> **Plain-language layer (Phase 18, on top of Phase 17):** Backend enums and ATT&CK technique codes do not appear raw in the UI. `frontend/app/lib/labels.ts` maps every enum value to `{ label, plain, slug? }`; `<PlainTerm>` renders the plain label as primary with the technical term as a muted inline secondary and full definition on hover. The backend now writes both `incident.rationale` (technical, kept for analyst depth) and `incident.summary` (plain-language) — the UI leads with `summary` and shows `rationale` behind a "Show technical detail" expander.
>
> **Auto-seeded demo data (Phase 17):** A fresh clone with empty volumes runs `credential_theft_chain` once on backend startup (gated by `CCT_AUTOSEED_DEMO=true` + Postgres advisory lock + Redis seed marker `cybercat:demo_active`). A `DemoDataBanner` at the top of the welcome page shows "You're viewing seeded demo data — Wipe and start fresh →" until an admin calls `DELETE /v1/admin/demo-data`. See `docs/runbook.md` "First-run experience" for the full contract.

This is the main analyst screen. URL: `http://localhost:3000/incidents`. Implemented in `frontend/app/incidents/page.tsx`.

### 8.1 What each incident card shows

Each incident in the list is a clickable card. On it you see:

| Element on card | What it means |
|---|---|
| **Severity badge** (colored pill: red / orange / amber / sky / zinc) | How serious this incident is. Red = critical. Orange = high. Amber = medium. Sky (light blue) = low. Zinc (grey) = informational. The card also has a **colored left border** that matches. |
| **Status pill** | The incident's current lifecycle state: `new`, `triaged`, `investigating`, `contained`, `resolved`, or `closed`. |
| **Title** | A short human-readable summary auto-generated when the incident is created, e.g., "Suspicious PowerShell from anomalous source." |
| **Primary user chip** | A clickable "EntityChip" showing the main user involved (e.g., `alice@example.com`). Click it → user detail page. |
| **Primary host chip** | Same thing, but for the primary machine (e.g., `lab-win10-01`). |
| **Event count** | How many raw normalized events belong to this incident. |
| **Detection count** | How many rules fired across those events. |
| **Entity count** | How many distinct entities (users, hosts, IPs, processes, files, observables) are involved. |
| **Kind** | The incident type: `identity_compromise`, `endpoint_compromise`, or `identity_endpoint_chain`. |
| **Relative timestamp** | "5 minutes ago," "2 hours ago," etc. |

### 8.2 Filters at the top of the page

- **Status filter** — toggleable multi-select buttons for any combination of `new`, `triaged`, `investigating`, `contained`, `resolved`, `closed`. Click the ones you want to see.
- **Severity filter** — a dropdown: "Any / critical / high / medium / low / info" — shows only incidents at or above the chosen floor.
- **Clear filters** button — appears once any filter is active so you can reset with one click.

### 8.3 Live behavior

- The page **polls the backend every 10 seconds** (`GET /v1/incidents` with whatever filters are active), so new incidents appear without a manual refresh.
- Polling is **visibility-aware**: if you switch tabs, it stops, so the backend isn't hammered for nothing.
- **Pagination**: the first 50 incidents load; a "Load more" button at the bottom fetches the next page via the `next_cursor` returned by the API.
- **Non-blocking error banner**: if the backend is unreachable, a small amber banner appears at the top saying "Backend unavailable — showing cached data" with a "Retry" button. The page does **not** crash.
- **Empty states**:
  - No incidents yet and no filters → hint to seed via `POST /v1/events/raw`.
  - No incidents matching the filters → "No incidents match the current filters" with a link to clear them.

### 8.4 Clicking into an incident (the detail page)

Route: `/incidents/[id]` → `frontend/app/incidents/[id]/page.tsx`.

This is where the real investigation happens. The layout is designed to guide the analyst's eye:

1. **Header strip** — Title, severity badge, status pill, confidence bar (0.00–1.00), which correlator rule built this incident, when it opened, when it last updated.
2. **Rationale box** — One plain-language paragraph explaining why these events were grouped into one incident (e.g., "5 failed logons for alice followed by a successful logon and suspicious child process within 3 minutes on host lab-win10-01").
3. **ATT&CK kill chain strip** (full width) — All 14 ATT&CK tactics from *Reconnaissance* to *Impact*, shown as a row. Tactics this incident touched are highlighted, with technique counts. Each tactic is clickable and shows whether it was derived from a fired rule or inferred from the incident shape.
4. **Graphical timeline** (full-width SVG, drawn by hand in code — no heavy chart library):
   - Events are dots plotted along a time axis.
   - Dot color tells you the **layer**: indigo = identity, lime = endpoint, cyan = network, emerald = session.
   - Triangles above the timeline are **detections**, with connector lines drawn down to the exact event(s) that triggered them.
   - Hover on any dot/triangle → tooltip with timestamp, event kind, and role.
5. **Two-column body:**
   - **Left column:**
     - **Timeline panel** — a readable list of events, with a toggle between "grouped by entity" and "chronological."
     - **Detections panel** — each fired rule, its source (Sigma or Python), severity, confidence, matched fields, ATT&CK tags.
   - **Right column:**
     - **Entity graph** — a small SVG circle layout showing which entities are linked to this incident and the relationships between them.
     - **Entities detail list** — each entity (user, host, IP, etc.) with attributes and a link to its full page.
     - **Actions panel** — all response actions on this incident: when they ran, who ran them, result, and (for reversible ones) a revert button.
     - **Evidence requests panel** — open / collected / dismissed evidence asks.
     - **Status transitions menu** — a dropdown to change status; it only shows transitions allowed by the lifecycle state machine.
     - **Analyst notes** — free-text notes the human can attach.
6. **Live polling**: the detail page polls every **5 seconds** so actions and new events appear in near-real time.

### 8.5 The small reusable pieces you see everywhere

- `SeverityBadge` — the colored pill.
- `StatusPill` — lifecycle state pill.
- `ConfidenceBar` — mini bar showing how certain the system is (0–1).
- `AttackTag` — ATT&CK technique chip, links out to the MITRE site.
- `EntityChip` — universal entity chip with an icon per kind (user/host/ip/process/file/observable).
- `RelativeTime` — "5 minutes ago" rendered from an ISO timestamp.
- `JsonBlock` — collapsible JSON viewer for raw/normalized event fields.
- `Panel` — the uniform titled section container with an item count.
- `TransitionMenu` — status-change dropdown that respects the lifecycle rules.
- `BlockedObservablesBadge` — shows on an entity page if one of its observables is currently blocked.

---

## 9. The Other Frontend Pages

| Route | File | What it's for |
|---|---|---|
| `/incidents` | `frontend/app/incidents/page.tsx` | The main list discussed above |
| `/incidents/[id]` | `frontend/app/incidents/[id]/page.tsx` | Incident detail |
| `/entities/[id]` | `frontend/app/entities/[id]/page.tsx` | All info about one user/host/IP/etc.: attributes, recent events, related incidents, any active observable blocks |
| `/detections` | `frontend/app/detections/page.tsx` | Every rule fire; filter by source / rule / time; click to jump to the incident |
| `/actions` | `frontend/app/actions/page.tsx` | Dashboard of every response action across every incident, with status tracking |
| `/lab` | `frontend/app/lab/page.tsx` | Register or delete "lab assets" (fake hosts/users) used for testing the incident engine without touching real systems |

---

## 10. Response Actions — the "buttons" at the end of the story

Eight response action kinds are wired end-to-end. Each is **classified** so the system knows how aggressive it is:

| Action | Classification | What it does |
|---|---|---|
| `tag` | auto-safe | Add a tag / note to an incident or entity. |
| `elevate` | auto-safe | Raise the incident's severity and record the reason. |
| `flag_host` | reversible | Mark a host as "needs a closer look"; revertable. |
| `quarantine` | disruptive (lab-safe today) | Mark a host as isolated; reversible via revert. |
| `kill_process` | disruptive (lab-safe today) | Mark a simulated process as terminated. |
| `invalidate_session` | reversible | Invalidate a user's session in the lab session store. |
| `block_observable` | reversible | Add an IP/hash to the `blocked_observables` table — the **detection engine then uses this as a feedback loop**: future events involving that observable get flagged immediately. |
| `request_evidence` | suggest-only | Opens an evidence collection request (`evidence_requests` table) that the analyst moves through open → collected (with notes/URI) or dismissed. |

Every run is logged in `action_logs` with timestamp, actor, result, and classification reason. Reversible actions can be reverted from the UI — the revert is itself an audit event.

> **Updated (Phase 11, shipped):** `quarantine_host_lab` and `kill_process_lab` are now wired through **real Wazuh Active Response**. When the `WAZUH_AR_ENABLED` flag is on, the backend authenticates to the Wazuh manager API (with token caching and automatic 401 re-auth), looks up the agent ID for the target host, and dispatches either the built-in `firewall-drop0` command (real iptables DROP rule on the lab container) or our custom `kill-process.sh` Active Response script (reads `/proc/<pid>/cmdline`, validates against the requested process name to defeat PID reuse, then `kill -9`). Results feed back into the action log as `ok` (dispatched), `failed`, or the new **`partial`** state — DB state committed but the enforcement call failed. Partial shows up in the UI as an amber badge with "Action partially completed — DB state written, enforcement did not confirm" tooltip. With the flag off (default), the system falls back cleanly to DB-only simulated behavior, so demos remain safe. Everything stays scoped to lab containers — the operator's host OS is never touched. See `docs/decisions/ADR-0007-wazuh-active-response-dispatch.md`.

---

## 11. The Lifecycle of an Incident

```
 new ──► triaged ──► investigating ──► contained ──► resolved ──► closed
   └─────────────────────────────────────────────────────────────────▲
                     (some direct transitions allowed)
```

Every transition is stored in `incident_transitions` with timestamp, actor, and reason. The frontend's `TransitionMenu` only offers the transitions the state machine permits.

---

## 12. How Everything Runs on Your Laptop

Two tiers, by design (see `docs/decisions/ADR-0003-resource-plan.md`):

### Tier A — always-on (daily development & local demos)

| Service | Rough idle RAM |
|---|---|
| Postgres | ~300 MB |
| Redis | ~50 MB |
| Backend (FastAPI) | ~200 MB |
| Frontend (Next.js) | ~100 MB |
| **Total** | **~650 MB** |

This is what runs all day on the Legion Slim 5.

### Tier B — on-demand (full Wazuh end-to-end demos)

Started with `docker compose --profile wazuh up -d`:

| Service | Rough RAM |
|---|---|
| Wazuh indexer (OpenSearch under the hood) | ~1 GB |
| Wazuh manager | ~200 MB |
| `lab-debian` container (Debian 12 + sshd + auditd + Wazuh agent) | ~256 MB |
| **Added total** | **~1.5 GB** |

Only spun up when you want to show "a real SSH brute-force on a real (lab) Linux box flowing into CyberCat."

### How you start it

`start.sh` at the project root brings the core stack up. Migrations run automatically on backend startup via Alembic. Frontend is served at `http://localhost:3000`, backend at `http://localhost:8000`.

---

## 13. Documentation Map

All docs live under `docs/` or at the repo root:

- `CLAUDE.md` — Project rules. The non-negotiable guardrails.
- `Project Brief.md` — Authoritative vision document; "why this product, for whom, with what scope."
- `PROJECT_STATE.md` — Living status tracker. Updated as phases complete.
- `START_HERE.md` — Quick orientation for a fresh session.
- `docs/architecture.md` — Canonical layered design.
- `docs/data-model.md` — Every Postgres column explained.
- `docs/api-contract.md` — Every REST endpoint.
- `docs/detection.md` — How detection + the blocked-observable feedback loop work.
- `docs/runbook.md` — Boot, seed, smoke-test commands.
- `docs/scenarios/` — Narrative attack chains used as test fixtures.
- `docs/decisions/ADR-XXXX-*.md` — Durable decisions: scope, stack, resources, Wazuh bridge design, response handler rules, attack simulator.
- `docs/phase-*-plan.md` / `phase-*-verification.md` — Per-phase plans and verification notes.

---

## 14. Testing

- **Unit + integration tests**: `pytest` in `backend/tests/` — **156 tests, all passing**. Covers Sigma parser/compiler (38 tests), Wazuh decoder for sshd + auditd + Sysmon (11 tests), response handlers (13 tests), Active Response dispatcher and agent lookup (6 tests), integration flows for quarantine/kill/block/evidence (5 tests), correlation rules including the cross-layer `identity_endpoint_chain` correlator, auth security unit tests (12 tests), auth router integration tests (15 tests), and parameterized route-gating tests (20 tests: 10×401 anonymous + 10×403 read_only across all analyst-gated endpoints).
- **End-to-end smoke scripts**: `labs/smoke_test_phase*.sh` (**8 scripts**, phases 3, 5, 6, 7, 8, 9a, 10, and 11), totalling 100+ assertions that hit the live backend + database and verify full flows. Phase 11's smoke test is **8/8** against a live Wazuh stack — it actually enrols a `lab-debian` agent, executes a quarantine, greps `iptables -L` for the DROP rule, and kills a real lab-side process.
- **Attack simulator** (`labs/simulator/`): a deterministic synthetic event generator that replays full chains like `credential_theft_chain` (5-stage brute-force → successful login → session → encoded PowerShell → C2 beacon) into the backend. Supports `--speed` to compress time (0.1 = ~30s compressed demo) and `--verify` to check that the expected incidents got created. Idempotent — safe to re-run within the same hour (dedup keys prevent duplicates).
- **Type checks**: `tsc --noEmit` in the frontend is clean (zero errors).

---

## 15. Where the Project Stands Today (as of 2026-05-02)

From `PROJECT_STATE.md`: **Phases 1–18 + Phase 19 fully shipped and merged to main; tag `v0.9` cut 2026-05-02.** 236/236 backend pytest, 104/104 agent pytest on the CI runner, ruff clean, frontend typecheck clean, smoke chain green on `main` and on every PR that touches the smoke surface. The platform is multi-operator capable, hardened for Redis blips and Postgres restarts (graceful degradation), and CI-gated on every push.

**Completed — the phases of work on disk today:**

1. **Event ingestion** — Wazuh poller (async, `search_after` cursor persisted in Postgres, survives crashes) + direct API (`POST /v1/events/raw`) for the simulator and tests.
2. **Normalization** — canonical event/entity model; decoder handles three event kinds from Wazuh (`auth.failed`, `auth.succeeded`, `process.created`) and two OS sources (Linux auditd, Windows Sysmon EventID 1).
3. **Detection** — Python rate/sequence rules + Sigma pack running side-by-side. Four Python detectors: `py.auth.failed_burst`, `py.auth.anomalous_source_success`, `py.process.suspicious_child`, `py.blocked_observable_match`.
4. **Correlation** — four correlator kinds on a first-match-wins engine: `identity_compromise`, `endpoint_compromise_standalone`, `endpoint_compromise_join`, and the flagship cross-layer `identity_endpoint_chain`. Auto-elevates chained incidents to `critical`.
5. **ATT&CK mapping** — 37-entry hand-curated catalog (v14.1). Every detection and incident is tagged; frontend renders all 14 tactics as a kill-chain strip.
6. **Response actions** — all 8 handlers real and wired end-to-end: `tag_incident`, `elevate_severity`, `flag_host_in_lab`, `quarantine_host_lab`, `kill_process_lab`, `invalidate_lab_session`, `block_observable`, `request_evidence`. Classified `auto_safe` / `suggest_only` / `reversible` / `disruptive`. Reversible actions can be reverted from the UI; disruptive ones stay as audit trail.
7. **Response feedback loop** — `block_observable` writes to `blocked_observables`; the detection engine re-reads it on every event (Redis-cached 30s). Blocking an IP makes future events involving that IP fire `py.blocked_observable_match`, which lands on the same incident. This is a real closed loop, not cosmetic.
8. **Evidence tracking** — `evidence_requests` table with `open` / `collected` / `dismissed` lifecycle. `identity_compromise` incidents auto-propose a `triage_log` request so the analyst always has a checklist. `kill_process_lab` auto-creates a `process_list` evidence request.
9. **Wazuh integration (end-to-end)** — TLS certs generated and mounted, `cybercat_reader` least-privilege role created via the Security REST API, async poller resilient to asyncpg JSONB serialization quirks (the bug that bit us and why the poller now has outer `try/except` + `CAST(:sa AS JSONB)` for the cursor). Filebeat pipeline live end-to-end on a Debian lab container with a real Wazuh agent.
10. **Analyst frontend** — Next.js 15 App Router with incidents list, incident detail, entity detail, detections, actions dashboard, lab asset CRUD, top-nav status badges, visibility-aware SSE streaming + polling fallback. TypeScript clean (`tsc --noEmit` 0 errors).
11. **Attack simulator** — `labs/simulator/` package with a scenario registry. The `credential_theft_chain` scenario fires 5 stages (brute force → anomalous success → session → encoded PowerShell → C2 beacon) against the running backend. `--speed 0.1` compresses to ~30s; `--verify` asserts both expected incidents exist after the run.
12. **Visual polish (Phase 12)** — three full-width hand-drawn SVG panels on the incident detail page: **AttackKillChainPanel** (14-tactic strip with matched-tactic highlights and technique badges), **IncidentTimelineViz** (events plotted on a baseline with role-based sizing, layer-color dots, and dashed connector lines from detection triangles to their triggering events), and **EntityGraphPanel** (circular layout, edges weighted by co-occurrence count, hover glow + weight labels). No `react-flow`, no `cytoscape.js` — pure SVG, under ~10 KB each added to the bundle.
13. **Wazuh Active Response dispatch (Phase 11)** — the disruptive actions now optionally produce **real** OS/network side-effects, not just DB state. `quarantine_host_lab` dispatches Wazuh's built-in `firewall-drop0` → real `iptables -I INPUT DROP` rule on the lab container. `kill_process_lab` dispatches our custom `kill-process.sh` Active Response script → reads `/proc/<pid>/cmdline`, validates against the requested process name (PID-reuse defense), then `kill -9`. Token cache + 270s TTL + single 401 re-auth. New `partial` action result when DB state commits but enforcement fails. All flag-gated behind `WAZUH_AR_ENABLED` (default `false`), all container-sandboxed, host OS untouched. ADR-0007 documents the design.
14. **Real-time SSE streaming (Phase 13)** — replaced the 5s/10s polling with a server-pushed SSE channel (`GET /v1/stream`). Redis pub/sub fans out to per-connection asyncio queues. Frontend uses a `useStream` hook with topic filters, auto-reconnect, and a 60s safety-net fallback poll. `StreamStatusBadge` in the header shows reconnection and polling-fallback states. Smoke test 8/8.
15. **Auth foundation (Phase 14.1)** — `users` + `api_tokens` tables, bcrypt+itsdangerous security primitives, HMAC-signed session cookies, API token (Bearer) path, three roles (`admin`/`analyst`/`read_only`), `legacy@cybercat.local` backfill for audit attribution. `AUTH_REQUIRED=false` by default — all existing tests and demos continue unchanged. Bootstrap CLI: `seed-admin`, `create-user`, `issue-token`, `revoke-token`.
16. **Session layer / login UI (Phase 14.2)** — `SessionContext` React context fetches `/v1/auth/me` + `/v1/auth/config` on mount; `UserBadge` in the header shows role + email + Sign out (hidden in dev-bypass mode); `LoginPage` at `/login` with email/password form and SSO placeholder; `api.ts` sends `credentials: include` on every request and auto-redirects to `/login` on 401; Next.js rewrite proxies `/v1/*` to backend for same-origin cookie delivery. Browser-verified 2026-04-27.
17. **Route gating + per-user audit attribution (Phase 14.3)** — every mutation endpoint now enforces `require_analyst` (analyst or admin role); every read endpoint enforces `require_user` (any role); SSE stream likewise. `actor_user_id` FKs written on every audit row (ActionLog, IncidentTransition, Note, EvidenceRequest, LabAsset) via `resolve_actor_id()` — real users get their own UUID, dev-bypass gets the `legacy@cybercat.local` sentinel UUID. Six frontend mutation controls (`TransitionMenu`, Execute/Revert buttons, Mark collected/Dismiss, Post note textarea + button, Propose submit, Register/Remove asset) render `disabled` with a "Read-only role" tooltip for `read_only` role. `test_auth_gating.py` is the canonical mutation-route inventory: 20 parameterized tests assert 401 for anonymous and 403 for `read_only` on every gated route. 0 TypeScript errors. Test-verified 2026-04-27.
18. **OIDC opt-in (Phase 14.4)** — any standard OIDC provider (Google Workspace, Okta, Auth0, Keycloak, Authentik, etc.) can now be wired in via four env vars (`OIDC_PROVIDER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`). On startup the backend fetches the provider's discovery document and JWKS and caches them. `GET /v1/auth/oidc/login` redirects to the provider; `GET /v1/auth/oidc/callback` exchanges the authorization code for an ID token, validates the JWT signature + nonce (authlib 1.7), and JIT-provisions the user with `role=read_only` (admin elevates via CLI or `PATCH /auth/users/{id}/role`). State + nonce are carried in a short-lived signed cookie (itsdangerous) so the backend stays stateless. The "Sign in with SSO" button on the login page was already conditional on `authConfig.oidc_enabled` from Phase 14.2 — it just works. `authlib>=1.3` added to deps. 156 tests green. 0 TypeScript errors. Test-verified 2026-04-27.
19. **Recommended Response Actions (Phase 15)** — static two-level mapping engine: `incident_kind → base candidates`, `ATT&CK technique prefix → priority boost`. Returns up to 4 ranked, pre-filled action suggestions per incident. New `RecommendedActionsPanel` on the incident detail page surfaces them with a "Use this" button that opens `ProposeActionModal` pre-populated. ADR-0010 records the design.
20. **Custom telemetry agent (Phase 16)** — replaces Wazuh as the *default* telemetry source. `cct-agent` Python sidecar tails `/var/log/auth.log` (sshd) directly into the canonical `auth.*` / `session.*` event shape — no Wazuh, no Filebeat, no Elasticsearch. Stack idle drops from ~4 GB to ~900 MB resident. Wazuh remains a fully-supported opt-in (`./start.sh --profile wazuh`) and is the only path for real OS-level Active Response. ADR-0011. **16.9** added auditd `process.created` / `process.exited` events via dual-tail (ADR-0012). **16.10** added conntrack `network.connection` events via triple-tail (ADR-0013); the `block_observable → blocked_observable_match` enforcement loop now closes on the agent path with no Wazuh.
21. **Frontend detective redesign + first-run experience (Phase 17)** — case-file aesthetic across every working view (warm-paper dossier tokens, typewriter case headers, stamp/seal accents); welcome landing page at `/` (replaced redirect-to-`/incidents`); typed glossary at `/lib/glossary.ts` + `<JargonTerm>` tooltip wrapper + `/help` page; 3-step `FirstRunTour` Radix dialog gated by localStorage; auto-seed contract (env flag + Postgres advisory lock + Redis seed marker `cybercat:demo_active`) with admin-gated `DELETE /v1/admin/demo-data` wipe. Adds `framer-motion` + four Radix primitives (Tooltip, Dialog, Popover, Dropdown-menu) for accessibility. ADR-0014.
22. **Site-wide plain-language pass + viz redesign (Phase 18)** — `frontend/app/lib/labels.ts` (single source of truth for enum-to-friendly-label mappings), `<PlainTerm>` component (plain primary + muted technical inline + tooltip), and an `incidents.summary` column (Alembic 0008) populated by every correlator rule + the recommendations engine. Frontend leads with `summary`; original `rationale` lives behind "Show technical detail" expander. Phase 18.8 then redesigned two flagship visualizations: `AttackKillChainPanel` ("The route" — only matched tactics shown as stamped stations on an animated path with a pulsing "HERE" marker on the latest) and `IncidentTimelineViz` ("The reel" — multi-lane reel with playhead sweep and red-string entity threads connecting events that share an entity). 174/174 backend tests, 0 typecheck errors.
23. **Hardening + CI/CD + detection-as-code (Phase 19, tag `v0.9`)** — four lanes that don't add product surface but make the existing thing trustworthy. **Resilience (A1–A5):** new `safe_redis()` helper in `backend/app/db/redis_state.py` with `asyncio.wait_for(_OP_TIMEOUT_SEC=3.0)` bound + circuit breaker (`_BREAKER_OPEN_SEC=5.0`); covers all detector code paths, the streaming publisher, and the `endpoint_compromise_standalone` SETNX dedup. `backend/app/streaming/bus.py` got an `EventBus._supervisor()` reconnect loop (`bus.py:97-123`) — a Redis blip no longer silently kills the SSE consumer. Wazuh poller circuit-breaks on 10 consecutive transient errors. Postgres pool is explicit (`pool_size=20, max_overflow=10, pool_recycle=1800, pool_timeout=10, pool_pre_ping=True`); `with_ingest_retry()` at `backend/app/ingest/retry.py` wraps both the Wazuh poller AND `POST /v1/events/raw` (Postgres restart mid-load went from 0/1992 events accepted to ≥99% after the fix). Event ingest validation in `app/api/schemas/events.py` rejects oversized payloads / bad timestamps / weird dedupe keys at the API boundary. **Perf (A6, A7):** `labs/perf/load_harness.py` is a repeatable load test; baseline ~100 req/s ceiling on single-worker uvicorn (multi-worker deferred to Phase 21). Hot routes batched: `/v1/incidents` 250+ → ≤12 queries, `/v1/detections` 200+ → ≤10. Enforced by `count_queries` fixture + `tests/integration/test_hot_route_query_count.py`. **Quality (B):** ruff clean across `backend/app/` + `agent/cct_agent/`, pytest-randomly added to dev deps. **CI (C):** `.github/workflows/ci.yml` gates every push (backend lint+pytest, agent lint+pytest, frontend typecheck+build); `.github/workflows/smoke.yml` runs the full smoke chain on `main` push, daily 06:00 UTC cron, and PR-triggered when smoke-relevant paths change. Both emit `::error::` annotations so failure surfaces in the public annotations API. **Detection-as-code (D):** `labs/fixtures/` tree with `manifest.yaml` + curated JSONL fixtures per detector; `tests/integration/test_detection_fixtures.py` walks the manifest. Phase 19.5 (chaos testing) is the named follow-up that takes on the live Redis kill verification deferred from item #2 — the `chaos-redis.yml` workflow ships now as that gate. Plan amendments in `docs/phase-19-plan.md` document the §A6 architectural ceiling (multi-worker → Phase 21) and the §A7 ≤12/≤10 query-budget floor (≤4 was an undercount).
24. **Chaos testing harness (Phase 19.5, ✅ fully verified locally)** — integration-level regression gate for every Phase-19 resilience primitive. New `labs/chaos/` tree: shared eval helper at `labs/chaos/lib/evaluate.sh` (four §A1 counter functions: sim/backend tracebacks, event_count_5min, scenario-specific degraded warnings + cleanup trap + log capture), six per-scenario shell scripts under `labs/chaos/scenarios/` (kill_redis, restart_postgres, partition_agent, pause_agent, oom_backend, slow_postgres), one orchestrator `labs/chaos/run_chaos.sh` that runs all six locally with a settle pause between, plus six `.github/workflows/chaos-*.yml` workflow_dispatch files mirroring the existing `chaos-redis.yml` pattern. Two recipe revisions vs the original roadmap, both forced by `ubuntu-latest` runner sandbox limits and both keeping the *intent* of the original test: A3 substitutes `docker network disconnect` for `iptables` (avoids `CAP_NET_ADMIN`); A6 redefines "slow disk" as cross-container network latency between backend and Postgres via `tc netem` injected by a `nicolaka/netshoot` sidecar with `--net container:<postgres>` + `--cap-add NET_ADMIN` (avoids `CAP_SYS_ADMIN` on postgres + the alpine/debian apt-vs-apk discrepancy). The four §A1 counters make every scenario's output read the same; the orchestrator's summary table shows scenario / status / duration at the end. **Live-verified 2026-05-03 on the operator's Windows + Docker Desktop + WSL2 stack** — five scenarios (A2/A3/A4/A5/A6) PASS standalone, AND the orchestrator returned `OVERALL: PASS` on round 2 (round 1 caught one A4 regression — agent startup log lines roll out of the 250-line capture window during sequential runs; fix demoted degraded_warnings to informational, made cursor-advance the real proof). Eight concrete calibration improvements landed during verification (commits `cc0e8bb` + `7cb67ae`): the `00`/`0` counter bug, the OCI-runtime stderr leak, A2's over-strict harness-acceptance flag (replaced with plan §A2 chaos criteria), Git-Bash MSYS path-mangling, local-vs-UTC timestamps in A3+A4 emitters, host-httpx-missing fallback in A5, RATE=50→20 in A6 to avoid pool exhaustion, and the A4 cursor-advance reframing. A1 (`kill_redis.sh`) was written directly on **2026-05-04** rather than waiting for the queued Wed remote agent; standalone result PASSed (`sim_tracebacks=0`, `backend_tracebacks=0`, `event_count_5min=1228`, `degraded_warnings=2`) with two further calibration findings that landed same-day (commit `6be162f`): time-window log capture (`--since 2m`) replaces the 250-line tail (which was burying resilience signals under SQLAlchemy echo at ~12k lines per run); accept_pct/transport_errors demoted to informational (not gated) because Windows+WSL2 has a documented 3.6s `getaddrinfo("redis")` NXDOMAIN quirk that doesn't apply on `ubuntu-latest`. **Regression-injection sanity check ✅ same day** — bypassed `safe_redis()` on `auth_failed_burst.py:41`, rebuilt backend, re-ran `kill_redis.sh` → FAILED with `degraded_warnings=0` exactly as plan §"Verification plan #4" predicted (file restored via `git checkout`, backend rebuilt clean). Plan: `docs/phase-19.5-plan.md`. Plain-language summary: `docs/phase-19.5-summary.md`.

**What's pending:**

- **Phase 19.5 (✅ fully verified locally 2026-05-04):** all six scenarios green + regression-injection sanity check passed both directions. Optional follow-ups deferred to operator preference: (a) `chaos-redis.yml` workflow refactor to source `lib/evaluate.sh` if cross-platform Linux verification of A1 is wanted (current inline eval is the original Phase-19 version that failed three times on 2026-05-02); (b) trigger the five non-redis `chaos-*.yml` workflows from the Actions tab — they're likely to pass on `ubuntu-latest` since the same scripts pass locally; (c) optional `v0.95` tag, or roll into Phase 20's `v1.0`. Plan: `docs/phase-19.5-plan.md`.
- **Phase 20:** Heavy-hitter choreographed scenarios (`lateral_movement_chain`, `crypto_mining_payload`, `webshell_drop`, `ransomware_staging`, `cloud_token_theft_lite`) + operator drills + merge/split incidents.
- **Phase 21:** Caldera adversary emulation + coverage scorecard. Also the natural home for multi-worker uvicorn if 1000/s sustained becomes a real requirement.
- **Phase 22 (LotL detection) + Phase 23 (UEBA-lite statistical baselining)** — agreed post-Phase-21 plan; detection thesis is "intent over tool name."
- **Ship story phase:** README rewrite, demo GIF of `credential_theft_chain`, public repo prep. Partial artifacts staged: `LICENSE` (MIT), `docs/assets/RECORDING.md` playbook. README intro + CI badges already landed in Phase 19.

---

## 16. What We Could Still Ship (Roadmap Candidates)

Honest list of features that would extend the product in meaningful, shippable directions. None of these are committed — they're candidates for future phases.

### Near-term, high-leverage (each = ~1 focused phase)

1. **More Sigma rules + more Python detectors.** The current pack is curated but small (6–8 Sigma rules + 4 Python detectors). Add detectors for: DNS tunneling, impossible travel, new-device-for-user, suspicious service creation, credential dumping (LSASS access), scheduled-task persistence. Low risk, high signal value.
2. **Playbooks / chained response actions.** Today actions are atomic. Add a `Playbook` model that chains `request_evidence` → `block_observable` → `invalidate_lab_session` with rollback on any failure. The correlator could auto-propose a playbook for each incident kind.
3. **Incident merging + splitting.** Analysts occasionally need to merge duplicates (same attacker, two dedup buckets) or split (two threats landed in one incident by accident). Junction tables already support this — just needs UI + API.
4. **Analyst notes collaboration features.** `@mention`, Markdown rendering, pinned notes, "analyst reached this conclusion" status-change reason. Zero infra lift — pure UI + tiny API change.
5. **Search across everything.** Full-text search across incidents, events, entities, notes. Postgres `tsvector` columns + GIN indexes — no new infra needed. Already spec'd by the data model.
6. **Export incident to PDF / Markdown / Jira ticket.** Investigators close incidents by writing a postmortem. One-click export of the full incident (rationale + timeline + detections + actions + notes) into a shareable artifact.

### Medium-term (each = ~2–3 phases, real engineering)

7. ~~**Real-time streaming instead of polling.**~~ **Done — Phase 13.** SSE channel (`GET /v1/stream`) live; frontend `useStream` hook with topic filters, auto-reconnect, and a 60s polling fallback. `StreamStatusBadge` in the header shows reconnection state.
8. **User & entity behavior analytics (UEBA-style).** Baseline per-entity: "alice typically logs in from one of these 3 IPs between 08:00–18:00 UTC." Detector fires on deviation (auth from a new country at 03:00). This is an honest-to-god behavior model, not a rule. Postgres + a rolling per-entity feature store in Redis works fine at lab scale.
9. **Threat intel feed integration.** Pull MISP / OTX / AbuseIPDB feeds on a cron; populate `blocked_observables` automatically with a `source=intel-feed` attribution. Closes the loop: the detection engine already consumes `blocked_observables`, so intel automatically becomes detection without new code.
10. ~~**Multi-operator auth + audit.**~~ **Done — Phase 14 (fully verified 2026-04-28).** Foundation (14.1): users/api_tokens tables, bcrypt session cookies, Bearer token path, three-role RBAC, audit FK columns, `AUTH_REQUIRED` feature flag, bootstrap CLI. Session layer (14.2): `SessionContext`, `UserBadge`, `LoginPage`, `credentials: include`, Next.js `/v1/*` rewrite. Route gating + audit attribution (14.3): every mutation endpoint enforces `require_analyst`, every read endpoint enforces `require_user`, `actor_user_id` populated on every audit write, six frontend mutation controls gated with `disabled={!canMutate}`, 20-test parameterized gating inventory. OIDC opt-in (14.4): `GET /v1/auth/oidc/login` + callback, authlib JWT validation, JIT user provisioning, stateless state/nonce cookie. Smoke + cutover (14.5): all 8 smoke scripts pass with and without auth token, `AUTH_REQUIRED=true` end-to-end stack-verified. ADR-0009 written. This was the single biggest "toy project" blocker — **resolved**.
11. **A second lab scenario (+ multiple simulator scenarios).** Add scenarios like `supply_chain_tool_abuse`, `cloud_token_theft`, `ransomware_staging`. Each one is a 200-line file under `labs/simulator/scenarios/` and stresses a different correlator path.
12. **Windows Active Response.** Phase 11 only implemented Linux AR (`iptables` + `kill -9`). Add a Windows Active Response script (PowerShell) for `quarantine_host_lab` (netsh advfirewall) and `kill_process_lab` (Stop-Process). Requires a Windows lab container or VM.

### Longer-term (would change the product's shape)

13. **Correlation across tenants / environments.** Introduce a `tenant_id` dimension. Each incident, entity, event is scoped. Correlators stay within a tenant. This is the real "productize for multiple teams" move.
14. **Detection-as-code pipeline.** Rules in Git, CI runs them against replayable event fixtures (`labs/fixtures/`), PR checks assert "rule fires on fixture A, does not fire on fixture B." Turns rule authoring into a real engineering workflow.
15. **Metrics / SLO dashboard.** Mean time to detect, mean time to respond, incident volume by ATT&CK tactic, false-positive rate if we add an `analyst_verdict` column. This is the "show your SOC to the CEO" layer.
16. **Anomaly scoring on top of rule fires.** Combine rule-based detections with a learned baseline score (simple Isolation Forest or just z-score on per-user event rates) to rank incidents by "weird-ness," not just rule severity.

---

## 17. Honest Ranking — where does CyberCat sit?

*(Self-assessed, 1–10 scale, calibrated against what a solo portfolio/resume project typically looks like.)*

- **Impressiveness — 9/10.** Most personal projects are a CRUD app, a chatbot, or a to-do clone. CyberCat is a **vertical product** with a clear point of view, 14+ sequential phases of real work, honest documentation (ADRs, runbook, phase plans), 156 tests, 8 smoke scripts, and a real integration with Wazuh — not a mock. The breadth of the stack (async Python + Postgres + Redis + Wazuh + Sigma + Next.js + TypeScript + Docker) is genuinely unusual for solo work, and the architecture discipline (Postgres-truth / Redis-ephemeral, explainability contract, classified response actions, feature-flagged multi-operator auth with OIDC) reads as senior-level thinking.
- **Technicality — 8/10.** Covers a lot of legit engineering ground: async end-to-end, Alembic migrations, hand-written Sigma parser/compiler, custom correlation engine with time windows and dedup keys, Wazuh REST integration with cursor-based polling, real Active Response dispatch with token caching and 401 re-auth, hand-drawn SVG visualizations without a chart library, end-to-end type safety (pydantic → OpenAPI → generated TypeScript). Not 10/10 because there's no distributed systems work (no Kafka, no multi-region), no ML, no real performance engineering — deliberately, per scope.
- **Uniqueness — 7/10.** Security products exist (there are a million "SIEM Lite" hobby projects on GitHub). What makes this one stand out: the *positioning* ("Wazuh is input, not the product; the investigation layer is the product"), the *explainability contract* (every incident answers 9 specific questions from the DB alone), the *cross-layer chain correlator* as the flagship feature (most personal projects stop at single-rule detection), and the *craft level* of the analyst UI (hand-drawn kill chain + timeline + entity graph — most security UIs are ugly tables). Not 10/10 because the domain isn't inherently new — it's a well-executed take on a known problem.

**Overall: 8/10** for a solo portfolio project. It would read as very strong on a resume — the kind of project a staff-level security engineer or product-minded backend engineer hiring manager would actually want to dig into.

**What would push it to 9 or 10:**
- A running **public demo** (even on a spot VPS) with a "reset + fire scenario" button — so reviewers don't have to clone and run it to see the product.
- **Recorded walkthrough video** (5 min max) narrated by you explaining what you built and why the architectural decisions matter.
- ~~**Multi-operator auth**~~ — **Done (Phase 14, fully verified 2026-04-28).** Removes the biggest "toy project" tell. Every mutation is role-gated, every audit row has a real `actor_user_id`, SSO sign-in via any OIDC-compatible provider works. All 8 smoke scripts pass with `AUTH_REQUIRED=true`.
- ~~**Real-time streaming**~~ — done. SSE channel live since Phase 13.
- **One case-study blog post** or the README itself pitching it as a product, not a code dump. The story matters as much as the code.

**Honest caveats to temper the number:**
- No CI/CD, no automated deploy, no GitHub Actions. Tests are manual (`pytest`, smoke scripts). On a resume this is fine for a personal project but would need to exist for a real team.
- Zero public traction (stars, contributors, issues). Solved by shipping + writing one good post. That's it.
- Single-host, single-operator scope. Spelled out explicitly in scope (ADR-0001), which is honest — but reviewers who skim will still note it.

The score is real. Finish the ship story, record the demo, and you're at 9.

---

## 18. Why Each Design Choice Matters (in one line each)

- **Postgres owns truth, Redis is temporary** — so if Redis dies, we recover; if we'd used Redis for incidents, we'd lose them.
- **Correlation is first-class, not an afterthought** — without it, you're just staring at alerts like everyone else.
- **Every incident is explainable** — the DB retains *which events* and *which rules* contributed, plus a plain-language rationale. No "trust me, it's bad" black boxes.
- **Response actions are classified** — we never let an automated tool do something disruptive without an analyst's blessing.
- **Sigma + Python co-fire** — two engines landing on the same evidence is stronger than one; duplicate detection rows are intentional and deduped at the incident level.
- **Lean stack, laptop-friendly** — no Kafka, no Kubernetes, no Elastic, no Temporal. The whole thing runs on a Lenovo Legion Slim 5 under ~1 GB idle.
- **Wazuh is input, not the product** — we deliberately don't reskin Wazuh. The investigation layer is the product.
- **Lab-safe by default** — every disruptive action stays inside a lab container. Wazuh Active Response dispatch (Phase 11) produces real OS/network effects but only on the `lab-debian` container's own namespace — the host OS is never touched, and the `WAZUH_AR_ENABLED` flag is off by default.
- **Typed everything** — Pydantic on the backend, generated TypeScript on the frontend. Whole classes of bugs disappear.

---

## 19. The One-Sentence Takeaway

CyberCat is a **focused, laptop-sized, explainable, threat-informed incident-response platform** that takes real Wazuh telemetry, stitches related signals into a single investigable story with ATT&CK context, and gives an analyst safe, audited, optionally-enforced buttons to respond — built from a clean layered architecture (ingest → normalize → detect → correlate → respond → UI) on a deliberately lean stack (Python/FastAPI, Postgres, Redis, Next.js, Docker) so the custom application layer — not the third-party infra — is what makes it worth using.
