# CyberCat — Strategic Roadmap Discussion (2026-04-30)

A structured capture of the strategic conversation around what CyberCat does today, what it's actually defending, what real-world testing looks like, and what the next three phases should be. Written so any future Claude session can pick up the thread without re-asking.

---

## 1. What CyberCat Currently Does (Feature Inventory)

### Telemetry intake (real-time)

The custom Python agent (`cct-agent`) tails three log streams in parallel and ships canonical events to the backend within seconds:

- **SSH / login activity** — `/var/log/auth.log` (sshd): `auth.failed`, `auth.succeeded`, `session.opened`, `session.closed`
- **Process execution** — `/var/log/audit/audit.log` (auditd EXECVE + exit_group): `process.created`, `process.exited`
- **Outbound network connections** — `/var/log/conntrack.log` (netfilter NEW): `network.connection`

Wazuh remains a fully-supported alternative source (`--profile wazuh`) and the only path for real OS-level Active Response. Both flow through the same normalizer.

### Detection layer

Four hand-written Python detectors run on every event:

1. **`py.auth.failed_burst`** — Brute force / spray ("5+ failed for same user in 10 min")
2. **`py.auth.anomalous_source_success`** — Successful login from new IP after recent failures
3. **`py.process.suspicious_child`** — Suspicious parent-child chains (sshd→bash→curl|sh, encoded PowerShell, base64-piped shell)
4. **`py.blocked_observable_match`** — Any event involving an IP/hash in the blocklist auto-fires (closes the feedback loop)

A real Sigma rule engine runs side-by-side, parsing real Sigma YAML files. Every detection is tagged with MITRE ATT&CK technique IDs (37-entry curated catalog, v14.1).

### Correlation layer (the real differentiator)

Four correlator rules turn related detections into one investigable story:

1. `identity_compromise` — Brute-force burst + successful login on same user
2. `endpoint_compromise_standalone` — Suspicious process behavior alone
3. `endpoint_compromise_join` — Multiple endpoint signals on same host
4. `identity_endpoint_chain` — Successful suspicious login + suspicious process activity on same host within minutes → one **critical** chained incident (the flagship)

Every incident gets severity (critical/high/medium/low/info), confidence (0.00–1.00), status lifecycle (new → triaged → investigating → contained → resolved → closed), plain-language summary + technical rationale, kill-chain mapping, linked entities, source events + detections.

### Response actions (8 wired end-to-end)

| Action | Class | What it does |
|---|---|---|
| `tag_incident` | auto-safe | Adds tag/note |
| `elevate_severity` | auto-safe | Bumps severity with audit reason |
| `flag_host_in_lab` | reversible | Marks host "needs review" |
| `quarantine_host_lab` | disruptive | With `WAZUH_AR_ENABLED=true`: real `iptables -I INPUT DROP` on lab container |
| `kill_process_lab` | disruptive | With AR: real `kill -9` on target PID, with `/proc/<pid>/cmdline` validation |
| `invalidate_lab_session` | reversible | Marks session invalid in lab session store |
| `block_observable` | reversible | Adds IP/hash to blocklist; detection engine reads on every event |
| `request_evidence` | suggest-only | Opens evidence-collection ticket |

Every run logged in `action_logs` with timestamp, actor, result (`ok`/`failed`/`partial`), and classification reason. AR is flag-gated and lab-container-scoped — the host OS is never touched.

### Frontend (Phase 17 + 18)

- `/` — Welcome landing page (operator handle, open-case count, hero stats, ticker, active cases, tour CTA)
- `/incidents` — Filterable list, polled in background
- `/incidents/[id]` — Investigation view with kill chain "Route" panel (animated path with pulsing "HERE" marker), timeline "Reel" (multi-lane with playhead sweep + red-string entity threads), detections, entity graph, recommendations, actions, evidence, transitions, notes
- `/entities/[id]`, `/detections`, `/actions`, `/lab`, `/help`

Detective/case-file aesthetic (warm-paper dossier tokens, typewriter case headers, stamp accents). Site-wide plain-language layer (`labels.ts` + `<PlainTerm>`).

### Auth and operator model

- Three roles: `admin` / `analyst` / `read_only`
- Email+password (bcrypt) OR API token (Bearer)
- OIDC SSO with any standard provider (4 env vars)
- Every mutation endpoint role-gated; read_only sees disabled buttons
- Every audit row carries `actor_user_id`
- 20-test parameterized inventory asserts 401/403 on every gated route
- Bootstrap CLI: `seed-admin`, `create-user`, `issue-token`, `revoke-token`

### Real-time streaming (Phase 13)

Server-Sent Events at `GET /v1/stream`. Redis pub/sub fans out. Frontend `useStream` hook with topic filters, auto-reconnect, 60s polling fallback. New incidents appear in UI within 1–2 seconds.

