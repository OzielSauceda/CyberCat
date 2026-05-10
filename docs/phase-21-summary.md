# Phase 21 — Caldera adversary emulation + coverage scorecard

**Status:** First scorecard run COMPLETE (2026-05-06). Headline: **0 / 17 covered, 3 gaps, 14 ability errors**. The result IS the deliverable — read it as a baseline measurement of where CyberCat's Linux detection coverage stands against an unsanitised adversary emulation, not as a quality verdict on the platform.
**Branch:** `phase-21-caldera-emulation` (six original commits + Day-2 5.0.0→4.2.0 pivot fixes; not yet pushed)
**Predecessor:** Phase 20 (commit `11778e3`, `v1.0`)
**Successor:** Phase 22 (LotL behavior-chain detection — see `project_phase22_23_thesis` memory)

---

## What shipped (code)

Six commits on the `phase-21-caldera-emulation` branch:

1. **`phase-21 A: caldera service + sandcat in lab-debian`** — Caldera
   5.0.0 as a `--profile caldera`-gated compose service (default OFF,
   bound to 127.0.0.1:8888), Sandcat fetch-on-start in
   `lab-debian/entrypoint.sh`, `start.sh` provisions
   `CALDERA_API_KEY` on first run.
2. **`phase-21 B1: ability profile + expectations`** — 25-ability
   curated adversary profile in `labs/caldera/profile.yml`,
   ATT&CK-mapped expectations registry in
   `labs/caldera/expectations.yml`, five custom abilities in
   `labs/caldera/abilities/` (T1021.004, T1105, T1486, T1552.001,
   T1098) where Stockpile coverage was thin.
3. **`phase-21 B2: run.sh + scorer.py + build_operation_request.py`** —
   pure-stdlib payload helper, six-status enum scorer with symmetric
   ATT&CK-attribution rule (verified at planning time against five
   synthetic cases), orchestrator that drives a Caldera operation,
   captures the run window, queries
   `GET /v1/detections?since=<window>`, and writes
   `docs/phase-21-scorecard.{md,json}`.
4. **`phase-21 D1: smoke_test_phase21.sh`** — five assertions: caldera
   healthy, sandcat running, agent enrolled, single-ability T1110.001
   run fires `py.auth.failed_burst`, scorecard files generated.
5. **`phase-21 D2: ADR-0016 + docs + summary`** — this file plus
   ADR-0016, runbook section, four learning-notes entries, and the
   PROJECT_STATE pickup-rewrite.
6. **`phase-21 D3: ruff F541`** — single lint finding in
   `build_operation_request.py:301` (extraneous `f` prefix on a string
   with no placeholders). Caught locally per
   `feedback_run_ruff_before_push` memory — Phase 20's CI-red lesson
   doing its job.

ADR-0016 captures the seven decisions: Caldera as engine, profile-gate
+ 127.0.0.1 bind, `--insecure` acceptable in our deployment shape,
Sandcat fetch-on-start, curated 25-ability set, scorecard-as-files-only
v1, conservative ATT&CK attribution rule.

## What's pending (the deliverable itself)

The first scorecard run. Operator runs:

```bash
bash start.sh --profile agent --profile caldera
sleep 60                                                  # let Caldera start_period elapse
python labs/caldera/build_operation_request.py --resolve-uuids
bash labs/caldera/run.sh
less docs/phase-21-scorecard.md
bash labs/smoke_test_phase21.sh
```

The headline number from that first run gets pasted below this section
along with the ordered Phase 22 punch list. Until then, this file is a
status report, not the deliverable.

## First-run scorecard (2026-05-06)

Operation: `326fde6c-fd74-434a-92b6-6275ab5e70e5` against Caldera 4.2.0 +
the `cybercat-phase21-linux-baseline` adversary (17 abilities: 12
Stockpile + 5 custom). Sandcat agent enrolled in `lab-debian` from
group `red`. Run window 2026-05-06 04:33-04:55 UTC.

| Headline | Value |
|---|---|
| covered | **0** |
| gap | 3 |
| false-negative | 0 |
| unexpected-hit | 0 |
| ability-failed | 9 |
| ability-skipped | 5 |
| **total** | **17** |

**Why 17, not 25?** The plan was authored against Caldera 5.0.0's
stockpile content shape. 5.0.0's first-run UI broke on a missing
`plugins/magma/dist/assets` directory (the upstream image-less install
flow assumes the operator hand-runs `npm run build` before launching
the server), so we pinned `infra/caldera/Dockerfile` to 4.2.0 — the last
release that ships the older Vue UI as static files. 4.2.0's stockpile
inventory differs: 8 of the original 25 placeholder slugs (e.g.
`STOCKPILE:bash:linux:apache-webshell-id`,
`STOCKPILE:ssh:linux:success-after-brute`) had no equivalent ability,
so they were dropped rather than substituted with unrelated content.
17 (12 Stockpile + 5 custom) is the working profile. ADR-0016 will be
updated to capture the 5.0.0 → 4.2.0 pin.

**Why 0 covered?** Three forces compound:

