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

### Comparison vs Phase 21 baseline (three validation cycles)

| Metric | Phase 21 (`326fde6c`) | 21.5 first re-run (`6994c565`) | 21.5 second re-run (`1fe6440a`) | Expected after timeout fix |
|---|---|---|---|---|
| covered | 0 | 0 | 0 | 0 |
| **gaps** (ran cleanly, no detector fired) | **3** | 10 | **11** | 12 |
| false-negatives | 0 | 1 | 1 | 1 |
| **ability errors** (rigging blocked execution) | **14** | 6 | **5** | 4 |

The 5 `ability-skipped` rows from the first run all flipped to `gap` or `false-negative`. Of the 9 original `ability-failed` rows, only 4 will remain after the timeout fix lands — and those 4 are stockpile abilities with hardcoded literals that need stockpile forks, not Phase 21.5 territory. The Phase 21.5 deliverable — *"rigging is no longer the bottleneck"* — is empirically met. **9 of the original 14 ability errors closed.**

**Three iterative passes during the validation:**

1. **First re-run (operation `6994c565`)** — uncovered the `scorer.py` deadman-overwrites bug (deadman cleanup links left in UNTRUSTED state -3 were overwriting the real run's status=0). Fixed by giving the scorer a status-priority order (0 > 1 > -3 > unknown) and skipping cleanup steps that never executed.
2. **Triage of remaining 6 errors** — re-reading the saved report's `plaintext_command` showed Caldera 4.2.0 strips literal newlines from multi-line block scalars before dispatch. This made `linux_file_burst_encrypt` outright fail (status=1) and silently produced false-positive successes for `linux_creds_aws_read` (heredoc collapsed) and `linux_useradd_persist` (if-block collapsed). Rewrote all three as single-line `;`-separated bash. Verified at the lab-debian execution layer.
3. **Second re-run (operation `1fe6440a`)** — confirmed the rewrite. `linux_creds_aws_read`, `linux_useradd_persist`, and the two already-working customs all status=0. `linux_file_burst_encrypt` newly returned exit 124 (Caldera 60s link timeout), surfacing one more issue. Final fix: drop the loop's `sleep 2` to `sleep 1` and add `timeout: 120` on the executor. Re-uploaded.

### Why coverage stayed at 0/17 (the unrelated constraint)

After the scorer ran, direct Postgres query confirmed: **only 3 events arrived in CyberCat during the 14-minute Caldera operation**, all `network.connection`. Zero `process.created`, zero `auth.failed`, zero `file.created`. The agent log showed the auditd tail was alive (`auditd source started, tailing /lab/var/log/audit/audit.log`), but `audit.log` itself was 3 days old and contained synthetic `cmd.exe` test-fixture entries — **`auditd` is not running inside `lab-debian`**.

This is the pre-existing Phase 16.9 constraint: *"Docker Desktop on Windows can't run real auditd; smoke uses synthetic injection."* Caldera ran the abilities, Sandcat returned successful exit codes, but the kernel audit subsystem the agent depends on is dormant in this environment. So even with perfect rigging and the full Phase 22 detector stack, coverage can't climb until the auditd pipeline is producing events.

This is **not Phase 21.5 territory**. Lifting it is a separate phase (Phase 21.6 candidate):

- **Option A (cheap):** Inject synthetic audit records during Caldera ops. Add a sidecar that watches Caldera's `chain[].plaintext_command` and writes auditd-shaped lines to `audit.log` for each. Preserves the Windows-friendly stack but only proves the *parser → detector* path, not the kernel → parser path.
- **Option B (TESTED — does not work):** Add `cap_add: [AUDIT_CONTROL, AUDIT_READ]` to `lab-debian`. Tested at the end of this session. The container's `CapEff` mask correctly shows both bits set after the change, BUT `auditctl -s` (read-only status) and `auditctl -a` (add rule) both still return `Operation not permitted`. Direct read of `/proc/sys/kernel/audit_enabled` shows the file does not exist — that sysfs entry is created only when the kernel is built with `CONFIG_AUDITSYSCALL=y`. **The WSL2 kernel has `CONFIG_AUDIT` (base framework) but NOT `CONFIG_AUDITSYSCALL` (the syscall-tap subsystem).** `DAEMON_START` log entries succeed because the base framework is alive, but no caps or `--privileged` setting will produce execve events because the tracing code isn't in the kernel binary at all. Reverted the cap_add change.
- **Option C (correct, more setup):** Run lab-debian on a real Linux host (Multipass VM on Windows, ~15 min one-time setup; or a dedicated Debian server). Real auditd, real execve events. The `cct-agent` already knows how to tail `/var/log/audit/audit.log` — point it at the VM's log and detection works.
- **Option D (eBPF fallback):** Skip auditd entirely. eBPF programs can attach to syscall tracepoints from inside a container without `CONFIG_AUDITSYSCALL`. Tools like `bpftrace` or a small custom `cilium/ebpf` Go program can produce execve events that the agent transforms into the canonical event shape. Larger lift than Option A; smaller than Option C; more portable than both.
- **Option E (deferred):** Accept Windows as a development environment, validate on Linux when needed.

**Updated recommendation:** Option A (synthetic injection) is the cheapest correct path *if* you accept that it only validates the parser-→-detector half of the pipeline. Option D (eBPF) is the most architecturally satisfying answer and forward-compatible — eBPF is where the industry is heading anyway (Falco, Tetragon, all use it). Option C is the rigorous baseline whenever you have a Linux box around. The decision is for the operator, not Phase 21.5.

### Bug found and fixed during validation: scorer "deadman overwrites real status"

The first-pass re-run reported 0 covered AND many `ability-failed` rows even though Caldera's chain endpoint clearly showed 22 status=0 successes. Investigation: **`scorer.py:75` had `ran[aid] = step` (later-wins).** Caldera fires deadman cleanup links *after* the operation completes; if the cleanup is left in `UNTRUSTED` state (-3 — common when the agent has already ended its beacon loop), it overwrites the real run's success status. Fix: `_record(aid, step)` now picks the entry with the **best status priority** (0 > 1 > -3 > unknown) and skips cleanup steps that never executed (`run is None`). After the fix, the same saved report scored correctly.

This bug existed in Phase 21's first scorer too — the headline 0/17 from Phase 21 was probably understating the rigging-rooted improvement that *would have* shown up there. We caught it now because Phase 21.5's rigging exposed enough successful executions to make the bug observable.

### What still errors (6 abilities) — second-pass triage

Re-reading the saved `caldera-op-6994c565-*.json`'s `plaintext_command` for each `status=1` row revealed the failures are **not** mostly fact misses (the recap doc's framing was an overgeneralization). Two distinct root causes:

