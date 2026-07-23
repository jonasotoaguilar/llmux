"""Contract tests for the provider adapter port."""

import inspect
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import get_origin

import pytest

from llmux.core.providers.base import (
    Chunk,
    CompletionResult,
    HealthStatus,
    ModelInfo,
    ProviderAdapter,
)


class StubProvider:
    """Test-only stub implementing ProviderAdapter."""

    async def complete(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> CompletionResult:
        return CompletionResult(
            content="hello",
            model=model,
            prompt_tokens=1,
            completion_tokens=1,
            finish_reason="stop",
        )

    def complete_stream(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> AsyncIterator[Chunk]:
        async def _gen() -> AsyncIterator[Chunk]:
            yield Chunk(delta="hello", model=model)

        return _gen()

    async def models(self) -> Sequence[ModelInfo]:
        return [ModelInfo(id="gpt-4", provider="openai", supports_streaming=True)]

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=True)


def test_provider_adapter_members_declared() -> None:
    assert hasattr(ProviderAdapter, "complete")
    assert hasattr(ProviderAdapter, "complete_stream")
    assert hasattr(ProviderAdapter, "models")
    assert hasattr(ProviderAdapter, "health")


def test_provider_adapter_is_subclassable() -> None:
    assert issubclass(StubProvider, ProviderAdapter)
    provider = StubProvider()
    assert isinstance(provider, ProviderAdapter)


def test_completion_result_required_fields() -> None:
    result = CompletionResult(
        content="hello",
        model="gpt-4",
        prompt_tokens=10,
        completion_tokens=5,
        finish_reason="stop",
    )
    assert result.content == "hello"
    assert result.model == "gpt-4"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.finish_reason == "stop"
    assert result.raw == {}


def test_completion_result_raw_default_factory() -> None:
    result = CompletionResult(
        content="hello",
        model="gpt-4",
        prompt_tokens=10,
        completion_tokens=5,
        finish_reason="stop",
        raw={"key": "value"},
    )
    assert result.raw == {"key": "value"}


def test_chunk_required_fields() -> None:
    chunk = Chunk(delta="hello", model="gpt-4")
    assert chunk.delta == "hello"
    assert chunk.model == "gpt-4"
    assert chunk.finish_reason is None


def test_chunk_with_finish_reason() -> None:
    chunk = Chunk(delta="hello", model="gpt-4", finish_reason="stop")
    assert chunk.finish_reason == "stop"


def test_model_info_required_fields() -> None:
    info = ModelInfo(id="gpt-4", provider="openai", supports_streaming=True)
    assert info.id == "gpt-4"
    assert info.provider == "openai"
    assert info.supports_streaming is True


def test_health_status_required_fields() -> None:
    status = HealthStatus(healthy=True)
    assert status.healthy is True
    assert status.latency_ms is None
    assert status.error is None


def test_health_status_with_optional_fields() -> None:
    status = HealthStatus(healthy=False, latency_ms=120, error="timeout")
    assert status.healthy is False
    assert status.latency_ms == 120
    assert status.error == "timeout"


def test_complete_stream_is_sync_returning_async_iterator() -> None:
    sig = inspect.signature(ProviderAdapter.complete_stream)
    assert get_origin(sig.return_annotation) is AsyncIterator
    assert str(sig.return_annotation).endswith("AsyncIterator['Chunk']")
    assert not inspect.iscoroutinefunction(ProviderAdapter.complete_stream)


@pytest.mark.asyncio
async def test_complete_stream_stub_yields_chunks() -> None:
    provider = StubProvider()
    result = provider.complete_stream("gpt-4", [])
    assert isinstance(result, AsyncIterator)
    chunks = [chunk async for chunk in result]
    assert len(chunks) == 1
    assert chunks[0].delta == "hello"
    assert chunks[0].model == "gpt-4"
