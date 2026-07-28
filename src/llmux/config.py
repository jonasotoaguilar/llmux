"""Settings (Pydantic v2 BaseSettings) for the LLMux gateway."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from llmux.core.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )
    llmux_host: Annotated[str, Field(alias="LLMUX_HOST")] = "0.0.0.0"
    llmux_port: Annotated[int, Field(alias="LLMUX_PORT", ge=1, le=65535)] = 8000
    llmux_version: Annotated[str, Field(alias="LLMUX_VERSION")] = "0.1.0"
    llmux_providers_configured: Annotated[
        list[str],
        NoDecode,
        Field(alias="LLMUX_PROVIDERS_CONFIGURED", default_factory=list),
    ]
    otel_service_name: Annotated[str, Field(alias="OTEL_SERVICE_NAME")] = "llmux"
    otel_exporter_otlp_endpoint: Annotated[
        str, Field(alias="OTEL_EXPORTER_OTLP_ENDPOINT", default="")
    ] = ""

    # OpenAI provider — per PR1 of provider-routing-vertical-slice.
    # Defaults match the design contract; missing key with the provider
    # enabled is a fail-fast ConfigurationError at construction time.
    openai_api_key: Annotated[SecretStr, Field(alias="OPENAI_API_KEY", default="")] = (
        SecretStr("")
    )
    openai_base_url: Annotated[
        str, Field(alias="OPENAI_BASE_URL", default="https://api.openai.com/v1")
    ] = "https://api.openai.com/v1"
    openai_models: Annotated[
        list[str],
        NoDecode,
        Field(
            alias="OPENAI_MODELS",
            default_factory=lambda: ["gpt-4o-mini", "gpt-4o"],
        ),
    ]
    openai_timeout_s: Annotated[
        float, Field(alias="OPENAI_TIMEOUT_S", gt=0.0, default=30.0)
    ] = 30.0

    @field_validator("llmux_providers_configured", mode="before")
    @classmethod
    def _parse_providers(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            s = value.strip()
            if s.startswith("["):
                return [str(v) for v in json.loads(s)]
            return [v.strip() for v in s.split(",") if v.strip()]
        if isinstance(value, list):
            return [str(v) for v in value]
        raise ValueError("LLMUX_PROVIDERS_CONFIGURED must be a list or string")

    @field_validator("openai_models", mode="before")
    @classmethod
    def _parse_openai_models(cls, value: object) -> list[str]:
        default = ["gpt-4o-mini", "gpt-4o"]
        if value is None or value == "":
            return default
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return default
            if s.startswith("["):
                return [str(v) for v in json.loads(s)]
            return [v.strip() for v in s.split(",") if v.strip()]
        if isinstance(value, list):
            return [str(v) for v in value]
        raise ValueError("OPENAI_MODELS must be a list or string")

    @field_validator("openai_base_url", mode="before")
    @classmethod
    def _parse_openai_base_url(cls, value: object) -> str:
        if value is None:
            return "https://api.openai.com/v1"
        s = str(value).strip()
        return s or "https://api.openai.com/v1"

    @model_validator(mode="after")
    def _validate_openai_required(self) -> Settings:
        """Fail-fast when the openai provider is enabled without a key."""
        if (
            "openai" in self.llmux_providers_configured
            and not self.openai_api_key.get_secret_value()
        ):
            raise ConfigurationError(
                "OPENAI_API_KEY is required when 'openai' is enabled",
                missing_key="OPENAI_API_KEY",
                provider="openai",
            )
        return self
