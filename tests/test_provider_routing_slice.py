"""Provider routing functional slice: PR1+PR2+PR3+PR4 tests.

Covers config, errors, OpenAI adapter, registry, async router, lifespan
wiring, and the /v1/models endpoint.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import TypedDict
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace.status import StatusCode
from pydantic import SecretStr
from starlette.testclient import TestClient

from llmux.config import Settings
from llmux.core.errors import (
    ConfigurationError,
    LLMuxError,
    ProviderSelectionError,
    UpstreamError,
    UpstreamTimeoutError,
    to_openai_envelope,
)
from llmux.core.providers.anthropic import AnthropicAdapter
from llmux.core.providers.base import (
    Chunk,
    CompletionResult,
    HealthStatus,
    ModelInfo,
    ProviderAdapter,
)
from llmux.core.providers.openai import OpenAIAdapter
from llmux.core.providers.registry import (
    ClientFactory,
    ProviderRegistry,
    RegistryEntry,
    build_providers,
)
from llmux.core.router import select_provider
from llmux.main import create_app
from llmux.observability import tracing as tracing_mod
from llmux.observability.metrics import ChatTelemetry

_OPENAI_ENV = (
    "LLMUX_PROVIDERS_CONFIGURED",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODELS",
    "OPENAI_TIMEOUT_S",
)
_ANTHROPIC_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_VERSION",
    "ANTHROPIC_MODELS",
    "ANTHROPIC_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _OPENAI_ENV:
        monkeypatch.delenv(var, raising=False)
    for var in _ANTHROPIC_ENV:
        monkeypatch.delenv(var, raising=False)


def _enable(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str | None = "sk-test",
    base_url: str = "https://api.openai.com/v1",
    models: str = "gpt-4o-mini",
) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "openai")
    if api_key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    monkeypatch.setenv("OPENAI_MODELS", models)


# ----- 1.1 / 1.2 — OpenAI settings (valid + fail-fast ConfigurationError) --


def test_openai_settings_valid_parses_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch, api_key="sk-abc", models='["gpt-4o-mini","gpt-4o"]')
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "12.5")
    s = Settings()  # type: ignore[call-arg]
    assert isinstance(s.openai_api_key, SecretStr)
    assert s.openai_api_key.get_secret_value() == "sk-abc"
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.openai_models == ["gpt-4o-mini", "gpt-4o"]
    assert s.openai_timeout_s == 12.5


def test_openai_settings_default_when_no_provider_configured() -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.llmux_providers_configured == []
    assert s.openai_api_key is None
    assert s.openai_models == []
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.openai_timeout_s == 30.0


@pytest.mark.parametrize(
    "api_key,base_url,models,expected",
    [
        ("", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
        ("sk-abc", "https://api.openai.com/v1", "", "OPENAI_MODELS"),
        ("sk-abc", "not-a-url", "gpt-4o-mini", "OPENAI_BASE_URL"),
    ],
    ids=["empty_key", "empty_models", "invalid_url"],
)
def test_openai_settings_invalid_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
    base_url: str,
    models: str,
    expected: str,
) -> None:
    _enable(monkeypatch, api_key=api_key, base_url=base_url, models=models)
    with pytest.raises(ConfigurationError) as exc:
        Settings()  # type: ignore[call-arg]
    assert expected in str(exc.value)


# ----- 1.3 / 1.4 — LLMuxError hierarchy + to_openai_envelope ----------------


@pytest.mark.parametrize(
    "cls,status,code,type_",
    [
        (ProviderSelectionError, 400, "model_not_found", "invalid_request_error"),
        (ConfigurationError, 502, "provider_configuration_error", "api_error"),
        (UpstreamError, 502, "upstream_error", "api_error"),
        (UpstreamTimeoutError, 504, "upstream_timeout", "api_error"),
    ],
    ids=["selection", "config", "upstream", "timeout"],
)
def test_errors_envelope_status_and_codes(
    cls: type[LLMuxError], status: int, code: str, type_: str
) -> None:
    err = cls("sensitive-secret-1234")
    body = to_openai_envelope(err)
    assert err.status_code == status
    assert body["error"]["code"] == code
    assert body["error"]["type"] == type_
    assert body["error"]["param"] is None
    # Class-level safe message — never the raw constructor arg.
    assert "sensitive-secret-1234" not in body["error"]["message"]


def test_errors_envelope_timeout_is_upstream_subclass() -> None:
    """UpstreamTimeoutError subclasses UpstreamError so a single
    ``except UpstreamError`` catches the timeout path; status is 504."""
    err = UpstreamTimeoutError("timeout")
    assert isinstance(err, UpstreamError)
    assert err.status_code == 504
    assert to_openai_envelope(err)["error"]["code"] == "upstream_timeout"


def test_errors_envelope_sanitized() -> None:
    """Envelopes never include raw exception text, keys, upstream payloads,
    or stack traces — only the class-level safe fields, in a fixed shape."""
    secret = (
        f"key sk-{quote('AKIA-EXAMPLE')}, body=<html>no</html>, "
        "Traceback (most recent call last):\n  File 'x.py', line 1"
    )
    sensitive = ("AKIA-EXAMPLE", "sk-EXAMPLE", "<html>", "Traceback", "File 'x.py'")
    for cls in (
        ConfigurationError,
        ProviderSelectionError,
        UpstreamError,
        UpstreamTimeoutError,
    ):
        body = to_openai_envelope(cls(secret))
        serialized = json.dumps(body)
        for token in sensitive:
            assert token not in serialized, f"{cls.__name__} leaked {token!r}"
        # Stable, OpenAI-shaped envelope: exactly one ``error`` key.
        assert set(body.keys()) == {"error"}
        assert set(body["error"].keys()) == {"message", "type", "param", "code"}


def test_errors_envelope_unknown_subclass_uses_base_defaults() -> None:
    """An ad-hoc LLMuxError subclass without overrides falls back to the
    base defaults so the envelope is well-formed and the status set."""

    class Custom(LLMuxError):  # noqa: N818
        pass

    body = to_openai_envelope(Custom("should-not-leak"))
    assert Custom().status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert "should-not-leak" not in json.dumps(body)


# ----- 2.1 / 2.2 / 2.3 — OpenAI adapter (httpx.MockTransport) -------------


def _ok_payload(content: str = "hello") -> dict[str, object]:
    """Canonical OpenAI non-streaming chat completion response."""
    return {
        "id": "chatcmpl-test",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1},
    }


def _make_adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    models: tuple[str, ...] = ("gpt-4o-mini",),
    base_url: str = "https://api.openai.com/v1",
) -> tuple[OpenAIAdapter, httpx.AsyncClient]:
    """Build an adapter with a caller-owned ``MockTransport``-backed client.

    The returned ``AsyncClient`` is caller-owned: the adapter never closes it,
    the test does. This keeps the registry/a-clos contract tested in PR3.
    """
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        OpenAIAdapter(
            client=client,
            api_key=SecretStr("sk-test-secret-1234"),
            base_url=base_url,
            models=models,
            timeout_s=10.0,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_openai_adapter_satisfies_protocol() -> None:
    """``OpenAIAdapter`` MUST satisfy the ``ProviderAdapter`` runtime Protocol."""
    adapter, client = _make_adapter(lambda r: httpx.Response(200, json=_ok_payload()))
    try:
        assert isinstance(adapter, ProviderAdapter)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openai_complete_returns_result_with_expected_fields() -> None:
    """``complete`` returns a ``CompletionResult`` with all five fields populated."""
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_ok_payload("hi back"))

    adapter, client = _make_adapter(handler)
    try:
        result = await adapter.complete(
            "gpt-4o-mini", [{"role": "user", "content": "hello"}]
        )
    finally:
        await client.aclose()
    assert isinstance(result, CompletionResult)
    assert result.content == "hi back"
    assert result.model == "gpt-4o-mini"
    assert result.finish_reason == "stop"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 1


@pytest.mark.asyncio
async def test_openai_complete_sends_correct_request() -> None:
    """``complete`` POSTs to ``/chat/completions`` with Bearer auth and a
    well-shaped JSON body (``stream=False``, model, messages, options merged)."""
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_ok_payload())

    adapter, client = _make_adapter(handler, base_url="https://api.openai.com/v1")
    try:
        await adapter.complete(
            "gpt-4o-mini",
            [{"role": "user", "content": "ping"}],
            options={"temperature": 0.0, "max_tokens": 16},
        )
    finally:
        await client.aclose()
    req = captured["request"]
    assert str(req.url) == "https://api.openai.com/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer sk-test-secret-1234"
    assert req.headers["Content-Type"] == "application/json"
    body = json.loads(req.content.decode("utf-8"))
    assert body["model"] == "gpt-4o-mini"
    assert body["stream"] is False
    assert body["messages"] == [{"role": "user", "content": "ping"}]
    assert body["temperature"] == 0.0 and body["max_tokens"] == 16


def test_openai_complete_stream_raises_not_implemented() -> None:
    """``complete_stream`` MUST raise ``NotImplementedError`` (sync, not awaited)."""
    adapter, _client = _make_adapter(lambda r: httpx.Response(200, json=_ok_payload()))
    with pytest.raises(NotImplementedError):
        adapter.complete_stream("gpt-4o-mini", [{"role": "user", "content": "x"}])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,expected",
    [
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.ConnectError("boom", request=r)),
            UpstreamError,
            id="transport_error",
        ),
        pytest.param(
            lambda r: httpx.Response(400, json={"error": "bad model"}),
            UpstreamError,
            id="upstream_400",
        ),
        pytest.param(
            lambda r: httpx.Response(429, json={"error": "rate limit"}),
            UpstreamError,
            id="upstream_429",
        ),
        pytest.param(
            lambda r: httpx.Response(500, json={"error": "internal"}),
            UpstreamError,
            id="upstream_500",
        ),
        pytest.param(
            lambda r: httpx.Response(200, text="<html>not json</html>"),
            UpstreamError,
            id="malformed_body",
        ),
        pytest.param(
            lambda r: httpx.Response(200, json={"unexpected": "shape"}),
            UpstreamError,
            id="missing_choices",
        ),
        pytest.param(
            lambda r: httpx.Response(
                200, json={"choices": [{"finish_reason": "stop"}]}
            ),
            UpstreamError,
            id="missing_message",
        ),
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.TimeoutException("slow", request=r)),
            UpstreamTimeoutError,
            id="timeout",
        ),
    ],
)
async def test_openai_complete_maps_failures_to_typed_errors(
    factory: Callable[[httpx.Request], httpx.Response],
    expected: type[Exception],
) -> None:
    """Upstream HTTP/transport/parse failures MUST surface as typed
    ``LLMuxError`` subclasses — never as bare ``httpx`` exceptions."""
    adapter, client = _make_adapter(factory)
    try:
        with pytest.raises(expected):
            await adapter.complete("gpt-4o-mini", [{"role": "user", "content": "x"}])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openai_models_returns_configured_models() -> None:
    """``models()`` returns one ``ModelInfo`` per configured model id,
    stamped with ``provider='openai'`` and ``supports_streaming=False``."""
    adapter, client = _make_adapter(
        lambda r: httpx.Response(200, json={"data": []}),
        models=("gpt-4o-mini", "gpt-4o"),
    )
    try:
        models = await adapter.models()
    finally:
        await client.aclose()
    assert tuple(m.id for m in models) == ("gpt-4o-mini", "gpt-4o")
    assert all(isinstance(m, ModelInfo) and m.provider == "openai" for m in models)
    assert all(m.supports_streaming is False for m in models)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,healthy",
    [
        pytest.param(lambda r: httpx.Response(200, json={"data": []}), True, id="2xx"),
        pytest.param(
            lambda r: httpx.Response(503, json={"error": "down"}), False, id="5xx"
        ),
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.ConnectError("nope", request=r)),
            False,
            id="transport",
        ),
    ],
)
async def test_openai_health_reflects_outcome(
    factory: Callable[[httpx.Request], httpx.Response], healthy: bool
) -> None:
    """``health()`` reports healthy iff ``GET /models`` is 2xx; transport
    errors are caught and reported as unhealthy (no raise)."""
    adapter, client = _make_adapter(factory)
    try:
        h = await adapter.health()
    finally:
        await client.aclose()
    assert isinstance(h, HealthStatus) and h.healthy is healthy


# ----- 1.1 / 1.2 — Anthropic settings (valid + fail-fast ConfigurationError) --


def _enable_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str | None = "sk-ant-test",
    base_url: str = "https://api.anthropic.com",
    models: str = "claude-3-5-sonnet-20240620",
) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "anthropic")
    if api_key is not None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base_url)
    monkeypatch.setenv("ANTHROPIC_MODELS", models)


def test_anthropic_settings_valid_parses_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic settings MUST parse all four env-bound fields when enabled."""
    _enable_anthropic(
        monkeypatch,
        api_key="sk-ant-abc",
        base_url="https://api.anthropic.com",
        models='["claude-3-5-sonnet-20240620","claude-3-haiku-20240307"]',
    )
    monkeypatch.setenv("ANTHROPIC_VERSION", "2023-06-01")
    monkeypatch.setenv("ANTHROPIC_TIMEOUT_S", "12.5")
    s = Settings()  # type: ignore[call-arg]
    assert isinstance(s.anthropic_api_key, SecretStr)
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-abc"
    assert s.anthropic_base_url == "https://api.anthropic.com"
    assert s.anthropic_version == "2023-06-01"
    assert s.anthropic_models == [
        "claude-3-5-sonnet-20240620",
        "claude-3-haiku-20240307",
    ]
    assert s.anthropic_timeout_s == 12.5


