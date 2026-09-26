"""All configuration comes from environment variables. See .env.example."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ingest.types import Limits


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field("development", description="development | staging | production")

    # Database. The login role must be a member of atlas_app (the migration grants this).
    database_url: str
    db_app_role: str = "atlas_app"
    db_pool_max: int = 10

    # Clerk sign-in. The issuer is your Clerk Frontend API URL.
    clerk_issuer: str
    clerk_jwks_url: str | None = None
    clerk_authorized_parties: str = "http://localhost:3000"

    # Object storage (S3, Cloudflare R2, MinIO…).
    storage_bucket: str
    storage_endpoint_url: str | None = None
    storage_region: str = "auto"
    storage_access_key_id: str
    storage_secret_access_key: str
    # "AES256" for Amazon S3. Leave empty for Cloudflare R2 (always encrypted at rest) and local MinIO.
    storage_server_side_encryption: str | None = None

    # Web app origins allowed to call the API (comma-separated).
    web_origins: str = "http://localhost:3000"

    # Limits.
    max_upload_mb: int = 25
    max_rows: int = 20_000
    raw_file_retention_days: int = 7
    max_active_parses_per_org: int = 3
    parse_timeout_seconds: int = 120
    parse_memory_mb: int = 1024

    # AI review of pairs the rules can't decide (optional). Without a key,
    # analysis still runs and those pairs stay under "needs review".
    anthropic_api_key: str | None = None
    ai_review_model: str = "claude-opus-5"
    ai_max_pairs_per_dataset: int = 2000
    ai_batch_size: int = 20

    @property
    def jwks_url(self) -> str:
        return self.clerk_jwks_url or self.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"

    @property
    def authorized_parties(self) -> list[str]:
        return [p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def limits(self) -> Limits:
        return Limits(max_bytes=self.max_upload_bytes, max_rows=self.max_rows)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
