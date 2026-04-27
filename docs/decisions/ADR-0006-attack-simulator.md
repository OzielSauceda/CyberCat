# ADR-0006 — Attack Simulator Architecture

**Status:** Accepted (Phase 10 Sub-track 2)
**Date:** 2026-04-23

## Context

Phase 10 added the `identity_endpoint_chain` correlator — the product's most impressive capability — but it can only be exercised via manual curl commands or the full Wazuh stack. We need a repeatable, automated way to demonstrate the cross-layer narrative end-to-end.

Options considered:

1. **Extend the bash smoke tests** — familiar pattern, zero new dependencies. But bash is brittle for timing-sensitive multi-stage scenarios: sleeping between stages is imprecise, error handling is minimal, and branching logic becomes unreadable.
2. **pytest integration test** — runs in-process via the test client. Fast and deterministic but bypasses the real HTTP layer; cannot serve as a live demo.
3. **Python package firing real HTTP calls** — exercises the same API surface an operator uses, works against any running backend (local or remote), readable timing model, easy to extend.

## Decision

A **Python package at `labs/simulator/`** that fires events via `POST /v1/events/raw` using `httpx.AsyncClient`. No backend imports — the simulator is a peer of the smoke tests.

Key design choices:

- **HTTP over in-process:** the simulator exercises the real API surface (serialization, auth, routing) rather than short-circuiting through the test client. This means a passing simulator run is genuine evidence the full stack works.
- **Python over bash:** `asyncio.sleep` gives sub-second timing control; structured return values from `run()` make `verify()` precise; the module registry makes adding scenarios a one-file operation.
- **`--speed` flag (0 < speed ≤ 1.0):** multiplies all inter-stage delays. `speed=0.1` compresses the ~250s scenario to ~25s for CI and demos. `speed=1.0` plays at real time for recording.
- **`--verify` (default on):** after scenario completes, asserts the expected incident tree via `GET /v1/incidents`. Exits non-zero on failure — safe to use as a smoke-test gate.
- **Dedup keys:** every event payload includes a stable `dedupe_key` so re-running the scenario within the hour is idempotent. Second run produces no new incidents; `--verify` still passes because the incidents from the first run are still open.
- **Module registry:** `scenarios/__init__.py` maps names to module paths. New scenarios are one file + one registry entry.

## Consequences

- Requires `httpx` installed in the local Python environment (`pip install httpx`). Not a backend dependency.
- Simulator fixtures must stay shape-compatible with the backend's `RawEventIn` schema. Any change to required normalized fields must be reflected in `event_templates.py`.
- `smoke_test_phase10.sh` invokes the simulator as a subprocess and is the permanent regression gate for the demo story. Future phases must keep it green.
- The simulator does not test Wazuh-ingested events — it tests the custom layer (normalization → detection → correlation). Wazuh end-to-end remains covered by `smoke_test_phase8.sh`.
