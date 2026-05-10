# ADR-0016 — Caldera adversary emulation + coverage scorecard (Phase 21)

**Date:** 2026-05-05 (amended 2026-05-06 — see "Day-2 amendments")
**Status:** Accepted (with amendments)
**Deciders:** Oziel (owner)
**Builds on:** ADR-0006 (attack simulator), ADR-0011 (direct-agent telemetry), ADR-0015 (incident merge/split)

---

## Context

Phase 20 shipped a hand-curated detection-gap list (4 evidenced gaps in
`docs/phase-20-summary.md:36-148`). It was authored by *reading* the
five Linux scenarios — useful, but not measured. Before designing
Phase 22 detectors ("intent over tool name," per the
`project_phase22_23_thesis` memory), we need a *measured*,
ATT&CK-mapped coverage signal so the Phase 22 punch list is ordered by
evidence rather than author judgment.

Phase 21 introduces MITRE Caldera as the adversary-emulation engine,
runs it against `lab-debian` via Sandcat (Caldera's Linux agent),
queries CyberCat's `detections` table for what fired during the run
window, and emits a markdown + JSON scorecard.

---

## Decisions

### 1. Caldera as the emulation engine

**Chosen:** MITRE Caldera 5.0.0, pinned in `infra/caldera/Dockerfile`,
built from upstream source rather than from a pre-built image.

**Why Caldera over alternatives.**

- **Atomic Red Team** is excellent for individual-test execution but
  has no agent model. We would need to write our own dispatcher,
  result-collector, and timeline. Caldera ships all three.
- **Custom emulation** (a Python harness driving `docker exec`) was
  considered and rejected — that's effectively what the Phase 20
  simulator already does. The point of Phase 21 is to *not* rely on
  author-curated scenarios.
- **Pre-built Caldera images** float on `latest`. Building from a
  pinned tag in our own Dockerfile gives reproducibility, lets us audit
  every dependency, and lets us drop our own `local.yml` at build time
  for deterministic first-run config.

### 2. `--profile caldera` gating + 127.0.0.1 bind

**Chosen:** New compose profile `caldera`, default OFF. Caldera's UI
port (8888) bound to `127.0.0.1` only, never to all interfaces.

**Why profile-gated.** §7 (resource discipline): the always-on stack
must idle <6 GB. Caldera adds ~1.0–1.5 GB when active; we cannot run
it always-on without violating that budget. Profile gating mirrors the
existing `--profile wazuh` pattern.

**Why 127.0.0.1 only.** §8 (host-safety): the operator's threat model
is a single laptop lab. Binding only to localhost means the Caldera UI
and REST API are reachable by the operator and by no one else on the
network. **If the operator ever runs CyberCat on a shared/multi-user
machine, this assumption inverts and the bind must be reconsidered.**

### 3. `--insecure` Caldera mode

**Chosen:** Run Caldera with `--insecure` (skips TLS bootstrap) inside
the compose network.

**Why acceptable.** Three layered constraints make this safe in our
deployment shape: (a) the service is bound to 127.0.0.1 only,
(b) the server runs on the private compose bridge network, not on the
host net, (c) the threat model is a laptop lab. Caldera's TLS support
is opinionated and would require generating a CA + indexer-style cert
material (we already maintain a separate one for Wazuh — adding a
second is busywork that doesn't change the threat model).

### 4. Sandcat fetch-on-start, not baked

**Chosen:** `lab-debian/Dockerfile` only creates `/opt/sandcat/`.
`lab-debian/entrypoint.sh` fetches the Sandcat binary from
`${CALDERA_URL}/file/download` at container start when `CALDERA_URL`
is non-empty.

**Why not bake the binary into the image.** Sandcat is a Caldera
artifact; baking it would couple `lab-debian`'s image to a specific
Caldera build. The fetch-on-start pattern matches Caldera's own Linux
enrollment docs and matches our existing Wazuh-agent
`WAZUH_REGISTRATION_PASSWORD` conditional.

**Why this is robust to "Caldera not running."** The fetch is wrapped
in `2>/dev/null`; the launch is wrapped in `( ... & ) || true`. With
the `agent` profile only (no `caldera`), `CALDERA_URL` is empty and
the entire block is a no-op. With both profiles up, the fetch may race
ahead of Caldera's 60-second `start_period` and fail — the
container's next restart fetches successfully.

### 5. Curated ~25 abilities, not full Stockpile

**Chosen:** A hand-curated 25-ability adversary profile aligned to the
ATT&CK techniques our Phase 20 scenarios touched, plus five custom
abilities authored in `labs/caldera/abilities/`.

**Why curated.** Stockpile ships 80–150 Linux abilities depending on
version. Many require tools `lab-debian` doesn't have (Metasploit,
msbuild, etc.); many run the wrong command for our gap-evidence
purpose (Stockpile's T1486 ability targets specific extensions we
don't seed). Running the full set produces a noisy 5–15% scorecard
with most rows showing `ability-failed`. Curation produces a clean
~12% scorecard whose rows directly map to our four documented gaps,
which is the Phase 22 input we actually need.

**Why five custom abilities.** Stockpile doesn't ship clean coverage
for: T1021.004 (sshd→bash→ssh chain — needs the parent shape), T1105
(curl|sh sibling-process pattern), T1486 (file-burst rate signature),
T1552.001 (clean cred-theft + new-IP login), T1098 (useradd with
strict cleanup). Each custom YAML carries a `cleanup` block; without
strict cleanup, `lab-debian` accumulates artifacts and the scorecard
becomes non-reproducible.

### 6. Scorecard as files (markdown + JSON), no Postgres persistence

**Chosen:** Phase 21 v1 ships `docs/phase-21-scorecard.md` and
`docs/phase-21-scorecard.json`. No `coverage_runs` table, no
`/v1/coverage` endpoint.

**Why defer persistence.** The scorer is deterministic — re-running it
against the same Caldera operation report and the same detections-
since-window window produces the same scorecard. The data already
exists in two systems (Caldera's operation reports, CyberCat's
`detections` table); persisting the *join* would just be a third
representation. Phase 22 needs the markdown for punch-list ordering;
it does not need an API surface. A coverage-runs table + endpoint
remains a Phase 21.5+ candidate if we want diff-across-runs in the
future.

### 7. Conservative ATT&CK attribution rule

**Chosen:** A rule fire is attributed to an ability iff the symmetric
overlap `{tag, parent(tag)} ∩ {target, parent(target)}` is non-empty,
where `target` is the ability's declared technique and `tag` is any
entry in the detection's `attack_tags`. Sub-technique IDs (e.g.
`T1059.004`) collapse to their parent (`T1059`) for the comparison.

**Why symmetric.** A detection tagged `T1059.001` should attribute to
an ability tagged `T1059` (the sub-technique is *evidence of* the
parent). A detection tagged `T1059` should attribute to an ability
tagged `T1059.004` (the parent fired, that's evidence of the
sub-technique surface). One-way comparison would make the scorecard
dependent on whether the detector author was more specific than the
ability author, which is noise.

**Why conservative (not strict-equal, not loose).** Strict equal
misses cross-subtechnique siblings within the same parent (false
negatives). Looser rules (e.g. matching on tactic) would pull in
adversarially-shaped happy accidents and inflate `unexpected-hit`
beyond useful signal. The set-overlap rule lands between the two and
is unit-testable; see `labs/caldera/scorer.py:_attribution_match`.

---

## What we're not doing yet (out of scope)

- **No abilities targeting external hosts.** §8 host-safety: the
  profile is locked to `lab-debian`. Custom abilities check the
  destination IP/host before issuing requests.
- **No real malware detonation.** Caldera abilities run shell
  commands, not droppers. No payload archives are downloaded and
  executed; the `linux_curl_pipe_sh` ability fails fast.
- **No privileged or host-namespace abilities.** No `--privileged`,
  no `--pid=host`, no `--network=host` on `lab-debian` or `caldera`.
- **No automated remediation triggered by Caldera-driven incidents.**
  Phase 21 is measurement, not response. Existing auto-safe action
  handlers continue to work for non-Caldera-driven incidents.
- **No coverage endpoint or DB tables.** Deferred to Phase 21.5+
  pending evidence we want diff-across-runs.
- **No multi-host emulation.** Sandcat enrollment is `lab-debian` only.
  The runner's preflight asserts ≥1 agent in the `red` group; it does
  not assume any specific count.

---

## Tradeoffs

- **+~1.0–1.5 GB RAM when active.** The WSL2 cap is ~6 GB
  (memory entry `env_wsl_memory_cap`). With `--profile wazuh` AND
  `--profile caldera` simultaneously up, the operator must bump
  `~/.wslconfig` to 8 GB. Documented in `labs/caldera/README.md`.
- **Stockpile UUIDs rotate across major Caldera releases.** Bumping
  `CALDERA_VERSION` in `infra/caldera/Dockerfile` requires re-running
  `python labs/caldera/build_operation_request.py --resolve-uuids` to
  rewrite the `*.resolved.yml` sidecars.
- **Sandcat persists in `/opt/sandcat/sandcat` for the container
  lifetime.** Gone on `down -v`. The lab's identity baseline stays
  clean across runs because every custom ability has a `cleanup` block.
- **`--insecure` Caldera assumes single-user laptop deployment.** If
  the operator ever runs on a shared/multi-user machine, this
  assumption inverts and `--insecure` must be removed alongside
  generating cert material.

---

## Verification

Phase 21 closes when all of the following pass:

```bash
bash start.sh --profile agent --profile caldera          # 1. bring-up
curl -sf http://127.0.0.1:8888/api/v2/health             # 2. caldera healthy
docker compose -f infra/compose/docker-compose.yml \
    exec lab-debian pgrep -af sandcat                    # 3. sandcat running
python labs/caldera/build_operation_request.py \
    --resolve-uuids                                      # 4. UUIDs resolved
bash labs/caldera/run.sh                                 # 5. scorecard generated
bash labs/smoke_test_phase21.sh                          # 6. smoke green
```

The scorecard at `docs/phase-21-scorecard.md` IS the deliverable. The
projected first-run number is 2-3 covered out of 25 (~8-12%). If much
higher, attribution may be too loose. If much lower, `py.auth.failed_burst`
may have a brittle parse path under Caldera-driven sshd traffic.
Either direction warrants investigation before the v1.1 tag.

> **Day-2 result note:** The first run came in at **0/17 covered**, not
> 2-3/25. The denominator dropped because 8 of the 25 stockpile slugs
> didn't exist on the 4.2.0 line we ended up pinning, and the numerator
> was 0 because (a) the 5 custom abilities never dispatched (their
> local IDs aren't registered in Caldera's stockpile — Phase 21.5
> follow-up) and (b) the one covered case (sudo brute-force) was raced
> by Caldera's cleanup deadman. The 3 abilities that did execute
> cleanly all hit known Phase 22 gap surfaces. See "Day-2 amendments"
> below and `docs/phase-21-summary.md` for the full read.

---

## Day-2 amendments (2026-05-06)

Phase 21's first-run pickup surfaced four classes of issue that
Decisions 1–7 above didn't anticipate. None of them invalidate the
original architecture; all of them required concrete patches that are
now baked into the working tree. Captured here for posterity so the
next operator (or the next time we bump `CALDERA_VERSION`) doesn't
re-discover them in the wild.

### A. Pin: Caldera 5.0.0 → 4.2.0

Decision 1 said "MITRE Caldera 5.0.0, pinned." The 5.0.0 first-run
launches `python3 server.py` which crashes on
`ValueError: No directory exists at '/usr/src/app/plugins/magma/dist/assets'`.
Caldera 5.0.0 introduced the `magma` Vue 3 UI plugin; the upstream
install instructions assume the operator hand-runs
`cd plugins/magma && npm install && npm run build` before launching
the server. We don't ship Node.js in the image and the build adds
~300 MB + first-time-run latency.

**Pivot:** pin to **Caldera 4.2.0** (last release with the older
bundled-static-files Vue UI). All Phase 21 scorer/runner code was
verified compatible with 4.2.0's `/api/v2` surface — Decision 1's
"audit every dependency" rationale still holds, just one major version
back. Future bump to 5.x requires the npm-build step in the Dockerfile.

### B. Transitive-dep pin set

Caldera 4.2.0 ships with permissive lower-bound-only pins
(`websockets>=10.3`, no upper-bound on `cryptography` or `yarl`).
Modern resolvers pull versions whose APIs Caldera was never tested
against:

- **`websockets<14`** — 14.0 rewrote the server connection API;
  Caldera's internal `/system/ready` probe gets a `1011 internal
  error` close on startup.
- **`yarl<1.10`** — 1.10+ added strict host-string validation in
  `_encode_host` that rejects `:port`. `aiohttp 3.8.4` still passes
  `request.host` (the raw `Host` header, which legitimately includes
  `:port` for non-default ports) directly to `URL.build(host=...)`.
  Result: every HTTP request with `Host: <name>:8888` raised
  `ValueError` mid-route-resolve and aiohttp returned a generic 500
  with **no log** (Caldera's `setup_logger` mutes everything outside
  `aiohttp.server` and `asyncio`). The clearest "silent failure" we've
  hit on the project.
- **`python:3.11-slim-bookworm`** instead of `python:3.11-slim` —
  the floating tag now resolves to Debian trixie (gcc 14), which
  hard-errors on `donut-shellcode`'s legacy implicit-int/pointer C
  via `-Werror=int-conversion`. Bookworm's gcc 12 leaves them as
  warnings.

All four pins are in `infra/caldera/Dockerfile` with rationale
comments. Touching any of them requires testing the bring-up path end
to end.

### C. API-key alignment via entrypoint

Decision 3 said "`--insecure` is acceptable." It is — but `--insecure`
also means Caldera loads `conf/default.yml` instead of our custom
`conf/local.yml`. `default.yml` hardcodes `api_key_red: ADMIN123` and
`api_key_blue: BLUEADMIN123`. Our scorer reads `CALDERA_API_KEY` from
`infra/compose/.env` (auto-provisioned by `start.sh`). Without
alignment, every `KEY:`-authenticated request from the scorer gets
401 silently.

**Resolution:** new `infra/caldera/entrypoint.sh` patches the keys in
place at container start using `sed`. The script is the new
`ENTRYPOINT`; `--insecure` is now an internal arg. `.env` and Caldera
agree by construction.

### D. Healthcheck endpoint mismatch

Decision 1 didn't specify the healthcheck path; the original compose
block hit `/api/v2/health`. That endpoint is **5.x only**. On 4.2.0,
the substitute is `/enter`, a public 302-redirect-to-login route that
`curl -sf` accepts (only 4xx/5xx fail). Both `infra/compose/docker-compose.yml`
and `labs/caldera/run.sh` preflight check were patched.

### E. API field-name drift

Caldera 4.2.0's `PlannerSchema` declares `planner_id =
ma.fields.String(data_key='id')`, so the wire key is `id` not
`planner_id`. The 4.2.0 `/api/v2/operations/<id>/report` endpoint is
**POST-only** (5.x added GET). The 4.2.0 `AdversarySchema` accepts
both `id` and `adversary_id` (it has a `pre_load` `fix_id` hook).
`labs/caldera/build_operation_request.py` and `labs/caldera/run.sh`
both patched to handle the 4.2.0 surface; the dual-shape handling is
explicit so a future bump back to 5.x continues to work.

### F. Scorer report-shape compatibility

Caldera's operation report shape varies by major version:
- 5.x: `report.steps = { paw: [{ability_id, status, ...}, ...] }`.
- 4.2.0: `report.steps = { paw: { "steps": [...] } }` plus a separate
  `report.host_group = [ {paw, links: [{ability: {...}, ...}]} ]`.

`labs/caldera/scorer.py` was patched with explicit dual-shape
extraction in `score()`. Same pattern as Decision 7's symmetric
attribution rule — the scorer is the contract surface and stays
portable across the version pin.

### G. Operation-completion semantics

Decision 4's "the fetch may race ahead of Caldera's 60-second
`start_period`" anticipated the Sandcat-fetch race. It didn't
anticipate the **`auto_close=true` deadman race** at the *operation*
level. Caldera 4.2.0's atomic planner injects a cleanup link
(`status=-3`) after each ability; if a brute-force ability hasn't
completed its 4-failures-in-60s window before the cleanup fires, the
brute-force is interrupted and the auth detector never sees enough
events. This is the mechanism behind the first-run "0 covered" — the
`SUDO Brute Force - Debian` ability ran but its window didn't
register on `auth.log` before deadman cleanup. Phase 21.5 candidate:
either disable the cleanup link for time-window abilities, or
generalize `auth_failed_burst.py` to PAM-failure-source (which would
catch the partial brute-force regardless of cleanup race).

### H. Custom-ability registration

Decision 5 said "five custom abilities authored in
`labs/caldera/abilities/`." The five YAML files are linter-clean and
the resolver leaves their local IDs unchanged in
`profile.resolved.yml`, but **Caldera's atomic planner only
dispatches abilities present in its in-process registry**. The
local YAML files are not auto-loaded. Phase 21.5 candidate: write
`labs/caldera/upload_custom_abilities.py` that POSTs each YAML to
`/api/v2/abilities` so the IDs are registered, then verify the
returned `ability_id` matches what `profile.yml` references.

Without this step, all 5 custom abilities are permanently
`ability-skipped` in every scorecard run. This is the single biggest
slice missing from the first scorecard's coverage signal.

### I. Sequencing decision (post-first-run)

The original Phase 21 → Phase 22 → Phase 21.5 path assumed Phase 21's
first scorecard would directly evidence Phase 22's punch list. With 14
of 17 abilities not running cleanly, the scorecard's *measured*
signal is thin. Two options:

1. **Phase 21.5 first** (fix the test rigging: upload custom abilities,
   add a fact source, resolve the cleanup deadman race), then re-run
   the scorecard, then Phase 22 from clean evidence.
2. **Phase 22 first** (build the four detectors Phase 20 evidenced
   plus the PAM broadening from Phase 21's sudo-brute-force finding),
   then Phase 21.5 to re-run the scorecard as a *regression test*
   instead of a baseline.

**Chosen: Phase 22 first.** Phase 20's gap evidence is already
concrete (5 scenarios, 4 documented gaps, named code paths). Phase
21's run mostly re-confirmed that evidence; the scorecard's measured
signal isn't telling us much we didn't already know. The product
value is in the detectors, not the rigging. Phase 22 detectors can
be authored against unit tests + the existing Phase 20 scenarios
without Caldera in the picture; once they exist, Phase 21.5's
scorecard re-run *validates* them with concrete coverage rather than
re-measuring gaps. Reverse order would mean spending a session fixing
Caldera content shapes that don't ship product value.

The one Phase-21 finding that DOES feed Phase 22: broaden
`auth_failed_burst.py` (or add a sibling) to fire on PAM failures
regardless of source binary — sshd-only is too narrow, sudo-source
brute force is invisible.

---

## Verification (revised post-first-run)

The Day-1 verification block above (`/api/v2/health`, `pgrep sandcat`)
is calibrated to the original 5.0.0 plan. The 4.2.0-pinned working
sequence is:

```bash
bash start.sh --profile agent --profile caldera         # 1. bring-up (~5 min on first build)
curl -sf http://127.0.0.1:8888/enter                    # 2. caldera healthy (302 OK)
docker compose -f infra/compose/docker-compose.yml \
    exec lab-debian grep "Beacon.*ALIVE" \
    /var/log/sandcat.log                                # 3. sandcat beaconed
docker compose -f infra/compose/docker-compose.yml \
    exec -T -e CALDERA_API_KEY="$KEY" backend \
    python -m labs.caldera.build_operation_request \
        --resolve-uuids --caldera http://caldera:8888   # 4. UUIDs resolved
bash labs/caldera/run.sh                                # 5. scorecard generated (~15-20 min)
bash labs/smoke_test_phase21.sh                         # 6. smoke green (T1+T2+T3+T5; T4 known partial pending Phase 22 PAM broadening)
```

The first scorecard's headline is now **0/17 covered, 3 gap, 14
ability errors**. That number is honest given the current platform
state; it improves to a meaningful baseline after Phase 22 detectors
ship and Phase 21.5 fixes the test rigging. See
`docs/phase-21-summary.md` for the row-by-row read.
