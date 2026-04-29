"""Environment-driven configuration for the cct-agent.

All settings are read from ``CCT_*`` env vars at startup. ``CCT_AGENT_TOKEN``
is the only required field; everything else has a sensible default for the
default compose deployment (lab-debian + cct-agent sidecar).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Static configuration for the agent process."""

    model_config = SettingsConfigDict(env_prefix="CCT_", env_file=None, extra="ignore")

    api_url: str = Field(default="http://backend:8000")
    agent_token: str = Field(default="")
    log_path: str = Field(default="/var/log/auth.log")
    checkpoint_path: str = Field(default="/var/lib/cct-agent/checkpoint.json")
    host_name: str = Field(default="lab-debian")
    batch_size: int = Field(default=50, ge=1, le=500)
    flush_interval_seconds: float = Field(default=2.0, gt=0.0, le=60.0)
    queue_max: int = Field(default=1000, ge=2, le=100_000)
    poll_interval_seconds: float = Field(default=0.5, gt=0.0, le=10.0)
    # auditd source (Phase 16.9). Independent kill switch + checkpoint so the
    # agent still works in environments without /var/log/audit/ (e.g. running
    # outside lab-debian, or kernel audit unavailable inside the container).
    audit_log_path: str = Field(default="/lab/var/log/audit/audit.log")
    audit_checkpoint_path: str = Field(
        default="/var/lib/cct-agent/audit-checkpoint.json"
    )
    audit_enabled: bool = Field(default=True)
    # conntrack source (Phase 16.10). Independent kill switch + checkpoint so
    # the agent still works on hosts where the kernel conntrack netlink group
    # is unreachable from inside the container (e.g. Docker Desktop on Windows).
    conntrack_log_path: str = Field(default="/lab/var/log/conntrack.log")
    conntrack_checkpoint_path: str = Field(
        default="/var/lib/cct-agent/conntrack-checkpoint.json"
    )
    conntrack_enabled: bool = Field(default=True)