### Attack simulator

`labs/simulator/` ships `credential_theft_chain` — 5-stage scenario (brute force → anomalous success → session → encoded PowerShell → C2 beacon). `--speed 0.1` for ~30s compressed demo, `--verify` asserts expected incidents created. Idempotent.

---

## 2. Real-time or Demo? — The Honest Answer

**Both, by design.** The pipeline is genuinely real-time on the technical side (SSE push, sub-second event latency end-to-end). The scope is laptop-sized: built to defend systems you own — your own Linux box, a lab VM, a homelab — not an enterprise fleet. If pointed at a real Linux machine you control, it will detect real attacks in real time and take real defensive actions on it. The "demo" part is the auto-seeded sample incident on first boot to make it look populated; one-click wipe and you can run it for real.

---

## 3. What CyberCat Watches vs Doesn't (Scope Clarification)

CyberCat does NOT defend the Windows laptop itself. It defends whatever Linux machine the agent is pointed at. By default that's a Docker container running on the laptop — not the laptop OS.

This is intentional and codified in `CLAUDE.md` §8 "Host Safety, non-negotiable." The whole stack is sandboxed inside Docker so it cannot touch the Windows OS, host network, host firewall, or any file outside the project folder.

| Layer | Monitored | Where it lives |
|---|---|---|
| `lab-debian` container / `cct-agent` sidecar | sshd logins, processes, network | Docker container with own namespaces |
| Windows 11 laptop host | **Nothing** | Untouched by project rule |
| Home WiFi / router | **Nothing** | Untouched |
| Browser, Steam, Discord, OneDrive | **Nothing** | Untouched |

When the simulator fires "5 failed SSH logins for alice on lab-debian," those happen *inside the container*. Like a security camera in a dollhouse on the desk — real camera, real events, but the dollhouse isn't the house.

### What it would/wouldn't catch

**Would catch (where pointed):** SSH brute-force, malicious process spawning, outbound to known-bad IPs — on Linux servers/VMs the agent is installed on, or on the bundled lab container.

**Wouldn't catch:** RDP attempts on the laptop, .exe malware on Windows, phishing/Office macros, browser exploits, USB malware, suspicious PowerShell on the host, phone/router activity, WiFi/ARP attacks, anything network-level outside the lab.

---

## 4. Extending to Windows Host Defense — Feasibility (Decided Against)

This was discussed and **declined** because of Windows-security/false-positive risk. Captured here for the record.

### Tiers if this were pursued

**Tier 1 (1–2 weeks):**
- RDP brute force (Win Event 4625/4624)
- Suspicious PowerShell (Sysmon EID 1)
- Process creation / parent-child chains
- Local logons

**Tier 2 (3–6 weeks):**
- File writes (Sysmon EID 11)
- Outbound network connections from Windows processes (Sysmon EID 3)
- USB device insertion
- Registry persistence (Sysmon EID 12–14)
- Office macro abuse

**Tier 3 (out of scope, different products):**
- Browser exploit detection (needs EDR-grade hooks)
- Phone monitoring (different OS, MDM territory)
- Router monitoring (SNMP/NetFlow)
- WiFi/ARP attacks (needs network sensor)
- Phishing email scanning (email security category)

### Why declined

- Detection on host is low-risk (~1–3% CPU, 50–150 MB RAM, mature Wazuh agent).
- **Response on host is the dangerous part.** False-positive `Stop-Process` could kill Discord/Steam/Chrome/IDE; bad `netsh advfirewall` could lock the laptop out of services; potential conflict with Windows Defender; recovery requires manual intervention.
- Privacy concern: every personal app process logged.
- Changes the project identity (would require rewriting `CLAUDE.md` §8 with an ADR).

**Decision: not pursuing. Lab-safe defensive identity is more valuable than added coverage.**

---

## 5. Linux vs Windows Targeting — The Reframe

Concern raised: "Nobody gets hacked on Linux, right?" — actually wrong, in a way that matters for how the project reads.

### Where the actual hacking happens

- **~96% of top million web servers run Linux.** Every site, API, cloud service.
- **AWS/Azure/GCP workloads are overwhelmingly Linux.** Cloud breaches almost always hit Linux instances.
- **SSH brute-force is constant on the internet.** Stand up a Linux VPS, expose port 22, get hit within minutes by botnets.
- **Modern ransomware crews specifically build Linux variants** to hit ESXi (ALPHV, LockBit, Royal).
- **Kubernetes / container attacks are Linux attacks.** Cryptojacking, supply-chain compromise, AWS-key leaks.
- **Big recent breaches** — SolarWinds, Log4Shell, MOVEit, XZ backdoor — primarily Linux infrastructure.

