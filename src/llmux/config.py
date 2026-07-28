"""Settings (Pydantic v2 BaseSettings) for the LLMux gateway."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
