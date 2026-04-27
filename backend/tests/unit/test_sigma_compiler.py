"""Unit tests for the Sigma compiler — modifiers, condition combinators, edge cases."""
import pytest
from app.detection.sigma.compiler import CompiledRule, UnsupportedSigmaConstruct, compile_rule
from app.detection.sigma.parser import parse_yaml


def _compile(yaml_text: str) -> CompiledRule:
    return compile_rule(parse_yaml(yaml_text))


def _norm(**kwargs) -> dict:
    """Build a fake normalized event dict."""
    return {k: v for k, v in kwargs.items()}


# ---------------------------------------------------------------------------
# Modifier: |contains
# ---------------------------------------------------------------------------

CONTAINS_RULE = """
title: Contains Test
logsource:
  category: process_creation
detection:
  selection:
    CommandLine|contains: -enc
  condition: selection
level: medium
"""


def test_modifier_contains_match():
    rule = _compile(CONTAINS_RULE)
    assert rule.predicate_match(_norm(cmdline="powershell.exe -enc abc"))


def test_modifier_contains_no_match():
    rule = _compile(CONTAINS_RULE)
    assert not rule.predicate_match(_norm(cmdline="powershell.exe -normal"))


# ---------------------------------------------------------------------------
# Modifier: |endswith
# ---------------------------------------------------------------------------

ENDSWITH_RULE = """
title: Endswith Test
logsource:
  category: process_creation
detection:
  selection:
    Image|endswith: \\powershell.exe
  condition: selection
level: medium
"""


def test_modifier_endswith_match():
    rule = _compile(ENDSWITH_RULE)
    assert rule.predicate_match(_norm(image="C:\\Windows\\System32\\powershell.exe"))


def test_modifier_endswith_no_match():
    rule = _compile(ENDSWITH_RULE)
    assert not rule.predicate_match(_norm(image="C:\\Windows\\System32\\cmd.exe"))


# ---------------------------------------------------------------------------
# Modifier: |startswith
# ---------------------------------------------------------------------------

STARTSWITH_RULE = """
title: Startswith Test
logsource:
  category: process_creation
detection:
  selection:
    CommandLine|startswith: powershell
  condition: selection
level: medium
"""


def test_modifier_startswith_match():
    rule = _compile(STARTSWITH_RULE)
    assert rule.predicate_match(_norm(cmdline="powershell -enc abc"))


def test_modifier_startswith_no_match():
    rule = _compile(STARTSWITH_RULE)
    assert not rule.predicate_match(_norm(cmdline="cmd /c powershell"))


# ---------------------------------------------------------------------------
# Modifier: |re
# ---------------------------------------------------------------------------

RE_RULE = """
title: Regex Test
logsource:
  category: process_creation
detection:
  selection:
    CommandLine|re: '-[eE][nN][cC]'
  condition: selection
level: medium
"""


def test_modifier_re_match():
    rule = _compile(RE_RULE)
    assert rule.predicate_match(_norm(cmdline="powershell -Enc abc"))


def test_modifier_re_no_match():
    rule = _compile(RE_RULE)
    assert not rule.predicate_match(_norm(cmdline="powershell -Normal"))


# ---------------------------------------------------------------------------
# Modifier: |contains|all (list AND semantics)
# ---------------------------------------------------------------------------

CONTAINS_ALL_RULE = """
title: Contains All Test
logsource:
  category: process_creation
detection:
  selection:
    CommandLine|contains|all:
      - -enc
      - powershell
  condition: selection
level: medium
"""


def test_modifier_contains_all_both_present():
    rule = _compile(CONTAINS_ALL_RULE)
    assert rule.predicate_match(_norm(cmdline="powershell -enc abc"))


def test_modifier_contains_all_only_one():
    rule = _compile(CONTAINS_ALL_RULE)
    assert not rule.predicate_match(_norm(cmdline="powershell -normal"))
    assert not rule.predicate_match(_norm(cmdline="cmd -enc abc"))


# ---------------------------------------------------------------------------
# Condition: AND
# ---------------------------------------------------------------------------

AND_RULE = """
title: AND Test
logsource:
  category: process_creation
detection:
  sel_image:
    Image|endswith: \\powershell.exe
  sel_cmd:
    CommandLine|contains: -enc
  condition: sel_image and sel_cmd
level: high
"""


def test_condition_and_both():
    rule = _compile(AND_RULE)
    assert rule.predicate_match(_norm(image="C:\\powershell.exe", cmdline="-enc abc"))


