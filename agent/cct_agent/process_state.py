"""Bounded in-memory PID tracking for the auditd pipeline.

Two responsibilities:

  1. **Enrich process.created** with ``parent_image`` by looking up the
     parent's previously-recorded image. The auditd EXECVE/SYSCALL pair
     does not carry the parent's binary path; we recover it from the cache.

  2. **Filter process.exited** to PIDs we actually saw start. The
     ``exit_group`` audit rule fires on every process exit in the lab,
     but we only want to ship exits we have provenance for (matching a
     prior process.created). Untracked exits are silently dropped.

Eviction is plain LRU on an ``OrderedDict`` capped at 4096 entries — about
600 KB worst-case (4096 × ~150 B). Cache is volatile: agent restart wipes
it, which is acceptable because the smoke test triggers fresh activity
after start-up; long-lived processes that span restarts simply produce an
unmatched exit (logged at debug, not shipped).
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from cct_agent.parsers.auditd import ParsedProcessEvent

log = logging.getLogger(__name__)

_DEFAULT_MAX_SIZE = 4096


@dataclass
class ProcessRecord:
    """Per-PID state stored while a process is alive."""

    image: str | None
    user: str | None
    started_at: datetime


class TrackedProcesses:
    """LRU map of pid → ProcessRecord, bounded in size."""

    def __init__(self, max_size: int = _DEFAULT_MAX_SIZE) -> None:
        self._cache: OrderedDict[int, ProcessRecord] = OrderedDict()
        self._max_size = max_size

    def __len__(self) -> int:
        return len(self._cache)

    def record(self, event: ParsedProcessEvent) -> ParsedProcessEvent:
        """Register a process.created event; return it (with parent_image filled in if known).

        Side effects on ``self._cache``:
          - parent ppid (if present) is touched (LRU bump).
          - new pid is stored / refreshed at the most-recent end.
          - oldest entries are evicted to enforce the size cap.
        """
        if event.kind != "process.created":
            raise ValueError(
                f"TrackedProcesses.record() expects kind=process.created, got {event.kind!r}"
            )

        if event.ppid is not None:
            parent = self._cache.get(event.ppid)
            if parent is not None:
                if event.parent_image is None:
                    event.parent_image = parent.image
                # Touch the parent so it stays warm while children are spawning.
                self._cache.move_to_end(event.ppid)

        self._cache[event.pid] = ProcessRecord(
            image=event.image,
            user=event.user,
            started_at=event.occurred_at,
        )
        self._cache.move_to_end(event.pid)

        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

        return event

    def resolve_exit(self, event: ParsedProcessEvent) -> ParsedProcessEvent | None:
        """Match a process.exited event to a tracked PID.

        Returns the (possibly enriched) event on hit (and pops the entry).
        Returns ``None`` on miss — caller should drop the event.
        """
        if event.kind != "process.exited":
            raise ValueError(
                f"TrackedProcesses.resolve_exit() expects kind=process.exited, got {event.kind!r}"
            )
        record = self._cache.pop(event.pid, None)
        if record is None:
            log.debug(
                "process.exited for untracked pid=%d (audit_event_id=%d) — dropping",
                event.pid,
                event.audit_event_id,
            )
            return None

        if event.image is None:
            event.image = record.image
        if event.user is None:
            event.user = record.user
        return event
