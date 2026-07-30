"""Provider routing functional slice: PR1+PR2+PR3+PR4 tests.

Covers config, errors, OpenAI adapter, registry, async router, lifespan
wiring, and the /v1/models endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI
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
from llmux.core.providers.base import (
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
    """
    clients: list[_CountingClient] = []
    settings = _settings(monkeypatch, providers="openai,anthropic")
    with pytest.raises(ConfigurationError) as exc:
        await build_providers(settings, client_factory=_counting_factory(clients))
    assert "anthropic" in str(exc.value)
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
    """Patch build_tracer/shutdown_tracer/build_providers in main + tracing."""
    import llmux.main as main_mod

    def fake_build_tracer(_settings: object) -> object:
        recorder.events.append("build_tracer")
        return object()

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
