"""Runtime acceptance tests: Settings, Tracing."""

from __future__ import annotations

from typing import Any, cast

import pytest
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import ValidationError

from llmux.config import Settings
from llmux.observability.tracing import build_tracer, shutdown_tracer

_ENV = (
    "LLMUX_HOST",
    "LLMUX_PORT",
    "LLMUX_VERSION",
    "LLMUX_PROVIDERS_CONFIGURED",
    "OTEL_SERVICE_NAME",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)
_BASE: dict[str, Any] = {
    "llmux_host": "0.0.0.0",
    "llmux_port": 8000,
    "llmux_version": "1.2.3",
    "llmux_providers_configured": ["openai", "anthropic"],
    "otel_service_name": "llmux",
    "otel_exporter_otlp_endpoint": "",
}


def _settings(**overrides: Any) -> Settings:
    return Settings.model_construct(**{**_BASE, **overrides})


def _reset_otel() -> None:
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # noqa: SLF001
    trace._TRACER_PROVIDER = None  # noqa: SLF001


def test_settings_defaults_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in _ENV:
        monkeypatch.delenv(v, raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.llmux_host == "0.0.0.0" and s.llmux_port == 8000
    assert s.llmux_providers_configured == [] and s.otel_exporter_otlp_endpoint == ""


def test_settings_providers_accepts_json_and_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", '["openai","anthropic"]')
    assert Settings().llmux_providers_configured == ["openai", "anthropic"]  # type: ignore[call-arg]
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "")
    assert Settings().llmux_providers_configured == []  # type: ignore[call-arg]


def test_settings_port_rejects_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLMUX_PORT", "0")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_build_tracer_is_noop_when_endpoint_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_otel()
    captured: list[Any] = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: captured.append(p))
    build_tracer(_settings(otel_exporter_otlp_endpoint=""))
    assert captured == []


def test_build_tracer_configures_sdk_provider_when_endpoint_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_otel()
    captured: list[Any] = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: captured.append(p))
    build_tracer(
        _settings(
            otel_exporter_otlp_endpoint="http://otel:4318",
            otel_service_name="llmux-prod",
        )
    )
    provider = cast("TracerProvider", captured[0])
    assert provider.resource.attributes.get("service.name") == "llmux-prod"
    multi = provider._active_span_processor
    assert any(isinstance(sp, BatchSpanProcessor) for sp in multi._span_processors)
    assert any(
        isinstance(cast("Any", sp).span_exporter, OTLPSpanExporter)
        for sp in multi._span_processors
    )


def test_shutdown_tracer_is_safe_when_no_sdk_provider() -> None:
    _reset_otel()
    shutdown_tracer()
