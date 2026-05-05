# Phase 21 — Caldera adversary emulation + coverage scorecard

**Status:** Code complete; first scorecard run pending.
**Branch:** `phase-21-caldera-emulation`
**Predecessor:** Phase 20 (commit `11778e3`, `v1.0`)
**Successor:** Phase 22 (LotL behavior-chain detection — see `project_phase22_23_thesis` memory)

---

## What shipped (code)

Five commits on the `phase-21-caldera-emulation` branch:

1. **`phase-21 A: caldera service + sandcat in lab-debian`** — Caldera
   5.0.0 as a `--profile caldera`-gated compose service (default OFF,
   bound to 127.0.0.1:8888), Sandcat fetch-on-start in
   `lab-debian/entrypoint.sh`, `start.sh` provisions
   `CALDERA_API_KEY` on first run.
2. **`phase-21 B1: ability profile + expectations`** — 25-ability
   curated adversary profile in `labs/caldera/profile.yml`,
   ATT&CK-mapped expectations registry in
   `labs/caldera/expectations.yml`, five custom abilities in
   `labs/caldera/abilities/` (T1021.004, T1105, T1486, T1552.001,
   T1098) where Stockpile coverage was thin.
3. **`phase-21 B2: run.sh + scorer.py + build_operation_request.py`** —
   pure-stdlib payload helper, six-status enum scorer with symmetric
   ATT&CK-attribution rule (verified at planning time against five
   synthetic cases), orchestrator that drives a Caldera operation,
   captures the run window, queries
   `GET /v1/detections?since=<window>`, and writes
   `docs/phase-21-scorecard.{md,json}`.
4. **`phase-21 D1: smoke_test_phase21.sh`** — five assertions: caldera
   healthy, sandcat running, agent enrolled, single-ability T1110.001
   run fires `py.auth.failed_burst`, scorecard files generated.
5. **`phase-21 D2: ADR-0016 + docs + summary`** — this file plus
   ADR-0016, runbook section, four learning-notes entries, and the
   PROJECT_STATE pickup-rewrite.

ADR-0016 captures the seven decisions: Caldera as engine, profile-gate
+ 127.0.0.1 bind, `--insecure` acceptable in our deployment shape,
Sandcat fetch-on-start, curated 25-ability set, scorecard-as-files-only
v1, conservative ATT&CK attribution rule.

## What's pending (the deliverable itself)

The first scorecard run. Operator runs:

```bash
bash start.sh --profile agent --profile caldera
sleep 60                                                  # let Caldera start_period elapse
python labs/caldera/build_operation_request.py --resolve-uuids
bash labs/caldera/run.sh
less docs/phase-21-scorecard.md
bash labs/smoke_test_phase21.sh
```

The headline number from that first run gets pasted below this section
along with the ordered Phase 22 punch list. Until then, this file is a
status report, not the deliverable.

## First-run scorecard (paste below after `bash labs/caldera/run.sh`)

> _To be filled in after the first successful Caldera operation. The
> projected first-run number is 2-3 covered / 25 (~8-12%). If much
> higher or much lower, investigate before merging — the number is the
> deliverable._

| Headline | Value |
|---|---|
| covered | _TBD_ |
| gap | _TBD_ |
| false-negative | _TBD_ |
| unexpected-hit | _TBD_ |
| ability-failed | _TBD_ |
| ability-skipped | _TBD_ |
| **total** | **25** |

## Phase 22 punch list (ordered by evidence)

> _To be ordered after the first run. Candidates known pre-run, in no
> particular order:_
>
> 1. **Linux process-chain (LotL) detector** —
>    `backend/app/detection/rules/process_lotl_chain.py` (new module),
>    Phase 20 Gap 1, A1+A2+A3+A4+A5 evidence. Behavior-chain rules:
>    `(parent, child, cmdline-fragment, time-window)` triples.
> 2. **`network_indicator_compromise` correlator** —
>    `backend/app/correlation/rules/network_indicator_compromise.py`
>    (new), Phase 20 Gap 2, A2+A5 evidence. Promotes
>    `py.blocked_observable_match` on `network.connection` events to
>    incidents, dedupes on `(host, dst_ip, hour-bucket)`.
> 3. **`auth_baseline_unknown_source_success` detector** —
>    `backend/app/detection/rules/auth_baseline_unknown_source_success.py`
>    (new), Phase 20 Gap 3, A5 evidence. Per-user 90-day source-IP
>    baseline; cold-start handling for new users.
> 4. **`file_burst_detector`** —
>    `backend/app/detection/rules/file_burst_detector.py` (new),
>    Phase 20 Gap 4, A4 evidence. Redis sliding window per host,
>    suffix or shared-parent-dir pattern.
>
> The first scorecard may add fifth+ candidates (e.g. account-
> manipulation, indicator-removal, persistence write detectors) that
> hit `gap` rows in the table above.

## Verification at close

The full operator checklist from `docs/phase-21-plan.md` ends Phase 21:

1. Bring-up green
2. Caldera health endpoint OK
3. Sandcat process running
4. `bash labs/caldera/run.sh` produces both scorecard files
5. `less docs/phase-21-scorecard.md` shows a coherent table
6. `bash labs/smoke_test_phase21.sh` → `passed: 5  failed: 0`
7. `ruff check app/` → no errors (Phase 20 CI-red lesson)
8. `pytest -q` inside the backend container → all green

When all eight pass, merge `--no-ff` into `main` with message
`Phase 21 — Caldera adversary emulation + coverage scorecard`. Optional
`v1.1` tag if the scorecard reveals enough to be a real platform-state
milestone.

## Operator-tooling findings (non-blocking, surface for backlog)

- _To be added after the first run reveals what additional admin/ops
  affordances would have made the run smoother._
