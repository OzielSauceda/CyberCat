# ADR-0003 — Resource constraints: laptop-first, on-demand heavy services

- **Status:** Accepted
- **Date:** 2026-04-19
- **Related:** `Project Brief.md`, ADR-0002 (stack)

## Context

The platform will be developed, run, and demonstrated on the operator's primary working machine: a **Lenovo Legion Slim 5 Gen 8, 14-inch, AMD**. This is a capable laptop but not a server. Long coding sessions cannot tolerate a constantly hot, fan-maxed, RAM-starved host. Several security platforms (Wazuh indexer, OpenSearch/Elastic, OpenCTI, k8s clusters) will chew through available resources if left running all day.

The project must still look ambitious and feel alive. "Laptop-sustainable" cannot become "anemic."

## Decision

All design and roadmap decisions must respect the following operating rules:

1. **Tiered service posture.** Services are classified into three tiers:
   - **Tier A (always-on, core):** `postgres`, `redis`, `backend`, `frontend`. Combined budget: ≤ ~4 GB RAM idle.
   - **Tier B (on-demand):** `wazuh-manager`, `wazuh-indexer`, `wazuh-dashboard`. Started for integration work and demos, stopped otherwise. Gated by `docker compose --profile wazuh`.
   - **Tier C (ephemeral):** lab VMs, synthetic seeders, load generators. Started per scenario, stopped when done.
2. **No fourth tier.** We do not add "always-on heavy" to the core.
3. **One compose file, profile-gated.** A single `docker-compose.yml` owns all services. Profiles control what runs.
4. **Restartable by design.** Redis state is ephemeral; Postgres state is durable. The system must recover cleanly from `compose down && compose up`.
5. **Demo-first sizing.** If a feature requires more than Tier A to *function*, it must either degrade gracefully when Tier B/C are off, or be marked as demo-only in the UI.

## Implications

- **Wazuh integration** must tolerate Wazuh being offline during dev. The ingest path should fall back to the direct API adapter + seeder so developers aren't forced to boot Wazuh to work on correlation.
- **Correlation** runs inside the backend process (asyncio) until/unless a real scaling need appears. No queue/worker in v1.
- **Frontend dev server** is stoppable without losing backend progress.
- **Lab VMs** are not part of the compose lifecycle. They are spun up separately for scenario runs.
- **Background tasks** (ATT&CK data refresh, rule-pack sync) should be manual commands first, scheduled later — never a hidden always-on consumer.

## Budget guardrails

Rough targets (to be measured, not theoretical):

| Posture | RAM target | CPU expectation |
|---|---|---|
| Core only (Tier A) | ≤ ~4 GB | Low background |
| Core + Wazuh | ≤ ~10 GB | Moderate during scans |
| Core + Wazuh + 1 lab VM | ≤ ~14 GB | Demo-only posture |

If measured numbers exceed these, we tune before we scale.

## Consequences

- Any PR that introduces a new always-on service must update this ADR (or be rejected).
- Any feature that only works when Tier B is up must be clearly labeled in the runbook and in the UI.
- Resource regressions are a legitimate reason to reject a change, same as correctness regressions.
- The project's "impressiveness" comes from product depth, not infrastructure sprawl. This is both a constraint and a design philosophy.

## Alternatives considered

- **Cloud dev environment.** Rejected: ongoing cost, dependency on connectivity, loses the "runs on a laptop" story that makes this project reproducible for reviewers.
- **Kill Wazuh, emit events ourselves.** Rejected: loses the real-telemetry credibility the integration provides.
- **Always-on Wazuh.** Rejected: violates the laptop-sustainability rule during normal coding sessions.
