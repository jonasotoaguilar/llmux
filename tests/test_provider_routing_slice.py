"""Provider Routing Vertical Slice — PR1 tests (RED/GREEN, behavior-first)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from llmux.config import Settings
from llmux.core.errors import (
    ConfigurationError,
    LLMuxError,
    ProviderSelectionError,
    UpstreamError,
    UpstreamTimeoutError,
)
from llmux.core.providers.base import (
    CompletionResult,
    HealthStatus,
    ModelInfo,
    ProviderAdapter,
)
from llmux.core.providers.openai import OpenAIAdapter
from llmux.core.providers.registry import ProviderRegistry, build_providers


def _ok_response(content: str = "hi") -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    models: tuple[str, ...] = ("gpt-4o-mini",),
) -> tuple[OpenAIAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        OpenAIAdapter(
            client=client,
            api_key=SecretStr("test-key"),
            base_url="https://api.openai.com/v1",
            models=models,
            timeout_s=10.0,
        ),
        client,
    )


def _openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODELS", "gpt-4o-mini")


# Settings (1.1/1.2) ======================================================


def test_settings_openai_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODELS", "OPENAI_TIMEOUT_S"):
        monkeypatch.delenv(v, raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.openai_api_key.get_secret_value() == ""
    assert str(s.openai_base_url).rstrip("/") == "https://api.openai.com/v1"
    assert s.openai_models == ["gpt-4o-mini", "gpt-4o"]
    assert s.openai_timeout_s == 30.0


def test_settings_openai_models_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODELS", '["gpt-4","gpt-3.5-turbo"]')
    assert Settings().openai_models == ["gpt-4", "gpt-3.5-turbo"]  # type: ignore[call-arg]


def test_settings_openai_timeout_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "0")
    with pytest.raises(Exception):  # noqa: B017, PT011
        Settings()  # type: ignore[call-arg]


def test_settings_openai_key_required_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError) as exc:
        Settings()  # type: ignore[call-arg]
    assert "OPENAI_API_KEY" in exc.value.message


# Errors (1.3/1.4) ========================================================


@pytest.mark.parametrize(
    "cls,status,etype",
    [
        (ConfigurationError, 502, "configuration_error"),
        (ProviderSelectionError, 400, "invalid_request_error"),
        (UpstreamError, 502, "upstream_error"),
        (UpstreamTimeoutError, 504, "upstream_timeout_error"),
    ],
)
def test_llmux_error_status_and_envelope(
    cls: type[LLMuxError], status: int, etype: str
) -> None:
    err = cls("boom")
    assert err.status_code == status
    assert issubclass(cls, LLMuxError)
    env = err.to_openai_envelope()
    inner = env["error"]
    assert isinstance(inner, dict)
    assert inner["type"] == etype and inner["message"] == "boom"
    assert inner["param"] is None and inner["code"] == etype


# OpenAI adapter (1.5/1.6) ===============================================


@pytest.mark.asyncio
async def test_openai_adapter_satisfies_protocol() -> None:
    adapter, client = _adapter(lambda r: httpx.Response(200, json={}))
    try:
        assert isinstance(adapter, ProviderAdapter)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openai_complete_returns_completion_result() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_ok_response())

    adapter, client = _adapter(handler)
    try:
        result = await adapter.complete(
            "gpt-4o-mini", [{"role": "user", "content": "hi"}]
        )
    finally:
        await client.aclose()
    assert isinstance(result, CompletionResult)
    assert (result.content, result.model, result.finish_reason) == (
        "hi",
        "gpt-4o-mini",
        "stop",
    )
    assert (result.prompt_tokens, result.completion_tokens) == (5, 1)
    req = captured["request"]
    assert req.headers["Authorization"] == "Bearer test-key"
    body = json.loads(req.content.decode())
    assert body["model"] == "gpt-4o-mini" and body["stream"] is False
    assert str(req.url) == "https://api.openai.com/v1/chat/completions"


def test_openai_complete_stream_raises_not_implemented() -> None:
    adapter, _ = _adapter(lambda r: httpx.Response(200, json={}))
    with pytest.raises(NotImplementedError):
        adapter.complete_stream("gpt-4o-mini", [])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_factory,exc_type",
    [
        (
            lambda: (
                lambda r: (_ for _ in ()).throw(
                    httpx.TimeoutException("sim", request=r)
                )
            ),
            UpstreamTimeoutError,
        ),
        (lambda: lambda r: httpx.Response(500, json={"error": "boom"}), UpstreamError),
        (
            lambda: lambda r: httpx.Response(200, json={"unexpected": "shape"}),
            UpstreamError,
        ),
    ],
)
async def test_openai_complete_maps_failures(
    handler_factory: Callable[[], Callable[[httpx.Request], httpx.Response]],
    exc_type: type[Exception],
) -> None:
    adapter, client = _adapter(handler_factory())
    try:
        with pytest.raises(exc_type):
            await adapter.complete("gpt-4o-mini", [{"role": "user", "content": "x"}])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openai_models_returns_configured_models() -> None:
    adapter, client = _adapter(
        lambda r: httpx.Response(200, json={}), models=("gpt-4o-mini", "gpt-4o")
    )
    try:
        models = await adapter.models()
    finally:
        await client.aclose()
    assert tuple(m.id for m in models) == ("gpt-4o-mini", "gpt-4o")
    assert all(isinstance(m, ModelInfo) and m.provider == "openai" for m in models)


@pytest.mark.asyncio
async def test_openai_health_reports_status() -> None:
    adapter, client = _adapter(lambda r: httpx.Response(200, json={"data": []}))
    try:
        health = await adapter.health()
    finally:
        await client.aclose()
    assert isinstance(health, HealthStatus) and health.healthy is True


# Registry (1.7/1.8) ======================================================


@pytest.mark.asyncio
async def test_registry_empty_when_no_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "")
    registry = build_providers(Settings())  # type: ignore[call-arg]
    try:
        assert len(registry) == 0 and isinstance(registry, ProviderRegistry)
    finally:
        await registry.aclose()


@pytest.mark.asyncio
async def test_registry_contains_openai_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _openai_env(monkeypatch)
    registry = build_providers(Settings())  # type: ignore[call-arg]
    try:
        assert len(registry) == 1
        assert isinstance(registry[0], OpenAIAdapter)
        assert all(
            isinstance(a, OpenAIAdapter) and a.name == "openai" for a in registry
        )
    finally:
        await registry.aclose()


@pytest.mark.asyncio
async def test_registry_aclose_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    _openai_env(monkeypatch)
    registry = build_providers(Settings())  # type: ignore[call-arg]
    await registry.aclose()
    await registry.aclose()  # must not raise
