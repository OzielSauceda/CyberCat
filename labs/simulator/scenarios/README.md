# Simulator Scenarios

Each scenario is a Python module under `labs/simulator/scenarios/`. The registry in `__init__.py` maps names to module paths.

## Available scenarios

| Name | Description | Duration (speed=1.0) |
|------|-------------|----------------------|
| `credential_theft_chain` | Brute-force → successful login → encoded PowerShell → C2 beacon. Produces one `identity_compromise` + one `identity_endpoint_chain` incident. | ~4 min |

## How to run

From the repo root (core stack must be running):

```bash
# Quick test (~30s)
python -m labs.simulator --scenario credential_theft_chain --speed 0.1

# Real-time (~4 min)
python -m labs.simulator --scenario credential_theft_chain --speed 1.0

# Skip verification
python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --no-verify
```

Prerequisites: `pip install httpx`

## How to add a new scenario

1. Create `labs/simulator/scenarios/my_scenario.py` with two async functions:
   - `run(client: SimulatorClient, speed: float) -> dict`
   - `verify(client: SimulatorClient) -> bool`
2. Add an entry to `_REGISTRY` in `labs/simulator/scenarios/__init__.py`.
3. Add a row to this README.
4. Add a smoke-test check to the relevant `labs/smoke_test_phaseN.sh`.
