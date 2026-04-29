# ADR-0011 — Custom Telemetry Agent (Direct Ingest, Replacing Wazuh as Default)

**Date:** 2026-04-28
**Status:** Accepted
**Deciders:** Phase 16 planning session
**Supersedes (in part):** ADR-0004 — only the *default* telemetry source. Wazuh bridge code, schema, tests, and the bridge ADR remain in force; Wazuh is now an opt-in alternative behind `--profile wazuh`.

> Note on numbering: the original Phase 16 plan referenced this ADR as `ADR-0004-direct-agent-telemetry.md`. That number was already taken by the Wazuh bridge ADR. ADR-0011 is used instead — it is the next available slot.

---

## Context

CyberCat shipped Phases 1–15 with Wazuh as the only working telemetry source. The Wazuh stack (manager + indexer + the lab-debian agent) consumes ≈ 1.8 GB of resident memory at idle. On the operator's 16 GB Windows laptop running WSL2 Docker, that pushes total system memory utilisation to ~80 % during dev sessions — comfortably below the WSL2 cap (`~/.wslconfig` is set to 6 GB), but tight enough that adding a browser, IDE, and the rest of the development environment leaves no headroom.

Two architectural commitments make a direct agent the right move now:

1. **CLAUDE.md §6** already declares telemetry pluggable: *"Telemetry intake (Wazuh + any direct agents/feeds)"* and *"the custom application layer is the star, Wazuh is upstream telemetry, not the product."* The codebase enforces this — `EventSource.direct` is a first-class enum member, `RawEventIn.source` accepts `"direct"`, and `POST /v1/events/raw` already validates and ingests events that arrive without going through any Wazuh decoder. The labs simulator (`labs/simulator/client.py`) has been exercising this path since Phase 6.
2. **No backend code changes are required to add a second telemetry source.** Every component downstream of `/v1/events/raw` — normalizer, entity extractor, detection rules, correlator, response policy, UI — already keys on the canonical normalized event shape. Whether an event arrived via the Wazuh poller or a direct POST is an `EventSource` enum value and nothing else.

The opportunity: build a small Python agent that POSTs canonical events directly to `/v1/events/raw`, make it the default telemetry source, and demote the Wazuh stack to an opt-in profile. The full identity-compromise scenario continues to detect and correlate identically — same rules, same correlator, same incidents, same UI — but the events arrive from a ~30 MB sidecar instead of a ~1.8 GB Wazuh tower.

---

## Decision

Add a Python 3.12 agent (`cct-agent`) packaged as a standalone container that:

1. **Tails** `/var/log/auth.log` inside the lab-debian container via a shared Docker volume mounted read-only.
2. **Parses** sshd log lines for v1's four event kinds: `auth.failed`, `auth.succeeded`, `session.started`, `session.ended`.
3. **Builds** canonical normalized events using shapes derived from `labs/simulator/event_templates.py`, with `source="direct"` (not `"seeder"`).
4. **POSTs** each event to `${CCT_API_URL}/v1/events/raw` with a `Bearer` token (analyst role; provisioned by `start.sh` on first run via `python -m app.cli issue-token`).
5. **Persists** a durable byte-offset checkpoint at `/var/lib/cct-agent/checkpoint.json` so restarts resume cleanly.

Make the agent the default telemetry source. The Wazuh stack (manager, indexer, lab-debian-with-agent) becomes opt-in behind `--profile wazuh`. Wazuh **code** (poller, decoder, AR dispatcher, status endpoint, Sigma pack mapping, Wazuh tests) stays in place and continues to compile, type-check, and pass tests; it just doesn't have any containers to talk to in the default configuration. `WAZUH_BRIDGE_ENABLED` defaults to `false`.

This is a **runtime replacement**, not a code deletion. Reversibility is non-negotiable: a single `--profile wazuh` flag brings the Wazuh stack back, the bridge re-enables, and Phase 8's existing 27-check smoke test still passes against it.

---

## Rationale

### Why now (not "delete Wazuh entirely" later)

Wazuh has carried the project from Phase 8 to Phase 15 — eight phases of detection, correlation, AR dispatch, multi-operator auth, and recommended-action work all built on top of real Wazuh-sourced events. The integration is real, working, and tested. Demos like the Phase 11 AR dispatch (Wazuh-managed `iptables -I INPUT DROP` and PID-validated `kill -9`) cannot be replicated by a direct agent without re-implementing meaningful chunks of Wazuh's manager-side machinery.

