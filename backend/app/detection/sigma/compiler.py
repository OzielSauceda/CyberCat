from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.detection.sigma.field_map import kinds_for_category, map_field
from app.detection.sigma.parser import SigmaRuleSpec


class UnsupportedSigmaConstruct(Exception):
    pass


# ---------------------------------------------------------------------------
# Matcher helpers
# ---------------------------------------------------------------------------

def _make_field_matcher(
    norm_key: str,
    modifiers: list[str],
    values: list[str],
) -> Callable[[dict], bool]:
    """Return a function that checks a normalized event dict for a single field condition."""

    use_all = "all" in modifiers
    has_re = "re" in modifiers
    has_contains = "contains" in modifiers
    has_startswith = "startswith" in modifiers
    has_endswith = "endswith" in modifiers

    # Validate no unsupported modifiers
    known = {"contains", "startswith", "endswith", "re", "all", "windash", "cidr", "base64offset"}
    for m in modifiers:
        if m not in known:
            raise UnsupportedSigmaConstruct(f"Unsupported field modifier: {m!r}")

    def _match_one(raw_value: Any, pattern: str) -> bool:
        text = str(raw_value).lower() if not has_re else str(raw_value)
        pat = pattern if has_re else pattern.lower()
        if has_re:
            return bool(re.search(pat, text, re.IGNORECASE))
        if has_contains:
            return pat in text
        if has_startswith:
            return text.startswith(pat)
        if has_endswith:
            return text.endswith(pat)
        # Plain equality
        return text == pat

    def matcher(normalized: dict) -> bool:
        raw = normalized.get(norm_key)
        if raw is None:
            return False
        if use_all:
            return all(_match_one(raw, p) for p in values)
        return any(_match_one(raw, p) for p in values)

    return matcher


# ---------------------------------------------------------------------------
# Selection → list of field matchers
# ---------------------------------------------------------------------------

def _compile_selection(
    selection_name: str,
    selection_body: Any,
) -> Callable[[dict], bool]:
    """Compile one named selection dict into a predicate over normalized event fields.

    A selection is a dict where every key is a field spec and the value is a
    string or list of strings. All field conditions must be true (AND across fields).
    """
    if not isinstance(selection_body, dict):
        raise UnsupportedSigmaConstruct(
            f"Selection {selection_name!r} is not a mapping — keywords/lists not supported"
        )

    field_matchers: list[Callable[[dict], bool]] = []

    for key, raw_values in selection_body.items():
        # Parse field name and modifiers: "Image|endswith|all" → ("Image", ["endswith", "all"])
        parts = key.split("|")
        sigma_field = parts[0]
        modifiers = [p.lower() for p in parts[1:]]

        norm_key = map_field(sigma_field)
        if norm_key is None:
            raise UnsupportedSigmaConstruct(
                f"Unmapped Sigma field {sigma_field!r} in selection {selection_name!r}"
            )

        # Normalise values to list[str]
        if isinstance(raw_values, list):
            values = [str(v) for v in raw_values]
        elif isinstance(raw_values, (str, int, float, bool)):
            values = [str(raw_values)]
        else:
            raise UnsupportedSigmaConstruct(
                f"Unexpected value type {type(raw_values)} for field {key!r}"
            )

        field_matchers.append(_make_field_matcher(norm_key, modifiers, values))

    def selection_predicate(normalized: dict) -> bool:
        return all(m(normalized) for m in field_matchers)

    return selection_predicate


# ---------------------------------------------------------------------------
# Condition tokenizer + parser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"(?P<LPAREN>\()"
    r"|(?P<RPAREN>\))"
    r"|(?P<KW>1|all|of|not|and|or)"
    r"|(?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*(?:\*)?)"
    r"|\s+",
    re.IGNORECASE,
)


def _tokenize(condition: str) -> list[str]:
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(condition):
        tok = m.group().strip()
        if tok:
            tokens.append(tok.lower() if m.lastgroup == "KW" else m.group().strip())
    return tokens


