"""Settings (Pydantic v2 BaseSettings) for the LLMux gateway."""

from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from llmux.core.errors import ConfigurationError


def _parse_str_list(value: object) -> list[str]:
    """Parse a JSON-or-CSV list of strings; ``None``/empty → ``[]``."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            return [str(v) for v in json.loads(s)]
        return [v.strip() for v in s.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    raise ValueError("expected a JSON or comma-separated string")


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

    # OpenAI provider settings (provider-routing-functional-slice / PR1).
    # Model validator fails fast with ``ConfigurationError`` when ``openai``
    # is enabled with an empty key, empty model list, or non-http(s) URL.
    openai_api_key: Annotated[
        SecretStr | None, Field(alias="OPENAI_API_KEY", default=None)
    ]
    openai_base_url: Annotated[
        str, Field(alias="OPENAI_BASE_URL", default="https://api.openai.com/v1")
    ]
    openai_models: Annotated[
        list[str], NoDecode, Field(alias="OPENAI_MODELS", default_factory=list)
    ]
    openai_timeout_s: Annotated[
        float, Field(alias="OPENAI_TIMEOUT_S", default=30.0, gt=0.0)
    ]

    @field_validator("llmux_providers_configured", mode="before")
    @classmethod
    def _parse_providers(cls, value: object) -> list[str]:
        return _parse_str_list(value)

    @field_validator("openai_models", mode="before")
    @classmethod
    def _parse_openai_models(cls, value: object) -> list[str]:
        return _parse_str_list(value)

    @model_validator(mode="after")
    def _validate_openai_when_enabled(self) -> Settings:
        """Fail-fast ``ConfigurationError`` when openai is mis-configured."""
        if "openai" not in self.llmux_providers_configured:
            return self
        key_value = (
            self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        )
        if not key_value:
            raise ConfigurationError(
                "OPENAI_API_KEY is required when 'openai' is enabled",
                missing_key="OPENAI_API_KEY",
                provider="openai",
            )
        if not self.openai_models:
            raise ConfigurationError(
                "OPENAI_MODELS must list at least one model when 'openai' is enabled",
                missing_field="OPENAI_MODELS",
                provider="openai",
            )
        parsed = urlparse(self.openai_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConfigurationError(
                "OPENAI_BASE_URL must be an http(s) URL with a host",
                invalid_field="OPENAI_BASE_URL",
                provider="openai",
            )
        return self