The right move is **multi-source telemetry**, not Wazuh removal. The default mode (laptop dev, demo recording, smoke tests, CI) should be cheap and self-contained. The opt-in mode (Wazuh demo, integration validation, AR dispatch story) should still work end-to-end on the same code path. ADR-0004 records *how* Wazuh is bridged; this ADR records *that the bridge is now optional*.

### Why Python 3.12 for the agent

| Criterion | Python 3.12 | Go | Rust |
|---|---|---|---|
| Reuse `labs/simulator/event_templates.py` event builders verbatim | Yes — identical dict shape | Re-implement | Re-implement |
| Reuse the `httpx.AsyncClient` pattern from `labs/simulator/client.py` | Yes | New HTTP layer | New HTTP layer |
| Stack consistency with backend (Python everywhere) | Yes | Adds a second runtime | Adds a second runtime |
| Memory footprint at idle | ~30–50 MB | ~5–10 MB | ~3–5 MB |
| Time to first working build | Days | 1–2 weeks | 2–3 weeks |
| Type checking / pydantic validation parity with backend | Native | Re-implement schemas | Re-implement schemas |

The 30 MB delta against Go/Rust is dwarfed by the ~1.8 GB Wazuh saving and is negligible against the 6 GB WSL2 cap. The "ship in days" criterion wins decisively. A Go rewrite is recorded as Phase 17 (optional) for the case where the agent ever becomes the bottleneck — at idle on a single auth.log tail, it never will.

### Why the agent is telemetry-only (no response channel)

This decision is deliberate and consequential. The agent is a one-way pipe: log file → backend. It has no mechanism to receive commands from the backend and execute them on the host. Concretely, this means:

- **Real OS-level Active Response stays Wazuh-only.** `quarantine_host_lab` → real `iptables -I INPUT DROP` and `kill_process_lab` → real PID-validated `kill -9` (Phase 11) require a Wazuh manager + agent to dispatch through. With the agent profile alone, those handlers run their DB-state branch (mark the lab asset, write the audit log, fire the SSE notification, update the UI) but do not touch the lab box's OS.
- **The action handlers gracefully degrade** based on `WAZUH_AR_ENABLED` and Wazuh manager reachability, both checked at execute time. They never error when Wazuh is absent — they simply do less in the real world. This is why the analyst workflow remains complete in agent-only mode: the platform sees, decides, records, and shows everything; only the final "and physically enforce on the host" step is skipped.
- **Two operational modes emerge from this asymmetry**, not from explicit configuration:
  - **Observe-and-record** (`./start.sh`): full platform behavior, DB-side response only.
  - **Observe-record-and-enforce** (`./start.sh --profile wazuh` + `WAZUH_AR_ENABLED=true`): adds real OS-level enforcement.
  Both are picked at *startup*, not per-incident. The runbook documents this distinction at length.
- **Why not build a response channel into the agent?** It's a meaningfully larger feature than Phase 16 — needs a command receiver, an action runner, a security model for "backend tells agent to run X on the host," authentication of inbound commands, audit invariants for who-did-what. Out of v1 scope. If we ever build it, it's a new ADR.

This asymmetry is **also why the Wazuh integration stays in the codebase indefinitely**: it provides a capability the agent doesn't have. The choice is not "agent OR Wazuh"; it's "agent for ingest by default, Wazuh available for real enforcement when needed."

### Why a separate container (not in-process with the backend)

- **Boundary clarity.** The agent is a telemetry source, not part of the product. Putting it in the backend process would conflate the two and violate the conceptual separation in CLAUDE.md §2.
- **Independent restart.** If the agent crashes, the backend keeps serving. If the backend restarts, the agent reconnects with retry/backoff. Coupling lifecycles loses both.
- **Match the lab-debian → Wazuh-manager pattern.** The Wazuh stack runs each component (manager, indexer, agent on lab-debian) in its own container. Mirroring that with `cct-agent` keeps the deployment shape uniform.
- **Read-only volume mount.** The agent gets `/var/log/auth.log` from lab-debian via a shared named volume mounted read-only on the agent side. Lab-debian writes the log; the agent reads it. Filesystem access is the boundary, not network — no inbound port on the agent, no outbound rsyslog from lab-debian.

