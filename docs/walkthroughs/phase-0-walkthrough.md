# Phase 0 Walkthrough — Project Foundations (Pre-Code)

*Phase 19.7 sprint, Week 1, Day 1 (Mon 2026-05-04)*

---

## Where we are in the journey

This is the very first walkthrough. Phase 0 is the phase **before any code was written** — no FastAPI app, no database schema, no React components, no telemetry agent. Phase 0 is where the project stopped being an idea in the operator's head and became a *contract* the future would build against. The artifact of Phase 0 is not software; it's the handful of documents that lock in *what CyberCat is, what it isn't, what stack it uses, and what budget it has to live within.*

A useful way to frame Phase 0: every later phase had the option to drift — to bolt on Kafka, to spin up Kubernetes, to position the project as a Wazuh dashboard, to chase whatever felt impressive that week. Phase 0 produced the documents that prevented that drift. Every time you read "out of scope" in this project, you're reading a Phase 0 decision.

**Honest note on the git history:** the very first commit in this repo is `7307177 Initial commit: CyberCat Phase 1-13 complete`. That means by the time `git init` was run, Phases 1–13 were already done and the Phase 0 documents were already mature. Phase 0's artifacts are visible in the repo, but there is no commit-by-commit trail to walk for Phase 0 itself — we read the artifacts and reverse-engineer the thinking.

---

## What Phase 0 produced

Six documents — all still in the repo, all still load-bearing — define what Phase 0 was:

| File | Purpose |
|---|---|
| `Project Brief.md` | The authoritative vision document. The operator's words, frozen, declaring what the project is. |
| `CLAUDE.md` | Stable repo rules. The contract between operator and any AI assistant working on this codebase. |
| `PROJECT_STATE.md` | Living status — what's done, what's next, what's blocked. Updated continuously throughout the project. |
| `docs/architecture.md` | Canonical system design. The "how it's structured" answer for any future session. |
| `docs/runbook.md` | How to run, seed, demo, and test the platform. Operations-side documentation. |
| `docs/decisions/ADR-0001-project-scope.md` | Locks in *what the project is and isn't*. |
| `docs/decisions/ADR-0002-tech-stack.md` | Locks in *the technology choices*. |
| `docs/decisions/ADR-0003-resource-constraints.md` | Locks in *the laptop-budget constraint*. |

Of these, the three ADRs and the Project Brief are the load-bearing artifacts. CLAUDE.md, PROJECT_STATE.md, architecture.md, and runbook.md were created in Phase 0 but evolved continuously through the build — what's in them today reflects 19 phases of growth, not Phase 0's original wording.

**Concept primer — ADR (Architecture Decision Record):**

> *Intuition:* an ADR is a one-page "we decided X, here's why, and what we considered" memo, written when the decision is made.
>
> *Precise:* a markdown document in `docs/decisions/` named `ADR-NNNN-short-slug.md`, structured around four sections: **Context** (what problem we faced), **Decision** (what we chose), **Consequences** (what this commits us to), and **Alternatives considered** (what we rejected and why). ADRs are *immutable in spirit* — when a decision changes, you write a new ADR that supersedes the old one rather than editing the original. This preserves the historical reasoning chain. The format originated in a 2011 blog post by Michael Nygard and has been adopted by AWS, Spotify, and many engineering orgs as a lightweight alternative to design-doc heaviness.
>
> *Why it exists:* without ADRs, decisions get re-litigated every six months by people who don't remember the original reasoning. The Context section especially is the failsafe — six months later, you may not agree with the decision, but you'll see the constraints that produced it.
>
> *Where in CyberCat:* `docs/decisions/ADR-0001-*.md` through `ADR-0014-*.md`, fourteen records.

---

## ADR-0001 — Project scope: what CyberCat is, in one decision

`docs/decisions/ADR-0001-project-scope.md` is the most important document in the repo. Read it in full. The TL;DR:

> CyberCat is a **threat-informed automated incident response platform** focused on **identity compromise + endpoint compromise**. The custom application layer (normalization, correlation, incident model, response policy, analyst UX) is the *primary deliverable*. Wazuh is the upstream telemetry source, integrated seriously, but never positioned as the product.

