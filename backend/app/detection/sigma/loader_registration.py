from __future__ import annotations

import hashlib
import logging
import re
from decimal import Decimal
from pathlib import Path

import yaml

from app.detection.sigma.compiler import CompiledRule, UnsupportedSigmaConstruct, compile_rule
from app.detection.sigma.parser import SigmaRuleSpec, parse_yaml
from app.enums import DetectionRuleSource, Severity

log = logging.getLogger(__name__)

_LEVEL_TO_SEVERITY: dict[str, Severity] = {
    "informational": Severity.info,
    "low": Severity.low,
    "medium": Severity.medium,
    "high": Severity.high,
    "critical": Severity.critical,
}

_LEVEL_TO_CONFIDENCE: dict[str, Decimal] = {
    "informational": Decimal("0.30"),
    "low": Decimal("0.40"),
    "medium": Decimal("0.60"),
    "high": Decimal("0.70"),
    "critical": Decimal("0.80"),
}

_ATTACK_TAG_RE = re.compile(r"^attack\.(t\d{4}(?:\.\d{3})?)$", re.IGNORECASE)


def _extract_attack_tags(raw_tags: list[str]) -> list[str]:
    result: list[str] = []
    for t in raw_tags:
        m = _ATTACK_TAG_RE.match(t)
        if m:
            normalized = m.group(1).upper()
            result.append(normalized)
    return result


def _slug(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"[^a-z0-9_]", "_", stem.lower())


def _make_detector(
    spec: SigmaRuleSpec,
    compiled: CompiledRule,
    rule_id: str,
    rule_version: str,
    attack_tags: list[str],
    pack_file: str,
) -> object:
    """Create and register an async detector function for one compiled Sigma rule."""
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import Event
    from app.detection.engine import DetectionResult, register

    severity = _LEVEL_TO_SEVERITY.get(spec.level, Severity.medium)
    confidence = _LEVEL_TO_CONFIDENCE.get(spec.level, Decimal("0.60"))
    matched_fields_base = {
        "sigma_id": spec.id or "",
        "rule_title": spec.title,
        "pack_file": pack_file,
    }

    async def sigma_detector(
        event: Event,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> list[DetectionResult]:
        if not compiled.logsource_match(event.kind):
            return []
        if not compiled.predicate_match(event.normalized):
            return []
        return [
            DetectionResult(
                rule_id=rule_id,
                rule_source=DetectionRuleSource.sigma,
                rule_version=rule_version,
                severity_hint=severity,
                confidence_hint=confidence,
                attack_tags=attack_tags,
                matched_fields={**matched_fields_base},
            )
        ]

    sigma_detector.__name__ = f"sigma_{_slug(pack_file)}"
    register(sigma_detector)
    return sigma_detector


def load_pack(pack_dir: Path) -> int:
    """Load and register all Sigma rules listed in pack.yml. Returns count registered."""
    manifest_path = pack_dir / "pack.yml"
    if not manifest_path.exists():
        log.warning("Sigma pack manifest not found at %s — no Sigma rules loaded", manifest_path)
        return 0

    with open(manifest_path, encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    rule_files: list[str] = manifest.get("rules", []) if isinstance(manifest, dict) else []
    count = 0

    for filename in rule_files:
        rule_path = pack_dir / filename
        if not rule_path.exists():
            log.warning("Sigma rule file %s not found — skipping", rule_path)
            continue

        raw = rule_path.read_text(encoding="utf-8")
        rule_version = hashlib.sha256(raw.encode()).hexdigest()[:12]

        try:
            spec = parse_yaml(raw)
        except Exception as exc:
            log.warning("Sigma rule %s failed to parse: %s — skipping", filename, exc)
            continue

        try:
            compiled = compile_rule(spec)
        except UnsupportedSigmaConstruct as exc:
            log.warning("Sigma rule %s skipped (unsupported construct): %s", filename, exc)
            continue
        except Exception as exc:
            log.warning("Sigma rule %s failed to compile: %s — skipping", filename, exc)
            continue

        rule_id = f"sigma-{spec.id}" if spec.id else f"sigma-{_slug(filename)}"
        attack_tags = _extract_attack_tags(spec.tags)

        _make_detector(
            spec=spec,
            compiled=compiled,
            rule_id=rule_id,
            rule_version=rule_version,
            attack_tags=attack_tags,
            pack_file=filename,
        )
        log.debug("Sigma rule registered: %s (%s)", rule_id, spec.title)
        count += 1

    log.info("Sigma pack loaded: %d rule(s) registered from %s", count, pack_dir)
    return count
