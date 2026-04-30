"""Durable byte-offset checkpoint for the cct-agent file tail.

The checkpoint records ``(inode, offset)`` for one tailed file. ``inode``
detects log rotation — when the live file's inode no longer matches,
the offset belongs to a now-rotated file and must be reset to 0.

Persisted as JSON. Writes are atomic (tempfile in the same directory +
``os.replace``) so a crash during write never leaves a half-written
checkpoint behind.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Mutable byte-offset state for one tailed file."""

    path: Path
    inode: int | None = None
    offset: int = 0

    @classmethod
    def load(cls, path: Path) -> Checkpoint:
        """Read the on-disk checkpoint, or return a fresh one (offset=0)."""
        if not path.exists():
            return cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("checkpoint at %s is unreadable (%s); treating as cold start", path, e)
            return cls(path=path)
        inode = data.get("inode")
        offset = data.get("offset", 0)
        return cls(
            path=path,
            inode=int(inode) if inode is not None else None,
            offset=int(offset),
        )

    def save(self) -> None:
        """Atomically persist the current state to ``self.path``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # NamedTemporaryFile in the same dir so os.replace is same-filesystem
        # (and therefore atomic on POSIX and Windows >= NTFS).
        fd, tmp_name = tempfile.mkstemp(
            prefix=".cp.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"inode": self.inode, "offset": self.offset}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            # Best-effort cleanup; if mkstemp succeeded but we failed to
            # rename, the tmp file is orphaned and would otherwise leak.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
