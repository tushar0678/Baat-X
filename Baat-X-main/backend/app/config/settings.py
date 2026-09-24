from __future__ import annotations


import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["dev", "staging", "prod", "test"]

# Every list field must be CsvList AND listed in the _split_csv validator
# below. Adding one without the other reintroduces the JSONDecodeError-at-boot
# bug, which is silent until something sets that variable.
CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---------------- Core ----------------
    app_name: str = "BaatX"
    app_tagline: str = "You talk. BaatX remembers, updates, and reminds."
    environment: Environment = "dev"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    allowed_origins: CsvList = Field(default_factory=lambda: ["*"])
    trusted_hosts: CsvList = Field(default_factory=lambda: ["*"])

    # ---------------- Database ----------------
    database_url: str = "postgresql+asyncpg://baatx:baatx@localhost:5432/baatx"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle_seconds: int = 1800
    db_echo: bool = False

    # ---------------- Redis / queue ----------------
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "baatx:jobs"
    job_max_tries: int = 5
    job_timeout_seconds: int = 3600  # 60+ minute recordings are supported

    # ---------------- Auth ----------------
    jwt_secret: str = "change-me-in-every-environment"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 30
    password_min_length: int = 8

    # ---------------- Rate limiting ----------------
    rate_limit_default: str = "300/minute"
    rate_limit_ai: str = "30/minute"
    rate_limit_auth: str = "20/minute"

    # ---------------- Audio / storage ----------------
    storage_provider: Literal["azure_blob", "s3", "gcs", "local"] = "azure_blob"
    azure_storage_account_url: str = ""
    azure_storage_container: str = "baatx-temp-audio"
    azure_storage_connection_string: str = ""
    local_storage_dir: str = "./.local-storage"
    audio_max_bytes: int = 200 * 1024 * 1024  # 200 MB
    audio_temp_ttl_minutes: int = 60
    audio_allowed_extensions: CsvList = Field(
        default_factory=lambda: ["mp3", "m4a", "wav", "aac", "amr", "ogg"]
    )
    audio_allowed_mime_types: CsvList = Field(
        default_factory=lambda: [
            "audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/wav",
            "audio/x-wav", "audio/wave", "audio/aac", "audio/amr", "audio/3gpp",
            "audio/ogg", "application/ogg",
        ]
    )
    delete_audio_after_processing: bool = True
    retain_transcripts: bool = False

    # ---------------- AI providers ----------------
    stt_provider: Literal["azure_speech", "openai_compatible", "google", "aws", "null"] = (
        "azure_speech"
    )
    llm_provider: Literal["azure_openai", "openai_compatible", "null"] = "azure_openai"

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_use_managed_identity: bool = True

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_stt_model: str = "whisper-1"

    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_endpoint: str = ""
    stt_candidate_locales: CsvList = Field(default_factory=lambda: ["hi-IN", "en-IN"])

    # ---------------- STT host (may differ from the LLM host) ----------------
    # Left blank these inherit the openai_* values above, so a single-provider
    # setup needs no extra config. Set them when STT lives elsewhere - e.g.
    # Gemini for chat plus Groq for Whisper, which is the free/budget stack.
    # Gemini has no /audio/transcriptions endpoint, so without this split every
    # audio import 404s.
    stt_base_url: str = ""
    stt_api_key: str = ""
    stt_model: str = ""
    stt_max_part_bytes: int = 24 * 1024 * 1024  # Groq free tier caps at 25 MB

    llm_timeout_seconds: int = 120
    llm_max_output_tokens: int = 4096
    llm_temperature: float = 0.1
    transcript_chunk_chars: int = 9000
    transcript_chunk_overlap_chars: int = 400

    # ---------------- Confidence policy ----------------
    confidence_high: float = 0.90
    confidence_medium: float = 0.60
    confidence_autosave_min: float = 0.60

    # ---------------- WhatsApp ----------------
    whatsapp_enabled: bool = False
    whatsapp_api_base: str = "https://graph.facebook.com/v21.0"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""

    # ---------------- Observability ----------------
    log_level: str = "INFO"
    log_json: bool = True
    applicationinsights_connection_string: str = ""

    @field_validator(
        "allowed_origins",
        "trusted_hosts",
        "stt_candidate_locales",
        "audio_allowed_extensions",
        "audio_allowed_mime_types",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Parse a list from an environment string.

        Accepts:
            "*"                          -> ["*"]
            "a.com,b.com"                -> ["a.com", "b.com"]
            "  a.com , b.com  "          -> ["a.com", "b.com"]
            '["a.com","b.com"]'          -> ["a.com", "b.com"]
            ""                           -> []

        Values that are already lists (the Python defaults) pass through
        untouched.
        """
        if not isinstance(v, str):
            return v

        text = v.strip()
        if not text:
            return []

        # NoDecode means pydantic no longer parses JSON for us, so accept it
        # here - some people do write env vars as JSON arrays.
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed]
            except json.JSONDecodeError:
                pass  # fall through to CSV parsing

        return [item.strip() for item in text.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    # ---------------- Resolved STT config ----------------
    @property
    def resolved_stt_base_url(self) -> str:
        return self.stt_base_url or self.openai_base_url

    @property
    def resolved_stt_api_key(self) -> str:
        return self.stt_api_key or self.openai_api_key

    @property
    def resolved_stt_model(self) -> str:
        return self.stt_model or self.openai_stt_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