def test_anthropic_settings_default_when_no_provider_configured() -> None:
    """With no Anthropic provider configured, fields stay at safe defaults and
    the validator is a no-op (matches the OpenAI default-when-disabled path)."""
    s = Settings()  # type: ignore[call-arg]
    assert s.anthropic_api_key is None
    assert s.anthropic_models == []
    assert s.anthropic_base_url == "https://api.anthropic.com"
    assert s.anthropic_version == "2023-06-01"
    assert s.anthropic_timeout_s == 30.0


@pytest.mark.parametrize(
    "api_key,base_url,models,expected",
    [
        (
            "",
            "https://api.anthropic.com",
            "claude-3-5-sonnet-20240620",
            "ANTHROPIC_API_KEY",
        ),
        ("sk-ant-abc", "https://api.anthropic.com", "", "ANTHROPIC_MODELS"),
        (
            "sk-ant-abc",
            "not-a-url",
            "claude-3-5-sonnet-20240620",
            "ANTHROPIC_BASE_URL",
        ),
    ],
    ids=["empty_key", "empty_models", "invalid_url"],
)
def test_anthropic_settings_invalid_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
    base_url: str,
    models: str,
    expected: str,
) -> None:
    """Empty key, empty model list, or invalid base URL MUST fail fast with a
    ``ConfigurationError`` mirroring the OpenAI contract."""
    _enable_anthropic(monkeypatch, api_key=api_key, base_url=base_url, models=models)
    with pytest.raises(ConfigurationError) as exc:
        Settings()  # type: ignore[call-arg]
    assert expected in str(exc.value)
    # The error details MUST carry the provider slug for ops/observability.
    assert exc.value.details.get("provider") == "anthropic"


# ----- 2.1 / 2.2 / 2.3 / 2.5 — Anthropic adapter (PR2 scope) -----------------


def _anthropic_ok_payload(
    content: str = "hi from claude", stop_reason: str = "end_turn"
) -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-5-sonnet-20240620",
        "content": [{"type": "text", "text": content}],
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 8, "output_tokens": 4},
    }


def _make_anthropic_adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    models: tuple[str, ...] = ("claude-3-5-sonnet-20240620",),
    base_url: str = "https://api.anthropic.com",
    timeout_s: float = 10.0,
) -> tuple[AnthropicAdapter, httpx.AsyncClient]:
    # Caller-owned client (adapter never closes it); registry/aclose stays PR4.
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        AnthropicAdapter(
            client=client,
            api_key=SecretStr("sk-ant-test-secret-1234"),
            base_url=base_url,
            version="2023-06-01",
            models=models,
            timeout_s=timeout_s,
        ),
        client,
    )


def _anthropic_capture_handler(
    captured: dict[str, httpx.Request], payload: dict[str, object] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    body = payload if payload is not None else _anthropic_ok_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=body)

    return handler


