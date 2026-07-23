"""Unit 2 tests: Settings, Tracing, /v1 routes, app factory."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import ValidationError

from llmux.api.chat import NOT_IMPLEMENTED_ERROR, chat_router
from llmux.api.health import health_router
from llmux.api.models import models_router
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


def _s(**kw: Any) -> Settings:
    return Settings.model_construct(**{**_BASE, **kw})


def _reset_otel() -> None:
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # noqa: SLF001
    trace._TRACER_PROVIDER = None  # noqa: SLF001


def _client(router: Any, settings: Any = None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    if settings is not None:
        app.state.settings = settings
    return TestClient(app)


# Settings ================================================================


def test_settings_defaults_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in _ENV:
        monkeypatch.delenv(v, raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.llmux_host == "0.0.0.0"
    assert s.llmux_port == 8000
    assert s.llmux_providers_configured == []
    assert s.otel_exporter_otlp_endpoint == ""


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


# Tracing =================================================================


def test_build_tracer_is_noop_when_endpoint_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_otel()
    captured: list[Any] = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: captured.append(p))
    build_tracer(_s(otel_exporter_otlp_endpoint=""))
    assert captured == []


def test_build_tracer_configures_sdk_provider_when_endpoint_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_otel()
    captured: list[Any] = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: captured.append(p))
    build_tracer(
        _s(
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


# /v1/health + /v1/models ================================================


def test_health_returns_required_fields_json_envelope() -> None:
    r = _client(health_router, _s()).get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "version": "1.2.3",
        "providers_configured": ["openai", "anthropic"],
    }
    assert r.headers["content-type"].startswith("application/json")


def test_health_supports_empty_providers() -> None:
    r = _client(
        health_router, _s(llmux_version="0.1.0", llmux_providers_configured=[])
    ).get("/v1/health")
    assert r.json() == {"status": "ok", "version": "0.1.0", "providers_configured": []}


def test_models_returns_openai_envelope_with_empty_data() -> None:
    r = _client(models_router).get("/v1/models")
    assert r.status_code == 200
    assert r.json() == {"object": "list", "data": []}


# /v1/chat/completions ===================================================


@pytest.mark.parametrize("s", [False, True, None], ids=["false", "true", "omitted"])
def test_chat_501_for_all_stream_modes(s: object) -> None:
    body: dict[str, object] = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "hi"}],
    }
    if s is not None:
        body["stream"] = s
    r = _client(chat_router).post("/v1/chat/completions", json=body)
    assert r.status_code == 501
    assert r.headers["content-type"].startswith("application/json")
    assert "text/event-stream" not in r.headers["content-type"]
    assert "data:" not in r.text
    assert r.json() == NOT_IMPLEMENTED_ERROR


# App factory + conftest client fixture ==================================


def test_create_app_stores_settings_and_exports_module_level_app() -> None:
    from llmux import main as m

    settings = _s()
    app = m.create_app(settings=settings)
    assert isinstance(app, FastAPI) and app.state.settings is settings
    assert isinstance(m.app, FastAPI)


def test_create_app_resolves_settings_and_runs_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for v in _ENV:
        monkeypatch.delenv(v, raising=False)
    from llmux.main import create_app

    app = create_app()
    assert app.state.settings is not None
    with TestClient(app):
        pass


def test_create_app_mounts_all_three_v1_routes() -> None:
    from llmux.main import create_app

    c = TestClient(create_app(settings=_s()))
    assert c.get("/v1/health").status_code == 200
    assert c.get("/v1/models").status_code == 200
    assert (
        c.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
        ).status_code
        == 501
    )


def test_client_fixture_from_conftest_reaches_all_v1_routes(client: TestClient) -> None:
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/models").status_code == 200
    assert (
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
        ).status_code
        == 501
    )
