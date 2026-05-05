# Drill — `crypto_mining_payload`

## Briefing

A compromised server (`host-mine.lab.local`) downloads `xmrig` via curl,
makes it executable, runs it pointed at a mining pool IP (`198.51.100.77`),
and beacons out to the pool.

In current platform state, the live drill **produces no incident**. Two
gaps are at play:

1. The Linux process chain (`bash → curl`, `bash → chmod`, run mining
   binary) doesn't match `process_suspicious_child`'s Windows-only branches.
2. Even if you had pre-seeded the pool IP and `blocked_observable_match`
   fired on the beacon, no correlator currently promotes that detection
   into an incident.

So this drill is a **gap-review drill** — practice reading raw events,
understanding why detection didn't engage, and reasoning about what
Phase 22 needs to add.

## Run

```bash
bash labs/drills/run.sh crypto_mining_payload --speed 0.1
```

## Decision points

1. **Inspect the raw events.** Open the events table in the UI (or
   `GET /v1/events?limit=20`). Find the 5 events on `host-mine.lab.local`:
   the curl download, the file appearance, the chmod, the miner launch,
   the pool beacon.
   - *Expected:* you can identify the choreography by reading event kinds
     + commandlines, even with no incident formed.

2. **Identify which detector *would* have fired.** Check the detections
   table (or `GET /v1/detections?limit=20`). Look for `py.blocked_observable_match`.
   - *Expected:* you find none — because we didn't pre-seed the pool IP.
     The regression test (`pytest tests/integration/test_detection_fixtures.py`)
     does seed it; that's why it passes there.

3. **Reason about the missing incident.** No detection fires, so no
   correlator runs. If you had run this *with* the pool IP pre-seeded,
   `blocked_observable_match` would fire — but no correlator handles it,
   so still no incident.
   - *Expected:* you can explain why the gap is two layers deep (detector
     gap *and* correlator gap), and which Phase 22 piece closes each.

4. **Manually open an incident.** (Optional, if you want to practice
   manual escalation.) Use the UI to create an incident from the events
   you just reviewed.
   - *Expected:* understand the UX for the case where automation didn't
     escalate but you, the analyst, decide to.

## Expected outcome

- Incident kind: none formed (current platform state — recorded gap).
- Drill outcome: you can articulate the two gaps that prevented escalation.

## What this teaches

- **`blocked_observable_match` is recorded but not escalated.** A blocked-IP
  hit produces a Detection row but no Incident — analysts only see it if
  they look at the detections list. Phase 22 needs a correlator.
- **Cryptojacking is invisible without the pool IP being known-bad.** This
  is a real-world gap — most Monero pool IPs are not on public threat lists.
- Practice: reading raw events when no incident formed; reasoning about
  the detection-to-incident pipeline.
