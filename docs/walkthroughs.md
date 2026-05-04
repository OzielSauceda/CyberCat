# CyberCat — Operator Walkthroughs

End-to-end traces of how the project works, written by the operator during Phase 19.7 (the consolidation sprint). Each slice follows a single piece of data or a single concept across every layer it touches, with every file path and every reason-it's-shaped-that-way called out in the operator's own words.

This file is the headline artifact of the consolidation sprint. It is the one document the operator should be able to open six months from now and immediately re-orient to the entire system.

---

## How to use this file

- **Each slice is operator-authored.** The assistant explains, points at files, and answers questions, but the prose in this file is the operator's own. That's not a stylistic choice — it's the friction mechanism that converts reading into retention.
- **Slices build on each other.** Slice 0 sets the project frame. Slices 1–10 walk progressively deeper into the data plane, then up into detection and correlation, then up into the UI and the resilience story. Read in order on first pass; jump around on re-reads.
- **Each slice ends with the slice's exit criterion.** That's the single sentence the slice should make answerable cold. If a re-read leaves the criterion unanswerable, the slice needs a rewrite.
- **No assistant-generated prose in this file.** If a slice section says "operator writes here" and is empty, that day hasn't been done yet. Empty sections are a feature — they show what's still ahead.

---

## Index

