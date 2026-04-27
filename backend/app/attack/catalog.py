from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

_CATALOG_PATH = Path(__file__).parent / "catalog.json"


class AttackEntry(BaseModel):
    id: str
    name: str
    kind: Literal["tactic", "technique", "subtechnique"]
    parent: str | None
    url: str


class AttackCatalog(BaseModel):
    version: str
    entries: list[AttackEntry]


def _load() -> AttackCatalog:
    data = json.loads(_CATALOG_PATH.read_text())
    return AttackCatalog.model_validate(data)


_catalog: AttackCatalog = _load()
_index: dict[str, AttackEntry] = {e.id: e for e in _catalog.entries}


def get_catalog() -> AttackCatalog:
    return _catalog


def get_entry(attack_id: str) -> AttackEntry | None:
    return _index.get(attack_id)
