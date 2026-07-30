"""Provider routing functional slice — PR1 (config + errors) + PR2 (OpenAI adapter)."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import quote

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
    to_openai_envelope,
)
from llmux.core.providers.base import (
    CompletionResult,
    HealthStatus,
    ModelInfo,
    ProviderAdapter,
)
from llmux.core.providers.openai import OpenAIAdapter

_OPENAI_ENV = (
    "LLMUX_PROVIDERS_CONFIGURED",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODELS",
    "OPENAI_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _OPENAI_ENV:
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
