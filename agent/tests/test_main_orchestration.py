"""Tests for the multi-source orchestration in cct_agent.__main__.

The full ``_run`` coroutine wires up the Shipper + tasks for all sources
and would need a stub backend. These tests focus on the small pieces of
pure logic that decide whether each non-default source spins up — that
is where the regressable behaviour lives (graceful degradation when a
subsystem is unavailable).
"""
from __future__ import annotations

from pathlib import Path

from cct_agent.__main__ import audit_source_active, conntrack_source_active
from cct_agent.config import AgentConfig


def _config(**overrides: object) -> AgentConfig:
    """Build an AgentConfig without picking up real ``CCT_*`` env vars."""
    base: dict[str, object] = {
        "agent_token": "test-token",
    }
    base.update(overrides)
    # type: ignore[arg-type] — overrides may pass typed kwargs as object
    return AgentConfig(**base)  # type: ignore[arg-type]


def test_audit_source_active_when_path_exists(tmp_path: Path):
    audit_log = tmp_path / "audit.log"
    audit_log.write_text("")  # exists but empty
    config = _config(
        audit_log_path=str(audit_log),
        audit_checkpoint_path=str(tmp_path / "audit-cp.json"),
        audit_enabled=True,
    )
    assert audit_source_active(config) is True


def test_audit_source_inactive_when_path_missing(tmp_path: Path):
    config = _config(
        audit_log_path=str(tmp_path / "no_such_audit.log"),
        audit_checkpoint_path=str(tmp_path / "audit-cp.json"),
        audit_enabled=True,
    )
    assert audit_source_active(config) is False


def test_audit_source_inactive_when_disabled_via_flag(tmp_path: Path):
    audit_log = tmp_path / "audit.log"
    audit_log.write_text("")  # would otherwise activate
    config = _config(
        audit_log_path=str(audit_log),
        audit_checkpoint_path=str(tmp_path / "audit-cp.json"),
        audit_enabled=False,
    )
    assert audit_source_active(config) is False


def test_default_config_uses_lab_audit_path():
    """The shipped default points at the path lab-debian's audit volume mounts to."""
    config = _config()
    assert config.audit_log_path == "/lab/var/log/audit/audit.log"
    assert config.audit_checkpoint_path == "/var/lib/cct-agent/audit-checkpoint.json"
    assert config.audit_enabled is True


# ---------------------------------------------------------------------------
# Phase 16.10: conntrack source gating
# ---------------------------------------------------------------------------


def test_conntrack_source_active_when_path_exists(tmp_path: Path):
    conntrack_log = tmp_path / "conntrack.log"
    conntrack_log.write_text("")
    config = _config(
        conntrack_log_path=str(conntrack_log),
        conntrack_checkpoint_path=str(tmp_path / "conntrack-cp.json"),
        conntrack_enabled=True,
    )
    assert conntrack_source_active(config) is True


def test_conntrack_source_inactive_when_path_missing(tmp_path: Path):
    config = _config(
        conntrack_log_path=str(tmp_path / "no_such_conntrack.log"),
        conntrack_checkpoint_path=str(tmp_path / "conntrack-cp.json"),
        conntrack_enabled=True,
    )
    assert conntrack_source_active(config) is False


def test_conntrack_source_inactive_when_disabled_via_flag(tmp_path: Path):
    conntrack_log = tmp_path / "conntrack.log"
    conntrack_log.write_text("")
    config = _config(
        conntrack_log_path=str(conntrack_log),
        conntrack_checkpoint_path=str(tmp_path / "conntrack-cp.json"),
        conntrack_enabled=False,
    )
    assert conntrack_source_active(config) is False


def test_default_config_uses_lab_conntrack_path():
    """The shipped default points at the path lab-debian writes conntrack.log to."""
    config = _config()
    assert config.conntrack_log_path == "/lab/var/log/conntrack.log"
    assert (
        config.conntrack_checkpoint_path
        == "/var/lib/cct-agent/conntrack-checkpoint.json"
    )
    assert config.conntrack_enabled is True