@dataclass
class _Parser:
    tokens: list[str]
    pos: int = 0
    selections: dict[str, Callable[[dict], bool]] = field(default_factory=dict)

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected: str | None = None) -> str:
        tok = self.tokens[self.pos]
        if expected is not None and tok.lower() != expected.lower():
            raise UnsupportedSigmaConstruct(
                f"Expected {expected!r} but got {tok!r} at position {self.pos}"
            )
        self.pos += 1
        return tok

    def parse_expr(self) -> Callable[[dict], bool]:
        left = self.parse_term()
        while self.peek() and self.peek().lower() in ("and", "or"):
            op = self.consume().lower()
            right = self.parse_term()
            if op == "and":
                left_captured, right_captured = left, right
                left = lambda n, l=left_captured, r=right_captured: l(n) and r(n)
            else:
                left_captured, right_captured = left, right
                left = lambda n, l=left_captured, r=right_captured: l(n) or r(n)
        return left

    def parse_term(self) -> Callable[[dict], bool]:
        if self.peek() and self.peek().lower() == "not":
            self.consume("not")
            inner = self.parse_factor()
            return lambda n, f=inner: not f(n)
        return self.parse_factor()

    def parse_factor(self) -> Callable[[dict], bool]:
        tok = self.peek()
        if tok is None:
            raise UnsupportedSigmaConstruct("Unexpected end of condition")

        if tok == "(":
            self.consume("(")
            expr = self.parse_expr()
            self.consume(")")
            return expr

        if tok.lower() in ("1", "all"):
            return self.parse_quantifier()

        # Identifier (selection name or "them")
        name = self.consume()
        if name.lower() == "them":
            # "them" references all named selections
            names = list(self.selections.keys())
            return lambda n, s=self.selections, ns=names: any(s[nm](n) for nm in ns)

        if name.endswith("*"):
            # Wildcard — resolve at parse time against known selections
            pattern = name.lower()
            matched = [k for k in self.selections if fnmatch.fnmatch(k.lower(), pattern)]
            if not matched:
                raise UnsupportedSigmaConstruct(f"No selections matched pattern {name!r}")
            matched_predicates = [self.selections[k] for k in matched]
            return lambda n, ps=matched_predicates: any(p(n) for p in ps)

        if name.lower() not in {k.lower() for k in self.selections}:
            raise UnsupportedSigmaConstruct(f"Reference to unknown selection {name!r}")

        # Case-insensitive lookup
        canon = next(k for k in self.selections if k.lower() == name.lower())
        pred = self.selections[canon]
        return lambda n, p=pred: p(n)

    def parse_quantifier(self) -> Callable[[dict], bool]:
        quant = self.consume().lower()  # "1" or "all"
        self.consume("of")
        pattern_tok = self.consume()

        if pattern_tok.lower() == "them":
            predicates = list(self.selections.values())
        else:
            glob = pattern_tok.lower()
            matched_keys = [k for k in self.selections if fnmatch.fnmatch(k.lower(), glob)]
            if not matched_keys:
                raise UnsupportedSigmaConstruct(
                    f"No selections matched quantifier pattern {pattern_tok!r}"
                )
            predicates = [self.selections[k] for k in matched_keys]

        if quant == "1":
            return lambda n, ps=predicates: any(p(n) for p in ps)
        else:  # all
            return lambda n, ps=predicates: all(p(n) for p in ps)


# ---------------------------------------------------------------------------
# CompiledRule
# ---------------------------------------------------------------------------

@dataclass
class CompiledRule:
    rule_id: str
    title: str
    target_kinds: list[str]
    predicate: Callable[[dict], bool]

    def logsource_match(self, event_kind: str) -> bool:
        return event_kind in self.target_kinds

    def predicate_match(self, normalized: dict) -> bool:
        return self.predicate(normalized)


# ---------------------------------------------------------------------------
# compile_rule
# ---------------------------------------------------------------------------

def compile_rule(spec: SigmaRuleSpec) -> CompiledRule:
    target_kinds = kinds_for_category(spec.logsource.category)
    if not target_kinds:
        raise UnsupportedSigmaConstruct(
            f"Logsource category {spec.logsource.category!r} maps to no known event kinds"
        )

    detection = spec.detection
    condition_raw: str | None = detection.get("condition")
    if not condition_raw:
        raise UnsupportedSigmaConstruct("Detection block has no 'condition' key")

    # Compile each named selection (everything except 'condition' and 'timeframe')
    selections: dict[str, Callable[[dict], bool]] = {}
    for sel_name, sel_body in detection.items():
        if sel_name in ("condition", "timeframe"):
            continue
        selections[sel_name] = _compile_selection(sel_name, sel_body)

    # Parse condition into a callable
    tokens = _tokenize(str(condition_raw))
    parser = _Parser(tokens=tokens, selections=selections)
    predicate = parser.parse_expr()
    if parser.pos < len(parser.tokens):
        raise UnsupportedSigmaConstruct(
            f"Trailing tokens in condition: {parser.tokens[parser.pos:]}"
        )

    rule_id = spec.id or ""
    return CompiledRule(
        rule_id=rule_id,
        title=spec.title,
        target_kinds=target_kinds,
        predicate=predicate,
    )