### What the project actually demonstrates (right frame)

Not "protect grandma's laptop" (solved space, dominated by Defender + commercial EDR). CyberCat is a **SOC / cloud incident response platform** — SSH brute-force, suspicious process trees, outbound C2 detection, ATT&CK mapping, identity↔endpoint correlation, classified response. Exactly the work detection engineers, SOC analysts, and cloud security engineers do every day. Higher-paid, more technical domain than consumer endpoint.

A hiring manager looking at this should see: "this person can build the kind of platform my SOC team uses."

---

## 6. Real-World Testing Options

### Option A — Internet VPS honeypot

The most authentic but the one with the most fear factor.

**Setup:** $4–6/month VPS (DigitalOcean, Hetzner, Vultr), bare Ubuntu, install `cct-agent`, expose SSH on 22 with deliberately weak trap users on restricted shells. Wait — within hours real botnets brute-force you.

**Hardening checklist (mandatory):**
1. New email account for VPS provider
2. New SSH keypair specific to this VPS — never reuse laptop keys
3. Unique strong password + 2FA on provider account
4. **No credential, token, API key, or file from your real life ever touches this box**
5. Different randomly-generated password for every account on the box
6. Fresh Ubuntu/Debian, fully updated, `unattended-upgrades`
7. Trap users with `/usr/sbin/nologin` or `rbash`, no sudo, locked from system paths
8. `PermitRootLogin no` in sshd_config
9. `ufw`: deny all inbound except port 22
10. `fail2ban` as backup blocker
11. iptables blocking outbound for trap user UID
12. Nothing else running (no web server, no DB)
13. Backend runs on laptop (or co-located on VPS), connected via WireGuard/Tailscale (never over public internet) if separated
14. Provider billing alerts at $10/$20/$50
15. Web-console destroy-and-rebuild ready

**Blast radius if compromised (with separation):** "I deleted a $5 droplet."

**Risks:**
- Provider abuse-policy if attacker pivots out (mitigated by no outbound from trap users)
- Bandwidth (manageable, brute-force is loud but not heavy)
- Recurring cost ($5/mo, can stop anytime)

**Legal:** completely fine — own the VPS, observing attacks against own machine, defensive only. No strike-back, no scanning.

### Option B — MITRE Caldera (recommended path)

Open-source autonomous adversary emulation framework, built by MITRE. The closest you get to "unknown attacker" without internet exposure.

- Caldera installed on laptop, registers `lab-debian` as target
- Tell it "run an operation" — it autonomously picks ATT&CK techniques and chains them itself
- You don't know what it'll do, in what order, when
- Each technique mapped to ATT&CK — direct comparison "Caldera attempted T1059.004, did our detectors fire?"
- Stays in local Docker network. Zero internet exposure.

**Resource cost:**
- Idle: ~200–400 MB RAM
- Mid-operation: ~500–800 MB RAM
- Sandcat agent on target: ~20–50 MB
- Total stack with Caldera: ~1.3–1.5 GB idle, ~2–3 GB peak under operations
- Well under WSL2 6 GB cap

### Option C — Atomic Red Team (Red Canary)

1,000+ real attack techniques, each mapped to ATT&CK, each runnable as one-line scripts. Less autonomous than Caldera (a library, not a brain), but technique coverage is enormous. Often used *with* Caldera (Caldera as brain, Atomic as arsenal). Essentially free at rest — only YAML files on disk.

### Option D — Purple teaming with a trusted friend

The actual gold standard. Friend gets SSH access to the lab container (not the laptop), "have at it for an hour, don't tell me what you're doing." 100% authentic, zero scripting, zero internet exposure. This is what big-company red teams do internally every quarter.

### Why adversary emulation is "real testing"

It isn't a consolation prize for internet honeypots. It's how mature security organizations validate their SOCs every week. Banks, government agencies, tech companies don't expose internet honeypots to test internal tooling — they hire (or build) red teams that emulate adversaries against lab environments. That's literally what Caldera is for. Test credibility comes from realism of technique, not anonymity of attacker.

---

## 7. Proposed Roadmap (User's Plan)

### Phase 19 — Loose ends, hardening, error-proofing

Tie up any remaining issues, ensure the system is rock-solid against complex attacks, no errors, fully functional. Get the platform in a state where you'd trust it under pressure.

### Phase 20 — Choreographed heavy-hitter testing + operator training

More aggressive synthetic scenarios beyond `credential_theft_chain` (e.g., `supply_chain_tool_abuse`, `cloud_token_theft`, `ransomware_staging`). Goal: confirm the system handles complex chains AND that the operator can read the dashboard fluently. Operator training is the underrated half here — knowing how to interpret the kill chain, the timeline, the entity graph, the action recommendations under pressure.

### Phase 21 — Real adversary emulation