That's a dense sentence. Let's unpack it.

### "Threat-informed"

A threat-informed system is built around *what attackers actually do*, not around *what's easy to log*. Concretely: the project doesn't try to ingest every possible log type and surface them. It picks two specific threat surfaces (identity, endpoint) because those are where modern attackers live, and it shapes the entire detection and correlation logic around them. The opposite of threat-informed is data-driven-from-volume — "we have a lot of logs, let's see what they tell us." That ends in SIEM-shaped projects with no detection thesis. CyberCat refused that path.

### "Automated incident response"

Three words doing a lot of work:

- **Incident** = a *correlated* event story, not a single alert. One brute-force login is not an incident; brute-force-followed-by-success-followed-by-suspicious-process is. The project builds the machinery to recognize the chain.
- **Response** = the system can *act*, not just observe. Block an IP, kill a process (in the lab), invalidate a session. The actions are real; the safety rails are what keep them lab-scoped.
- **Automated** = the response policy decides what's safe to do automatically vs. what needs an analyst to approve. The four-tier classification (auto-safe / suggest-only / reversible / disruptive) lives downstream of this single word.

### "Identity compromise + endpoint compromise"

The fusion is the whole point. A SIEM might surface "user X had 5 failed logins" and "host Y ran a suspicious binary" as two separate alerts on two separate dashboards. CyberCat's correlator joins them when the same user owns the session that ran the binary — that's the `identity_endpoint_chain` rule (Phase 11). This pairing is also the project's *defense* against scope creep: every proposed feature gets tested against "does this improve the identity-endpoint correlation story?" If not, it's probably out of scope.

### "Custom application layer is the star"

This is the rule that prevents CyberCat from becoming a Wazuh skin. Wazuh is consumed as upstream — it ships agents, it has rules, it has a manager. CyberCat does not rebuild any of that. But everything *above* the raw Wazuh alert (normalization to a canonical event shape, entity extraction, correlation across signals, incident lifecycle, response policy, analyst UI) is custom code in the `backend/app/` tree. That's where the engineering credibility lives. Anyone can deploy Wazuh; the project's value is the layer above it.

### Out-of-scope items

ADR-0001 is also *defined by what it rejects*: offensive tooling, hack-back, multi-tenant SaaS, vuln management, malware detonation, generic log dashboards, enterprise-parity SIEM/EDR rebuilds. Each rejection prunes a potential growth path that would have made the project less coherent. When an ADR explicitly closes a door, future-you stops asking "should we add X?" — the answer was already given.

**Why this matters for you, the operator, in 2026-05:** every time someone (including a future Claude session) suggests "what if we added Y feature," ADR-0001 is the test. If Y doesn't improve normalization, correlation, the incident model, the response policy, or the analyst UX, it's probably out. That's not a constraint — that's the reason the project still has a clear shape after 19 phases.

---

## ADR-0002 — Tech stack: what runs the project, and why each piece

`docs/decisions/ADR-0002-tech-stack.md` is the second-most-load-bearing document. The decision is a table:

| Layer | Choice | Why this and not the alternative |
|---|---|---|
| Backend language | **Python 3.11+** | Security tooling lingua franca. Python is what Sigma rules are written in, what most threat-intel libraries ship for, what auditd/Wazuh tooling assumes. Picking Go would have been faster at runtime but lost the security-ecosystem fit. |
| API framework | **FastAPI** | Pydantic models compile to OpenAPI compile to a typed TypeScript client. End-to-end type safety with no manual contract writing. Django was rejected as too heavy for an API-first product. |
| Primary DB | **PostgreSQL** | Single-store decision. Postgres' `JSONB` column type handles semi-structured fields (raw event snapshots, evidence blobs, rationale metadata) without pulling in a second database. |
| Ephemeral store | **Redis** | Sliding correlation windows, dedup keys, cooldowns, caches — exactly what Redis is good at. Intentionally *not* used as a queue (queues would need durability guarantees Redis doesn't trivially provide). |
| Telemetry source | **Wazuh** | Real agent-collected endpoint telemetry. Treated as upstream boundary — we consume, we don't rebuild. |
| Detection format | **Sigma** | Portable, community-backed, threat-informed detection language. Signals detection-engineering credibility on a resume. |
| Frontend | **Next.js + TypeScript** | Product-grade UI with the App Router. Co-located in the same monorepo so a solo builder isn't context-switching between two repos. |
| Container runtime | **Docker / Podman Compose** | One file, profile-gated. K8s was rejected as the wrong tool for a laptop-scale single-operator product. |

The deeper reason this stack matters: **every choice has to compose with every other choice without a fight.** Pydantic + FastAPI + OpenAPI + openapi-typescript + Next.js means a single source of truth (the Pydantic models in `backend/app/api/schemas/`) flows all the way to the frontend's typed API client. Postgres + JSONB means evidence blobs don't need a second database. Compose + profiles means Wazuh can be off during normal coding without breaking ingest (the direct API path still works). Each piece is conventional in its layer; the compositional simplicity is the win.

### Concept primer — JSONB single-store decision

> *Intuition:* `JSONB` is Postgres' way of storing arbitrary JSON inside a single column while still being able to query into it.
>
> *Precise:* `JSONB` is a binary-encoded JSON storage format. Unlike storing a JSON string in `TEXT`, `JSONB` is parsed once on insert and stored in a tree form, so subsequent queries can extract fields without re-parsing — `WHERE raw_event->>'src_ip' = '10.0.0.1'` is a fast operation. You can also index *into* JSONB with GIN indexes. This gives you the flexibility of a document store (MongoDB-style) without leaving Postgres.
>
> *Why it exists for CyberCat:* the project ingests events from multiple telemetry sources, each with slightly different shapes. Forcing every field into a rigid relational schema would either be brittle (every new source = migration) or shallow (lowest-common-denominator schema loses information). JSONB lets the canonical fields be relational columns (typed, indexed, foreign-keyed) while raw payloads live in a JSONB sidecar — the best of both worlds.
>
> *Where else you'll see it:* GitLab uses JSONB for issue metadata; Sentry uses it for error context; Elasticsearch's value proposition was largely "we do this and Postgres can't" — until Postgres gained JSONB and largely closed the gap for OLTP-shaped workloads.

### Concept primer — Redis as ephemeral coordination, *not* queue

ADR-0002 explicitly says Redis is for "sliding correlation windows, dedup keys, cooldowns, caches" — not for queues. That's a deliberate scope-narrowing. Redis can be used as a queue (`LPUSH`/`BRPOP`), but if a queue worker crashes mid-job, the work can be lost without careful idempotency handling. CyberCat has a rule: **state that must survive a restart goes to Postgres; state that's allowed to evaporate goes to Redis.** Correlation windows are inherently ephemeral (a 60-second sliding window doesn't matter after 60 seconds). Incident records are not — they go to Postgres.

### Explicit non-choices

ADR-0002 lists what's *not* in the core stack and requires a new ADR to add:

- Kafka / Redpanda / NATS — no always-on event backbone.
- Temporal / Airflow / Prefect — no heavyweight workflow engine.
- ClickHouse / Elastic — no second analytic database.
- Kubernetes — not in core.
- Paid SaaS dependencies — anywhere in the critical path.

This is the same idea as ADR-0001's out-of-scope list, applied to infrastructure. It's a forcing function: anyone proposing one of these has to write an ADR, which forces them to articulate the tradeoff. Most proposals don't survive that step.

---

## ADR-0003 — Resource constraints: laptop-first

`docs/decisions/ADR-0003-resource-constraints.md` is the *operating-environment* ADR. CyberCat runs on the operator's daily-driver laptop (Lenovo Legion Slim 5 Gen 8, AMD). That single sentence has cascading implications.

### The three-tier service posture

```
Tier A (always-on, core): postgres + redis + backend + frontend
   Combined budget: ≤ ~4 GB RAM idle.

Tier B (on-demand): wazuh-manager + wazuh-indexer + wazuh-dashboard
   Started for integration work / demos, stopped otherwise.
   Gated by `docker compose --profile wazuh`.

Tier C (ephemeral): lab VMs, synthetic seeders, load generators
   Started per scenario, stopped when done.
```

The rule "no fourth tier" is the load-bearing part. Every "what if we added X always-on service" question is answered by this rule. There is no fourth tier; either the new thing fits in Tier A (and earns its RAM) or it goes to Tier B/C (and starts on demand).

### Concept primer — Compose profiles

> *Intuition:* Docker Compose profiles are a flag system that lets one `docker-compose.yml` describe multiple service configurations.
>
> *Precise:* in Compose v2, you can tag a service with `profiles: [wazuh]`. By default, `docker compose up` skips profiled services. Run `docker compose --profile wazuh up` and the tagged services start alongside the unprofiled ones. This lets a single compose file describe both "minimum stack" and "demo stack" without splitting into multiple files.
>
> *Why CyberCat uses it:* the Wazuh stack is heavy (~1.8 GB additional). Without profiles, you'd either run Wazuh always (violates ADR-0003), maintain two compose files (violates DRY), or add an env-var `if` block (Compose doesn't support that cleanly). Profiles are the clean answer.
>
> *Where in CyberCat:* `infra/compose/docker-compose.yml` tags `wazuh-manager`, `wazuh-indexer`, and `lab-debian`'s wazuh-agentd with `profiles: [wazuh]`. The `agent` profile (default) tags the custom telemetry agent. `start.sh` accepts `--profile wazuh`/`--profile agent`/both/neither.
>
> *Where else you'll see it:* Compose's own docs use it for dev/prod/test variants. Many open-source projects (Mastodon, Sentry self-hosted) use profiles to separate optional services like ElasticSearch.

### Restartability as a design rule

ADR-0003 says: "the system must recover cleanly from `compose down && compose up`." This sounds boring. It's actually one of the most important rules in the project. It means:

- Every Postgres write must be durable on its own. No "the queue is in Redis, we'll flush it later."
- Every Redis structure must be reconstructible on restart. Sliding windows are *allowed* to lose history on restart because their semantics are time-windowed.
- Every long-running async task must tolerate being killed mid-run. Idempotency keys, dedup keys, cursor checkpoints — all the patterns CyberCat uses for ingest were chosen with this rule in mind.

Phase 19 (resilience hardening) made this rule load-bearing in code: the `safe_redis` circuit breaker and the `EventBus._supervisor` reconnect loop both exist because ADR-0003 promised restartability. Without that promise, the chaos testing in Phase 19.5 would have nothing to verify against.

### Demo-first sizing

ADR-0003 also sets a demo-day expectation: "Core + Wazuh + 1 lab VM" should fit in ~14 GB RAM during a demo, but not have to fit during normal coding. The implication: if you're building a feature for the demo, build the lab-VM-running version. If you're building a feature for normal use, assume Tier A only. This is why `lab-debian` is opt-in via Compose profile rather than always-on.

---

## The Project Brief

`Project Brief.md` is the operator's *original prompt* to the AI assistant — frozen, immutable. It's the document that says "this is the project; do not reinterpret it into something easier." Reading it tells you what was load-bearing in the operator's head before any code existed:

- "Threat-informed automated incident response platform"
- "Focused on identity compromise + endpoint compromise"
- "The custom application layer is the most important part"
- "Defensive-only operation, lab-scoped"
- "Polished analyst frontend as a first-class deliverable"
- "Resume-grade — should feel like a real defensive product to a recruiter or security engineer"

ADR-0001 is the formal version of these claims; the Project Brief is the human version. They say the same thing, but the Project Brief includes phrasings that didn't make the ADR — like "incident brain layered on top of security telemetry" and "incidents are made of relationships, not just alerts." Those phrasings are the soul of the project; the ADR is the contract.

The Project Brief is also where the *anti-vision* lives. It explicitly lists what CyberCat must not be:

- not a SIEM clone
- not an EDR clone
- not a threat-intel portal
- not a vuln scanner
- not a log dashboard
- not a Wazuh dashboard
- not a CTF toy

Every one of these would have been an *easier* project to build. Phase 0 ruled them out before code started so the build stayed coherent.

---

## CLAUDE.md — the operating contract

`CLAUDE.md` is the rule file every AI session reads first. Phase 0 produced its initial structure; it's been refined continuously through 19 phases (Phase 16 added the agent rules; Phase 17 added the host-safety section; Phase 18 added the §9 Teaching Mode section after the operator's first session of feeling lost in their own codebase). Today it has 11 sections and ~250 lines. The most important sections:

- **§1 Project Identity (non-negotiable)** — the one-paragraph version of ADR-0001. This is the rule that prevents the project from drifting into SIEM territory.
- **§2 Architecture Guardrails** — the conceptual layers (telemetry → normalization → detection → correlation → incident state → response → frontend) that every code change must respect.
- **§3 Stack Constraints** — the codified version of ADR-0002.
- **§4 Scope Boundaries** — codified version of ADR-0001's out-of-scope list.
- **§5 Coding Expectations** — typed Python, typed TypeScript, Alembic-only schema changes, no silent assumption changes.
- **§7 Resource Discipline** — codified version of ADR-0003.
- **§8 Host Safety (non-negotiable)** — added Phase 16 when the project introduced response actions that could affect filesystem state. The rule: nothing in the project may affect the operator's host OS, host network, host firewall, or any path outside the project directory. All "destructive" actions stay inside lab containers.
- **§9 Teaching Mode (non-negotiable)** — added Phase 18-ish. Every non-trivial change requires a *before* and *after* explanation, logged to `docs/learning-notes.md`. This is the rule that's making *this very document* exist. Phase 19.7's whole sprint is built on §9.
- **§11 Documentation Map** — the index of stable documents.

CLAUDE.md is *operator-authored* — every rule in there exists because the operator decided it should. It's the operator's voice talking to all future sessions. If a rule's reason isn't obvious, that's a sign the rule needs more "why" — the operator's been adding "why" lines to rules as the project matures.