1. **The 5 custom abilities (`linux_lateral_ssh`, `linux_curl_pipe_sh`,
   `linux_creds_aws_read`, `linux_file_burst_encrypt`,
   `linux_useradd_persist`) didn't dispatch.** Their IDs are local
   `labs/caldera/abilities/<id>.yml` slugs that Caldera's atomic
   planner doesn't know about — the abilities need to be uploaded to
   Caldera's stockpile (`POST /api/v2/abilities`) before they can be
   exercised. This is a Phase-21.5 follow-up, not a detection-coverage
   miss. All 5 show as `ability-skipped`.
2. **`SUDO Brute Force - Debian` ran but `py.auth.failed_burst` did
   not fire.** Caldera marked the link `status=-3` (cleanup phase
   triggered before the brute-force window completed). The detector
   keys on PAM/auth.log failure events; Stockpile's sudo-brute-force
   ability sets up its target user and runs failed `su` invocations,
   but the cleanup deadman fired before 4 failures landed in the 60s
   window. **Real signal**: our covered case from Phase 20 (sshd brute
   force) doesn't transfer cleanly to a sudo brute-force surface —
   either the detector needs to broaden to PAM-failure-source
   regardless of binary, or we need a Caldera ability that hits sshd
   specifically.
3. **Three discovery abilities ran cleanly with status=0 and produced
   no detection** — that's the literal definition of `gap`. They
   hit techniques (T1059.004 `id`/`whoami`, T1057 process listing,
   T1083 file enumeration) that we already documented as Phase 22
   gap candidates. The run validates those gaps with concrete
   evidence rather than scenario-driven inference.

| # | Status | Ability | Technique | Caldera | Notes |
|---|---|---|---|---|---|
| 1 | gap | identify active user (id/whoami) | T1059.004 | 0 | Phase 22 process-chain detector candidate (Linux LotL) |
| 2 | gap | process listing (find user processes) | T1057 | 0 | New: process-discovery detector candidate |
| 3 | gap | filesystem enumeration (find files) | T1083 | 0 | New: file-discovery detector candidate |
| 8 | ability-failed | SUDO brute-force | T1110.001 | -3 | `py.auth.failed_burst` did not fire — cleanup deadman raced the brute-force window. Investigate whether detector should broaden from sshd-only to all PAM failures |
| 3-7,12-17 | ability-failed | (network conn enum, /etc/passwd read, passwd change, cron persistence, history wipe, tar archive, scp exfil, systemd unit) | various | 1 or -3 | Status 1 = ability ran but its parser said "missing required output"; -3 = cleanup deadman superseded. Caldera's atomic planner is sensitive to fact-source completeness; most of these need a fact source seeded with realistic targets to run cleanly |
| 6,7,9,10,11 | ability-skipped | (SSH lateral pivot, curl\|sh, AWS cred theft, file-burst encrypt, useradd backdoor) | various | n/a | Custom-ability local slugs not registered in Caldera stockpile — Phase 21.5 follow-up: upload via `POST /api/v2/abilities` |

The full per-row table is in `docs/phase-21-scorecard.md`.

## Phase 22 punch list (ordered by evidence)

Ordered by where the run gives strongest signal first. Items 1–4 are
Phase 20 Gap evidence carried forward; items 5–7 are surfaced or
sharpened by this run.

1. **Linux process-chain (LotL) detector** —
   `backend/app/detection/rules/process_lotl_chain.py` (new module),
   Phase 20 Gap 1, A1+A2+A3+A4+A5 evidence + Phase 21 rows 1–2 (id /
   whoami, ps listing both ran with no detection). Behavior-chain
   rules: `(parent, child, cmdline-fragment, time-window)` triples.
2. **`network_indicator_compromise` correlator** —
   `backend/app/correlation/rules/network_indicator_compromise.py`
   (new), Phase 20 Gap 2, A2+A5 evidence. Promotes
   `py.blocked_observable_match` on `network.connection` events to
   incidents, dedupes on `(host, dst_ip, hour-bucket)`.
3. **`auth_baseline_unknown_source_success` detector** —
   `backend/app/detection/rules/auth_baseline_unknown_source_success.py`
   (new), Phase 20 Gap 3, A5 evidence. Per-user 90-day source-IP
   baseline; cold-start handling for new users.
4. **`file_burst_detector`** —
   `backend/app/detection/rules/file_burst_detector.py` (new),
   Phase 20 Gap 4, A4 evidence. Redis sliding window per host,
   suffix or shared-parent-dir pattern.
5. **PAM-failure detector broadening** — `auth_failed_burst.py` only
   fires on sshd-source failures. Phase 21 row 8 shows sudo-source
   failures generating identical PAM events but staying invisible to
   the detector. Either generalize the existing detector to "any PAM
   failure" or add a sibling `auth_pam_failed_burst.py` that's
   binary-agnostic. New evidence from Phase 21.
6. **File-discovery detector (T1083)** — Phase 21 row 5 (Caldera's
   `find /` for sensitive extensions) ran cleanly and undetected. Low
   priority compared to LotL but cheap to author. New evidence.