### Why v1 scope = sshd auth events only

The four sshd event kinds (`auth.failed` / `auth.succeeded` / `session.started` / `session.ended`) are **enough to drive the existing `auth_failed_burst` detector and the `identity_compromise` correlator end-to-end**. That is the single most important detection-to-incident-to-response chain in the product. If the agent ships with just those four, the entire identity-compromise demo runs on agent-sourced telemetry alone, with no Wazuh containers running.

Process events (`process.created`, `process.exited`) require auditd integration; network events (`network.connection`) require conntrack. Both are real work — multi-line audit log parsing, Linux-distro-specific quirks, separate container privileges. They land in Phase 16.9+ when v1 is stable. Shipping narrow first is more valuable than shipping wide-and-buggy.

### Why durable byte-offset checkpoint (not "start fresh on each restart")

A telemetry agent that loses position on restart silently drops events for the duration of the outage. That breaks two product invariants:

1. **Detection determinism.** `auth_failed_burst` requires four failed attempts in 60 s. Restarting mid-burst would re-emit some events (depending on timing) and drop others, skewing the burst count.
2. **Operator trust.** "Did the agent see that?" should never be a question with a probabilistic answer.

Byte-offset over `/var/log/auth.log` is the simplest correct primitive: file is append-only between rotations, offset advances monotonically within a generation, rotation triggers a checkpoint reset. The plan covers rotation (inode-change detection) and truncation (offset > size detection) explicitly.

### Why httpx async + bounded queue + no-retry on 4xx

- **httpx async** matches the simulator's pattern (`labs/simulator/client.py`) and the backend's HTTP idioms. No new HTTP library introduced.
- **Bounded queue (1000 events, drop-oldest with metric on overflow).** If the backend is down for an extended outage, an unbounded queue grows until the agent OOMs. Drop-oldest under pressure is the right behavior for a telemetry agent: the alternative is "agent crashes, loses everything, and the backend never gets the recent events anyway." A persistent disk-spool would be more robust but is overkill for v1 against a backend that is one container away.
- **Exponential backoff retry on 5xx and network errors.** Standard. The backend is occasionally slow during cold start (Alembic migrations, fixture load); retrying past the warm-up window is correct.
- **NEVER retry on 4xx.** A 4xx means our payload is malformed (`invalid_kind`, `normalized_shape_mismatch`). Retrying loops forever and emits the same garbage forever. Log the error, drop the event, advance the queue. This is also why the agent's event builders are derived from `labs/simulator/event_templates.py` — keeping the shapes locked to a known-good source minimizes 4xx risk.

### Why `start.sh` provisions the agent token automatically

Two failure modes if the operator has to bootstrap manually:

1. They forget, the agent fails to start with `401 Unauthorized` on first POST, and they have to dig through logs to figure out why.
2. They check a working token into git.

`start.sh` already runs after Alembic migrations. On first run, if `CCT_AGENT_TOKEN` is empty in `infra/compose/.env`, it execs `python -m app.cli issue-token --email cct-agent@local --name cct-agent` inside the running backend container and writes the resulting token into `.env`. The token is created with role `analyst` (required to call `POST /v1/events/raw`). A separate `cct-agent@local` user exists so the audit trail (`actor_user_id` on every ingest-side write) clearly attributes events to the agent rather than to a human or the legacy sentinel.

---

## Alternatives considered