Caldera as the headline tool, possibly with Atomic Red Team as an arsenal. Run autonomous unknown-sequence attacks, build a coverage scorecard ("Caldera tried these N techniques across M tactics; CyberCat detected X, missed Y"). Real test of what the platform claims it can do.

### After 21 — Add detectors based on what real attackers actually did

Use the coverage gaps from Phase 21 to drive the next round of detection engineering, not abstract guessing.

---

## 8. Honest Evaluation of the Plan

The plan is **good**. The instinct ("get the foundation rock-solid before pointing real attack tooling at it") is the right engineering instinct, and the order is correct: harden → choreographed stress → real adversary emulation → targeted detection growth. Most solo projects skip straight from "first version works" to "ship it" and never do the hardening pass; doing it deliberately is the difference between an 8/10 portfolio piece and a 9/10.

A few things to add or sharpen:

### What Phase 19 should specifically include (concrete punch list)

**Resilience and error paths:**

| Failure mode | Expected behavior | Files likely touched | New test |
|---|---|---|---|
| Wazuh poller raises mid-batch | Outer try/except catches, log + continue, cursor not advanced | `backend/app/ingest/wazuh_poller.py` | `test_wazuh_poller_resilience.py` (new) |
| Redis unreachable mid-correlation | Correlator falls back to no-windowing path, logs warning, no event drop | `backend/app/correlate/*` | `test_correlate_redis_down.py` (new) |
| Postgres connection drops mid-write | Transaction rolls back, retry on next event, no half-written incident | `backend/app/db/session.py`, ingestion path | `test_postgres_disconnect.py` (new) |
| Malformed event from agent (missing required field, bad timestamp, oversize blob) | Pydantic rejects with 422 + structured error log; nothing reaches the DB | `backend/app/api/events.py`, `backend/app/schemas/event.py` | `test_event_validation_negative.py` (new) |
| SSE consumer disconnects mid-push | Per-connection queue drained + closed, no zombie tasks, no Redis subscriber leak | `backend/app/api/stream.py`, `backend/app/stream/*` | `test_sse_disconnect.py` (new) |
| Backpressure at 1k events/sec | p95 detection latency stays under 500 ms, no event loss, no OOM | ingestion pipeline | `labs/perf/` load harness (new) |

**Acceptance criteria for resilience pass:**
- Every failure mode in the table above has at least one targeted test that asserts the expected behavior.
- A `labs/perf/load_harness.py` script can fire 1k events/sec for 60 seconds against the dev stack without dropped events or stuck queues.
- All existing 174/174 backend tests still pass.
- All 8 smoke scripts still pass.

**Quality bar punch list:**

- `grep -rn "TODO\|FIXME\|XXX\|HACK" backend/ frontend/app/ agent/` — every hit either gets resolved or converted to a tracked ticket with a real "remove once X" condition. Stale comments get deleted.
- `grep -rn ": any" frontend/app/` — every `any` in product code gets a real type or a justification comment.
- Run `pytest backend/tests/ -p no:randomly` 5 times consecutively, then with `-p randomly` 5 times. Any test that's non-deterministic is fixed (usually a missing `freezegun` or unseeded `random`).
- `EXPLAIN ANALYZE` the four hottest API queries: `GET /v1/incidents` (with severity + status filters), `GET /v1/incidents/{id}` (joined load), `GET /v1/entities/{id}/incidents`, `GET /v1/detections` (with rule + time filters). Any that aren't using indexes get an Alembic migration adding the right index.
- All FastAPI route signatures explicitly type the response model. Audit `backend/app/api/` for any handler returning bare `dict` or untyped `Response`.

**CI/CD setup (concrete deliverables):**

`.github/workflows/ci.yml` — runs on every push and PR:
- Backend: `pytest backend/tests/`, `mypy backend/app/`, `ruff check backend/`
- Frontend: `tsc --noEmit`, `eslint .`, `next build`
- Agent: `pytest agent/tests/`
- Caches `pip` and `node_modules` keyed on lockfile hashes

`.github/workflows/smoke.yml` — runs on push to main + nightly schedule:
- Brings up the docker-compose stack
- Runs all `labs/smoke_test_phase*.sh` scripts in sequence
- Posts a summary to the run page (pass/fail per script)

`.github/workflows/release.yml` — runs on tag push:
- Builds + pushes backend, frontend, and agent images to GHCR
- Generates a release artifact bundle (compose file + `.env.example` + runbook excerpt)

**Acceptance criteria for CI pass:**
- All three workflow files exist and pass on a clean push.
- The README has CI status badges.
- A deliberately broken commit fails CI cleanly within 5 minutes.

**Detection-as-code pipeline (concrete shape):**

