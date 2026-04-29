"""Async file tail with rotation and truncation handling.

Yields complete (newline-terminated) lines from a growing log file. Maintains
a :class:`~cct_agent.checkpoint.Checkpoint` so the next run picks up where
the last one left off.

Behavior:
  - **Cold start**: the on-disk checkpoint records ``inode=None, offset=0``,
    so we start at the beginning of the current file.
  - **Restart**: the on-disk checkpoint stores the inode and byte offset of
    the last successfully processed line. We resume from that offset.
  - **Rotation**: detected by a change in inode. Offset resets to 0.
  - **Truncation**: detected by ``file.size < checkpoint.offset``. Offset
    resets to 0.

Lines are yielded as text (decoded as UTF-8 with ``errors="replace"``).
The yielded line includes its terminating ``\\n``.

Mutation contract:
  - The tail mutates ``checkpoint.inode`` and ``checkpoint.offset`` as it
    advances through the file. It **does not** call ``checkpoint.save()``.
    The caller saves after a batch is successfully processed (e.g. shipped
    to the backend), so a crash between yield and ship causes a re-read,
    not a lost line.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from cct_agent.checkpoint import Checkpoint

log = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 0.5


async def tail_lines(
    path: Path,
    checkpoint: Checkpoint,
    *,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    stop_event: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """Yield complete lines from ``path`` as they appear.

    Loops indefinitely until ``stop_event`` is set (or the consumer breaks
    out of the iteration). When the file does not yet exist, polls until
    it does.
    """
    while True:
        if stop_event is not None and stop_event.is_set():
            return

        try:
            stat = path.stat()
        except FileNotFoundError:
            await asyncio.sleep(poll_interval)
            continue

        current_inode = stat.st_ino

        # Rotation: stored inode no longer matches.
        if checkpoint.inode is not None and checkpoint.inode != current_inode:
            log.info(
                "log rotation detected for %s (inode %d -> %d); resetting offset to 0",
                path,
                checkpoint.inode,
                current_inode,
            )
            checkpoint.inode = current_inode
            checkpoint.offset = 0
        elif checkpoint.inode is None:
            # First sighting of this file — adopt its inode.
            checkpoint.inode = current_inode

        # Truncation: stored offset is past the new end of file.
        if stat.st_size < checkpoint.offset:
            log.info(
                "truncation detected for %s (size %d < offset %d); resetting offset to 0",
                path,
                stat.st_size,
                checkpoint.offset,
            )
            checkpoint.offset = 0

        if stat.st_size == checkpoint.offset:
            await asyncio.sleep(poll_interval)
            continue

        # Read new content off the event loop to avoid blocking on large files.
        lines, new_offset = await asyncio.to_thread(
            _read_complete_lines, path, checkpoint.offset
        )

        for line in lines:
            # Advance BEFORE yield. If the consumer breaks out of the
            # async-for after this line (or its task is cancelled), the
            # checkpoint already reflects "this line was emitted." The
            # caller is still responsible for calling checkpoint.save()
            # only after the line is durably shipped.
            checkpoint.offset += len(line.encode("utf-8"))
            yield line

        # Sanity: trust the file-system offset if our running tally diverges
        # (only possible if a partial trailing line was excluded from `lines`).
        if checkpoint.offset != new_offset:
            checkpoint.offset = new_offset


def _read_complete_lines(path: Path, start_offset: int) -> tuple[list[str], int]:
    """Read from ``start_offset`` to end-of-file; return complete lines only.

    A "complete" line ends in ``\\n``. If the file ends mid-line (no trailing
    newline), the partial fragment is left unread and ``end_offset`` is
    positioned just past the last complete line. The next call to this
    function (after the line completes) will pick up the full line.
    """
    out: list[str] = []
    end_offset = start_offset
    with path.open("rb") as f:
        f.seek(start_offset)
        buf = f.read()
    pos = 0
    while True:
        nl = buf.find(b"\n", pos)
        if nl < 0:
            break
        line_bytes = buf[pos : nl + 1]
        out.append(line_bytes.decode("utf-8", errors="replace"))
        end_offset += len(line_bytes)
        pos = nl + 1
    return out, end_offset
