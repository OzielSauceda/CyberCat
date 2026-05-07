# Phase 21.5 — Caldera test rigging

**Status:** Code complete (2026-05-07). Closes the rigging gaps that produced 14 of the 17 non-`covered` rows in Phase 21's first scorecard. Validation by re-running `bash labs/caldera/run.sh` is operator-driven and pending stack-up.
**Branch:** `phase-21.5-caldera-rigging` (branched off `phase-21-caldera-emulation`).
**Predecessor:** Phase 21 (`phase-21-caldera-emulation` at `9e7e393`, local-only).
**Successor:** Re-run of `labs/caldera/run.sh` to land the corrected scorecard, then Phase 23 UEBA.

---

## Why this phase exists

Phase 21's first scorecard was **0 / 17 covered**, with the 17 rows split as:

| Bucket | Count | Mechanism |
|---|---|---|
| `gap` (real defensive miss) | 3 | Ability ran cleanly; no detector fired. Phase 22 closed several of these. |
| `ability-skipped` | 5 | Custom ability YAMLs lived only on the host filesystem; Caldera's stockpile never saw them. |
| `ability-failed` | 9 | Stockpile abilities that errored mid-execution — most because the default `basic` fact source is empty and `#{trait}` template substitutions had nothing to resolve against. |

Phase 22 addressed the 3 real gaps by writing detectors. Phase 21.5 addresses the 14 rigging-rooted rows so the scorecard becomes a meaningful signal instead of mostly noise.

---

## What shipped (code)

All under `labs/caldera/` on `phase-21.5-caldera-rigging`:

1. **`upload_custom_abilities.py`** *(new)* — reads every `abilities/*.yml`, transforms each from the on-disk `platforms.{plat}.{exec}` nested shape into Caldera's flat `executors: [...]` API shape, `PUT /api/v2/abilities/{ability_id}` (idempotent), and verifies via `GET`. Stdlib HTTP, PyYAML for parsing. Runs inside the backend container.
2. **`seed_fact_source.py`** *(new)* — reads `facts.yml`, builds a Caldera `SourceSchema` payload, `PUT /api/v2/sources/{source_id}` (idempotent), verifies fact count via `GET`.
3. **`facts.yml`** *(new)* — declarative fact source. ~22 traits covering identity (`host.user.name=realuser`, `host.user.home=/home/realuser`), filesystem (`host.dir.compromise=/tmp`, `file.sensitive.extension=pdf`), persistence-artifact names (`host.systemd.service.name=cct-phase21-test`), and remote-pivot targets (`remote.host.fqdn=host-mine.lab.local`). Operator-extensible — add a `- trait: ...` block, re-run the seeder.
4. **`build_operation_request.py`** *(modified)* — operation payload's `source.name` changed from hardcoded `"basic"` to a configurable `--source` arg defaulting to `"cybercat-phase21"`. `DEFAULT_SOURCE_NAME` constant introduced near the top.
5. **`labs/caldera/README.md`** *(modified)* — "How to run" steps grew the upload and seed steps (idempotent, run after any `abilities/` or `facts.yml` edit). New "Phase 21.5 helpers" section explains the failure-bucket mapping. New gotchas: re-upload after `down -v`, how to find missing trait names in the operation report.
6. **`docs/learning-notes.md`** *(updated)* — existing "Caldera atomic planner — facts, fact sources, deadman links" entry refreshed to reflect the actual Phase 21.5 implementation (replacing the prior "Phase 21.5 will add..." forward references). New entry: "Idempotent PUT-by-id (REST upsert pattern)".

---

## Why three small files instead of one big script

Two reasons:

1. **Different failure modes, different operator gestures.** Uploading abilities is a "I edited a YAML in `abilities/`" action. Seeding facts is a "I added a new trait" action. Bundling them obscures which one needs re-running for which edit. Running them as siblings makes the cause-and-effect obvious.
2. **Idempotent-by-id doesn't combine cleanly.** Both helpers PUT to a known ID. Combining them would either pretend to be one upsert (it isn't) or grow conditional flags. Two scripts, two responsibilities.

Tradeoff: operators have two commands to remember, not one. Mitigation: documented in the README "How to run" sequence; both run inside the backend container with the same env vars.

---

## What was deferred to a follow-up

