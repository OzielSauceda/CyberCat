"""Scenario registry — maps scenario names to their runner modules."""
from __future__ import annotations

import importlib
import types

_REGISTRY: dict[str, str] = {
    "credential_theft_chain": "labs.simulator.scenarios.credential_theft_chain",
    "lateral_movement_chain": "labs.simulator.scenarios.lateral_movement_chain",
    "crypto_mining_payload": "labs.simulator.scenarios.crypto_mining_payload",
    "webshell_drop": "labs.simulator.scenarios.webshell_drop",
    "ransomware_staging": "labs.simulator.scenarios.ransomware_staging",
}


def get_scenario(name: str) -> types.ModuleType | None:
    module_path = _REGISTRY.get(name)
    if module_path is None:
        return None
    return importlib.import_module(module_path)


def list_scenarios() -> list[str]:
    return list(_REGISTRY)