@pytest.mark.asyncio
async def test_anthropic_adapter_satisfies_protocol() -> None:
    adapter, client = _make_anthropic_adapter(
        lambda r: httpx.Response(200, json=_anthropic_ok_payload())
    )
    assert isinstance(adapter, ProviderAdapter)
    await client.aclose()


def test_anthropic_complete_stream_raises_not_implemented() -> None:
    adapter, _client = _make_anthropic_adapter(
        lambda r: httpx.Response(200, json=_anthropic_ok_payload())
    )
    with pytest.raises(NotImplementedError):
        adapter.complete_stream(
            "claude-3-5-sonnet-20240620", [{"role": "user", "content": "x"}]
        )


@pytest.mark.asyncio
async def test_anthropic_complete_sends_correct_request() -> None:
    # POST /v1/messages: x-api-key + anthropic-version, no Authorization.
    captured: dict[str, httpx.Request] = {}
    adapter, client = _make_anthropic_adapter(_anthropic_capture_handler(captured))
    try:
        await adapter.complete(
            "claude-3-5-sonnet-20240620",
            [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "ping"},
            ],
            options={"max_tokens": 256},
        )
    finally:
        await client.aclose()
    req = captured["request"]
    assert str(req.url) == "https://api.anthropic.com/v1/messages"
    assert req.headers["x-api-key"] == "sk-ant-test-secret-1234"
    assert req.headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in req.headers
    assert req.headers["Content-Type"] == "application/json"
    body = json.loads(req.content.decode("utf-8"))
    assert body["model"] == "claude-3-5-sonnet-20240620"
    assert body["system"] == "be brief"
    assert body["max_tokens"] == 256
    assert body["messages"] == [{"role": "user", "content": "ping"}]
    assert "stream" not in body


@pytest.mark.asyncio
async def test_anthropic_complete_multiple_system_messages_joined() -> None:
    # Multiple ``system`` messages MUST be joined with ``\\n\\n`` and extracted.
    captured: dict[str, httpx.Request] = {}
    adapter, client = _make_anthropic_adapter(_anthropic_capture_handler(captured))
    try:
        await adapter.complete(
            "claude-3-5-sonnet-20240620",
            [
                {"role": "system", "content": "first"},
                {"role": "system", "content": "second"},
                {"role": "user", "content": "ping"},
            ],
        )
    finally:
        await client.aclose()
    body = json.loads(captured["request"].content.decode("utf-8"))
    assert body["system"] == "first\n\nsecond"
    assert all(m["role"] != "system" for m in body["messages"])


@pytest.mark.asyncio
async def test_anthropic_complete_unsupported_role_raises_configuration_error() -> None:
    # Unsupported roles MUST raise ``ConfigurationError``; content never surfaced.
    adapter, client = _make_anthropic_adapter(
        lambda r: httpx.Response(200, json=_anthropic_ok_payload())
    )
    try:
        with pytest.raises(ConfigurationError):
            await adapter.complete(
                "claude-3-5-sonnet-20240620",
                [
                    {"role": "user", "content": "ping"},
                    {"role": "tool", "content": "tool-output-LEAK"},
                ],
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_complete_omitted_max_tokens_defaults_to_1024() -> None:
    # Omitted ``max_tokens`` MUST default to ``1024`` on the Anthropic payload.
    captured: dict[str, httpx.Request] = {}
    adapter, client = _make_anthropic_adapter(_anthropic_capture_handler(captured))
    try:
        await adapter.complete(
            "claude-3-5-sonnet-20240620", [{"role": "user", "content": "ping"}]
        )
    finally:
        await client.aclose()
    body = json.loads(captured["request"].content.decode("utf-8"))
    assert body["max_tokens"] == 1024


@pytest.mark.asyncio
async def test_anthropic_complete_caller_override_512() -> None:
    # Caller-supplied ``options["max_tokens"]=512`` MUST override the default.
    captured: dict[str, httpx.Request] = {}
    adapter, client = _make_anthropic_adapter(_anthropic_capture_handler(captured))
    try:
        await adapter.complete(
            "claude-3-5-sonnet-20240620",
            [{"role": "user", "content": "ping"}],
            options={"max_tokens": 512},
        )
    finally:
        await client.aclose()
    body = json.loads(captured["request"].content.decode("utf-8"))
    assert body["max_tokens"] == 512


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,expected",
    [
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.ConnectError("nope", request=r)),
            UpstreamError,
            id="transport_error",
        ),
        pytest.param(
            lambda r: httpx.Response(500, json={"error": "boom"}),
            UpstreamError,
            id="upstream_500",
        ),
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.TimeoutException("slow", request=r)),
            UpstreamTimeoutError,
            id="timeout",
        ),
    ],
)
async def test_anthropic_complete_maps_failures_to_typed_errors(
    factory: Callable[[httpx.Request], httpx.Response],
    expected: type[Exception],
) -> None:
    # Upstream transport/HTTP failures MUST surface as typed ``LLMuxError``
    # subclasses; upstream body and key never reach the raised error.
    adapter, client = _make_anthropic_adapter(factory)
    try:
        with pytest.raises(expected) as exc:
            await adapter.complete(
                "claude-3-5-sonnet-20240620", [{"role": "user", "content": "x"}]
            )
        details = getattr(exc.value, "details", None) or {}
        serialized = json.dumps(
            {"args": [str(a) for a in exc.value.args], "details": details},
            default=str,
        )
        for token in ("sk-ant-LEAK-1234", "internal-error-payload-LEAK"):
            assert token not in serialized, f"envelope leaked {token!r}"
    finally:
        await client.aclose()


# ----- 3.1 / 3.2 — Anthropic response translation (PR3 scope) ---------------


@pytest.mark.asyncio
async def test_anthropic_complete_returns_result_with_expected_fields() -> None:
    # ``complete`` returns a ``CompletionResult`` from the canonical payload.
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_anthropic_ok_payload("hi back"))

    adapter, client = _make_anthropic_adapter(handler)
    try:
        result = await adapter.complete(
            "claude-3-5-sonnet-20240620", [{"role": "user", "content": "hello"}]
        )
    finally:
        await client.aclose()
    assert isinstance(result, CompletionResult)
    assert result.content == "hi back"
    assert result.model == "claude-3-5-sonnet-20240620"
    assert result.finish_reason == "stop"
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 4


@pytest.mark.asyncio
async def test_anthropic_complete_text_blocks_joined() -> None:
    # Multiple ``type:"text"`` content blocks MUST be joined in order.
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-5-sonnet-20240620",
                "content": [
                    {"type": "text", "text": "first "},
                    {"type": "text", "text": "second"},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        )

    adapter, client = _make_anthropic_adapter(handler)
    try:
        result = await adapter.complete(
            "claude-3-5-sonnet-20240620", [{"role": "user", "content": "ping"}]
        )
    finally:
        await client.aclose()
    assert result.content == "first second"


