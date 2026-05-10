# labs/caldera/ — Phase 21 adversary emulation

This directory holds the curated MITRE Caldera adversary profile and the
runner that produces CyberCat's coverage scorecard. See
`docs/phase-21-plan.md` and `docs/decisions/ADR-0016-caldera-emulation.md`
for design context.

## What this is

A ~25-ability Caldera adversary profile, curated to exercise the ATT&CK
techniques our Phase 20 scenarios touched (T1078, T1059.004, T1057,
T1018, T1003.008, T1083, T1071.001, T1105, T1486, T1110.001, T1021.004,
T1546, T1505.003, T1098, T1552.001, T1070.003, T1560.001, T1048.002,
T1543.002, T1082). Running it against `lab-debian` produces a
markdown + JSON scorecard at `docs/phase-21-scorecard.{md,json}`.

The brutal-looking coverage number IS the deliverable — projected ~2-3
covered out of 25. That number is Phase 22's input list.

## Layout

```
labs/caldera/
├── README.md                        ← this file
├── profile.yml                      ← adversary profile (ordered ability list)
├── expectations.yml                 ← source of truth: ability → technique → expected rule_id
├── abilities/                       ← custom abilities for techniques Stockpile lacks
│   ├── linux_lateral_ssh.yml        ← T1021.004
│   ├── linux_curl_pipe_sh.yml       ← T1105
│   ├── linux_file_burst_encrypt.yml ← T1486
│   ├── linux_creds_aws_read.yml     ← T1552.001
│   └── linux_useradd_persist.yml    ← T1098
├── build_operation_request.py       ← payload assembler + UUID resolver
├── upload_custom_abilities.py       ← (Phase 21.5) PUT abilities/*.yml to Caldera stockpile
├── seed_fact_source.py              ← (Phase 21.5) PUT fact source from facts.yml
├── facts.yml                        ← (Phase 21.5) declarative facts the seeder uploads
├── run.sh                           ← orchestrator (preflight → operation → scorer)
└── scorer.py                        ← coverage-status logic + markdown/JSON renderer
```

## How to run

```bash
# 1. Bring up CyberCat with both the agent and caldera profiles.
bash start.sh --profile agent --profile caldera

# 2. (First run only) Resolve Stockpile ability UUIDs.
docker compose -f infra/compose/docker-compose.yml exec -T backend \
    python -m labs.caldera.build_operation_request --resolve-uuids

# 3. (Phase 21.5 — first run after any abilities/*.yml or facts.yml edit)
#    Upload the 5 custom abilities into Caldera's stockpile.
docker compose -f infra/compose/docker-compose.yml exec -T \
    -e CALDERA_API_KEY="$(grep '^CALDERA_API_KEY=' infra/compose/.env | cut -d= -f2-)" \
    backend python -m labs.caldera.upload_custom_abilities \
        --caldera "http://caldera:8888" --here "//app/labs/caldera"

# 4. (Phase 21.5 — same trigger) Seed the CyberCat fact source so
#    stockpile abilities templated against #{trait} can substitute.
docker compose -f infra/compose/docker-compose.yml exec -T \
    -e CALDERA_API_KEY="$(grep '^CALDERA_API_KEY=' infra/compose/.env | cut -d= -f2-)" \
    backend python -m labs.caldera.seed_fact_source \
        --caldera "http://caldera:8888" --here "//app/labs/caldera"

# 5. Run the full curated profile and produce the scorecard.
bash labs/caldera/run.sh

# 6. Read the result.
less docs/phase-21-scorecard.md
```