Directory layout:
```
labs/fixtures/
  ├── README.md
  ├── auth/
  │   ├── ssh_brute_force_burst.jsonl       # 5x auth.failed in 90s
  │   ├── successful_login_clean.jsonl      # one auth.succeeded, known-IP
  │   └── successful_login_anomalous.jsonl  # auth.succeeded after failures from new IP
  ├── process/
  │   ├── benign_apt_update.jsonl
  │   ├── encoded_powershell.jsonl
  │   └── curl_pipe_sh.jsonl
  └── network/
      ├── benign_outbound.jsonl
      └── known_bad_ip_beacon.jsonl
```

Each fixture is line-delimited JSON of canonical events with relative timestamps, replayable into the backend at any speed.

A new `backend/tests/test_detection_fixtures.py` parameterizes over a manifest:
```yaml
- fixture: auth/ssh_brute_force_burst.jsonl
  must_fire: [py.auth.failed_burst]
  must_not_fire: [py.auth.anomalous_source_success, py.process.suspicious_child]
- fixture: process/benign_apt_update.jsonl
  must_fire: []
  must_not_fire: [py.process.suspicious_child]
```

CI runs this manifest on every PR. Adding a new rule means adding fixtures that prove it fires correctly AND doesn't false-positive on a benign baseline. Compounding payoff: every fixture added in Phase 20 / 21 becomes a permanent regression test.

**Phase 19 done-criteria (single sentence):** Every resilience scenario, quality-bar item, CI workflow, and the detection-as-code pipeline above is complete, with all existing tests still green and the new test count visible in the README.

### What Phase 20 should specifically include

**New simulator scenarios** (each lives at `labs/simulator/scenarios/<name>.py`, registered in the scenario registry, with `--verify` assertions):

| Scenario | ATT&CK coverage | Length | Verification |
|---|---|---|---|
| `lateral_movement_chain` | T1078, T1021.004 (SSH), T1059.004, T1083 | ~9 stages | One `identity_endpoint_chain` incident severity=critical with hosts A and B linked via shared user |
| `crypto_mining_payload` | T1059, T1496, T1071.001 | ~6 stages | One `endpoint_compromise_standalone` + outbound to known mining pool IP triggering `py.blocked_observable_match` |
| `webshell_drop` | T1190, T1505.003, T1059.004 | ~7 stages | One `endpoint_compromise_join` correlating file write + suspicious child + outbound C2 |
| `ransomware_staging` | T1486 (precursors only — no actual encryption), T1490 | ~8 stages | One critical chained incident; staging-only, no real file destruction |
| `cloud_token_theft_lite` | T1552.001, T1078.004 | ~5 stages | Identity-only chain demonstrating credential leak → reuse pattern |

Each scenario:
- Is idempotent (dedup keys prevent duplicate firings within an hour)
- Supports `--speed 0.1` for ~30s compressed runs
- Ships with `--verify` assertions enumerating expected incidents and expected ATT&CK techniques touched
- Adds a corresponding fixture under `labs/fixtures/scenarios/<name>/` for the detection-as-code pipeline

**Demo runbook** (`docs/demo-runbook.md`, new):

For each scenario, document:
- Plain-language summary ("an attacker stole alice's password from a leaked secret store and tried to pivot to a second host")
- Exact CLI to fire it (`python -m labs.simulator.run lateral_movement_chain --speed 0.1 --verify`)
- What the dashboard should show, panel by panel:
  - Which incident appears, with what severity
  - Which ATT&CK tactics light up on the kill chain panel
  - Which entities should be linked in the entity graph
  - Which events should appear on the timeline reel and how the red-string threads should connect them
  - Which actions are recommended
- Common misreadings to avoid
- "Time to triage" target (see operator drill below)

**Operator drill protocol:**

Run a stopwatch test for each scenario:
- Start: scenario fires, first incident appears in `/incidents`
- End: incident transitioned to `contained` with at least one response action executed
- Pass: under 2 minutes for any scenario
- If any scenario takes > 2 minutes, the UX has a real gap — file it as a Phase 20 sub-issue and fix before phase exit

**Incident merging / splitting (UI + API):**

- New endpoint `POST /v1/incidents/{id}/merge` (target: `incident_id`) — moves all junction rows from source to target, archives source, writes a transition row on both
- New endpoint `POST /v1/incidents/{id}/split` (body: `event_ids: [...]`) — creates a new incident, moves the listed event/detection junction rows over, recomputes severity/confidence on both
- Frontend: dropdown on the detail page header — "Merge into…" (autocomplete by recent incidents) and "Split selected events out…" (multi-select on the timeline)
- Both gated by `require_analyst`
- Both write an `incident_transitions` audit row with the actor and reason

