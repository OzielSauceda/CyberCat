"""Unit tests for wazuh_decoder — no Wazuh required, purely JSON fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingest.wazuh_decoder import decode_wazuh_alert

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wazuh"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ── positive cases ────────────────────────────────────────────────────────────

def test_sshd_failed_decodes_correctly():
    alert = _load("sshd-failed.json")
    result = decode_wazuh_alert(alert)
    assert result is not None
    assert result.kind == "auth.failed"
    assert result.normalized["user"] == "baduser"
    assert result.normalized["source_ip"] == "203.0.113.7"
    assert result.normalized["auth_type"] == "ssh"
    assert result.dedupe_key == "AX1234567890abcdef"


def test_sshd_success_decodes_correctly():
    alert = _load("sshd-success.json")
    result = decode_wazuh_alert(alert)
    assert result is not None
    assert result.kind == "auth.succeeded"
    assert result.normalized["user"] == "realuser"
    assert result.normalized["source_ip"] == "203.0.113.7"
    assert result.normalized["auth_type"] == "ssh"
    assert result.dedupe_key == "AX1234567890ghijkl"


def test_auditd_execve_decodes_correctly():
    alert = _load("auditd-execve.json")
    result = decode_wazuh_alert(alert)
    assert result is not None
    assert result.kind == "process.created"
    assert result.normalized["host"] == "lab-debian"
    assert result.normalized["image"] == "/usr/bin/id"
    assert result.normalized["pid"] == 1234
    assert result.dedupe_key == "AX1234567890mnopqr"


# ── drop cases ────────────────────────────────────────────────────────────────

def test_drops_unknown_rule_groups():
    alert = _load("sshd-failed.json")
    alert["rule"]["groups"] = ["syscheck", "ossec"]
    assert decode_wazuh_alert(alert) is None


def test_drops_auth_failed_missing_srcip():
    alert = _load("sshd-failed.json")
    del alert["data"]["srcip"]
    assert decode_wazuh_alert(alert) is None


def test_drops_unparseable_timestamp():
    alert = _load("sshd-failed.json")
    alert["timestamp"] = "not-a-date"
    alert["@timestamp"] = "not-a-date"
    assert decode_wazuh_alert(alert) is None


def test_drops_auditd_non_execve():
    alert = _load("auditd-execve.json")
    alert["rule"]["groups"] = ["audit"]
    alert["data"]["audit"]["type"] = "OPEN"
    assert decode_wazuh_alert(alert) is None


def test_drops_process_created_missing_agent_name():
    alert = _load("auditd-execve.json")
    del alert["agent"]["name"]
    assert decode_wazuh_alert(alert) is None


def test_sysmon_process_created_decodes_correctly():
    alert = _load("sysmon-process-create.json")
    result = decode_wazuh_alert(alert)
    assert result is not None
    assert result.kind == "process.created"
    assert result.normalized["host"] == "lab-win10-01"
    assert result.normalized["image"] == "C:\\Windows\\System32\\cmd.exe"
    assert result.normalized["cmdline"] == "cmd.exe /c whoami"
    assert result.normalized["pid"] == 1234
    assert result.normalized["ppid"] == 5678
    assert result.normalized["user"] == "LAB\\alice"
    assert result.dedupe_key == "AX1234567890stuvwx"


def test_drops_sysmon_non_eid1():
    alert = _load("sysmon-process-create.json")
    alert["data"]["win"]["system"]["eventID"] = "3"  # network connection
    assert decode_wazuh_alert(alert) is None


def test_drops_sysmon_missing_host():
    alert = _load("sysmon-process-create.json")
    del alert["agent"]["name"]
    del alert["data"]["win"]["system"]["computer"]
    assert decode_wazuh_alert(alert) is None
