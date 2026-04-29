# CLAUDE.md — CyberCat Project Rules

Stable guardrails for all Claude sessions on this repository. Read this first, every session. Do not drift from these rules without an ADR update.

---

## 1. Project Identity (non-negotiable)

CyberCat is a **threat-informed automated incident response platform** focused on **identity compromise + endpoint compromise**. It is a focused, product-shaped mini XDR/SOAR slice — not a SIEM, not an EDR, not a Wazuh skin, not a dashboard, not a threat-intel portal, not a CTF toy.

The **custom application layer is the star**: normalization, correlation, the incident model, response policy, analyst UX. Wazuh is **upstream telemetry**, not the product.

Defensive-only. Lab-safe. Designed for systems the operator owns.

## 2. Architecture Guardrails

- Maintain conceptual separation between these layers even when services are colocated:
  1. Telemetry intake (Wazuh + any direct agents/feeds)
  2. Normalization (raw events → internal canonical event/entity model)
  3. Detection interpretation (Sigma + custom detectors)
  4. Correlation (signals → incidents)
  5. Incident state + evidence history (Postgres-owned truth)
  6. Response policy + action execution (guarded, auditable)
  7. Analyst frontend (Next.js, product-grade)
- Postgres owns durable truth. Redis is for ephemeral coordination (correlation windows, dedup, cooldowns, throttles, caches) — never the system of record.
- Every incident must be explainable: the DB must retain *which events* and *which rules* contributed, plus a human-readable rationale.
- Response actions are first-class, logged, and classified as `auto-safe`, `suggest-only`, `reversible`, or `disruptive`.

## 3. Stack Constraints (finalized — see ADR-0002)

Backend: Python + FastAPI. Data: PostgreSQL + Redis. Telemetry: Wazuh. Detection: Sigma. Frontend: Next.js + TypeScript. Runtime: Podman or Docker Compose. Lab: 1–2 lightweight VMs max.

Do not introduce Kafka, Temporal, ClickHouse, Elastic, full OpenCTI, Kubernetes, or any always-on heavyweight infra into the core. Optional "future possibility" notes are fine; core plan must run on the operator's laptop.

## 4. Scope Boundaries

**In scope:** identity signals, endpoint signals, correlation across them, ATT&CK-aware context, incident lifecycle, guarded lab response, explainability, polished analyst UI.

**Out of scope:** offensive tooling, hack-back, exploitation against third parties, malware detonation, pure vuln management, generic SIEM rebuild, enterprise-parity auth, multi-tenant SaaS concerns.

## 5. Coding Expectations

- Typed Python (pydantic models, type hints). Typed TypeScript (no `any` in product code).
- API contracts defined once (pydantic → OpenAPI → typed frontend client).
- Migrations via Alembic. No ad-hoc schema drift.
- Tests meaningful at seams: normalization, correlation rules, response policy gating. Skip trivial getter tests.
- No silent changes to core assumptions. If reality forces a pivot, write an ADR.
- Frontend must reflect the actual mental model of the product, not a generic admin CRUD.

## 6. Custom-Built vs Integrated

**Custom (we own, we build):** internal event/entity schema, normalization layer, correlation engine, incident model + lifecycle, response policy engine, product APIs, analyst UI, ATT&CK mapping glue, evidence model, **and (since Phase 16) the default telemetry agent** (`agent/`, `cct-agent` container) which tails sshd events directly into the canonical event shape.

**Integrated (consumed, not rebuilt):** Wazuh (alternative telemetry source + Active Response dispatch), Sigma (rule format + parsers), MITRE ATT&CK reference data, Postgres, Redis.

The telemetry layer is **pluggable**: agent and Wazuh are interchangeable as ingest sources, and downstream code is source-agnostic (keys on `EventSource` enum, not on adapter specifics). Agent is default; Wazuh is opt-in via `--profile wazuh`. **Both stay supported indefinitely** — Wazuh remains the only path for real OS-level Active Response (`iptables`, `kill -9`); the agent is telemetry-only by design. See ADR-0011.

When a decision is ambiguous, prefer "build it custom in the app layer" over "bolt on another tool."

## 7. Resource Discipline (see ADR-0003)

Target machine: Lenovo Legion Slim 5 Gen 8 (AMD). Daily-usable. Core compose stack should idle under ~4–6 GB RAM and wake-spike reasonably. Lab VMs are started on demand for demos, not kept hot 24/7.

## 8. Host Safety (non-negotiable)

CyberCat runs on the operator's personal Lenovo Legion. Nothing in this project — no response handler, no lab container, no smoke test, no command run during a session — may affect the host OS, host network, host firewall, or any filesystem path outside this project directory.

- **All "destructive-sounding" actions stay inside lab containers.** `iptables` rules, `kill -9`, file mutations, blocked observables — these execute inside the lab container's own network/PID namespace and disappear when the container is removed. Lab containers must not run with `--network=host`, `--pid=host`, or `--privileged` unless an ADR explicitly justifies it.
- **`*_lab` action handlers target lab containers only.** Never wire a Wazuh agent installed on the host (or any non-CyberCat machine) into the AR dispatch path. If a future feature needs to act on a real host, it gets a separate name, a separate flag, and an ADR.
- **No host-level escalation during sessions.** Commands run by Claude must not require `sudo` / Administrator on the Windows host, must not modify the host firewall / registry / services / scheduled tasks, and must not write outside the project directory.
- **Use Docker's own reset path.** `docker compose down -v`, `docker system prune` — these are the cleanup tools. Never reach for host-level destructive shortcuts.
- **No secrets to third-party services.** Don't upload code, logs, or `.env` contents to pastebins, gist, or external diagram/render tools without explicit operator approval.
- **When in doubt, ask first.** If an action could plausibly escape the container, confirm with the operator before running it.

## 9. Session Behavior

- Before major changes, state what was found and what will be created/updated.
- Prefer editing existing files to creating new ones.
- If something is ambiguous, take the narrowest reasonable assumption and record it in `PROJECT_STATE.md` under Open Questions.
- Update `PROJECT_STATE.md` when status changes.
- Write an ADR when a decision has long-term architectural weight.
- Never mark work "done" that wasn't actually verified (typecheck, run, or exercise).

## 10. Documentation Map

- `CLAUDE.md` — this file. Stable rules.
- `PROJECT_STATE.md` — living status.
- `docs/architecture.md` — canonical system design.
- `docs/runbook.md` — how to run, seed, demo, test.
- `docs/decisions/ADR-XXXX-*.md` — durable decisions.
- `Project Brief.md` — authoritative vision document. Source of truth for intent.