**Phase 20 done-criteria:** Five new scenarios registered and passing `--verify`, demo runbook published, every scenario triages in under 2 minutes, merge/split endpoints + UI shipped and gated, fixtures added under `labs/fixtures/scenarios/` so all five scenarios are CI-replayable.

### What Phase 21 should specifically include

**Caldera integration as a docker-compose service** (behind `--profile redteam`, off by default):

- New service `caldera` in `docker-compose.yml`:
  - Image: `mitre/caldera:latest` (pinned to a specific commit hash for reproducibility)
  - Exposes web UI on `localhost:8888` (analyst access only, never internet-routed)
  - Mounts `labs/redteam/caldera-config/` for adversary profiles + custom abilities
  - On the same internal Docker network as `lab-debian` (the target)
  - Healthcheck: HTTP 200 on `/api/v2/health`
- `lab-debian` gets the Sandcat agent baked into its image (or installed at container start via an entrypoint hook), beaconing back to `caldera:8888`. Only fires when `--profile redteam` is up.
- New env var `CCT_REDTEAM_ENABLED` controls whether the backend exposes the coverage-report endpoint (off by default).

**Coverage scorecard generator** (`backend/app/redteam/coverage.py`, new):

After a Caldera operation completes, this module:
1. Pulls the operation's executed-abilities log via Caldera's REST API (`GET /api/v2/operations/{op_id}`)
2. For each executed ability, extracts the ATT&CK technique ID
3. Queries CyberCat's database for detections + incidents in the operation's time window
4. Joins them into a scorecard:

```
Operation: ransom_emulation_2026-05-15
Started: 14:02:11 UTC  Ended: 14:09:47 UTC

Techniques attempted:  12
Techniques detected:    9    (75%)
Techniques missed:      3
Tactics covered:        5/14 (kill-chain footprint)

Detection latency p50:  3.2s
Detection latency p95:  11.4s

Incidents created:      4
  - 1x identity_endpoint_chain (critical)
  - 2x endpoint_compromise_join
  - 1x identity_compromise

Missed techniques:
  - T1003.001  (LSASS Memory)        — no detector
  - T1547.001  (Run Keys)            — no detector
  - T1041      (Exfil over C2)       — fired but not correlated

Detection-to-incident-creation lag:
  - p50: 1.8s
  - p95: 6.7s
```

5. Persists the scorecard as a markdown file in `docs/redteam-runs/YYYY-MM-DD-<op-name>.md`
6. New endpoint `GET /v1/redteam/coverage/{op_id}` returns the scorecard as JSON for the frontend
7. New `/redteam` page in the frontend renders the latest scorecard with hover detail per missed technique

**Adversary-emulation runbook** (`docs/redteam-runbook.md`, new):

- How to bring up the redteam profile: `./start.sh --profile redteam`
- How to access Caldera UI and load adversary profiles
- Pre-built adversary profiles to run first:
  - `recon-only` — discovery techniques only, sanity check the agent connection
  - `endpoint-burst` — process-execution heavy, stress-tests the suspicious_child detector
  - `identity-pivot` — auth + lateral movement, stress-tests the identity_endpoint_chain correlator
  - `full-kill-chain` — initial access through impact, the headline operation
- How to read the coverage scorecard
- How to feed missed-technique findings back into Phase-22+ detector planning
- How to safely tear down: `./start.sh --profile redteam down -v` cleans the operation log

**Atomic Red Team integration (optional companion):**

- `labs/redteam/atomic/` — clone of the Atomic Red Team repo (or git submodule)
- A small wrapper script `labs/redteam/atomic_runner.py` that:
  - Picks N random techniques from a configurable subset (e.g. only Linux techniques)
  - Executes each against `lab-debian` over SSH (using the existing lab credentials)
  - Logs which techniques fired, with timestamps
  - Feeds the same coverage scorecard generator
- Useful for bursty technique-coverage sweeps that complement Caldera's autonomous chain operations

**Pre-flight: performance baseline (run before any Caldera operation):**

`labs/perf/baseline.py` script captures, over a 60-second steady-state run:
- Events/sec sustained
- p50/p95/p99 detection latency (event-write to detection-fire)
- p50/p95/p99 incident-creation latency (first detection to incident-row)
- Backend RSS, Postgres connection count, Redis ops/sec
- Persisted to `docs/perf-baselines/YYYY-MM-DD.json`

After each Caldera operation, re-run the baseline and compare. If a Caldera operation pushes p95 detection latency over 2x the baseline, file it as a perf bug.

**Phase 21 done-criteria:** Caldera service shipped behind `--profile redteam`, Sandcat agent on `lab-debian` confirmed beaconing, four named adversary profiles (recon-only / endpoint-burst / identity-pivot / full-kill-chain) executable end-to-end, coverage scorecard generator producing the markdown + JSON outputs, `/redteam` frontend page rendering the latest scorecard, runbook published, performance baseline captured pre- and post-operation, at least one full-kill-chain operation completed with its scorecard committed to `docs/redteam-runs/`.

