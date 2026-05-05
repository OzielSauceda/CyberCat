from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Topic(str, enum.Enum):
    incidents = "incidents"
    detections = "detections"
    actions = "actions"
    evidence = "evidence"
    wazuh = "wazuh"


EventType = Literal[
    "incident.created",
    "incident.updated",
    "incident.transitioned",
    "incident.merged",
    "incident.split",
    "detection.fired",
    "action.proposed",
    "action.executed",
    "action.reverted",
    "evidence.opened",
    "evidence.collected",
    "evidence.dismissed",
    "wazuh.status_changed",
]

_TOPIC_MAP: dict[str, Topic] = {
    "incident.created": Topic.incidents,
    "incident.updated": Topic.incidents,
    "incident.transitioned": Topic.incidents,
    "incident.merged": Topic.incidents,
    "incident.split": Topic.incidents,
    "detection.fired": Topic.detections,
    "action.proposed": Topic.actions,
    "action.executed": Topic.actions,
    "action.reverted": Topic.actions,
    "evidence.opened": Topic.evidence,
    "evidence.collected": Topic.evidence,
    "evidence.dismissed": Topic.evidence,
    "wazuh.status_changed": Topic.wazuh,
}


def topic_for(event_type: EventType) -> Topic:
    return _TOPIC_MAP[event_type]


class StreamEvent(BaseModel):
    id: str
    type: EventType
    topic: Topic
    ts: datetime
    data: dict
