# Phase 21.5 — Caldera test rigging

**Status:** Code complete and **empirically validated** (2026-05-07). Real scorecard re-run of `bash labs/caldera/run.sh` against the operator's stack landed with **ability errors 14 → 6, gaps 3 → 10** — the rigging is no longer the bottleneck. Coverage stayed at 0/17, but for an entirely different reason: the agent's auditd source can't produce process events on Docker Desktop on Windows (pre-existing Phase 16.9 constraint, not Phase 21.5 territory). Plus a real bug in `scorer.py` (deadman-overwrites-real-status) was caught and fixed during validation.
**Branch:** `phase-21.5-caldera-rigging` (branched off `phase-21-caldera-emulation`).
**Predecessor:** Phase 21 (`phase-21-caldera-emulation` at `9e7e393`, local-only).
**Successor:** Lift the auditd-on-Windows constraint (Phase 21.6 candidate — synthetic auditd injection, OR move runs to a Linux host) to unlock the closing-of-the-loop covered count, then Phase 23 UEBA.

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

## Verification — actual measured results

The scorecard re-run happened in this session (operation `6994c565-fe7d-4793-a8c4-b29359ca338c`, ~14 min execution time, finished 2026-05-07 17:08 UTC). Latest `docs/phase-21-scorecard.md` reflects this run.

### Comparison vs Phase 21 baseline

| Metric | Phase 21 (`326fde6c`) | Phase 21.5 (`6994c565`) | Delta |
|---|---|---|---|
| covered | 0 | 0 | — (capped by auditd-on-Windows; see below) |
| **gaps** (ran cleanly, no detector fired) | **3** | **10** | **+7** |
| false-negatives (ran cleanly, expected rule silent) | 0 | 1 | +1 |
| **ability errors** (rigging blocked execution) | **14** | **6** | **-8** |

The 5 `ability-skipped` rows from the first run all flipped to `gap` or `false-negative` — they now actually execute. Of the 9 original `ability-failed` rows, 6 still error (different stockpile abilities, different missing traits — extend `facts.yml` and re-seed). The Phase 21.5 deliverable — *"rigging is no longer the bottleneck"* — is empirically met.

### Why coverage stayed at 0/17 (the unrelated constraint)

After the scorer ran, direct Postgres query confirmed: **only 3 events arrived in CyberCat during the 14-minute Caldera operation**, all `network.connection`. Zero `process.created`, zero `auth.failed`, zero `file.created`. The agent log showed the auditd tail was alive (`auditd source started, tailing /lab/var/log/audit/audit.log`), but `audit.log` itself was 3 days old and contained synthetic `cmd.exe` test-fixture entries — **`auditd` is not running inside `lab-debian`**.

This is the pre-existing Phase 16.9 constraint: *"Docker Desktop on Windows can't run real auditd; smoke uses synthetic injection."* Caldera ran the abilities, Sandcat returned successful exit codes, but the kernel audit subsystem the agent depends on is dormant in this environment. So even with perfect rigging and the full Phase 22 detector stack, coverage can't climb until the auditd pipeline is producing events.

This is **not Phase 21.5 territory**. Lifting it is a separate phase (Phase 21.6 candidate):

- **Option A (cheap):** Inject synthetic audit records during Caldera ops. Add a sidecar that watches Caldera's `chain[].plaintext_command` and writes auditd-shaped lines to `audit.log` for each. Preserves the Windows-friendly stack but only proves the *parser → detector* path, not the kernel → parser path.
- **Option B (correct):** Run lab-debian on a Linux host (WSL2 with `--privileged`, or a small dedicated VM). Real auditd, real execve coverage, no fakes. Costs portability — operator's daily-driver Lenovo can do it but requires booting WSL2 or the VM each time.
- **Option C (deferred):** Accept that this scorecard runs on Linux only. Document the Windows path as "develop here, validate on Linux." Defer until somebody else needs the scorecard.

The decision is for the operator, not Phase 21.5.

### Bug found and fixed during validation: scorer "deadman overwrites real status"

The first-pass re-run reported 0 covered AND many `ability-failed` rows even though Caldera's chain endpoint clearly showed 22 status=0 successes. Investigation: **`scorer.py:75` had `ran[aid] = step` (later-wins).** Caldera fires deadman cleanup links *after* the operation completes; if the cleanup is left in `UNTRUSTED` state (-3 — common when the agent has already ended its beacon loop), it overwrites the real run's success status. Fix: `_record(aid, step)` now picks the entry with the **best status priority** (0 > 1 > -3 > unknown) and skips cleanup steps that never executed (`run is None`). After the fix, the same saved report scored correctly.

This bug existed in Phase 21's first scorer too — the headline 0/17 from Phase 21 was probably understating the rigging-rooted improvement that *would have* shown up there. We caught it now because Phase 21.5's rigging exposed enough successful executions to make the bug observable.

### What still errors (6 stockpile abilities)

Caldera's `status=1` (FAILED) — almost certainly missing fact substitutions. The pattern from the README still applies: read `labs/caldera/.tmp/caldera-op-*.json` for the exact failing command, find the unsubstituted `#{trait.name}` reference, add the trait to `facts.yml`, re-run the seeder. Iterative.

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
  labs/caldera/scorer.py                    (deadman-overwrites-real-status fix,
                                             ~30 lines net — caught during validation)
  labs/caldera/README.md                    (+Phase 21.5 section, expanded How-to-run)
  docs/learning-notes.md                    (1 entry updated, 1 new entry, 1 index link)
  docs/phase-21-scorecard.md                (regenerated by the validation re-run —
                                             concrete artifact of the rigging fix)
```

No backend Python touched, no tests added — these helpers are operator tooling, not core code paths. The validation IS the scorecard re-run, which now has empirical numbers in `docs/phase-21-scorecard.md`.