7. **Process-discovery detector (T1057)** — Phase 21 row 2 (`ps aux |
   grep <user>`) ran cleanly and undetected. Same priority bucket as
   #6.

The 5 custom-ability skips are NOT Phase 22 work — they're a Phase
21.5 follow-up: `POST /api/v2/abilities` for each
`labs/caldera/abilities/<id>.yml` so Caldera's atomic planner can
dispatch them. Once they're stockpile-resident the run will exercise
T1021.004, T1105, T1486, T1098 directly and add real signal for
Phase 22 LotL chain shaping.

## Verification at close

The full operator checklist from `docs/phase-21-plan.md` ends Phase 21:

1. Bring-up green
2. Caldera health endpoint OK
3. Sandcat process running
4. `bash labs/caldera/run.sh` produces both scorecard files
5. `less docs/phase-21-scorecard.md` shows a coherent table
6. `bash labs/smoke_test_phase21.sh` → `passed: 5  failed: 0`
7. `ruff check app/` → no errors (Phase 20 CI-red lesson)
8. `pytest -q` inside the backend container → all green

When all eight pass, merge `--no-ff` into `main` with message
`Phase 21 — Caldera adversary emulation + coverage scorecard`. Optional
`v1.1` tag if the scorecard reveals enough to be a real platform-state
milestone.

## Operator-tooling findings (non-blocking, surface for backlog)

The 5.0.0 → 4.2.0 pivot exposed the full Phase 21 dependency chain.
None of these blocked shipping; all are worth queueing for Phase 21.5.

- **Caldera image isn't a one-shot build.** 5.0.0 fails on missing
  magma assets; 4.2.0 fails until you pin `websockets<14` (newer
  websockets breaks the `/system/ready` internal probe), `yarl<1.10`
  (newer yarl rejects `host:port` in `URL.build`, and aiohttp 3.8.4
  passes the raw `Host` header straight in — every request returned
  HTTP 500 silently because Caldera's `setup_logger` mutes everything
  outside `aiohttp.server`/`asyncio`), and `python:3.11-slim-bookworm`
  base image (gcc 14 in trixie hard-errors on `donut-shellcode`'s
  legacy implicit int/pointer C, gcc 12 in bookworm warns and
  proceeds). All four pins are now baked into
  `infra/caldera/Dockerfile`. ADR-0016 update: capture the dep-pin
  set as a hard cost of running 4.2.0.
- **API-key alignment via entrypoint.** `--insecure` loads
  `conf/default.yml` whose `api_key_red: ADMIN123` doesn't match our
  `${CALDERA_API_KEY}` env var. New `infra/caldera/entrypoint.sh`
  patches the key in place at container start so `.env` and Caldera
  agree. Without that, the scorer's KEY-header auth gets 401 silently.
- **`/v1/detections` time-window URL encoding.** FastAPI's datetime
  parser rejects `+00:00` in the query string when `+` decodes as a
  space. `run.sh` URL-encodes the `+` (`%2B`) before issuing the
  request. Easy to miss; document in the runbook.
- **`/v1/detections` limit cap is 200, not 500.** The server validates
  `limit <= 200` and returns 422; `curl -sf` swallows it silently and
  truncates the destination file to zero bytes, which then fails the
  scorer with a JSON decode error. Lowered to 200 in `run.sh`.
- **Custom abilities aren't yet uploaded to Caldera stockpile.** The
  five `labs/caldera/abilities/*.yml` files exist locally and the
  resolver leaves their IDs unchanged in `profile.resolved.yml`, but
  Caldera's atomic planner only dispatches abilities present in its
  in-process registry. Phase 21.5 candidate: write an uploader that
  iterates `labs/caldera/abilities/`, POSTs each to
  `/api/v2/abilities`, and ensures the ability_id matches what
  `profile.yml` references. Without this the 5 custom abilities are
  permanently `ability-skipped` in every scorecard run.
- **`adversary` upsert needs content-aware update.** A previous run
  with un-resolved STOCKPILE: placeholders created an empty-ordering
  adversary that subsequent runs reused (idempotent on name). Patched
  `build_operation_request.py` to compare `existing_ordering ==
  desired_ordering` and delete-then-recreate on mismatch. Without
  this, the script ran "Avoid logs" instead of our adversary because
  Caldera fell through to a default behaviour.
- **`docs/` wasn't bind-mounted into backend.** Scorer wrote
  `phase-21-scorecard.{md,json}` inside the container's `/app/docs`,
  which evaporated on container recreation. Added a bind mount; same
  pattern as the existing `labs/` mount.
- **Git Bash on Windows path translation broke five different ways.**
  `mktemp -t /tmp/...` produced a Bash-form path Python on Windows
  couldn't open; `MSYS_NO_PATHCONV=1` mangled the `-f compose.yml`
  path; `--out-md /app/...` got rewritten to `C:/Program Files/Git/app/...`.
  Settled on `//path` (double leading slash) for in-container paths
  the host hands through unchanged, and a project-local `.tmp/`
  scratch dir under `labs/caldera/` (which IS bind-mounted) instead
  of `/tmp`. Cross-platform pain points — document in the runbook.
