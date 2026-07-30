# Design: Provider Routing Functional Slice

## Technical Approach

Activate the existing `ProviderAdapter` port with one OpenAI non-streaming adapter, an ordered registry, and an async first-match router. FastAPI lifespan owns production clients; handlers obtain registry and telemetry from `app.state`. Omitted `stream` follows the existing Pydantic default (`false`) and routes; only explicit `true` short-circuits to JSON 501 before provider or telemetry work. ADR-0002 already governs this specialization; no ADR or `ARCHITECTURE.md` change is required.

## Architecture Decisions

| Decision | Choice | Alternative / trade-off | Rationale |
|---|---|---|---|
| Construction and ownership | Transaction-like `build_providers(settings)` owns created clients until returning a complete `ProviderRegistry`. Duplicate/unknown slug, invalid configuration, or later adapter-construction failure MUST close all clients created so far before re-raising `ConfigurationError`. Return transfers ownership exactly once; registry `aclose()` is idempotent and closes only factory-created clients. | Best-effort/partial registry; close injected clients. | Prevents degraded startup, leaks, and caller-owned client double-close. |
| Selection | `async select_provider(model, registry)` returns the first adapter whose awaited `models()` contains an exact ID. | Weighted/fallback routing. | Deterministic configured priority; retries and fallback remain out of scope. |
| HTTP errors | One typed `LLMuxError` mapping; unexpected exceptions are observed then re-raised. | Handler-specific mappings or swallowing broad exceptions. | Stable sanitized envelopes while preserving genuine 500 behavior. |
| Telemetry | A `ChatTelemetry` wrapper owns OTel instruments and accepts public tracer/meter dependencies. | Global/private OTel or registry mutation in tests. | Stable keys and deterministic in-memory/fake testing. |

## Data Flow and Lifecycle

```text
lifespan: build_tracer → await build_providers → app.state.providers → yield
                    failure └→ factory closes constructed clients ─┐
shutdown: registry.aclose (if returned) → shutdown_tracer ←────────┘

POST → explicit stream=true? → JSON 501 (stop)
     → span/timer → select_provider → adapter.complete → normalized 200
                    └ typed error → ERROR span + metrics → 400/502/504
                    └ unexpected → ERROR span + error timer → re-raise
```

Lifespan always shuts down the tracer, including when `build_providers` fails. It calls registry `aclose()` only after successful ownership transfer, avoiding double-close of factory-cleaned clients; incomplete registries never reach `app.state`.

## Interfaces / Contracts

```python
class ProviderRegistry:
    providers: tuple[ProviderAdapter, ...]
    async def models(self) -> tuple[ModelInfo, ...]: ...
    async def aclose(self) -> None: ...

async def build_providers(settings: Settings) -> ProviderRegistry: ...
async def select_provider(model: str, registry: ProviderRegistry) -> ProviderAdapter: ...

class OpenAIAdapter:
    def __init__(self, api_key: SecretStr, base_url: str,
                 models: tuple[str, ...], timeout_s: float,
                 client: httpx.AsyncClient | None = None) -> None: ...
    async def complete(self, model, messages, options=None) -> CompletionResult: ...
    def complete_stream(self, model, messages, options=None) -> AsyncIterator[Chunk]:
        raise NotImplementedError
```

Settings add `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODELS`, and `OPENAI_TIMEOUT_S`; enabled OpenAI with empty key/models, malformed URL, unknown/duplicate slug raises `ConfigurationError`.

| Error | HTTP | Stable code |
|---|---:|---|
| `ProviderSelectionError` | 400 | `model_not_found` |
| `ConfigurationError` | 502 | `provider_configuration_error` |
| `UpstreamError` | 502 | `upstream_error` |
| `UpstreamTimeoutError` | 504 | `upstream_timeout` |

`to_openai_envelope()` uses safe class messages only—never exception text, keys, upstream bodies, or traces. Success responses normalize `CompletionResult`; models emit `{id, object:"model", created:0, owned_by}`.

Telemetry keys are fixed: span `chat.completion`; instruments `chat_completion_requests_total`, `chat_completion_errors_total`, `chat_completion_duration_seconds`; attributes `provider`, `model`, `outcome`, `error_type`. Selection misses use `MODEL_UNKNOWN = "unknown"`, never the requested model. Typed and unexpected errors set `Status(StatusCode.ERROR, error_type)` plus `error.type`; unexpected failures use bounded `uncaught_exception`, record duration as error, then propagate.

## File and PR Boundaries

| PR | Files / autonomous outcome |
|---|---|
| PR1 | Modify `src/llmux/config.py`, `.env.example`; create `core/errors.py`, `providers/openai.py`, `providers/registry.py`; adapter/config/error/lifecycle unit tests. |
| PR2 | Create `core/router.py`; modify `main.py`, `api/models.py`; prove first-match, models, and build-failure teardown. |
| PR3 | Create `observability/metrics.py`; modify `api/chat.py`; live-ASGI success/error/omitted-stream/explicit-stream and telemetry tests. |

Each PR stays within 400 authored lines; PR1 targets the tracker branch, PR2 targets PR1, PR3 targets PR2. No source file is deleted.

## Testing Strategy

RED tests precede each PR. Unit tests use `MockTransport`, caller-owned clients, and recording adapters. A deterministic construction seam fails the second adapter after one client exists; assert that client closes exactly once, no registry returns, and `ConfigurationError` propagates. Lifespan seams assert cleanup order, tracer shutdown on build failure, no factory-cleaned client is closed twice, and repeated registry `aclose()` is safe after success. Telemetry tests use public OTel fakes/exporters only. Live-ASGI tests cover omitted stream, explicit-`true` 501 without provider/telemetry, mappings, sanitization, stable keys, unknown sentinel, ERROR status, and uncaught-error timing.

## Threat Matrix

| Boundary | Applicability | Reason |
|---|---|---|
| Documentation-like paths | N/A | No executable classification. |
| Git repository selection | N/A | No Git invocation. |
| Commit state | N/A | No commit automation. |
| Push state | N/A | No push automation. |
| PR commands | N/A | PR boundaries are documentation only; no command composition. |

## Migration / Rollout

No data migration. Roll back PR3 → PR2 → PR1.

## Open Questions

None.