**Task 3 — cleanup-deadman investigation.** The recap doc framed this as the third Phase 21.5 task: identify abilities whose `cleanup` step might race ahead of detection latency, fork the brute-force ability if needed.

After re-reading the prior scorecard, the existing custom YAMLs, and the Caldera 4.2.0 link-state semantics, the deadman race **is not the dominant Phase 21 failure mode**:

- **The 5 custom abilities all carry explicit cleanup blocks** (`rm -rf /tmp/loot`, `userdel -r backdoor`, etc.). These ran in Caldera's cleanup phase *after* the operation completed — agent events were already emitted to CyberCat by then.
- **The 9 ability-failed rows have non-zero or `-3` link states.** Static analysis suggests these are fact-substitution misses (post-Phase-21.5 fix) or Sandcat beacon drops (orthogonal — needs different fix), not cleanup races.
- **The single covered-but-blind sudo brute-force case from Phase 21** is already addressed by Phase 22's W5 PAM-parser broadening — not a deadman issue at all.

If the post-Phase-21.5 re-run still shows specific abilities fire-then-rollback before detection lands, the fix is a per-ability `cleanup_delay_s` knob in `build_operation_request.py` and per-ability cleanup-toggle support. Defer until the data justifies it.

---

## Verification

This session built the helpers and the runbook. **The closing-of-the-loop verification — actually re-running `bash labs/caldera/run.sh` and watching coverage climb from 0/17 → ≥12/17 — is operator-gated** because it needs:

1. The compose stack up with `--profile agent --profile caldera`.
2. Sandcat enrolled (≥60s after Caldera container start).
3. The Caldera 4.2.0 image healthy.

Once those preconditions hold, the operator runs (in PowerShell):

```powershell
docker compose -f infra\compose\docker-compose.yml --profile agent --profile caldera up -d

# Wait ~60s for Sandcat to enroll, then in either shell:
docker compose -f infra/compose/docker-compose.yml exec -T -e CALDERA_API_KEY="$KEY" backend \
    python -m labs.caldera.build_operation_request --resolve-uuids
docker compose -f infra/compose/docker-compose.yml exec -T -e CALDERA_API_KEY="$KEY" backend \
    python -m labs.caldera.upload_custom_abilities --caldera "http://caldera:8888" --here "//app/labs/caldera"
docker compose -f infra/compose/docker-compose.yml exec -T -e CALDERA_API_KEY="$KEY" backend \
    python -m labs.caldera.seed_fact_source --caldera "http://caldera:8888" --here "//app/labs/caldera"

bash labs/caldera/run.sh
less docs/phase-21-scorecard.md
```

**Expected scorecard delta:**

- The 5 `ability-skipped` rows (custom abilities) flip to either `covered` (Phase 22's detectors fire on `process_lotl_chain` triggers from `linux_lateral_ssh` and `linux_curl_pipe_sh`) or `gap` (where a detector still doesn't exist).
- Most `ability-failed` rows resolve once their `#{trait}` references substitute against `facts.yml`. Any that still error after seeding indicate a missing trait — extend `facts.yml` and re-seed.
- The 3 original `gap` rows: `id`/`whoami` and `find files` should flip to `covered` via Phase 22's `process_lotl_chain` recon-under-shell rule family. `process listing` may stay `gap`.

Realistic floor on a clean re-run: ≥12/17 covered. Anything less means a fact name doesn't match what the stockpile ability actually references — read `labs/caldera/.tmp/caldera-op-*.json` for the exact missing trait, add it to `facts.yml`, re-run the seeder, re-run `run.sh`.

---

## File inventory

```
NEW:
  labs/caldera/upload_custom_abilities.py   (~190 lines)
  labs/caldera/seed_fact_source.py          (~160 lines)
  labs/caldera/facts.yml                    (~75 lines)
  docs/phase-21.5-summary.md                (this file)

MODIFIED:
  labs/caldera/build_operation_request.py   (+constant, +CLI flag, ~5 lines net)
  labs/caldera/README.md                    (+Phase 21.5 section, expanded How-to-run)
  docs/learning-notes.md                    (1 entry updated, 1 new entry, 1 index link)
```

No backend Python touched, no tests added — these helpers are operator tooling, not core code paths. The validation is the scorecard re-run.