### Things to consider adding

**Phase 19.5 — Chaos test (half a phase, between 19 and 20):**

`labs/chaos/run_chaos.sh` orchestrates the following scenarios while the simulator is running `credential_theft_chain` in the background:

| Chaos action | How | Recovery target | Pass criteria |
|---|---|---|---|
| Kill Redis | `docker compose kill redis` for 30s, then `docker compose start redis` | Backend reconnects automatically, no event loss after restart | Backend logs show `redis reconnect ok`, all simulator events present in Postgres `events` table |
| Restart Postgres | `docker compose restart postgres` | Backend handles connection drop, retries cleanly, no half-written incidents | No orphan rows in `incident_events` without parent `incidents` row |
| Network-partition agent → backend | `iptables` rule on host (lab-only), block port 8000 from `cct-agent` for 60s | Agent buffers locally, replays after partition heals | All blocked-period events arrive after partition lift, in-order |
| SIGSTOP agent for 30s | `docker compose pause cct-agent`, then `unpause` | Agent resumes from last cursor, no log re-read or skip | `cursor_position` advances correctly after resume |
| OOM-kill backend mid-correlation | Force-kill backend container during a correlator window | On restart, in-flight correlator state is rebuilt from Postgres truth | No lost incidents, no duplicate incidents from the same window |
| Slow-disk simulation | Inject 200ms latency on Postgres volume via `tc` | Backpressure handled, no event loss, latency degraded but bounded | p99 detection latency stays under 5s |

Each scenario is a script under `labs/chaos/scenarios/` that prints PASS or FAIL with a structured reason.

**Phase 19.5 done-criteria:** All six chaos scenarios pass on a clean stack. Failures get filed as blockers and fixed before Phase 20 starts.

**Between Phase 20 and Phase 21 — performance baseline (already covered in Phase 21 pre-flight above):**
Captured by `labs/perf/baseline.py`. Persisted to `docs/perf-baselines/YYYY-MM-DD.json`. Re-run after each Caldera operation for delta tracking.

**After Phase 21 — Ship-story phase (concrete deliverables):**

| Artifact | Where it lives | Length / format |
|---|---|---|
| README rewrite | `README.md` | ~600–800 words. Hero diagram (the layered arch), one-paragraph positioning ("threat-informed IR platform for Linux servers and cloud workloads"), 3-bullet feature highlights, single-command quickstart, screenshots, CI badges, link to demo video. |
| Demo video | Linked from README, hosted on YouTube/asciinema | 5 min max. Narrated. Shows: clean boot → simulator runs `credential_theft_chain` → operator triages incident → fires `block_observable` → re-runs sim, second incident auto-blocks via feedback loop. |
| Caldera writeup | `docs/redteam-runs/2026-XX-XX-headline-operation.md` + a Medium/dev.to blog cross-post | The coverage scorecard from a real full-kill-chain operation, with prose explaining what was caught, what was missed, what the missed techniques teach about Phase 22. |
| Architecture deep-dive blog | `docs/writeups/architecture-2026.md` (with cross-post) | The "why these design choices" piece — Postgres-truth/Redis-ephemeral, classified actions, identity-endpoint chain correlator. ~1500 words. |
| Public-repo prep | LICENSE (already MIT), CONTRIBUTING.md (new), CODE_OF_CONDUCT.md (new), GitHub repo description + topics | Standard OSS hygiene. |
| One-page resume bullet | `docs/resume-bullet.md` | 4–6 lines. The exact sentence to drop on a resume — built around the Phase 21 coverage scorecard, not feature lists. |

**Ship-story can run in parallel** with Phase 19/20/21 work — README rewrites, demo recordings, and writeup drafts don't have to wait until the end. Recommended cadence: a draft of each artifact per phase, polished pass after Phase 21.

### What NOT to do in these three phases

- Don't add new detectors during Phase 19 hardening. The temptation will be strong; resist it. Every new detector added before Phase 21 is a guess; every detector added after Phase 21 is informed by data.
- Don't extend to Windows host defense (already declined).
- Don't add more telemetry sources (Phase 16/16.9/16.10 already covered the three major ones). Save sourcing breadth for after the platform is proven robust on the existing three.
- Don't introduce heavy infrastructure (Kafka, Temporal, Elastic) — CLAUDE.md §3 forbids this, and Phase 19/20/21 don't need it.

### Optional, in parallel with any of the three phases

**Ship-story drip:** README rewrite, demo GIF capture, public-repo prep (`LICENSE` already in place per `PROJECT_STATE.md`). Doesn't have to be a phase — can happen in pull requests alongside the work.

