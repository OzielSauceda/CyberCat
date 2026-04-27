from __future__ import annotations

from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.detection.engine import DetectionResult, register
from app.enums import DetectionRuleSource, Severity

RULE_ID = "py.process.suspicious_child"

# Office binaries whose child processes are inherently suspicious
_SUSPICIOUS_PARENTS = frozenset({
    "winword.exe", "excel.exe", "outlook.exe", "powerpnt.exe",
    "onenote.exe", "msaccess.exe",
})

# Shell/script interpreters that should not be direct office children
_SHELL_CHILDREN = frozenset({
    "cmd.exe", "powershell.exe", "pwsh.exe",
    "wscript.exe", "cscript.exe", "mshta.exe",
})

# Flags that indicate encoded/obfuscated PowerShell commands
_ENC_FLAGS = ("-encodedcommand", "-enc ", "-e ", "-ec ")


@register
async def process_suspicious_child(
    event: Event,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> list[DetectionResult]:
    if event.kind != "process.created":
        return []

    n = event.normalized
    image: str = (n.get("image") or "").lower()
    cmdline: str = (n.get("cmdline") or "").lower()
    parent_image: str = (n.get("parent_image") or "").lower()

    if not image:
        return []

    # Branch 1: encoded/obfuscated PowerShell command line
    if "powershell.exe" in image or "pwsh.exe" in image:
        for flag in _ENC_FLAGS:
            if flag in cmdline:
                return [DetectionResult(
                    rule_id=RULE_ID,
                    rule_source=DetectionRuleSource.py,
                    rule_version="1.0.0",
                    severity_hint=Severity.high,
                    confidence_hint=Decimal("0.85"),
                    attack_tags=["T1059.001", "T1027.010"],
                    matched_fields={"image": image, "cmdline_fragment": cmdline[:200], "branch": "encoded_powershell"},
                )]

    # Branch 2: office binary spawning a shell interpreter
    if parent_image in _SUSPICIOUS_PARENTS and image in _SHELL_CHILDREN:
        return [DetectionResult(
            rule_id=RULE_ID,
            rule_source=DetectionRuleSource.py,
            rule_version="1.0.0",
            severity_hint=Severity.high,
            confidence_hint=Decimal("0.90"),
            attack_tags=["T1059.003", "T1566.001"],
            matched_fields={"parent_image": parent_image, "image": image, "branch": "office_spawns_shell"},
        )]

    # Branch 3: rundll32 with suspicious invocation
    if "rundll32.exe" in image:
        if "javascript:" in cmdline or "vbscript:" in cmdline:
            return [DetectionResult(
                rule_id=RULE_ID,
                rule_source=DetectionRuleSource.py,
                rule_version="1.0.0",
                severity_hint=Severity.high,
                confidence_hint=Decimal("0.80"),
                attack_tags=["T1218.011"],
                matched_fields={"image": image, "cmdline_fragment": cmdline[:200], "branch": "rundll32_script"},
            )]

    return []
