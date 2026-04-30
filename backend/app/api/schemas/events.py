from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Phase 19: bounds applied at the API boundary.
# Values are intentionally generous (real lab events are well under these)
# but tight enough to prevent accidental or malicious unbounded payloads.
_RAW_MAX_BYTES = 64 * 1024
_NORMALIZED_MAX_BYTES = 16 * 1024
_TIMESTAMP_PAST_LIMIT = timedelta(days=30)
_TIMESTAMP_FUTURE_LIMIT = timedelta(minutes=5)
# Printable ASCII excluding whitespace, NUL, and control characters; 1–128 chars.
# Covers Wazuh _id values, agent-generated structured keys, and test fixtures
# (which use @-separated values), while rejecting whitespace and binary garbage.
_DEDUPE_KEY_RE = re.compile(r"^[\x21-\x7e]{1,128}$")


class RawEventIn(BaseModel):
    source: Literal["direct", "seeder"]
    kind: str
    occurred_at: datetime
    raw: dict[str, Any]
    normalized: dict[str, Any]
    dedupe_key: str | None = None

    @field_validator("raw")
    @classmethod
    def _validate_raw_size(cls, v: dict) -> dict:
        size = len(json.dumps(v, default=str))
        if size > _RAW_MAX_BYTES:
            raise ValueError(
                f"raw payload exceeds {_RAW_MAX_BYTES} bytes (got {size})"
            )
        return v

    @field_validator("normalized")
    @classmethod
    def _validate_normalized_size(cls, v: dict) -> dict:
        size = len(json.dumps(v, default=str))
        if size > _NORMALIZED_MAX_BYTES:
            raise ValueError(
                f"normalized payload exceeds {_NORMALIZED_MAX_BYTES} bytes (got {size})"
            )
        return v

    @field_validator("occurred_at")
    @classmethod
    def _validate_timestamp_range(cls, v: datetime) -> datetime:
        # Naive datetimes are interpreted as UTC for comparison purposes;
        # we don't normalize the stored value because downstream code accepts both.
        compare = v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if compare < now - _TIMESTAMP_PAST_LIMIT:
            raise ValueError(
                f"occurred_at is more than {_TIMESTAMP_PAST_LIMIT.days} days in the past"
            )
        if compare > now + _TIMESTAMP_FUTURE_LIMIT:
            raise ValueError(
                "occurred_at is more than"
                f" {int(_TIMESTAMP_FUTURE_LIMIT.total_seconds())}s in the future"
            )
        return v

    @field_validator("dedupe_key")
    @classmethod
    def _validate_dedupe_key(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _DEDUPE_KEY_RE.match(v):
            raise ValueError(
                "dedupe_key must be 1–128 printable ASCII characters with no whitespace"
            )
        return v


class RawEventAccepted(BaseModel):
    event_id: uuid.UUID
    dedup_hit: bool
    detections_fired: list[uuid.UUID] = Field(default_factory=list)
    incident_touched: uuid.UUID | None = None


class EventSummary(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    source: str
    kind: str
    dedupe_key: str | None = None


class EventList(BaseModel):
    items: list[EventSummary]
    total: int
