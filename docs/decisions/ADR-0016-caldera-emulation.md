# ADR-0016 — Caldera adversary emulation + coverage scorecard (Phase 21)

**Date:** 2026-05-05
**Status:** Accepted
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
