# CyberCat

[![CI](https://github.com/OzielSauceda/CyberCat/actions/workflows/ci.yml/badge.svg)](https://github.com/OzielSauceda/CyberCat/actions/workflows/ci.yml)
[![Smoke](https://github.com/OzielSauceda/CyberCat/actions/workflows/smoke.yml/badge.svg?branch=main)](https://github.com/OzielSauceda/CyberCat/actions/workflows/smoke.yml)

A threat-informed incident-response platform for Linux servers and cloud workloads — a focused mini XDR/SOAR slice that turns SSH brute-force attempts, suspicious process trees, and outbound C2 patterns into investigable incidents with kill-chain mapping and classified response actions.

CyberCat is **defensive-only and lab-safe**. It runs on a laptop in Docker. The custom application layer (normalization → correlation → incident lifecycle → response policy → analyst UX) is the product; Wazuh and Sigma are integrated upstream as telemetry sources.

## Quickstart

```bash
git clone https://github.com/OzielSauceda/CyberCat.git
cd CyberCat
./start.sh
# Backend on http://localhost:8000  •  Frontend on http://localhost:3000
```

The default profile brings up the custom Python telemetry agent, a sandboxed `lab-debian` target container, Postgres, Redis, the FastAPI backend, and the Next.js frontend. First boot auto-seeds a demo incident so the dashboard isn't empty.

To run with Wazuh as an alternative telemetry source: `./start.sh --profile wazuh`.

## What's in the box

- **Telemetry intake** — sshd login events, auditd process execution, and conntrack outbound connections, normalized into a single canonical event shape.
- **Detection** — four hand-written Python detectors plus a real Sigma engine, every detection tagged with MITRE ATT&CK technique IDs.
- **Correlation** — four correlator rules turn related detections into investigable stories. The headline rule, `identity_endpoint_chain`, joins a successful suspicious login with subsequent endpoint activity into one critical chained incident.
- **Response actions** — eight wired end-to-end, classified `auto-safe` / `reversible` / `disruptive` / `suggest-only`. Disruptive actions are scoped to the lab container; the host OS is never touched.
- **Real-time UI** — Server-Sent Events fan-out via Redis pub/sub. New incidents appear in the dashboard within 1–2 seconds.
- **Auth** — three roles (admin / analyst / read-only), email+password or Bearer tokens, optional OIDC SSO.
- **Attack simulator** — `labs/simulator/` ships a 5-stage credential-theft chain you can fire with `--speed 0.1 --verify` for a ~30-second compressed demo.

## Documentation

- **Vision** — [`Project Brief.md`](./Project%20Brief.md)
- **Architecture** — [`docs/architecture.md`](./docs/architecture.md)
- **Runbook** — [`docs/runbook.md`](./docs/runbook.md)
- **Decisions** — [`docs/decisions/`](./docs/decisions/)
- **Project state** — [`PROJECT_STATE.md`](./PROJECT_STATE.md)
- **Roadmap** — [`docs/roadmap-discussion-2026-04-30.md`](./docs/roadmap-discussion-2026-04-30.md)

## Status

Phase 19 (hardening + CI/CD + detection-as-code) ✅ shipped 2026-05-02 — tag `v0.9`. The CI badge tracks every push; the Smoke badge tracks the docker-compose chain run on `main` and nightly. Phase 19.5 (chaos testing) is next per the roadmap. See `PROJECT_STATE.md` for current phase status and the full verification scorecard.

## License

MIT
