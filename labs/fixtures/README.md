# Detection-as-code fixtures

Per-rule canonical-event fixtures used as a regression suite for the four
Python detectors. Each `.jsonl` is a sequence of events that should produce a
specific, named detection outcome when replayed into a clean stack.

## Layout

```
labs/fixtures/
├── README.md              ← this file
├── manifest.yaml          ← which detectors must / must-not fire per fixture
├── replay.py              ← CLI replay harness
├── auth/                  ← auth.failed / auth.succeeded patterns
├── process/               ← process.created patterns
└── network/               ← network.connection patterns
```

## Fixture line format

Each line is a JSON object — the same shape POSTed to `/v1/events/raw` —
plus one extra synthetic field:

| Field             | Meaning                                                              |
|-------------------|----------------------------------------------------------------------|
| `_t_offset_sec`   | Seconds before "now" the event happened. Replayer computes           |
|                   | `occurred_at = now() - _t_offset_sec` and strips the field.          |
| `source`          | `direct` or `seeder` (kept simple — agent path emits `direct`).      |
| `kind`            | One of the canonical event kinds the normalizer accepts.             |
| `raw`             | Raw payload (not interpreted, just persisted).                       |
| `normalized`      | Per-kind required fields — see `backend/app/ingest/normalizer.py`.   |
| `dedupe_key`      | Stable key for idempotent replay.                                    |

The replayer rewrites every `occurred_at` so all events fall within the
Phase 19 30-day past-bound, regardless of when the fixture was authored.

## Manifest format

`manifest.yaml` is a list of entries. Each entry binds a fixture path to:

- `must_fire`: detector rule IDs that **must** appear in the resulting
  detection set (any subset of the four IDs in `app/detection/rules/`).
- `must_not_fire`: rule IDs that **must not** appear (false-positive
  guard rail).
- `setup`: optional seed actions run **before** replay. Currently supports
  `block_observable: [{value, kind}, ...]` for the blocked-IP path.

## Running locally

Replay a single fixture:

```bash
python labs/fixtures/replay.py auth/ssh_brute_force_burst.jsonl --base-url http://localhost:8000
```

Run the full manifest as a regression test:

```bash
docker compose -f infra/compose/docker-compose.yml exec backend \
  python -m pytest tests/integration/test_detection_fixtures.py -v
```

## Adding a new detector

1. Add a positive fixture under the right subdir.
2. Add (or augment) a benign baseline fixture that proves it doesn't false-positive.
3. Add an entry to `manifest.yaml` referencing both.
4. Run `pytest tests/integration/test_detection_fixtures.py`.

The `test_detection_fixtures` test fails if any detector ID is referenced only
in `must_not_fire` across the manifest — every rule must have at least one
positive fixture.
