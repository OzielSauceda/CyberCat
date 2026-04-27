# ADR-0002 — Tech stack: Python/FastAPI + Postgres/Redis + Wazuh/Sigma + Next.js/TS

- **Status:** Accepted
- **Date:** 2026-04-19
- **Related:** `Project Brief.md`, ADR-0003 (resource constraints)

## Context

A stack that simultaneously looks credible to a security-engineering reviewer, costs zero in licensing, and runs sustainably on a single laptop (Lenovo Legion Slim 5 Gen 8, AMD). Several popular "enterprise-feel" stacks (Kafka + ClickHouse + Temporal + K8s) fail the laptop-sustainability test. Several "easy" stacks (pure Flask + SQLite + plain HTML) fail the credibility test.

## Decision

The stack is finalized:

| Layer | Choice | Role |
|---|---|---|
| Backend language | **Python 3.11+** | Security tooling lingua franca; strong ecosystem for parsers, rule engines, ATT&CK data. |
| API framework | **FastAPI** | Typed pydantic models → OpenAPI → typed frontend client. Modern, fast, minimal ceremony. |
| Primary DB | **PostgreSQL** | Durable truth for incidents, entities, evidence, actions. JSONB columns cover semi-structured fields without a separate doc store. |
| Ephemeral store | **Redis** | Sliding correlation windows, dedup keys, cooldowns, caches. |
| Telemetry source | **Wazuh** | Upstream agent + rule infrastructure; we consume it, we don't rebuild it. |
| Detection format | **Sigma** | Portable, community-backed, threat-informed detection language. |
| Frontend | **Next.js + TypeScript** | App Router, product-grade UI, SSR where useful, strong TS ergonomics. |
| Container runtime | **Podman or Docker Compose** | Compose file works with either. One-command local stack. |
| Lab | **1–2 lightweight VMs** | For realistic endpoint telemetry demos without a homelab. |

## Rationale

- **Python + FastAPI** gives us typed contracts end-to-end when paired with generated TS clients. It also matches the security-engineering skill Python signal on a resume.
- **PostgreSQL single-store** removes the "which database?" question for a solo builder. JSONB handles evidence blobs, raw-event snapshots, and rationale metadata without pulling in Mongo/ES.
- **Redis** is intentionally scoped to the ephemeral work where it excels. We won't use it as a queue unless/until we demonstrably need one (ADR-worthy at that point).
- **Wazuh** gives us real agent-collected endpoint telemetry and a credible integration story without us writing an agent. We treat it as an upstream boundary.
- **Sigma** signals detection-engineering credibility. It also gives us a real rule pack to mine for initial detectors.
- **Next.js + TS** lets the analyst UI feel productized without fighting framework quirks. Co-locating frontend in the same repo keeps a solo builder fast.
- **Compose over K8s** — K8s is the wrong tool for a laptop-scale single-operator product.

## Explicit non-choices

The following are **not** part of the core stack. Any proposal to add one requires a new ADR:

- Kafka / Redpanda / NATS JetStream — no always-on event backbone in core.
- Temporal / Airflow / Prefect — no heavyweight workflow engine in core.
- ClickHouse / Elastic-as-product-store — no second analytic DB in core.
- Kubernetes — not in core.
- Full OpenCTI — not in core (may reference specific ATT&CK / STIX data files).
- Paid SaaS dependencies anywhere in the critical path.

## Consequences

- Backend code should treat pydantic models as the canonical contract; frontend types flow from OpenAPI.
- Correlation windows implemented on Redis must tolerate restarts (they are ephemeral by definition). Any state that must survive restart goes to Postgres.
- When we need async work (scheduled correlation sweeps, Wazuh polling), start with FastAPI `BackgroundTasks` or a simple asyncio loop inside the backend process. Introduce a worker (RQ/Arq) only when that breaks down, and record it in an ADR.
- Adding a new top-level service costs laptop RAM. The bar for new services is high.

## Alternatives considered

- **Go + gRPC + React.** Faster runtime but slower to build; loses the Python security-ecosystem advantage.
- **Django + DRF.** Heavier than FastAPI for an API-first product; template layer unused.
- **MongoDB as primary.** Weaker for the relational incident/evidence graph we need.
- **Elastic as primary store.** Too heavy for laptop, and we'd be rebuilding SIEM.
- **Plain React (Vite).** Works, but Next.js App Router gives a more product-like frontend with minimal extra weight.