Steps 3 + 4 are **idempotent** — both helpers PUT-by-id, so re-running
them simply replaces the prior version. Run them once after any
`abilities/*.yml` or `facts.yml` edit; the `run.sh` orchestrator does
not re-invoke them automatically (operator-controlled by design — they
mutate Caldera's persistent stockpile/sources, not just per-run state).

## Status enum (per row of the scorecard)

| Status | Meaning |
|---|---|
| **covered** | Ability ran AND its expected `rule_id` fired. |
| **gap** | Ability ran AND `expected_rule_id == GAP` AND nothing attributable fired. The honest miss. |
| **false-negative** | Ability ran AND `expected_rule_id != GAP` AND that rule did NOT fire. Bug or brittleness — investigate before merging. |
| **unexpected-hit** | Ability ran AND `expected_rule_id == GAP` BUT a rule with overlapping ATT&CK tags fired. Possibly a happy accident; investigate to confirm. |
| **ability-failed** | Caldera reported the ability did not execute on the agent. Diagnostic only. |
| **ability-skipped** | Ability was in `expectations.yml` but never appeared in Caldera's operation report. Diagnostic only. |

Attribution is conservative: a rule fire is attributed to an ability iff
any detection's `attack_tags` overlaps the ability's `technique` (or its
parent technique — e.g. `T1059` is the parent of `T1059.004`). False
attributions are preferable to missed ones for the v1 scorecard.

## What the scorer does NOT do

- It does not write to Postgres. The scorecard is a file artifact for v1.
  A coverage-runs API + tables is a Phase 21.5+ candidate (see ADR-0016).
- It does not infer technique mappings the operator did not declare. Every
  ability in `expectations.yml` carries its `technique:` field by hand.
- It does not deduplicate detections across multiple operations. Re-running
  `run.sh` overwrites the scorecard with the latest run's window.

## Phase 21.5 helpers — closing the rigging gaps

The first scorecard ran 0/17 covered. The recap doc breaks the failures into:

- **5 ability-skipped** — custom abilities (`linux_lateral_ssh`, `linux_curl_pipe_sh`, `linux_file_burst_encrypt`, `linux_creds_aws_read`, `linux_useradd_persist`) that lived in `abilities/*.yml` but were never uploaded to Caldera's stockpile.
- **9 ability-failed** — Stockpile abilities that errored mid-execution because `#{trait}` template references couldn't substitute against the empty default `basic` fact source.
- **3 honest gaps** — abilities that ran cleanly but no detector fired (Phase 22's input list).

Phase 21.5 adds two helpers and a declarative facts file to fix the rigging halves:

| Helper | What it does | Idempotent | Re-run when |
|---|---|---|---|
| `upload_custom_abilities.py` | Reads `abilities/*.yml`, transforms each into Caldera's API shape, `PUT /api/v2/abilities/{id}`. Verifies via GET. | ✓ (PUT-by-id) | After editing any `abilities/*.yml`. |
| `seed_fact_source.py` | Reads `facts.yml`, builds a Caldera fact-source payload, `PUT /api/v2/sources/{id}`. | ✓ (PUT-by-id) | After editing `facts.yml`. |

`build_operation_request.py` was updated in lock-step: the operation payload's `source.name` is now `cybercat-phase21` (configurable via `--source`) instead of the empty default `basic`.

## Known Caldera 4.2.0 quirks (post-Phase-21.5)

Three gotchas that any future ability author needs to know about. See `docs/phase-21.5-summary.md` and `docs/learning-notes.md` for the full diagnostic stories.

- **Newlines are silently stripped from multi-line commands.** A YAML block scalar (`|`) like `mkdir -p /tmp/loot\nfor i in $(seq 1 30); do` becomes `mkdir -p /tmp/lootfor i in $(seq 1 30); do` at dispatch time. Bash treats that as `mkdir -p /tmp/lootfor` followed by a syntax error. **Workaround:** write multi-statement abilities as a single line with explicit `;` separators. The 5 customs in `abilities/` follow this pattern after Phase 21.5; new customs should too. `linux_lateral_ssh` and `linux_curl_pipe_sh` get away with multi-line YAML because their effective code is one statement preceded by comments — the comments fuse into one harmless `# ... # ...` line and bash ignores it.
- **The default per-link timeout is 60 seconds.** Loops with `sleep` quickly exceed it. Add `timeout: 120` (or higher) on the executor when authoring an ability that takes more than a few seconds. `linux_file_burst_encrypt` does this — see its YAML for the inline rationale.
- **Cleanup links can leave deadman entries in `UNTRUSTED` (-3) state.** The pre-Phase-21.5 scorer's `ran[aid] = step` later-wins logic let those overwrite the real run's status=0. Fixed in `scorer.py` by picking the entry with the best status priority (0 > 1 > -3 > unknown) per ability.

## auditd-on-Windows constraint (post-Phase-21.5)

Real Caldera-driven coverage validation requires process events from the lab. On Docker Desktop on Windows, `auditd` does not produce events because **the WSL2 kernel was built with `CONFIG_AUDIT` but without `CONFIG_AUDITSYSCALL`** — the syscall-tap subsystem is not in the kernel binary. No `cap_add` or `--privileged` setting on `lab-debian` will fix this; it's a kernel-build-time decision Microsoft made.

Diagnostic: inside `lab-debian`, run `cat /proc/sys/kernel/audit_enabled`. If the file does not exist, you are on a kernel without `CONFIG_AUDITSYSCALL` and no audit rules will ever fire. See `docs/learning-notes.md` "Linux kernel CONFIG_AUDIT vs CONFIG_AUDITSYSCALL" for the full story and the four-option fix tree (synthetic injection / Linux VM / eBPF / accept Linux-only).

## Operator gotchas

- **Stockpile UUIDs change between Caldera versions.** `build_operation_request.py --resolve-uuids` writes a `expectations.resolved.yml` sidecar that the runner reads. Re-run resolution after any `CALDERA_VERSION` bump.
- **Sandcat enrollment is fetch-on-start.** With both `--profile agent` and `--profile caldera` brought up simultaneously, `lab-debian` may try to fetch Sandcat before Caldera's 60s `start_period` elapses. The first `start.sh` run will still print PASS for the four core checks, but re-run after ~90s if `pgrep sandcat` is empty.
- **Cleanup discipline.** Every custom ability YAML carries a `cleanup` block. Without cleanup, `lab-debian` accumulates artifacts (e.g. `.encrypted` files, the `backdoor` user) across runs and the scorecard becomes non-reproducible. If you author a new ability, write its cleanup at the same time.
- **Custom abilities and facts must be re-uploaded after Caldera-container restarts.** Caldera 4.2.0 persists abilities/sources to its on-disk store, but a `down -v` (volume wipe) drops them. Re-running `upload_custom_abilities.py` + `seed_fact_source.py` is cheap and idempotent — make it muscle memory.
- **Facts that don't substitute fail silently per-link.** If a stockpile ability references a trait we haven't declared (e.g. a `#{user.password}` variant), the link errors mid-execution and shows up as `ability-failed` in the scorecard. Read the Caldera operation report (`labs/caldera/.tmp/caldera-op-*.json`) and grep for `Missing fact` to find missing trait names; add them to `facts.yml` and re-run the seeder.