**Caldera 4.2.0 strips literal newlines from `plaintext_command` before dispatch.** Multi-line YAML block scalars (`|`) become single lines without separators — `mkdir -p /tmp/loot\nfor i in...` becomes `mkdir -p /tmp/lootfor` which bash parses as `mkdir -p /tmp/lootfor` (a directory named `lootfor`) followed by an unparseable bare `for` clause → status=1. This affected 1 of our customs outright (`linux_file_burst_encrypt`) and silently produced *false-positive successes* for two others (`linux_creds_aws_read` heredoc and `linux_useradd_persist` if-block — both reported status=0 but executed mangled commands). Fix: rewrote each command as a single-line `;`-separated bash with explicit comments at the YAML level explaining why. Verified by direct execution inside `lab-debian` — the rewritten forms run cleanly. Re-uploaded via the helper.

**The 5 remaining stockpile failures are hardcoded literal references, not fact misses:**

| Stockpile ability | Failing command | Root cause | Fix path |
|---|---|---|---|
| Find System Network Connections | `netstat -anto` | `-o` is a Windows flag; not valid on Linux netstat | Stockpile fork — replace with `ss -tunpl` |
| Change User Password via passwd | `passwd ARTUser` | Literal username `ARTUser`, not `#{host.user.name}` | Stockpile fork — `#{host.user.name}` substitution |
| Data Compressed - tar | `tar -cvzf $HOME/data.tar.gz $HOME/$USERNAME` | `$USERNAME` shell var is unset on Linux | Either set USERNAME via env or stockpile fork |
| scp remote file copy | `scp /tmp/adversary-scp victim@victim-host:...` | Literal `victim@victim-host`, target doesn't exist | Stockpile fork or pre-create SSH config |
| Create Systemd Service | `echo "[Unit]" > /etc/systemd/system/...` | Multi-statement command newline-collapsed by Caldera | Same newline-strip bug as our customs (stockpile YAML uses `|` block scalars) |

`facts.yml` doesn't help here — the abilities don't reference `#{trait}` placeholders. Three of these need stockpile-fork work; one (Create Systemd Service) is the same Caldera 4.2.0 newline bug affecting any multi-line command. None of these are Phase 21.5 territory; they're material for Phase 21.6+ when somebody decides to broaden coverage. The pattern documented in the README ("read the failing command, find the missing trait, extend `facts.yml`") still applies *if* the failure is a real fact miss — it just turned out most weren't.

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