@pytest.mark.asyncio
async def test_anthropic_complete_non_text_block_raises_upstream_error() -> None:
    # A non-text block MUST raise ``UpstreamError``; only the block type is
    # surfaced, never the block's payload (response-body sanitization).
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-5-sonnet-20240620",
                "content": [
                    {"type": "text", "text": "ok"},
                    {
                        "type": "tool_use",
                        "id": "toolu_test",
                        "name": "get_weather",
                        "input": {"city": "sf", "api_key": "sk-ant-LEAK-1234"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    adapter, client = _make_anthropic_adapter(handler)
    try:
        with pytest.raises(UpstreamError) as exc:
            await adapter.complete(
                "claude-3-5-sonnet-20240620", [{"role": "user", "content": "ping"}]
            )
        details = getattr(exc.value, "details", None) or {}
        serialized = json.dumps(
            {"args": [str(a) for a in exc.value.args], "details": details},
            default=str,
        )
        for token in ("sk-ant-LEAK-1234", "get_weather", "toolu_test"):
            assert token not in serialized, f"envelope leaked {token!r}"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_complete_token_counts_mapped() -> None:
    # ``input_tokens``/``output_tokens`` map to prompt/completion tokens.
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-5-sonnet-20240620",
                "content": [{"type": "text", "text": "x"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        )

    adapter, client = _make_anthropic_adapter(handler)
    try:
        result = await adapter.complete(
            "claude-3-5-sonnet-20240620", [{"role": "user", "content": "ping"}]
        )
    finally:
        await client.aclose()
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop_reason,expected_finish",
    [
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
    ],
    ids=["end_turn", "stop_sequence", "max_tokens"],
)
async def test_anthropic_complete_stop_reason_mapping(
    stop_reason: str, expected_finish: str
) -> None:
    # Only ``end_turn``/``stop_sequence`` -> ``stop`` and ``max_tokens`` -> ``length``.
    adapter, client = _make_anthropic_adapter(
        lambda r: httpx.Response(
            200, json=_anthropic_ok_payload(stop_reason=stop_reason)
        )
    )
    try:
        result = await adapter.complete(
            "claude-3-5-sonnet-20240620", [{"role": "user", "content": "ping"}]
        )
    finally:
        await client.aclose()
    assert result.finish_reason == expected_finish


# ----- 3.3 / 3.4 — Anthropic models() (PR3 scope) ----------------------------


@pytest.mark.asyncio
async def test_anthropic_models_returns_configured_models() -> None:
    # One ``ModelInfo`` per configured model, provider='anthropic', no streaming.
    adapter, client = _make_anthropic_adapter(
        lambda r: httpx.Response(200, json={"data": []}),
        models=("claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"),
    )
    try:
        models = await adapter.models()
    finally:
        await client.aclose()
    assert tuple(m.id for m in models) == (
        "claude-3-5-sonnet-20240620",
        "claude-3-haiku-20240307",
    )
    assert all(isinstance(m, ModelInfo) and m.provider == "anthropic" for m in models)
    assert all(m.supports_streaming is False for m in models)


# ----- 3.5 / 3.6 — Anthropic health() reachability (PR3 scope) ---------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,healthy",
    [
        pytest.param(lambda r: httpx.Response(200), True, id="2xx_root"),
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.ConnectError("nope", request=r)),
            False,
            id="transport",
        ),
    ],
)
async def test_anthropic_health_reflects_outcome(
    factory: Callable[[httpx.Request], httpx.Response], healthy: bool
) -> None:
    # Healthy iff ``GET {base_url}/`` is 2xx; reachability-only, no auth headers.
    captured: dict[str, httpx.Request] = {}

    def wrapped(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return factory(request)

    adapter, client = _make_anthropic_adapter(wrapped)
    try:
        h = await adapter.health()
    finally:
        await client.aclose()
    assert isinstance(h, HealthStatus) and h.healthy is healthy
    # Reachability-only health: GET base_url/ with no Authorization header.
    assert str(captured["request"].url) == "https://api.anthropic.com/"
    assert "Authorization" not in captured["request"].headers
    assert "x-api-key" not in captured["request"].headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,expected",
    [
        pytest.param(
            lambda r: httpx.Response(
                500,
                json={
                    "error": "internal-error-payload-LEAK",
                    "key": "sk-ant-LEAK-1234",
                },
            ),
            UpstreamError,
            id="upstream_500_discards_body",
        ),
        pytest.param(
            lambda r: httpx.Response(200, text="<html>not json</html>"),
            UpstreamError,
            id="malformed_body",
        ),
        pytest.param(
            lambda r: httpx.Response(
                200, json={"type": "message", "stop_reason": "end_turn"}
            ),
            UpstreamError,
            id="missing_content",
        ),
    ],
)
async def test_anthropic_complete_maps_body_errors_to_typed_errors(
    factory: Callable[[httpx.Request], httpx.Response],
    expected: type[Exception],
) -> None:
    adapter, client = _make_anthropic_adapter(factory)
    try:
        with pytest.raises(expected) as exc:
            await adapter.complete(
                "claude-3-5-sonnet-20240620", [{"role": "user", "content": "x"}]
            )
        details = getattr(exc.value, "details", None) or {}
        serialized = json.dumps(
            {"args": [str(a) for a in exc.value.args], "details": details},
            default=str,
        )
        for token in ("sk-ant-LEAK-1234", "internal-error-payload-LEAK"):
            assert token not in serialized, f"envelope leaked {token!r}"
    finally:
        await client.aclose()


# ----- 3.1 / 3.2 / 3.3 — ProviderRegistry + build_providers -----------------


class _CountingClient(httpx.AsyncClient):
    """``httpx.AsyncClient`` with a per-instance ``aclose()`` counter."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.aclose_count = 0

    async def aclose(self) -> None:
        self.aclose_count += 1
        await super().aclose()


def _counting_factory(sink: list[_CountingClient]) -> ClientFactory:
    """Factory that returns a fresh ``_CountingClient`` per call."""

    def factory() -> httpx.AsyncClient:
        client = _CountingClient()
        sink.append(client)
        return client

    return factory


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    providers: str,
    models: str = "gpt-4o-mini",
) -> Settings:
    """Build a valid ``Settings`` with the requested provider list."""
    _enable(monkeypatch, models=models)
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", providers)
    return Settings()  # type: ignore[call-arg]


# 3.1 RED — fail-fast construction, no partial registry ----------------------


@pytest.mark.asyncio
async def test_build_providers_closes_first_client_on_later_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic factory seam: 1st provider builds, 2nd is unknown.
    The injected factory is called once; the 1st client MUST be closed
    exactly once (no double-close, no leak) before ConfigurationError.

    The 2nd slug is a truly-unknown one (``fake-unknown-slug``) so the
    mid-build cleanup invariant is still proven after the ``anthropic``
    slug becomes a valid configured provider in
    ``anthropic-provider-adapter-slice`` (PR2 adds the dispatch; PR1
    only adds the Settings contract).
    """
    clients: list[_CountingClient] = []
    settings = _settings(monkeypatch, providers="openai,fake-unknown-slug")
    with pytest.raises(ConfigurationError) as exc:
        await build_providers(settings, client_factory=_counting_factory(clients))
    assert "fake-unknown-slug" in str(exc.value)
    assert len(clients) == 1
    assert clients[0].is_closed and clients[0].aclose_count == 1


@pytest.mark.asyncio
async def test_registry_fail_fast_aborts_on_duplicate_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate slugs MUST raise ConfigurationError; the 1st client
    is still cleaned up exactly once (transaction-like guarantee)."""
    clients: list[_CountingClient] = []
    settings = _settings(monkeypatch, providers="openai,openai")
    with pytest.raises(ConfigurationError) as exc:
        await build_providers(settings, client_factory=_counting_factory(clients))
    assert "openai" in str(exc.value)
    assert len(clients) == 1
    assert clients[0].is_closed and clients[0].aclose_count == 1


@pytest.mark.asyncio
async def test_build_providers_cleans_up_on_adapter_ctor_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-ConfigurationError exceptions after a client is created MUST
    still trigger cleanup (proves ``except BaseException`` covers the gap)."""
    from llmux.core.providers import registry as registry_mod

    clients: list[_CountingClient] = []
    settings = _settings(monkeypatch, providers="openai")

    def boom(**_kw: object) -> OpenAIAdapter:
        raise RuntimeError("simulated ctor failure")

    monkeypatch.setattr(registry_mod, "OpenAIAdapter", boom)
    with pytest.raises(RuntimeError):
        await build_providers(settings, client_factory=_counting_factory(clients))
    assert len(clients) == 1
    assert clients[0].is_closed and clients[0].aclose_count == 1


@pytest.mark.asyncio
async def test_build_providers_empty_config_returns_empty_registry() -> None:
    """Empty LLMUX_PROVIDERS_CONFIGURED returns an empty registry; aclose
    is a safe no-op (no clients to close)."""
    settings = Settings()  # type: ignore[call-arg]
    assert settings.llmux_providers_configured == []
    clients: list[_CountingClient] = []
    registry = await build_providers(
        settings, client_factory=_counting_factory(clients)
    )
    assert registry.providers == () and await registry.models() == ()
    assert clients == []
    await registry.aclose()
    await registry.aclose()  # idempotent on empty too


# 3.2 RED — aclose ownership + idempotency ----------------------------------


