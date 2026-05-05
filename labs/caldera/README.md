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

# 3. Run the full curated profile and produce the scorecard.
bash labs/caldera/run.sh

# 4. Read the result.
less docs/phase-21-scorecard.md
```

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

## Operator gotchas

- **Stockpile UUIDs change between Caldera versions.** `build_operation_request.py --resolve-uuids` writes a `expectations.resolved.yml` sidecar that the runner reads. Re-run resolution after any `CALDERA_VERSION` bump.
- **Sandcat enrollment is fetch-on-start.** With both `--profile agent` and `--profile caldera` brought up simultaneously, `lab-debian` may try to fetch Sandcat before Caldera's 60s `start_period` elapses. The first `start.sh` run will still print PASS for the four core checks, but re-run after ~90s if `pgrep sandcat` is empty.
- **Cleanup discipline.** Every custom ability YAML carries a `cleanup` block. Without cleanup, `lab-debian` accumulates artifacts (e.g. `.encrypted` files, the `backdoor` user) across runs and the scorecard becomes non-reproducible. If you author a new ability, write its cleanup at the same time.