---

## What the layers look like, conceptually

ADR-0002 + the Project Brief together imply a layered architecture that wasn't yet built in Phase 0 but was decided in Phase 0. Knowing this layering before reading the code is what makes Phases 1–19 navigable:

```
┌───────────────────────────────────────────────────────────────┐
│  Analyst Frontend (Next.js + TypeScript)                      │
│  — incidents, entity detail, detections, kill chain, actions  │
└───────────────────────────▲───────────────────────────────────┘
                            │ typed REST (OpenAPI → TS client)
┌───────────────────────────┴───────────────────────────────────┐
│  Product API (FastAPI)                                        │
│  /incidents · /entities · /events · /detections · /responses  │
└───▲─────────▲─────────────▲──────────────────▲────────────────┘
    │         │             │                  │
    │     ┌───┴───────┐ ┌───┴────────┐ ┌───────┴──────────┐
    │     │ Correlator│ │ Detection  │ │ Normalizer       │
    │     │ engine    │ │ evaluation │ │ raw → canonical  │
    │     └───▲───────┘ └────▲───────┘ └───────▲──────────┘
    │         │              │                 │
    │         │              │      ┌──────────┴──────────┐
    │         │              │      │ Ingest adapters     │
    │         │              │      │ Wazuh poller / API  │
    │         │              │      │ + custom agent      │
    │         │              │      └──────────▲──────────┘
    │         │              │                 │
    │         │              │            ┌────┴─────┐
    │         │              │            │  Wazuh   │
    │         │              │            │ + agents │
    │         │              │            └──────────┘
    │     ┌───┴────┐    ┌────┴─────────┐
    │     │ Redis  │    │ Postgres     │
    │     │(ephem) │    │ (truth)      │
    │     └────────┘    └──────────────┘
    │
    └──► Response policy + handlers (block_observable, kill_process,
         quarantine_host, invalidate_session, request_evidence...)
```

**Read this diagram top-down:** an analyst clicks something in the UI → the request hits a FastAPI route → the route reads from Postgres (or writes to Redis for ephemeral state) → the response renders in the UI.

**Read this diagram bottom-up:** a Wazuh agent (or the custom telemetry agent) emits an event → an ingest adapter receives it → the normalizer converts it to canonical form → entity extraction populates the entities table → detectors evaluate it → the correlator decides if it joins an incident → response policy decides if any action should fire → the result eventually surfaces to the analyst.