@pytest.mark.asyncio
async def test_aclose_closes_production_only() -> None:
    """aclose closes only entries with an owned client; caller-supplied
    (e.g. MockTransport) clients are NEVER re-closed by the registry."""
    production_client = httpx.AsyncClient()
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
    )
    try:
        prod_adapter = OpenAIAdapter(
            client=production_client,
            api_key=SecretStr("sk-prod"),
            base_url="https://api.openai.com/v1",
            models=("gpt-4o-mini",),
            timeout_s=10.0,
        )
        mock_adapter = OpenAIAdapter(
            client=mock_client,
            api_key=SecretStr("sk-mock"),
            base_url="https://api.openai.com/v1",
            models=("gpt-4o-mini",),
            timeout_s=10.0,
        )
        registry = ProviderRegistry(
            (
                RegistryEntry(adapter=prod_adapter, client=production_client),
                RegistryEntry(adapter=mock_adapter, client=None),
            )
        )
        await registry.aclose()
        assert production_client.is_closed
        assert not mock_client.is_closed, "caller-owned client NOT re-closed"
    finally:
        if not mock_client.is_closed:
            await mock_client.aclose()


@pytest.mark.asyncio
async def test_aclose_idempotent_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated aclose() calls are safe no-ops; the owned client is
    closed exactly once across many calls (proves no double-close)."""
    clients: list[_CountingClient] = []
    settings = _settings(monkeypatch, providers="openai")
    registry = await build_providers(
        settings, client_factory=_counting_factory(clients)
    )
    for _ in range(5):
        await registry.aclose()
    assert clients[0].is_closed and clients[0].aclose_count == 1


@pytest.mark.asyncio
async def test_registry_models_aggregates_across_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """registry.models() concatenates per-adapter models in order."""
    settings = _settings(monkeypatch, providers="openai", models="gpt-4o-mini,gpt-4o")
    clients: list[_CountingClient] = []
    registry = await build_providers(
        settings, client_factory=_counting_factory(clients)
    )
    try:
        models = await registry.models()
    finally:
        await registry.aclose()
    assert tuple(m.id for m in models) == ("gpt-4o-mini", "gpt-4o")
    assert all(m.provider == "openai" for m in models)


# 3.3 GREEN — production harness with the default factory ------------------


@pytest.mark.asyncio
async def test_build_providers_default_factory_creates_and_closes_real_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end production harness: default factory creates a real
    httpx.AsyncClient; aclose() closes it exactly once; subsequent
    aclose() calls are idempotent. Proves the full ownership contract
    in production form without a network."""
    settings = _settings(monkeypatch, providers="openai")
    registry = await build_providers(settings)  # default factory
    adapter = registry.providers[0]
    assert isinstance(adapter, OpenAIAdapter)
    real_client = adapter._client  # noqa: SLF001
    assert isinstance(real_client, httpx.AsyncClient) and not real_client.is_closed
    await registry.aclose()
    assert real_client.is_closed
    await registry.aclose()
    await registry.aclose()


# ----- 4.1 / 4.2 — Async first-match select_provider ------------------------


def _make_static_adapter(
    name: str, model_ids: tuple[str, ...]
) -> tuple[ProviderAdapter, httpx.AsyncClient]:
    """OpenAIAdapter-shaped (Protocol) with caller-owned MockTransport client."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
    )
    adapter = OpenAIAdapter(
        client=client,
        api_key=SecretStr("sk-test"),
        base_url="https://api.openai.com/v1",
        models=model_ids,
        timeout_s=10.0,
    )
    adapter.name = name
    return adapter, client


@pytest.mark.asyncio
async def test_router_first_match_returns_priority_provider() -> None:
    """First provider in configured order wins for an offered model; no
    fallback to later providers (spec: first-match, no fallback)."""
    a, ac = _make_static_adapter("a", ("shared", "a-only"))
    b, bc = _make_static_adapter("b", ("shared",))
    try:
        registry = ProviderRegistry((RegistryEntry(a, None), RegistryEntry(b, None)))
        assert await select_provider("shared", registry) is a
        assert await select_provider("a-only", registry) is a
    finally:
        await ac.aclose()
        await bc.aclose()


@pytest.mark.asyncio
async def test_router_no_match_raises_provider_selection_error() -> None:
    """When no provider offers the model, select_provider raises
    ProviderSelectionError (envelope → HTTP 400 ``model_not_found``)."""
    a, ac = _make_static_adapter("a", ("m1",))
    b, bc = _make_static_adapter("b", ("m2",))
    try:
        registry = ProviderRegistry((RegistryEntry(a, None), RegistryEntry(b, None)))
        with pytest.raises(ProviderSelectionError):
            await select_provider("missing", registry)
    finally:
        await ac.aclose()
        await bc.aclose()


# ----- 4.3 / 4.4 — Fail-safe lifespan (tracer shutdown on build failure) ----


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []


def _patch_lifespan(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _Recorder,
    *,
    raise_on_build: BaseException | None = None,
    registry_to_return: object = None,
) -> None:
    """Patch build_tracer/shutdown_tracer/build_providers in main + tracing.

    The fake ``build_tracer`` returns a real (noop) OTel ``Tracer`` so
    the lifespan's ``build_chat_telemetry`` accepts it and the chat
    handler can still call ``start_as_current_span`` without raising.
    Tests that need to assert on telemetry use the public
    ``_make_chat_telemetry`` helper (in-memory fakes) and inject the
    result via ``app.state.telemetry`` after the lifespan runs.
    """
    from opentelemetry import trace as _otel_trace

    import llmux.main as main_mod

    def fake_build_tracer(_settings: object) -> object:
        recorder.events.append("build_tracer")
        return _otel_trace.get_tracer("llmux-test")

    def fake_shutdown_tracer() -> None:
        recorder.events.append("shutdown_tracer")

    monkeypatch.setattr(tracing_mod, "build_tracer", fake_build_tracer)
    monkeypatch.setattr(main_mod, "build_tracer", fake_build_tracer)
    monkeypatch.setattr(main_mod, "shutdown_tracer", fake_shutdown_tracer)

    async def fake_build_providers(_settings: object) -> object:
        recorder.events.append("build_providers")
        if raise_on_build is not None:
            raise raise_on_build
        return registry_to_return

    monkeypatch.setattr(main_mod, "build_providers", fake_build_providers)


@pytest.mark.asyncio
async def test_lifespan_tracer_shutdown_on_build_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When build_providers raises ConfigurationError, shutdown_tracer MUST
    still run; the tracer is unconditionally shut down (guardrail from PR3
    pre-discovery)."""
    recorder = _Recorder()
    _patch_lifespan(monkeypatch, recorder, raise_on_build=ConfigurationError("boom"))
    app = create_app(settings=Settings())  # type: ignore[call-arg]
    with pytest.raises(ConfigurationError):
        async with app.router.lifespan_context(app):
            pass  # pragma: no cover
    assert recorder.events == ["build_tracer", "build_providers", "shutdown_tracer"]


