from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://cybercat:cybercat_dev@localhost:5432/cybercat"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000"

    # Multi-operator auth (Phase 14)
    auth_required: bool = False
    auth_cookie_secret: str = ""
    auth_cookie_name: str = "cybercat_session"
    auth_session_ttl_minutes: int = 480

    # OIDC opt-in (Phase 14.4 — all None until configured)
    oidc_provider_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_redirect_uri: Optional[str] = None

    @model_validator(mode="after")
    def _validate_auth_cookie_secret(self) -> "Settings":
        if self.auth_required and not self.auth_cookie_secret:
            raise ValueError("AUTH_COOKIE_SECRET must be non-empty when AUTH_REQUIRED=true")
        return self

    # Wazuh bridge (Phase 8+9B)
    wazuh_bridge_enabled: bool = False
    wazuh_indexer_url: str = "https://wazuh-indexer:9200"
    wazuh_indexer_user: str = "cybercat_reader"
    wazuh_indexer_password: str = ""
    wazuh_indexer_index_pattern: str = "wazuh-alerts-*"
    wazuh_poll_interval_seconds: int = 5
    wazuh_poll_batch_size: int = 100
    wazuh_indexer_verify_tls: bool = True
    wazuh_ca_bundle_path: str = "/etc/ssl/certs/wazuh-ca.pem"
    wazuh_first_run_lookback_minutes: int = 5

    # Wazuh Active Response dispatch (Phase 11)
    wazuh_ar_enabled: bool = False
    wazuh_manager_url: str = "https://wazuh-manager:55000"
    wazuh_manager_user: str = "wazuh-wui"
    wazuh_manager_password: str = ""
    wazuh_ar_timeout_seconds: int = 10


settings = Settings()
