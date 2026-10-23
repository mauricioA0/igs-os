"""Service settings.

Values come from environment variables prefixed with ``IGS_`` (and from ``.env`` in local dev).
On Cloud Run, secrets are mounted from Secret Manager as env vars; the secret names are:

| Env var                | Secret Manager secret      |
|------------------------|----------------------------|
| ``IGS_DATABASE_URL``   | ``igs-core-database-url``  |
| ``IGS_OPENAI_API_KEY`` | ``openai-api-key``         |
| ``IGS_PROPOSAL_SIGNING_KEY`` | ``igs-proposal-signing-key`` |
| ``IGS_TEMPORAL_CODEC_KEY`` | ``igs-temporal-codec-key`` (shared with the worker) |
| ``IGS_INTAKE_HMAC_SECRET`` | ``igs-intake-hmac-secret`` (shared with the form/mail forwarder) |

Nothing secret is ever read from the request or sent to the browser.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from igs_common.temporal import DEFAULT_NAMESPACE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IGS_", env_file=".env", extra="ignore", populate_by_name=True
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = "postgresql+asyncpg://igs:igs@localhost:5433/igs"

    # Requests without credentials run as the public demo tenant (read-only demo, no login).
    # Unset → on everywhere except production, where it must be enabled explicitly
    # (IGS_DEMO_MODE=true) for the public demo deployment.
    demo_mode: bool | None = None
    # MCP runs a session manager inside the app lifespan; tests that drive the lifespan from
    # a module-scoped fixture (another task) turn it off.
    mcp_enabled: bool = True
    demo_tenant_slug: str = "igs"

    # Vercel web app + local dev. Preview deployments match the regex.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str | None = r"https://igs-os(-[a-z0-9-]+)?\.vercel\.app"

    # Absolute base for links in the morning digest (email). Empty → links stay relative.
    web_base_url: str = ""

    openai_api_key: SecretStr | None = None
    proposal_signing_key: SecretStr | None = None

    # Temporal (flow executions). The client connects lazily on first use.
    temporal_address: str = Field(
        default="localhost:7233",
        validation_alias=AliasChoices("IGS_TEMPORAL_ADDRESS", "TEMPORAL_ADDRESS"),
    )
    temporal_namespace: str = Field(
        default=DEFAULT_NAMESPACE,
        validation_alias=AliasChoices("IGS_TEMPORAL_NAMESPACE", "TEMPORAL_NAMESPACE"),
    )
    # Payload codec key (base64 AES-256), the same one the worker uses. Required in production.
    temporal_codec_key: SecretStr | None = None
    temporal_codec_key_id: str = "k1"
    temporal_task_queue_flows: str = "flows"
    # Run the outbox dispatcher inside the API process (local dev). In the cloud it runs as
    # its own deployment: `python -m igs_core.events.dispatcher`.
    run_outbox_dispatcher: bool = False

    # POST /v1/imports: the AI column mapper is off unless enabled here *and* asked for.
    import_llm_mapping: bool = False
    import_max_bytes: int = 5 * 1024 * 1024
    # Lead intake (POST /v1/intake/form, /v1/intake/email). The site's server (or a mail
    # forwarder) signs requests with the HMAC secret; a browser posting the form directly sends
    # the public site key from an allowed origin. With neither configured, intake only works in
    # demo mode, for the demo tenant.
    intake_hmac_secret: SecretStr | None = None
    intake_site_key: str | None = None
    intake_allowed_origins: list[str] = Field(default_factory=list)
    intake_tenant_slug: str | None = None  # unset → demo_tenant_slug
    intake_timezone: str = "America/New_York"  # the US sales team's business day

    page_size_default: int = 50
    page_size_max: int = 200

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.demo_mode is None:
            self.demo_mode = self.environment != "production"
        if self.environment == "production":
            # The API must run tenant queries under the non-owner role so Postgres RLS applies;
            # as the table owner RLS is silently skipped (docs/architecture/security.md).
            if not os.environ.get("IGS_DB_APP_ROLE"):
                raise ValueError("IGS_DB_APP_ROLE is required in production (RLS)")
            if self.temporal_codec_key is None:
                raise ValueError("IGS_TEMPORAL_CODEC_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
