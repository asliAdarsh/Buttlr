"""Application settings.

Every setting is optional: Buttlr boots with no cloud account, using ``AUTH_MODE=dev``
and the in-memory/file store. Production deployments flip ``AUTH_MODE=firebase`` and
``STORE_BACKEND=firestore``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AuthMode = Literal["dev", "firebase"]
StoreBackend = Literal["auto", "firestore", "memory"]
Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- application -------------------------------------------------------
    app_name: str = "Buttlr"
    version: str = "0.1.0"
    environment: Environment = "development"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    # NoDecode: the value is a plain comma-separated list, not JSON. Without it,
    # pydantic-settings rejects the string before the validator below ever runs.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    )

    # ---- logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # ---- auth --------------------------------------------------------------
    auth_mode: AuthMode = "dev"
    dev_auth_secret: str = "buttlr-dev-secret-change-me-in-production"
    dev_auth_ttl_hours: int = 24 * 7
    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None
    firebase_credentials_json: str | None = None

    # ---- storage -----------------------------------------------------------
    store_backend: StoreBackend = "auto"
    firestore_emulator_host: str | None = None
    memory_store_path: str = ".data/buttlr-store.json"

    # ---- secrets -----------------------------------------------------------
    # Fernet key used to encrypt integration credentials at rest. When unset, a key is
    # derived from ``dev_auth_secret`` so local development still encrypts at rest.
    encryption_key: str | None = None

    # ---- runtime -----------------------------------------------------------
    max_agent_steps: int = 12
    tool_timeout_seconds: float = 60.0
    execution_timeout_seconds: float = 900.0
    execution_workers: int = 4
    planner_temperature: float = 0.2
    max_observation_chars: int = 6000

    # ---- models ------------------------------------------------------------
    default_provider: str = "auto"
    default_model: str = "auto"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_default_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_default_model: str = "claude-3-5-sonnet-latest"
    google_api_key: str | None = None
    google_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    google_default_model: str = "gemini-2.0-flash"
    ollama_base_url: str | None = None
    ollama_default_model: str = "qwen2.5:7b"
    estimated_cost_per_1k_input: float = 0.0
    estimated_cost_per_1k_output: float = 0.0

    # ---- integrations ------------------------------------------------------
    # Optional deployment-wide OAuth apps. A workspace can register its own under
    # Integrations → OAuth apps and needs none of these; provider credentials themselves are
    # never read from the environment.
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    oauth_redirect_base_url: str = "http://localhost:8000"

    # ---- scheduler ---------------------------------------------------------
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept both ``a,b`` and a real list, so `.env` stays readable."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def resolved_store_backend(self) -> Literal["firestore", "memory"]:
        """``auto`` means Firestore when this service actually holds credentials for it.

        Deliberately *not* keyed off ``firebase_project_id``: that is needed to verify ID
        tokens, and turning Firebase Authentication on must not drag the datastore with it.
        Without credentials the memory store is used, and ``STORE_BACKEND=firestore`` is still
        available for deployments that authenticate through Application Default Credentials.
        """
        if self.store_backend != "auto":
            return self.store_backend
        if self.firestore_emulator_host:
            return "firestore"
        if self.firebase_credentials_json or self.firebase_credentials_path:
            return "firestore"
        return "memory"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