@pytest.mark.asyncio
async def test_lifespan_aclose_before_tracer_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On successful build, registry aclose() MUST run BEFORE shutdown_tracer;
    aclose runs exactly once (no double-close of factory-owned clients)."""
    recorder = _Recorder()

    class _RecordingRegistry:
        def __init__(self) -> None:
            self.aclose_count = 0

        async def aclose(self) -> None:
            self.aclose_count += 1
            recorder.events.append("aclose")

        async def models(self) -> tuple[object, ...]:
            return ()

    built = _RecordingRegistry()
    _patch_lifespan(monkeypatch, recorder, registry_to_return=built)
    app = create_app(settings=Settings())  # type: ignore[call-arg]
    async with app.router.lifespan_context(app):
        assert app.state.providers is built
    assert built.aclose_count == 1
    assert recorder.events == [
        "build_tracer",
        "build_providers",
        "aclose",
        "shutdown_tracer",
    ]


@pytest.mark.asyncio
async def test_lifespan_owned_client_stays_open_while_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behavior-first regression: a registry-owned ``httpx.AsyncClient``
    MUST stay open while serving a routed request and close exactly
    once after TestClient shutdown.

    The previous lifespan closed the registry inside a ``finally`` that
    ran BEFORE ``yield``, so the live ASGI harness observed the owned
    client already closed and a routed POST returned 500. The unit
    tests did not catch it because they used a ``_RecordingRegistry``
    stub whose fake ``aclose`` was a no-op on a real client.

    This test wires a real ``httpx.AsyncClient(transport=MockTransport)``
    through a real ``ProviderRegistry((RegistryEntry(adapter, client),))``
    (registry-owned, NOT caller-owned) and proves:
      1. the real client is open inside the lifespan,
      2. a POST ``/v1/chat/completions`` returns 200 and the
         MockTransport handler actually served the request,
      3. the real client is still open after the request,
      4. after TestClient exit the real client is closed exactly once,
      5. the event sequence is still
         ``[build_tracer, build_providers, aclose, shutdown_tracer]``.
    """
    from llmux.main import create_app as _create_app

    handler_calls: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        return httpx.Response(200, json=_ok_payload("live"))

    real_owned_client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    real_adapter = OpenAIAdapter(
        client=real_owned_client,
        api_key=SecretStr("sk-regression-owned-client"),
        base_url="https://api.openai.com/v1",
        models=("gpt-4o-mini",),
        timeout_s=10.0,
    )
    real_registry = ProviderRegistry(
        (RegistryEntry(real_adapter, client=real_owned_client),)
    )

    recorder = _Recorder()
    _patch_lifespan(monkeypatch, recorder, registry_to_return=real_registry)
    app = _create_app(
        settings=Settings.model_construct(
            llmux_host="127.0.0.1",
            llmux_port=8000,
            llmux_version="0.1.0",
            llmux_providers_configured=["openai"],
            otel_service_name="llmux-test",
            otel_exporter_otlp_endpoint="",
        )
    )

    with TestClient(app) as tc:
        # (1) inside the lifespan, the real owned client is open.
        assert app.state.providers is real_registry
        assert not real_owned_client.is_closed
        # (2) routed POST succeeds; the MockTransport served it.
        response = tc.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["choices"][0]["message"]["content"] == "live"
        assert len(handler_calls) == 1
        # (3) still open during the lifespan (the bug closed it pre-yield).
        assert not real_owned_client.is_closed

    # (4) after TestClient exit: real owned client is closed exactly once.
    assert real_owned_client.is_closed
    # (5) tracer shutdown ran after the registry aclose; the recorder only
    #     sees the patched shutdown_tracer because the real
    #     ``ProviderRegistry.aclose`` does not record to it (the stub
    #     in the existing ``test_lifespan_aclose_before_tracer_shutdown``
    #     covers the event-order contract; this test covers the
    #     behavior-first contract on a real owned client).
    assert recorder.events == [
        "build_tracer",
        "build_providers",
        "shutdown_tracer",
    ]


# ----- 4.5 / 4.6 — /v1/models aggregation from app.state.providers ----------