def test_condition_and_only_one():
    rule = _compile(AND_RULE)
    assert not rule.predicate_match(_norm(image="C:\\powershell.exe", cmdline="-normal"))
    assert not rule.predicate_match(_norm(image="C:\\cmd.exe", cmdline="-enc abc"))


# ---------------------------------------------------------------------------
# Condition: OR
# ---------------------------------------------------------------------------

OR_RULE = """
title: OR Test
logsource:
  category: process_creation
detection:
  sel_ps:
    Image|endswith: \\powershell.exe
  sel_pwsh:
    Image|endswith: \\pwsh.exe
  condition: sel_ps or sel_pwsh
level: medium
"""


def test_condition_or_first():
    rule = _compile(OR_RULE)
    assert rule.predicate_match(_norm(image="C:\\Windows\\powershell.exe"))


def test_condition_or_second():
    rule = _compile(OR_RULE)
    assert rule.predicate_match(_norm(image="C:\\Program Files\\pwsh.exe"))


def test_condition_or_neither():
    rule = _compile(OR_RULE)
    assert not rule.predicate_match(_norm(image="C:\\cmd.exe"))


# ---------------------------------------------------------------------------
# Condition: NOT
# ---------------------------------------------------------------------------

NOT_RULE = """
title: NOT Test
logsource:
  category: process_creation
detection:
  sel_cmd:
    CommandLine|contains: suspicious
  sel_filter:
    Image|endswith: \\whitelist.exe
  condition: sel_cmd and not sel_filter
level: medium
"""


def test_condition_not_excludes():
    rule = _compile(NOT_RULE)
    assert rule.predicate_match(_norm(cmdline="suspicious command", image="C:\\other.exe"))
    assert not rule.predicate_match(_norm(cmdline="suspicious command", image="C:\\whitelist.exe"))


# ---------------------------------------------------------------------------
# Condition: 1 of selection_*
# ---------------------------------------------------------------------------

ONE_OF_RULE = """
title: One Of Test
logsource:
  category: process_creation
detection:
  selection_a:
    Image|endswith: \\powershell.exe
  selection_b:
    Image|endswith: \\pwsh.exe
  condition: 1 of selection_*
level: medium
"""


def test_condition_one_of_first():
    rule = _compile(ONE_OF_RULE)
    assert rule.predicate_match(_norm(image="C:\\powershell.exe"))


def test_condition_one_of_second():
    rule = _compile(ONE_OF_RULE)
    assert rule.predicate_match(_norm(image="C:\\pwsh.exe"))


def test_condition_one_of_none():
    rule = _compile(ONE_OF_RULE)
    assert not rule.predicate_match(_norm(image="C:\\cmd.exe"))


# ---------------------------------------------------------------------------
# Condition: all of selection_*
# ---------------------------------------------------------------------------

ALL_OF_RULE = """
title: All Of Test
logsource:
  category: process_creation
detection:
  selection_img:
    Image|endswith: \\powershell.exe
  selection_cmd:
    CommandLine|contains: -enc
  condition: all of selection_*
level: high
"""


def test_condition_all_of_both():
    rule = _compile(ALL_OF_RULE)
    assert rule.predicate_match(_norm(image="C:\\powershell.exe", cmdline="-enc abc"))


def test_condition_all_of_missing_one():
    rule = _compile(ALL_OF_RULE)
    assert not rule.predicate_match(_norm(image="C:\\powershell.exe", cmdline="-normal"))


# ---------------------------------------------------------------------------
# Logsource matching
# ---------------------------------------------------------------------------

def test_logsource_match():
    rule = _compile(AND_RULE)
    assert rule.logsource_match("process.created")
    assert not rule.logsource_match("auth.succeeded")
    assert not rule.logsource_match("network.connection")


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unsupported_modifier_raises():
    raw = """
title: Bad Modifier
logsource:
  category: process_creation
detection:
  selection:
    Image|base64: abc
  condition: selection
level: medium
"""
    with pytest.raises(UnsupportedSigmaConstruct):
        _compile(raw)


def test_unmapped_field_raises():
    raw = """
title: Unmapped Field
logsource:
  category: process_creation
detection:
  selection:
    EventID: 4688
  condition: selection
level: medium
"""
    with pytest.raises(UnsupportedSigmaConstruct):
        _compile(raw)


def test_unknown_category_raises():
    raw = """
title: Unknown Category
logsource:
  category: registry_set
detection:
  selection:
    Image: test.exe
  condition: selection
level: medium
"""
    with pytest.raises(UnsupportedSigmaConstruct):
        _compile(raw)