---

## 9. Verdict

The three-phase plan is good. With the additions above (CI/CD + detection-as-code pipeline in Phase 19, chaos testing as a half-phase between 19 and 20, performance baselines before Phase 21, ship-story drip in parallel), it becomes the project's "1.0 release" arc.

After Phase 21 completes successfully, the project moves from "8/10 portfolio piece" to "9/10 — here's a SOC platform I built, tested against autonomous adversary emulation, and have the coverage scorecard to prove it works."

Recommended order of execution:

1. **Phase 19** — Hardening, error proofing, CI/CD, detection-as-code pipeline
2. **(half-phase 19.5)** — Chaos testing
3. **Phase 20** — Heavy-hitter choreographed scenarios + operator training + performance baseline
4. **Phase 21** — Caldera (and optionally Atomic Red Team) integration, coverage scorecard, adversary-emulation runbook
5. **Ship-story phase** — README rewrite, demo video, blog post
6. **Future detection growth** — informed by Phase 21 coverage gaps, not by guessing

This sequence answers the original question — "is the threat model robust, does it actually work against complex attacks?" — with evidence, not assertions.

---

## 10. Phase Dependency and Time Estimate Summary

| Phase | Depends on | Rough effort (focused work) | Blocking for |
|---|---|---|---|
| 19 — Hardening + CI/CD + DaC | Current main | ~2–3 weeks | 19.5, 20, 21 |
| 19.5 — Chaos testing | 19 | ~3–5 days | 20 (advisory), 21 (advisory) |
| 20 — Choreographed heavy hitters + UX drills + merge/split | 19, 19.5 | ~2–3 weeks | 21 |
| 21 — Caldera + scorecard | 20 (especially CI + DaC + perf baseline) | ~2–3 weeks | Ship story (in part) |
| Ship story | 21 (for headline scorecard) | ~1 week dedicated, plus drip during 19–21 | None |

**Total focused effort for the 1.0 release arc: ~8–11 weeks.** Realistic calendar time depending on how many sessions per week: 2–4 months.

Stop-points along the way that each represent a meaningful release on their own:
- **End of Phase 19**: "platform is hardened and CI-protected" — already a meaningful version bump (call it v0.9).
- **End of Phase 20**: "platform handles five real attack chains in under 2 minutes each, with merge/split capability" — v0.95.
- **End of Phase 21**: "platform tested against autonomous adversary emulation with a coverage scorecard" — v1.0.
- **End of ship story**: "v1.0 with a public demo video and a writeup linking to the coverage scorecard."

---

## 11. Risks and Mitigations Across the Arc

| Risk | Where it shows up | Mitigation |
|---|---|---|
| Hardening drags on indefinitely (perfectionism trap) | Phase 19 | Hard-cap each punch list item: if it takes > 2 days of focused time, it gets timeboxed or deferred to Phase 22. |
| Adding new detectors instead of hardening | Phase 19 | Strict rule in CLAUDE.md update: "no new detectors before Phase 21 completes." |
| CI flakiness becoming the new toil | Phase 19 onward | Treat any CI flake as a Phase 19 bug, not a CI problem to ignore. Quarantine flaky tests with `@pytest.mark.flaky` only as a last resort, with a tracking comment. |
| Caldera setup complexity blocking Phase 21 | Phase 21 | Allocate the first 3 days of Phase 21 to "stand up Caldera, prove it can talk to the agent, run a recon-only operation." If that's stuck, escalate fast. |
| Performance baseline reveals existing slowness pre-Caldera | End of Phase 20 | Treat this as a Phase 19.5 finding, not a Phase 21 blocker. Either fix it before Phase 21 or document the known limit and move on. |
| Operator drill (Phase 20) reveals UX gaps | Phase 20 | Budget 1 week inside Phase 20 specifically for UX fixes uncovered by drills. The drill is the test, not the demo. |
| Coverage scorecard reveals embarrassing detection gaps | Phase 21 | Reframe as feature, not bug: "the platform's coverage was honest enough to surface its own gaps." Document the gaps as Phase 22 candidates. The scorecard's existence is the impressive thing, not its score. |
| Ship-story phase gets postponed indefinitely (the classic) | Ship story | Pre-commit to a date. Treat the public demo video as the actual "done" signal of the 1.0 arc — without it, none of the Phase 19–21 work gets shared. |

---

## 12. One-Sentence Summary of the Arc

The next 8–11 weeks of focused work harden the platform, prove it survives real load and real failure modes, prove it handles five distinct realistic attack chains in under 2 minutes each, prove it stands up to autonomous adversary emulation with a coverage scorecard you can show, and ship the writeup that turns all of that into a story — at which point CyberCat is no longer "an impressive personal project" but "a working SOC platform with evidence."
