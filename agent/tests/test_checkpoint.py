"""Unit tests for cct_agent.checkpoint.Checkpoint."""
from __future__ import annotations

from pathlib import Path

import pytest

from cct_agent.checkpoint import Checkpoint


def test_load_missing_file_returns_cold_start(tmp_path: Path):
    cp_path = tmp_path / "checkpoint.json"
    cp = Checkpoint.load(cp_path)
    assert cp.path == cp_path
    assert cp.inode is None
    assert cp.offset == 0


def test_save_then_load_roundtrip(tmp_path: Path):
    cp_path = tmp_path / "checkpoint.json"
    cp = Checkpoint(path=cp_path, inode=42, offset=100)
    cp.save()

    cp2 = Checkpoint.load(cp_path)
    assert cp2.inode == 42
    assert cp2.offset == 100


def test_save_creates_parent_dir(tmp_path: Path):
    cp_path = tmp_path / "deep" / "nested" / "checkpoint.json"
    cp = Checkpoint(path=cp_path, inode=1, offset=0)
    cp.save()
    assert cp_path.exists()


def test_save_atomic_no_tmp_files_left(tmp_path: Path):
    cp_path = tmp_path / "checkpoint.json"
    cp = Checkpoint(path=cp_path, inode=1, offset=0)
    cp.save()
    cp.save()  # multiple saves
    cp.save()
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".cp.")]
    assert leftovers == [], f"unexpected tmp leftovers: {leftovers}"


def test_load_corrupt_file_returns_cold_start(tmp_path: Path):
    cp_path = tmp_path / "checkpoint.json"
    cp_path.write_text("not valid json {", encoding="utf-8")
    cp = Checkpoint.load(cp_path)
    assert cp.inode is None
    assert cp.offset == 0


def test_load_partial_data_uses_defaults(tmp_path: Path):
    cp_path = tmp_path / "checkpoint.json"
    cp_path.write_text('{"offset": 50}', encoding="utf-8")
    cp = Checkpoint.load(cp_path)
    assert cp.inode is None
    assert cp.offset == 50


def test_save_then_modify_then_save_persists_latest(tmp_path: Path):
    cp_path = tmp_path / "checkpoint.json"
    cp = Checkpoint(path=cp_path, inode=1, offset=0)
    cp.save()

    cp.offset = 200
    cp.inode = 99
    cp.save()

    cp2 = Checkpoint.load(cp_path)
    assert cp2.offset == 200
    assert cp2.inode == 99