- [Slice 0 — What CyberCat is and isn't](#slice-0--what-cybercat-is-and-isnt)
- [Slice 1 — A request arrives at the FastAPI backend](#slice-1--a-request-arrives-at-the-fastapi-backend)
- [Slice 2 — A raw event becomes an incident-eligible row](#slice-2--a-raw-event-becomes-an-incident-eligible-row)
- [Slice 3 — A detection fires](#slice-3--a-detection-fires)
- [Slice 4 — Detections become an incident](#slice-4--detections-become-an-incident)
- [Slice 5 — An incident appears in the analyst's browser without polling](#slice-5--an-incident-appears-in-the-analysts-browser-without-polling)
- [Slice 6 — A login becomes a request the backend trusts](#slice-6--a-login-becomes-a-request-the-backend-trusts)
- [Slice 7 — From an incident to a one-click response suggestion](#slice-7--from-an-incident-to-a-one-click-response-suggestion)
- [Slice 8 — An SSH login on lab-debian becomes a backend event](#slice-8--an-ssh-login-on-lab-debian-becomes-a-backend-event)
- [Slice 9 — Redis dies; the system stays up](#slice-9--redis-dies-the-system-stays-up)
- [Slice 10 — A chaos scenario runs end-to-end](#slice-10--a-chaos-scenario-runs-end-to-end)
- [Closing — What I now understand](#closing--what-i-now-understand)
- [Parallel mini-project](#parallel-mini-project)

---

## Slice 0 — What CyberCat is and isn't

*Phase 19.7 sprint, Week 1, Mon. Operator writes here.*

> **Reading list before writing:** `CLAUDE.md` § 1–9, `Project Brief.md`, ADRs 0001 / 0002 / 0003.
>
> **Exit criterion:** finish the sentence "CyberCat is not a SIEM because…" with a concrete answer naming a specific feature CyberCat does have and a SIEM doesn't.

---

## Slice 1 — A request arrives at the FastAPI backend

*Phase 19.7 sprint, Week 1, Wed. Operator writes here.*

> **Reading list before writing:** `backend/app/main.py`, `backend/app/api/routers/incidents.py`, `backend/app/auth/dependencies.py`, learning-notes § "FastAPI".
>
> **Exit criterion:** explain what `Depends(get_db)` does and why it's there.

---

## Slice 2 — A raw event becomes an incident-eligible row

*Phase 19.7 sprint, Week 1, Thu. Operator writes here.*

> **Reading list before writing:** `backend/app/api/routers/events.py`, `backend/app/ingest/pipeline.py`, `backend/app/ingest/normalizer.py`, `backend/app/ingest/dedup.py`, `backend/app/ingest/entity_extractor.py`.
>
> **Exit criterion:** name the seven stages of `ingest_normalized_event` without looking.
>
> **Note:** this is the most foundational slice in the entire sprint. Every detection / correlation / UI flow assumes the row is already in the events table. Spend the time.

---

## Slice 3 — A detection fires

*Phase 19.7 sprint, Week 2, Mon. Operator writes here.*

> **Reading list before writing:** `backend/app/detection/engine.py`, `backend/app/detection/rules/auth_failed_burst.py`, `backend/app/db/redis_state.py`.
>
> **Exit criterion:** explain why `auth_failed_burst` uses Redis instead of `SELECT count(*) FROM events WHERE ...`.

---

## Slice 4 — Detections become an incident

*Phase 19.7 sprint, Week 2, Tue. Operator writes here.*

> **Reading list before writing:** `backend/app/correlation/engine.py`, `correlation/rules/identity_compromise.py`, `correlation/rules/endpoint_compromise_standalone.py`, `correlation/rules/identity_endpoint_chain.py`.
>
> **Exit criterion:** name the three correlator rules and what each one looks for.

---

## Slice 5 — An incident appears in the analyst's browser without polling

*Phase 19.7 sprint, Week 2, Thu + Fri. Operator writes here.*

Two-part slice: backend SSE pipeline (Thu) and frontend rendering (Fri).

> **Reading list before writing:** `backend/app/streaming/bus.py`, `backend/app/streaming/publisher.py`, `backend/app/api/routers/streaming.py`, `frontend/app/incidents/[id]/page.tsx` and its panel components.
>
> **Exit criterion:** explain what would happen if `safe_redis` returned `None` instead of executing the publish.

---

## Slice 6 — A login becomes a request the backend trusts

*Phase 19.7 sprint, Week 3, Mon. Operator writes here.*

> **Reading list before writing:** `backend/app/auth/security.py`, `backend/app/auth/router.py`, `backend/app/auth/dependencies.py`, `backend/app/auth/models.py`.
>
> **Exit criterion:** explain why bcrypt uses a salt and what would break if it didn't.

---

## Slice 7 — From an incident to a one-click response suggestion

*Phase 19.7 sprint, Week 3, Wed. Operator writes here.*

> **Reading list before writing:** `backend/app/response/recommendations.py`, `backend/app/api/routers/incidents.py` (the `/recommended-actions` endpoint), `frontend/app/incidents/[id]/RecommendedActionsPanel.tsx`, ADR-0010.
>
> **Exit criterion:** explain why the engine is static rules and not ML, and what tradeoff that buys.

---

## Slice 8 — An SSH login on lab-debian becomes a backend event

*Phase 19.7 sprint, Week 3, Thu. Operator writes here.*

> **Reading list before writing:** `agent/cct_agent/main.py`, `agent/cct_agent/sources/sshd.py`, `agent/cct_agent/parsers/sshd.py`, `agent/cct_agent/shipper.py`, `agent/cct_agent/checkpoint.py`, ADR-0011.
>
> **Exit criterion:** explain what the agent does on log truncation versus log rotation.

---

## Slice 9 — Redis dies; the system stays up

*Phase 19.7 sprint, Week 4, Tue. Operator writes here.*

> **Reading list before writing:** `backend/app/db/redis.py`, `backend/app/streaming/bus.py:97-123`, wherever `safe_redis` is defined, `backend/tests/integration/test_redis_unavailable.py`, `docs/phase-19-plan.md` § A1.1.
>
> **Exit criterion:** explain what happens to in-flight detections during a Redis outage and why no events are lost.

---

## Slice 10 — A chaos scenario runs end-to-end

*Phase 19.7 sprint, Week 4, Wed. Operator writes here.*

> **Reading list before writing:** `labs/chaos/run_chaos.sh`, `labs/chaos/lib/evaluate.sh`, one scenario script (recommend `restart_postgres.sh`), `docs/phase-19.5-plan.md`.
>
> **Exit criterion:** explain why the orchestrator measures `accept_pct` instead of `acceptance_passed`.

---

## Closing — What I now understand

*Phase 19.7 sprint, Week 4, Fri. Operator writes here. 500–1000 words, operator-voice, the artifact you can re-read in six months.*

> **Reading list before writing:** this entire file, top to bottom, in one sitting.
>
> **Suggested structure (use, modify, or ignore):**
> 1. The one-paragraph elevator pitch — what CyberCat is in your own words.
> 2. The seven stages of ingest, briefly. (The spine of the whole system.)
> 3. The three detection-to-incident steps: detection → correlation → response policy.
> 4. The two telemetry sources and why both are kept.
> 5. The two resilience primitives (`safe_redis`, `EventBus._supervisor`) and why they exist.
> 6. The single biggest tradeoff CyberCat makes, and why you'd defend it.
> 7. Where you'd take it next, and what you've decided not to do.
>
> **Exit criterion:** you can recite this essay's outline (not verbatim — the structure) without looking.

---

## Parallel mini-project

Side track running across the sprint's four weekends. Lives in a separate public GitHub repo. Builds the same primitives CyberCat uses (FastAPI route, Postgres table, Alembic migration, Redis pub/sub, sliding-window detector) from scratch with no AI assistance.

### Scope (do not exceed)

- **Stack:** FastAPI + Postgres + Redis. Same versions as CyberCat.
- **Surface:** one POST endpoint, one GET-listing endpoint, one SSE endpoint, one detector rule.
- **Schema:** one table, two columns plus `id` and `created_at`. One Alembic migration.
- **Tests:** at least one pytest test that exercises the POST endpoint. (Not the goal — but a real test forces you to confront `pytest` fixtures and `httpx.AsyncClient`.)

### Why this exists

The mini-project is the only artifact that proves you can build CyberCat-shaped code with zero AI. Every line you type forces a tiny moment of "wait, what does this actually do?" Those moments compound into mastery. The CyberCat repo is co-authored by definition; the mini-project is yours alone, and that's exactly the recruiter signal you actually want.

### Weekly cadence

| Weekend | Goal |
|---|---|
| Week 1 | Repo init, FastAPI app, one POST endpoint, one Alembic migration, one Postgres table. Two evenings, two commits. |
| Week 2 | Add Redis pub/sub. POST publishes a message. New SSE endpoint emits each published message to subscribed clients. |
| Week 3 | Add a "≥3 events in 10s" detector using a Redis sorted-set sliding window. Log when it trips. |
| Week 4 | Polish: README, a paragraph in the README per concept used, pin to GitHub profile. |

### Self-imposed rules

- No AI assistance. No GitHub Copilot. No Claude, Cursor, or ChatGPT for any line of code in this repo. (Reading the FastAPI / Postgres / Redis docs is mandatory; reading CyberCat to remember a pattern is fine — *typing* is yours.)
- No copy-paste from CyberCat. Re-derive every pattern by hand even if you've seen it before. The point is the friction.
- Commit when work is coherent, not by the clock.
- Public repo from commit one. No "I'll polish first." The polish is the README, and you write it last.
