# Drill — `ransomware_staging`

## Briefing

An attacker on `host-rw.lab.local` enumerates valuable documents
(`find /home -name "*.pdf" -o ...`), archives them for exfiltration
(`tar czf /tmp/loot.tar.gz`), simulates encryption with a 30-file
`.encrypted` creation burst over 60 seconds, and deletes the originals
(`rm -rf`).

**STAGING ONLY.** Per CLAUDE.md §8 (host safety), this scenario emits
*events* describing the behavior — it does NOT actually encrypt files,
does NOT actually rm, does NOT actually write to `/home`. The lab
container and operator's host are untouched. Synthetic events only.

In current platform state, **no incident forms**. Two distinct gaps:

1. The Linux process chain (`bash → find/tar/rm`) doesn't match
   `process_suspicious_child`'s Windows-only branches.
2. **No file-creation-burst detector exists.** The 30-file burst over
   60 seconds is the canonical ransomware signature — it's the kind of
   detector Phase 22 will add.

This drill is the first to surface the **volumetric / time-window**
detector category (vs the categorical / process-chain category).

## Run

```bash
bash labs/drills/run.sh ransomware_staging --speed 0.1
```

## Decision points

1. **Watch the file-creation burst.** Open the events table during the
   drill. You should see ~30 `file.created` events arriving within ~6
   seconds (compressed from 60s by `--speed 0.1`).
   - *Expected:* you can see the burst pattern visually — it's distinct
     from the steady stream of normal file activity.

2. **Reason about volumetric detection.** Sketch the detector logic:
   "if more than N `file.created` events appear for the same `host` within
   T seconds, where the paths share a common prefix or a common suffix
   pattern, fire a `ransomware_burst` detection."
   - *Expected:* you can explain why this detector type needs Redis (for
     a sliding window per host) and how it differs from
     `process_suspicious_child` (which is stateless per event).

3. **Identify the staging archive.** Find the `process.created` event
   with `image=/bin/tar`. The cmdline shows what the attacker bundled
   for exfil.
   - *Expected:* you understand the staging→exfil gap (we never see the
     actual outbound transfer of `/tmp/loot.tar.gz` here — that would be
     a separate `network.connection` event Phase 22+ might add).

4. **Identify the destruction step.** Find the `rm -rf` event. In a real
   ransomware run this would mean the originals are gone — the only path
   to recovery is the encrypted-files-decryption ransom or backups.
   - *Expected:* you can articulate the urgency a real `rm -rf
     /home/<user>/Documents/*` event would carry, and why detection has
     to be fast enough to stop *between* file-creation burst and rm.

## Expected outcome

- Incident kind: none formed (current platform state — recorded gap).
- Drill outcome: you can describe a volumetric file-creation-burst
  detector at code-paragraph detail and contrast it with categorical
  process detectors.

## What this teaches

- **Volumetric detection is its own detector category.** Process-chain
  detectors trigger on a single event's properties; volumetric detectors
  trigger on a *rate* (events per host per time window).
- **Ransomware staging vs detonation matters for response design.** Catch
  it during staging (the 60s window) and you save the data; catch it after
  the rm and you're restoring from backups.
- Practice: recognizing burst patterns in the events table, reasoning
  about windowed/stateful detector designs.