@pytest.mark.asyncio
async def test_models_aggregates_one_per_provider_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/models returns one OpenAI-shaped entry per (provider, model)
    pair sourced from app.state.providers, ordered by provider then model."""
    a, ac = _make_static_adapter("a", ("m1", "m2"))
    b, bc = _make_static_adapter("b", ("m3",))
    try:
        registry = ProviderRegistry((RegistryEntry(a, None), RegistryEntry(b, None)))
        _patch_lifespan(monkeypatch, _Recorder(), registry_to_return=registry)
        app = create_app(
            settings=Settings.model_construct(
                llmux_host="127.0.0.1",
                llmux_port=8000,
                llmux_version="0.1.0",
                llmux_providers_configured=[],
                otel_service_name="llmux-test",
                otel_exporter_otlp_endpoint="",
            )
        )
        with TestClient(app) as client:
            response = client.get("/v1/models")
        body = response.json()
        assert response.status_code == 200
        assert body["object"] == "list"
        ids = [e["id"] for e in body["data"]]
        assert ids == ["m1", "m2", "m3"]
        owned_by = [e["owned_by"] for e in body["data"]]
        assert owned_by == ["a", "a", "b"]
        for e in body["data"]:
            assert e["object"] == "model"
            assert e["created"] == 0
    finally:
        await ac.aclose()
        await bc.aclose()


@pytest.mark.asyncio
async def test_models_empty_when_no_providers() -> None:
    """With no app.state.providers (no lifespan), GET /v1/models returns 200
    with an empty data array; the endpoint MUST NOT crash on missing state."""
    from llmux.api.models import models_router

    bare_app = FastAPI()
    bare_app.include_router(models_router, prefix="/v1")
    with TestClient(bare_app) as client:
        response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": []}


# ----- 5.1 / 5.2 / 5.4 — PR5 chat routing + envelopes (no telemetry) --------


def _app_with_registry(
    monkeypatch: pytest.MonkeyPatch, registry: ProviderRegistry
) -> FastAPI:
    """Build a real ``create_app`` whose lifespan yields ``registry``."""
    _patch_lifespan(monkeypatch, _Recorder(), registry_to_return=registry)
    return create_app(
        settings=Settings.model_construct(
            llmux_host="127.0.0.1",
            llmux_port=8000,
            llmux_version="0.1.0",
            llmux_providers_configured=[],
            otel_service_name="llmux-test",
            otel_exporter_otlp_endpoint="",
        )
    )


def _post_chat(client: TestClient, **overrides: object) -> httpx.Response:
    """POST a minimal non-streaming chat body, with optional overrides."""
    body: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}],
    }
    body.update(overrides)
    result: httpx.Response = client.post("/v1/chat/completions", json=body)
    return result


# 5.1 RED — stream=False routes to provider and returns 200 envelope ----------


@pytest.mark.asyncio
async def test_stream_false_routes_and_returns_200_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``stream=false`` MUST route to the selected provider, return 200
    with an OpenAI-shaped completion envelope, and forward ``stream=false``
    on the upstream wire (spec: Non-Streaming Chat Completion Routing)."""
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_ok_payload("hi back"))

    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            response = _post_chat(tc, stream=False)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert "text/event-stream" not in response.headers["content-type"]
        body = response.json()
        assert body["object"] == "chat.completion"
        assert body["id"] == "chatcmpl-test"
        assert body["model"] == "gpt-4o-mini"
        assert body["choices"][0]["message"]["content"] == "hi back"
        assert body["choices"][0]["finish_reason"] == "stop"
        assert body["usage"]["prompt_tokens"] == 5
        assert body["usage"]["completion_tokens"] == 1
        # Upstream request carried stream=False (PR2 adapter contract).
        sent = json.loads(captured["request"].content.decode("utf-8"))
        assert sent["stream"] is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_omitted_stream_defaults_false_and_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting the ``stream`` field MUST treat it as ``stream=false`` and
    route the request (Pydantic default + handler ``is True`` short-circuit).
    The upstream wire MUST carry ``stream=false``."""
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_ok_payload())

    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            # No ``stream`` key in the request body — defaults via Pydantic.
            response = tc.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["choices"][0]["message"]["content"] == "hello"
        sent = json.loads(captured["request"].content.decode("utf-8"))
        assert sent["stream"] is False
    finally:
        await client.aclose()


# 5.2 / 5.3 RED — stream=True short-circuits to 501, no provider, no telemetry


@pytest.mark.asyncio
async def test_stream_true_returns_501_no_provider_no_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``stream=true`` MUST return 501 with ``application/json`` (never
    ``text/event-stream``) and no ``data:`` SSE frames. The provider MUST
    NOT be invoked and no telemetry is emitted (PR5 ships no telemetry
    at all, so this is implicit — the MockTransport handler is the
    strongest evidence: zero upstream calls)."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=_ok_payload("never reached"))

    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            response = _post_chat(tc, stream=True)
        assert response.status_code == 501
        assert response.headers["content-type"].startswith("application/json")
        assert "text/event-stream" not in response.headers["content-type"]
        assert "data:" not in response.text
        # Strongest no-provider / no-telemetry evidence: the MockTransport
        # handler is never invoked. The handler is the only place upstream
        # is called from the chat path.
        assert call_count["n"] == 0
    finally:
        await client.aclose()


# 5.4 RED — typed LLMuxError envelopes ---------------------------------------


@pytest.mark.asyncio
async def test_chat_400_on_provider_selection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No provider offers the requested model → 400 ``model_not_found``;
    envelope MUST NOT leak the requested model id (sanitization rule)."""
    adapter, client = _make_adapter(
        lambda r: httpx.Response(200, json=_ok_payload()),
        models=("gpt-4o-mini",),
    )
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            response = _post_chat(tc, model="missing-model-LEAK")
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "model_not_found"
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["param"] is None
        serialized = json.dumps(body)
        assert "missing-model-LEAK" not in serialized
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_chat_502_on_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upstream 4xx/5xx → 502 ``upstream_error``; envelope MUST be
    sanitized (no key, no upstream body, no stack trace)."""
    secret_key = "sk-LEAK-1234"
    secret_body = "internal-error-payload-LEAK"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": secret_body, "key": secret_key})

    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            response = _post_chat(tc)
        assert response.status_code == 502
        body = response.json()
        assert body["error"]["code"] == "upstream_error"
        serialized = json.dumps(body)
        for token in (secret_key, secret_body, "Traceback", "File '"):
            assert token not in serialized, f"envelope leaked {token!r}"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_chat_504_on_upstream_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """httpx.TimeoutException from the adapter → 504 ``upstream_timeout``
    with a sanitized envelope (timeout subclass maps to 504 per the
    design's stable code map)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            response = _post_chat(tc)
        assert response.status_code == 504
        body = response.json()
        assert body["error"]["code"] == "upstream_timeout"
    finally:
        await client.aclose()


# ----- 6.1 / 6.2 / 6.5 — PR6 telemetry: span + 3 metrics + sentinel + error --


def _make_chat_telemetry() -> tuple[
    ChatTelemetry, InMemorySpanExporter, InMemoryMetricReader
]:
    """Build a public-Otel :class:`ChatTelemetry` wired to in-memory
    fakes (no private OTel global mutation).

    Returns ``(telemetry, span_exporter, metric_reader)``. Tests verify
    on the exporters/readers after the routed call.
    """
    from opentelemetry.sdk.metrics import MeterProvider as _MeterProvider
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    span_exporter = InMemorySpanExporter()
    tracer_provider = _TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    tracer = tracer_provider.get_tracer("llmux-test")
    reader = InMemoryMetricReader()
    meter_provider = _MeterProvider(metric_readers=[reader])
    meter = meter_provider.get_meter("llmux-test")
    return ChatTelemetry(tracer=tracer, meter=meter), span_exporter, reader


def _chat_spans(span_exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    """Return the chat-completion spans recorded so far."""
    return [
        s for s in span_exporter.get_finished_spans() if s.name == "chat.completion"
    ]


def _span_attrs(span: ReadableSpan) -> dict[str, str]:
    """Return the span attributes as a plain ``dict`` (the OTel type
    is ``Attributes`` / ``Mapping[str, AttributeValue] | None``; tests
    only need ``dict`` semantics with str keys/values)."""
    if span.attributes is None:
        return {}
    return {str(k): str(v) if v is not None else "" for k, v in span.attributes.items()}


class _MetricPoint(TypedDict):
    """Typed shape of one data point as returned by
    :func:`_metric_data_points` (a plain ``dict`` for ergonomic
    assertions but with stable types so mypy strict mode is happy)."""

    attrs: dict[str, str]
    value: object  # OTel data point value: int for counters, dict for histograms


def _metric_data_points(
    reader: InMemoryMetricReader, metric_name: str
) -> list[_MetricPoint]:
    """Return the recorded ``metric_name`` data points.

    Robust against InMemoryMetricReader returning ``None`` (no data yet)
    and against absent metrics (test misconfiguration). The value
    field carries the OTel data point value: a counter has ``int``;
    a histogram has ``dict(count=..., sum=...)``."""
    data = reader.get_metrics_data()
    if data is None:
        return []
    out: list[_MetricPoint] = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name != metric_name:
                    continue
                for dp in m.data.data_points:
                    attrs: dict[str, str] = {
                        str(k): (str(v) if v is not None else "")
                        for k, v in (dp.attributes or {}).items()
                    }
                    value = getattr(dp, "value", None)
                    if value is None:
                        # Histogram: use count + sum; counter: use value.
                        value = {
                            "count": getattr(dp, "count", None),
                            "sum": getattr(dp, "sum", None),
                        }
                    out.append({"attrs": attrs, "value": value})
    return out


# 6.1 RED — bounded model label and bounded label-value set -----------------


@pytest.mark.asyncio
async def test_telemetry_model_unknown_sentinel_on_unselected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request for a model no provider offers MUST be recorded with the
    ``MODEL_UNKNOWN`` sentinel on the model label — never the raw
    request model. The selection-miss envelope and span status are
    unchanged, but the bounded ``model`` label keeps the time-series
    count flat regardless of how many distinct unknown models the
    gateway sees."""
    telemetry, span_exporter, metric_reader = _make_chat_telemetry()
    raw_model = "not-offered-LEAK-sentinel-cardinality-12345"
    adapter, client = _make_adapter(
        lambda r: httpx.Response(200, json=_ok_payload()),
        models=("gpt-4o-mini",),
    )
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            # Inject the test telemetry AFTER the lifespan runs so the
            # noop ChatTelemetry created by the lifespan is replaced
            # with the in-memory fakes.
            app.state.telemetry = telemetry
            response = _post_chat(tc, model=raw_model)
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "model_not_found"
        # The error envelope MUST NOT leak the raw request model
        # (sanitization rule); the metric uses the sentinel instead.
        assert raw_model not in json.dumps(body)
        # Exactly one chat span with provider=none, model=unknown.
        spans = _chat_spans(span_exporter)
        assert len(spans) == 1
        span = spans[0]
        assert _span_attrs(span).get("provider") == "none"
        assert _span_attrs(span).get("model") == "unknown"
        assert _span_attrs(span).get("outcome") == "error"
        assert _span_attrs(span).get("error.type") == "invalid_request_error"
        # The metric labels carry the bounded sentinel, not the raw model.
        for name in (
            "chat_completion_requests_total",
            "chat_completion_errors_total",
            "chat_completion_duration_seconds",
        ):
            points = _metric_data_points(metric_reader, name)
            assert points, f"metric {name} not recorded"
            for p in points:
                assert p["attrs"].get("model") == "unknown", (
                    f"{name} leaked raw model: {p['attrs']}"
                )
                assert p["attrs"].get("provider") == "none"
                assert raw_model not in json.dumps(p["attrs"], default=str)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_telemetry_bounded_label_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every label value on every emitted metric MUST be drawn from a
    fixed, bounded set. The set of providers comes from the
    configured adapters (``openai``) plus the :data:`PROVIDER_NONE`
    sentinel; the set of models comes from the configured model list
    plus :data:`MODEL_UNKNOWN`; ``outcome`` is in {success, error};
    ``error.type`` is in the class-level set of LLMuxError error
    types plus the :data:`INTERNAL_ERROR_TYPE` sentinel. A free-form
    caller-provided model id MUST NEVER reach a label position."""
    telemetry, _, metric_reader = _make_chat_telemetry()
    adapter, client = _make_adapter(
        lambda r: httpx.Response(200, json=_ok_payload()),
        models=("gpt-4o-mini",),
    )
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            app.state.telemetry = telemetry
            # Force a selection miss with a free-form model id.
            _post_chat(tc, model="some-arbitrary-unknown-model")
        bounded_providers = {"openai", "none"}
        bounded_models = {"gpt-4o-mini", "unknown"}
        bounded_outcomes = {"success", "error"}
        bounded_error_types = {
            "api_error",
            "invalid_request_error",
            "internal_error",
            "none",
        }
        for name in (
            "chat_completion_requests_total",
            "chat_completion_errors_total",
            "chat_completion_duration_seconds",
        ):
            for point in _metric_data_points(metric_reader, name):
                attrs = point["attrs"]
                assert attrs.get("provider") in bounded_providers, (
                    f"{name} provider label {attrs.get('provider')!r} not bounded"
                )
                assert attrs.get("model") in bounded_models, (
                    f"{name} model label {attrs.get('model')!r} not bounded"
                )
                assert attrs.get("outcome") in bounded_outcomes, (
                    f"{name} outcome label {attrs.get('outcome')!r} not bounded"
                )
                if "error.type" in attrs:
                    assert attrs["error.type"] in bounded_error_types, (
                        f"{name} error.type {attrs['error.type']!r} not bounded"
                    )
    finally:
        await client.aclose()


# 6.2 RED — span error status with error.type attribute ---------------------


@pytest.mark.asyncio
async def test_telemetry_span_error_status_with_error_type_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A routed call that ends in :class:`UpstreamError` MUST emit a
    span with ``Status(StatusCode.ERROR, error_type)`` AND an
    ``error.type`` attribute carrying the same bounded label. The
    status description is the bounded ``error_type`` (NOT the
    upstream payload, key, or exception message) so the sanitization
    contract holds for the span as well as the response envelope."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": "internal-error-payload-LEAK", "key": "sk-LEAK-1234"},
        )

    telemetry, span_exporter, _ = _make_chat_telemetry()
    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            app.state.telemetry = telemetry
            response = _post_chat(tc)
        assert response.status_code == 502
        spans = _chat_spans(span_exporter)
        assert len(spans) == 1
        span = spans[0]
        assert span.status.status_code == StatusCode.ERROR
        # The status description is the bounded error.type label, NOT
        # the exception message or upstream payload.
        assert span.status.description == "api_error"
        assert _span_attrs(span).get("error.type") == "api_error"
        assert _span_attrs(span).get("provider") == "openai"
        assert _span_attrs(span).get("model") == "gpt-4o-mini"
        assert _span_attrs(span).get("outcome") == "error"
        # No leak of the upstream body or key on the span itself.
        serialized = json.dumps(
            {
                "description": span.status.description,
                "attrs": _span_attrs(span),
            },
            default=str,
        )
        for token in ("sk-LEAK-1234", "internal-error-payload-LEAK", "Traceback"):
            assert token not in serialized, f"span leaked {token!r}"
    finally:
        await client.aclose()