These two paths share the *same Postgres tables* and the *same canonical event schema*. The whole architecture is built around that single shared model. If a change breaks the symmetry — adds something that's only visible to the bottom-up flow but not the top-down — that's a code smell.

---

## What you should be able to answer cold after this walkthrough

If you re-read this document a week from now and these answers come back smoothly, Phase 0 has stuck:

1. **What is CyberCat in one sentence?** A threat-informed automated incident response platform focused on identity + endpoint compromise, with a custom application layer above pluggable telemetry sources.

2. **What is CyberCat *not*?** Not a SIEM, not an EDR, not a threat-intel portal, not a Wazuh dashboard, not a CTF toy. Each of these was explicitly rejected in ADR-0001.

3. **Why Postgres + Redis instead of just Postgres?** Postgres holds durable truth (incidents, entities, evidence). Redis holds ephemeral coordination (sliding windows, dedup, cooldowns, caches). The separation is intentional: state that must survive a restart goes to Postgres; state allowed to evaporate goes to Redis.

4. **Why is Wazuh in profile and not always-on?** ADR-0003. Wazuh costs ~1.8 GB RAM. The laptop-budget rule says core stack must fit in ~4 GB Tier A. So Wazuh is Tier B — opt-in via `docker compose --profile wazuh` for integration work and demos.

5. **What's an ADR and where do they live?** Architecture Decision Record. One-page memo with Context / Decision / Consequences / Alternatives. Lives in `docs/decisions/ADR-NNNN-*.md`. Immutable in spirit — when a decision changes, write a new ADR rather than editing the old one.

6. **Why does CyberCat fuse identity + endpoint signals?** Because incidents in 2026 don't stay in one surface — an attacker compromises a credential (identity) and uses it to do something on a host (endpoint). A platform that joins these signals tells a coherent attack story; a platform that shows them on separate dashboards forces the analyst to do the joining manually.

If any of these answers don't come smoothly, re-read the ADR they live in. The ADRs are not long.

---

## Try-it-yourself (optional, ~10 minutes)

Open these three files side by side in your editor:

1. `docs/decisions/ADR-0001-project-scope.md`
2. `docs/decisions/ADR-0002-tech-stack.md`
3. `docs/decisions/ADR-0003-resource-constraints.md`

Read the **Consequences** section of each. Then ask yourself: *"In Phase 19.5 (the chaos testing we just finished), which Consequence from these three ADRs was the design constraint we were verifying against?"*

Hint: it's in ADR-0003. Look for the word "restart."

The answer is: ADR-0003's "the system must recover cleanly from `compose down && compose up`" is the consequence Phase 19.5 was verifying. The chaos scenarios (kill Redis / restart Postgres / etc.) are the *operational tests* of that single rule. Eighteen phases later, a Phase 0 sentence is still load-bearing.

---

## Concepts logged from this phase

The following concepts are introduced in this walkthrough and have learning-notes entries (or should — flag any that don't, and the assistant will write them):

- **ADR (Architecture Decision Record)** — *new entry needed in `learning-notes.md`* (flag for sweep).
- **JSONB single-store decision** — *new entry needed*.
- **Redis as ephemeral coordination, not queue** — *new entry needed*.
- **Compose profiles** — already in `learning-notes.md` § "Docker Compose profiles."
- **Tiered service posture** — *new entry needed* under "Project-specific patterns."

These will be added to `learning-notes.md` during Week 4's audit sweep, or earlier on request.

---

## What's next

**Phase 1 walkthrough** — `phase-1-walkthrough.md`. Topic: the first code. Repo skeleton, `backend/app/main.py`, the FastAPI scaffold, the first Postgres schema (Alembic migration 0001), the first Pydantic model. Phase 0 was deciding; Phase 1 was building the skeleton you build everything else into.

The reading list for Phase 1 will live in that walkthrough. For tonight, you're done.

**Today's commit:** `docs/walkthroughs/phase-0-walkthrough.md` (this file). Suggested message:
```
docs(walkthroughs): phase 0 — project foundations, ADRs 0001-0003, the scope contract
```
