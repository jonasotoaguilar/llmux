"""Provider adapter port: Protocol and normalized dataclasses."""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class ProviderAdapter(Protocol):
    """Abstract port for LLM provider adapters."""

    async def complete(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> "CompletionResult":
        """Return a single non-streaming completion."""
        ...

    def complete_stream(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> AsyncIterator["Chunk"]:
        """Return an async iterator of streaming chunks.

        Declared as a synchronous method returning ``AsyncIterator[Chunk]`` so
        concrete adapters can yield chunks without forcing callers through a
        nested coroutine object.
        """
        ...

    async def models(self) -> Sequence["ModelInfo"]:
        """Return models exposed by this provider."""
        ...

    async def health(self) -> "HealthStatus":
        """Return current provider health."""
        ...


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Normalized non-streaming completion response."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    raw: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    """Single streaming completion chunk."""

    delta: str
    model: str
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Model exposed by a provider."""

    id: str
    provider: str
    supports_streaming: bool


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Provider health snapshot."""

    healthy: bool
    latency_ms: int | None = None
    error: str | None = None
