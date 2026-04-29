"""Async tests for cct_agent.sources.tail.tail_lines.

Covers cold start, mid-stream append, restart resume, log rotation
(inode change), and truncation. Each test creates a temp log file,
appends or rotates it, and asserts the yielded lines match.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from cct_agent.checkpoint import Checkpoint
from cct_agent.sources.tail import tail_lines

# Short poll interval so tests don't drag.
POLL = 0.05


async def _collect(
    path: Path,
    checkpoint: Checkpoint,
    expected: int,
    *,
    timeout: float = 5.0,
) -> list[str]:
    """Read up to ``expected`` lines or fail after ``timeout`` seconds."""
    out: list[str] = []
    stop = asyncio.Event()

    async def _run():
        async for line in tail_lines(path, checkpoint, poll_interval=POLL, stop_event=stop):
            out.append(line)
            if len(out) >= expected:
                stop.set()
                return

    try:
        await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return out


@pytest.mark.asyncio
async def test_cold_start_reads_existing_file_from_beginning(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    log_path.write_bytes(b"line1\nline2\nline3\n")

    cp = Checkpoint(path=tmp_path / "cp.json")
    lines = await _collect(log_path, cp, expected=3)

    assert lines == ["line1\n", "line2\n", "line3\n"]
    # Inode adopted, offset advanced to end of file
    assert cp.inode is not None
    assert cp.offset == log_path.stat().st_size


@pytest.mark.asyncio
async def test_mid_stream_append_yields_new_lines(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    log_path.write_bytes(b"first\n")

    cp = Checkpoint(path=tmp_path / "cp.json")
    stop = asyncio.Event()
    yielded: list[str] = []

    async def _consumer():
        async for line in tail_lines(log_path, cp, poll_interval=POLL, stop_event=stop):
            yielded.append(line)
            if len(yielded) >= 3:
                stop.set()
                return

    consumer_task = asyncio.create_task(_consumer())

    # Wait for the first line, then append more.
    await asyncio.sleep(0.2)
    with log_path.open("ab") as f:
        f.write(b"second\n")
        f.write(b"third\n")

    await asyncio.wait_for(consumer_task, timeout=3.0)
    assert yielded == ["first\n", "second\n", "third\n"]


@pytest.mark.asyncio
async def test_restart_resumes_from_offset(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    log_path.write_bytes(b"alpha\nbeta\n")

    # First run: read both lines, save checkpoint
    cp_path = tmp_path / "cp.json"
    cp = Checkpoint.load(cp_path)
    lines1 = await _collect(log_path, cp, expected=2)
    assert lines1 == ["alpha\n", "beta\n"]
    cp.save()

    # Append two more lines
    with log_path.open("ab") as f:
        f.write(b"gamma\n")
        f.write(b"delta\n")

    # Second run: load checkpoint → only the new lines are yielded
    cp2 = Checkpoint.load(cp_path)
    assert cp2.offset > 0
    lines2 = await _collect(log_path, cp2, expected=2)
    assert lines2 == ["gamma\n", "delta\n"]


@pytest.mark.asyncio
async def test_partial_trailing_line_is_held_until_complete(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    log_path.write_bytes(b"complete\nincomplete-no-newline")

    cp = Checkpoint(path=tmp_path / "cp.json")
    # Only one complete line should be yielded
    stop = asyncio.Event()
    yielded: list[str] = []

    async def _consumer():
        async for line in tail_lines(log_path, cp, poll_interval=POLL, stop_event=stop):
            yielded.append(line)
            stop.set()
            return

    consumer_task = asyncio.create_task(_consumer())
    await asyncio.wait_for(consumer_task, timeout=3.0)

    assert yielded == ["complete\n"]
    # Offset should be just past the first complete line, NOT including the partial.
    assert cp.offset == len(b"complete\n")


@pytest.mark.asyncio
async def test_truncation_resets_to_offset_zero(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    log_path.write_bytes(b"a\nb\nc\n")

    cp_path = tmp_path / "cp.json"
    cp = Checkpoint.load(cp_path)
    lines1 = await _collect(log_path, cp, expected=3)
    assert lines1 == ["a\n", "b\n", "c\n"]
    cp.save()

    # Simulate truncation: write a smaller file in place
    log_path.write_bytes(b"X\n")

    cp2 = Checkpoint.load(cp_path)
    # cp2.offset is now > the new file size; truncation handler should
    # reset to 0 and yield "X\n" as a fresh line.
    lines2 = await _collect(log_path, cp2, expected=1)
    assert lines2 == ["X\n"]


@pytest.mark.asyncio
async def test_rotation_inode_change_resets_offset(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    log_path.write_bytes(b"old1\nold2\n")

    cp_path = tmp_path / "cp.json"
    cp = Checkpoint.load(cp_path)
    lines1 = await _collect(log_path, cp, expected=2)
    assert lines1 == ["old1\n", "old2\n"]
    cp.save()
    original_inode = cp.inode
    assert original_inode is not None

    # Simulate rotation: delete + recreate. On Windows this requires
    # nothing to be holding the file open — we close after each batch
    # in tail.py, so this is safe.
    log_path.unlink()
    log_path.write_bytes(b"new1\nnew2\n")
    rotated_inode = log_path.stat().st_ino
    # Filesystem should give a different file index for the recreated file.
    # If it doesn't (some emulated filesystems), skip the rotation assertion.
    if rotated_inode == original_inode:
        pytest.skip("filesystem reuses file index — rotation cannot be tested here")

    cp2 = Checkpoint.load(cp_path)
    lines2 = await _collect(log_path, cp2, expected=2)
    assert lines2 == ["new1\n", "new2\n"]
    # Inode adopted post-rotation
    assert cp2.inode == rotated_inode


@pytest.mark.asyncio
async def test_missing_file_polls_until_present(tmp_path: Path):
    log_path = tmp_path / "auth.log"
    cp = Checkpoint(path=tmp_path / "cp.json")

    yielded: list[str] = []
    stop = asyncio.Event()

    async def _consumer():
        async for line in tail_lines(log_path, cp, poll_interval=POLL, stop_event=stop):
            yielded.append(line)
            stop.set()
            return

    consumer_task = asyncio.create_task(_consumer())
    # Wait, then create the file
    await asyncio.sleep(0.2)
    log_path.write_bytes(b"hello\n")

    await asyncio.wait_for(consumer_task, timeout=3.0)
    assert yielded == ["hello\n"]
