"""Unit tests for Sigma field mapping."""
from app.detection.sigma.field_map import CATEGORY_TO_KINDS, SIGMA_TO_NORMALIZED, kinds_for_category, map_field


def test_known_fields_map():
    assert map_field("Image") == "image"
    assert map_field("CommandLine") == "cmdline"
    assert map_field("ParentImage") == "parent_image"
    assert map_field("User") == "user"
    assert map_field("DestinationPort") == "dst_port"
    assert map_field("LogonType") == "auth_type"


def test_unknown_field_returns_none():
    assert map_field("UnknownSigmaField") is None
    assert map_field("") is None
    assert map_field("WinEventId") is None


def test_category_to_kinds_process_creation():
    kinds = kinds_for_category("process_creation")
    assert "process.created" in kinds


def test_category_to_kinds_authentication():
    kinds = kinds_for_category("authentication")
    assert "auth.succeeded" in kinds
    assert "auth.failed" in kinds


def test_category_to_kinds_network():
    kinds = kinds_for_category("network_connection")
    assert "network.connection" in kinds


def test_unknown_category_returns_empty():
    assert kinds_for_category("unknown_category") == []
    assert kinds_for_category(None) == []


def test_sigma_to_normalized_no_duplicates():
    values = list(SIGMA_TO_NORMALIZED.values())
    # All target normalized keys should be lowercase snake_case
    for v in values:
        assert v == v.lower(), f"Normalized key {v!r} should be lowercase"
