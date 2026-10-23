"""Worker configuration, read from the environment (prefix ``IGS_WORKER_``)."""

import base64

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from igs_common.temporal import DEFAULT_NAMESPACE


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IGS_WORKER_", env_file=".env", extra="ignore", populate_by_name=True
    )

    temporal_address: str = Field(
        default="localhost:7233",
        validation_alias=AliasChoices("IGS_WORKER_TEMPORAL_ADDRESS", "TEMPORAL_ADDRESS"),
    )
    temporal_namespace: str = Field(
        default=DEFAULT_NAMESPACE,
        validation_alias=AliasChoices("IGS_WORKER_TEMPORAL_NAMESPACE", "TEMPORAL_NAMESPACE"),
    )
    task_queue_flows: str = "flows"
    task_queue_ingestion: str = "ingestion"

    # AES-256 key (base64) for the payload codec. Empty disables encryption, which is only
    # allowed outside production: coach and lead data must never sit in Temporal in clear text.
    # Same key as the API (IGS_TEMPORAL_CODEC_KEY), so both sides can read each other's payloads.
    codec_key: str = Field(
        default="", validation_alias=AliasChoices("IGS_WORKER_CODEC_KEY", "IGS_TEMPORAL_CODEC_KEY")
    )
    codec_key_id: str = Field(
        default="k1",
        validation_alias=AliasChoices("IGS_WORKER_CODEC_KEY_ID", "IGS_TEMPORAL_CODEC_KEY_ID"),
    )
    environment: str = "local"

    otel_enabled: bool = False

    # Postgres for domain actions and the outbox. Empty = in-memory sinks (tests, demos).
    database_url: str = Field(
        default="", validation_alias=AliasChoices("IGS_WORKER_DATABASE_URL", "DATABASE_URL")
    )

    # Continue-as-new after this many node runs in one run (Temporal history stays small).
    max_node_runs_per_run: int = Field(default=2000, ge=10)
    # Outputs larger than this are stored outside Temporal and passed by reference.
    inline_output_max_bytes: int = Field(default=256 * 1024, ge=1024)

    @field_validator("codec_key")
    @classmethod
    def _key_is_256_bits(cls, v: str) -> str:
        if v and len(base64.b64decode(v)) != 32:
            raise ValueError("codec_key must be 32 bytes, base64-encoded")
        return v
