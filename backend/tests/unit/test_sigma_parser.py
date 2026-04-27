"""Unit tests for the Sigma YAML parser."""
import pytest
from app.detection.sigma.parser import SigmaRuleSpec, parse_yaml

MINIMAL_RULE = """
title: Minimal Rule
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    Image|endswith: \\powershell.exe
  condition: selection
level: high
"""

FULL_RULE = """
id: test-rule-001
title: Full Rule
description: A complete test rule
logsource:
  category: process_creation
  product: windows
detection:
  selection_image:
    Image|endswith:
      - \\powershell.exe
      - \\pwsh.exe
  selection_enc:
    CommandLine|contains: -enc
  condition: selection_image and selection_enc
level: high
tags:
  - attack.execution
  - attack.t1059.001
"""


def test_parse_minimal_rule():
    spec = parse_yaml(MINIMAL_RULE)
    assert spec.title == "Minimal Rule"
    assert spec.level == "high"
    assert spec.logsource.category == "process_creation"
    assert spec.id is None
    assert spec.tags == []


def test_parse_full_rule():
    spec = parse_yaml(FULL_RULE)
    assert spec.id == "test-rule-001"
    assert spec.title == "Full Rule"
    assert spec.description == "A complete test rule"
    assert spec.level == "high"
    assert "attack.t1059.001" in spec.tags
    assert "attack.execution" in spec.tags
    sel_image = spec.detection["selection_image"]
    assert sel_image["Image|endswith"] == ["\\powershell.exe", "\\pwsh.exe"]


def test_parse_normalises_unknown_level():
    raw = """
title: Bad Level
logsource:
  category: process_creation
detection:
  selection:
    Image: test.exe
  condition: selection
level: supercritical
"""
    spec = parse_yaml(raw)
    assert spec.level == "medium"


def test_parse_non_mapping_raises():
    with pytest.raises(Exception):
        parse_yaml("- item1\n- item2\n")


def test_parse_missing_title_raises():
    raw = """
logsource:
  category: process_creation
detection:
  selection:
    Image: test.exe
  condition: selection
"""
    with pytest.raises(Exception):
        parse_yaml(raw)


def test_parse_missing_detection_raises():
    raw = """
title: No Detection
logsource:
  category: process_creation
"""
    with pytest.raises(Exception):
        parse_yaml(raw)
