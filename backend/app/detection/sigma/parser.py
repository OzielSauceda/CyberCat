from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, field_validator


class SigmaLogSource(BaseModel):
    product: str | None = None
    category: str | None = None
    service: str | None = None


class SigmaRuleSpec(BaseModel):
    id: str | None = None
    title: str
    description: str | None = None
    logsource: SigmaLogSource
    detection: dict[str, Any]
    level: str = "medium"
    tags: list[str] = []

    @field_validator("level")
    @classmethod
    def _normalise_level(cls, v: str) -> str:
        v = v.lower()
        if v not in {"low", "medium", "high", "critical", "informational"}:
            return "medium"
        return v


def parse_yaml(raw: str) -> SigmaRuleSpec:
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("Sigma rule YAML must be a mapping")
    return SigmaRuleSpec.model_validate(data)
