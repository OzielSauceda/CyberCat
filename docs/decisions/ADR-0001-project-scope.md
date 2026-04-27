# ADR-0001 — Project scope: threat-informed IR platform for identity + endpoint compromise

- **Status:** Accepted
- **Date:** 2026-04-19
- **Related:** `Project Brief.md`, `CLAUDE.md`

## Context

The operator wants a single, serious, resume-grade defensive security project. The market of plausible projects splits roughly into: SIEM clones, EDR clones, threat-intel portals, vuln scanners, sandboxes, red-team frameworks, generic SOC simulators, and Wazuh dashboards. These are either oversaturated, shallow, or require infrastructure beyond a single laptop.

The brief identifies a more defensible slice: a **product-shaped incident response platform** that sits *above* raw telemetry and *below* human analyst work — the layer that turns fragmented signals into structured, explainable incidents and guarded responses, with a specific threat focus on **identity compromise + endpoint compromise**.

## Decision

CyberCat's scope is a threat-informed automated incident response platform with:

1. A custom application layer (normalization, correlation, incident model, response policy, analyst UX) as the primary deliverable and the primary source of engineering credibility.
2. Identity + endpoint as the joint threat surface. The product value comes specifically from *fusing* the two.
3. Wazuh as the upstream telemetry source, integrated seriously but never positioned as the product.
4. Defensive-only operation, lab-scoped, for systems the operator owns.
5. A polished analyst frontend as a first-class deliverable, not a late-stage skin.

## Explicitly out of scope

- Offensive/red-team tooling, hack-back behavior, exploitation of third-party systems.
- Rebuilding enterprise-parity SIEM/EDR/SOAR features.
- Multi-tenant SaaS concerns.
- Vulnerability management, malware detonation, phishing simulation as core features.
- Generic log dashboards.

## Rationale

- **Fit for one strong builder on a laptop.** The correlation/incident/response layer is mostly software and data model work; it scales with engineering effort, not infra spend.
- **Differentiation.** Most portfolio projects stop at "ingest and display." Correlation + incident lifecycle + guarded response is visibly harder and more product-shaped.
- **Threat relevance.** Identity abuse and endpoint post-compromise are the realistic pressure points defenders work today; pairing them signals modern understanding.
- **Explainability.** An incident model built around "why does this exist, what supports it, what did we do" is both a real engineering problem and a strong demo artifact.
- **Lab-safe.** Restricting to owned systems lets us ship real response actions without legal or ethical concerns.

## Consequences

- Feature decisions must be tested against: does this improve the correlation / incident / response / explainability story? If not, it is probably out of scope.
- "Add more log sources" is only valuable if it *enables new correlations*. Pure volume is not a product improvement here.
- Wazuh-centric features are acceptable as integrations but should not dominate the roadmap.
- Frontend must ship vertically with backend slices; it cannot be deferred to the end.

## Alternatives considered

- **Pure SIEM / log platform.** Rejected: oversaturated, and the interesting problems live *above* storage.
- **Pure EDR-lite.** Rejected: the endpoint-only surface misses the identity dimension, which is where modern attacks start.
- **Threat-intel portal.** Rejected: too passive; no operational decision surface.
- **CTF-style scenario runner.** Rejected: reads as a toy, not a product.