### Filebeat → `/v1/events/raw` (Wazuh-less)
Run only Filebeat on lab-debian, ship raw lines to a new ingest endpoint. **Rejected:** would require a *new* parsing layer in the backend (today's `/v1/events/raw` consumes already-normalized events, and the Wazuh decoder is the only thing that turns raw alerts into normalized form). That's a backend code change — exactly what we are committing not to do.

### Promtail / Vector / OpenTelemetry collector
General-purpose log shippers. **Rejected:** all three are heavier than a 200-line Python agent (Vector binary alone is ~50 MB; OTel collector with the file receiver ~80 MB) and none of them produce CyberCat's canonical event shape natively. Adapting them would mean writing a transform stage anyway, against a more complex configuration surface.

### Run the agent in lab-debian (sidecar to sshd)
Avoids the shared-volume mount. **Rejected:** lab-debian is supposed to look like a "vulnerable Linux host." Running the telemetry agent inside it conflates the attacker target with the defensive collector — a real-world deployment would never do this. Separate container with read-only log mount preserves the mental model.

### In-backend log tail (no separate container)
Have the FastAPI process tail `/var/log/auth.log` directly. **Rejected:** crosses the architecture boundary (backend should not be reaching into telemetry-source filesystems), couples backend lifecycle to log-source lifecycle, and would block on file I/O inside the request loop unless wrapped in a thread pool or async file lib.

### Delete the Wazuh code path
Tempting given the "go fast" framing. **Rejected:** Wazuh is the source of truth for the AR dispatch story (Phase 11), the live rule-engine demo (Phase 8), and the integration story for any future reviewer who asks "but does this work with a real SIEM?" Deleting the code shrinks the repo by ~1k lines and saves nothing operationally — the code is dormant when the containers aren't running. Reversibility is more valuable than tidiness.

---

## Consequences

**Positive:**
- Default `./start.sh` boots a 6-container, ~900 MB stack instead of an 8–9-container, ~3 GB stack. Full identity-compromise scenario still detects and correlates end-to-end. **Measured 2026-04-28** (post-shipping): container resident memory totals **902 MB** (frontend 622, backend 142, postgres 59, lab-debian 47, cct-agent 25, redis 8). vmmemWSL on the host dropped from ~4 GB to **2.8 GB** — a ~1.2 GB / ~30% reduction, freeing system memory utilization from ~80% to **73.6%** on the 16 GB Lenovo Legion. The cct-agent itself uses ~25 MB at idle versus the ~1.8 GB Wazuh stack it replaces.
- Demonstrates pluggable-telemetry concretely. The platform can show two telemetry sources running the same detection chain — strong portfolio story.
- Backend test suite remains unchanged (target: 173/173 passing). Wazuh integration tests still pass against the dormant code path.
- New `agent/` tree is testable in isolation (`cd agent && pytest`) without bringing up any compose stack.

**Negative / accepted trade-offs:**
- Lab-debian's installed Wazuh agent (from the existing image) becomes orphaned when running with `--profile agent`. It just runs, fails to register with a non-existent manager, and emits nothing. Acceptable in v1 — recorded as Phase 16.9 cleanup ("either remove from image or repurpose").
- Operator must remember `--profile wazuh` to bring the Wazuh stack back. Mitigated by `start.sh` startup banner ("Wazuh disabled by default. Run with --profile wazuh to enable.") and by the runbook documenting both modes.
- The agent and the Wazuh decoder both produce events with the same `kind` values. Cross-source dedup is *not* implemented in v1 — running both profiles simultaneously would cause double-ingestion. Documented; deferred to Phase 18 along with token rotation.
- Bounded in-memory queue means the agent will drop events under sustained backend outage. Acceptable for a lab tool; documented in the runbook as a known limit.

**Future revisits:**
- Phase 16.9 — process events via auditd (`process.created`, `process.exited`).
- Phase 16.10 — network events via conntrack (`network.connection`).
- Phase 17 (optional) — Go rewrite of the hot path.
- Phase 18 (optional) — token rotation + multi-source dedup.

---

## Files affected

**New:**
- `docs/decisions/ADR-0011-direct-agent-telemetry.md` (this file)
- `agent/` (new top-level tree — see `docs/phase-16-plan.md` for the full file list)
- `labs/smoke_test_agent.sh`

**Modified:**
- `infra/compose/docker-compose.yml` — adds `cct-agent` service; lab-debian extended into the `agent` profile so it comes up under both `--profile agent` and `--profile wazuh`.
- `infra/compose/.env.example` — adds `CCT_AGENT_TOKEN=`; sets `WAZUH_BRIDGE_ENABLED=false` as the default.
- `start.sh` — default profile becomes `core agent`; first-run token bootstrap; Wazuh-disabled banner.
- `docs/architecture.md`, `docs/runbook.md`, `Project Brief.md`, `PROJECT_STATE.md` — updated with the new default mode and the agent operations section.

**Explicitly NOT touched:** see `docs/phase-16-plan.md` "Files explicitly NOT touched" — backend ingest, schemas, enums, normalizer, Wazuh poller/decoder, AR dispatcher, detection rules, Sigma pack, frontend, and existing tests all stay exactly as they are.