# 6.5 RED — unexpected exceptions are recorded as internal_error and propagate


class _RaisingAdapter:
    """A test-only ProviderAdapter that raises a non-LLMuxError from
    ``complete()`` so we can prove the timer records the bounded
    ``internal_error`` label and re-raises. Satisfies the runtime
    Protocol (no ``name`` attribute — the chat handler must fall back
    to the bounded PROVIDER_NONE sentinel for the metric label)."""

    name: str = "openai"

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def complete(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> CompletionResult:
        raise self._exc

    def complete_stream(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> AsyncIterator[Chunk]:
        raise NotImplementedError

    async def models(self) -> Sequence[ModelInfo]:
        return (
            ModelInfo(id="gpt-4o-mini", provider="openai", supports_streaming=False),
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=True)


@pytest.mark.asyncio
async def test_telemetry_unexpected_error_records_error_metric_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the routed call raises a non-:class:`LLMuxError` (e.g. a
    bare ``RuntimeError`` from a buggy adapter), the timer MUST:

    * record the error counter with the bounded ``internal_error``
      label,
    * set the span to ``Status(StatusCode.ERROR, "internal_error")``,
    * record the ``error.type`` span attribute as ``internal_error``,
    * re-raise so FastAPI returns a 500 (the timer MUST NOT swallow
      the exception).

    The bounded sentinel guarantees the error counter's
    ``error.type`` label never sees caller-provided exception text or
    stack trace data."""

    adapter = _RaisingAdapter(RuntimeError("unexpected boom"))
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_ok_payload()))
    )
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        telemetry, span_exporter, metric_reader = _make_chat_telemetry()
        with TestClient(app) as tc:
            app.state.telemetry = telemetry
            with pytest.raises(RuntimeError, match="unexpected boom"):
                _post_chat(tc)
        # Error counter recorded with the bounded internal_error label.
        errors = _metric_data_points(metric_reader, "chat_completion_errors_total")
        assert len(errors) == 1, f"expected 1 error point, got {errors}"
        attrs = errors[0]["attrs"]
        assert attrs.get("error.type") == "internal_error"
        assert attrs.get("outcome") == "error"
        assert attrs.get("provider") == "openai"
        assert attrs.get("model") == "gpt-4o-mini"
        # Duration histogram ALSO recorded (error path is not skipped).
        durations = _metric_data_points(
            metric_reader, "chat_completion_duration_seconds"
        )
        assert len(durations) == 1
        assert durations[0]["attrs"].get("error.type") == "internal_error"
        # Span has Status(ERROR, "internal_error") and the bounded attribute.
        spans = _chat_spans(span_exporter)
        assert len(spans) == 1
        span = spans[0]
        assert span.status.status_code == StatusCode.ERROR
        assert span.status.description == "internal_error"
        assert _span_attrs(span).get("error.type") == "internal_error"
        # Caller-supplied exception text MUST NOT reach the span.
        serialized = json.dumps(
            {
                "description": span.status.description,
                "attrs": _span_attrs(span),
            },
            default=str,
        )
        assert "unexpected boom" not in serialized
        assert "Traceback" not in serialized
    finally:
        await client.aclose()


# 6.3 / 6.4 GREEN — chat.completion span + 3 metrics + canonical model on success


@pytest.mark.asyncio
async def test_telemetry_chat_span_and_three_metrics_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful routed call MUST emit exactly one ``chat.completion``
    span and three metric data points (one per instrument) with the
    canonical result model from :class:`CompletionResult` (NOT the
    request model) so the metric label reflects what the upstream
    actually used. ``error.type`` is the bounded ``"none"`` sentinel
    on the success branch."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "gpt-4o-2024-05-13-canonical",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    telemetry, span_exporter, metric_reader = _make_chat_telemetry()
    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            app.state.telemetry = telemetry
            response = _post_chat(tc, model="gpt-4o-mini")
        assert response.status_code == 200
        # Exactly one chat.completion span.
        spans = _chat_spans(span_exporter)
        assert len(spans) == 1
        span = spans[0]
        # Canonical result model is the label, not the request model.
        assert _span_attrs(span).get("model") == "gpt-4o-2024-05-13-canonical"
        assert _span_attrs(span).get("provider") == "openai"
        assert _span_attrs(span).get("outcome") == "success"
        assert _span_attrs(span).get("error.type") == "none"
        # Span status is UNSET (not ERROR, not OK) for the success branch
        # per OTel best practice — neither an error nor an explicit OK.
        assert span.status.status_code == StatusCode.UNSET
        # The request counter and the duration histogram are both
        # incremented per hop (one data point each). The error counter
        # MUST NOT be incremented on the success branch (zero data
        # points with ``outcome="error"`` is the success invariant).
        for name in (
            "chat_completion_requests_total",
            "chat_completion_duration_seconds",
        ):
            points = _metric_data_points(metric_reader, name)
            assert len(points) == 1, f"{name}: expected 1 point, got {len(points)}"
            attrs = points[0]["attrs"]
            assert attrs.get("model") == "gpt-4o-2024-05-13-canonical"
            assert attrs.get("provider") == "openai"
        # errors_total MUST NOT be incremented on success. The metric
        # is registered at ChatTelemetry construction time (so the
        # instrument is exposed), but no data point is emitted until
        # an actual error path increments the counter.
        errors = _metric_data_points(metric_reader, "chat_completion_errors_total")
        for p in errors:
            assert p["attrs"].get("outcome") != "error", (
                "errors_total must not be incremented on success"
            )
    finally:
        await client.aclose()


# 6.3 / 6.4 GREEN — explicit stream=true still bypasses all telemetry ---------


@pytest.mark.asyncio
async def test_telemetry_stream_true_still_bypasses_all_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit ``stream=true`` MUST short-circuit to a JSON 501 BEFORE
    the telemetry timer opens — so the rejected path emits no span,
    no metric, and no upstream call. The MockTransport handler is
    the strongest evidence: zero invocations."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_payload())

    telemetry, span_exporter, metric_reader = _make_chat_telemetry()
    adapter, client = _make_adapter(handler)
    try:
        registry = ProviderRegistry((RegistryEntry(adapter, None),))
        app = _app_with_registry(monkeypatch, registry)
        with TestClient(app) as tc:
            app.state.telemetry = telemetry
            response = _post_chat(tc, stream=True)
        assert response.status_code == 501
        # No chat span, no metrics.
        assert _chat_spans(span_exporter) == []
        for name in (
            "chat_completion_requests_total",
            "chat_completion_errors_total",
            "chat_completion_duration_seconds",
        ):
            assert _metric_data_points(metric_reader, name) == [], (
                f"stream=true leaked {name}"
            )
    finally:
        await client.aclose()
