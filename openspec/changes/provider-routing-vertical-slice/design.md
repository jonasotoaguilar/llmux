# Design: Provider Routing Vertical Slice

## Technical Approach

Activate the existing `ProviderAdapter` port with one OpenAI adapter, an ordered startup registry, and an async priority router. FastAPI lifespan owns registry resources; API handlers translate between OpenAI HTTP envelopes and normalized core results. This implements the four change specs without Anthropic, fallback/retry, or streaming.

## Architecture Decisions

| Decision | Choice | Trade-off and rationale |
|---|---|---|
| Registry/config | `build_providers(settings)` returns an ordered `ProviderRegistry`; `LLMUX_PROVIDERS_CONFIGURED` is authoritative. OpenAI settings use `SecretStr`, URL, parsed model list, and positive timeout. Unknown slugs, duplicate slugs, empty key/models, or invalid URL fail startup with `ConfigurationError`. | Fail-fast prevents silently degraded routing; env-backed config is intentionally transitional to ADR-0002 persistence. |
| HTTP ownership | `OpenAIAdapter` requires an injected `httpx.AsyncClient`; the registry creates production clients, records ownership, and exposes `aclose()`. Lifespan builds after tracing and closes the registry in `finally` before tracer shutdown. Injected test clients remain caller-owned. | Explicit ownership avoids leaked pools and makes `MockTransport` deterministic. |
| Selection | `select_provider` asynchronously checks `models()` serially in registry order and returns the first exact model match. It never retries another adapter after selection. | Preserves Protocol-only coupling and deterministic priority; automatic fallback remains deferred. |
| Errors | `ProviderSelectionError` is **400** (`invalid_request_error`): the requested model is unsupported, not transient capacity. `ConfigurationError` remains **502** per spec, but normally aborts startup; 503 would incorrectly promise transient availability. Upstream HTTP/transport/schema errors map to 502; `httpx.TimeoutException` maps to 504. Bodies never expose keys/upstream payloads. | Stable OpenAI envelopes beat leaking provider-specific failures. |
| Translation | POST `{base_url}/chat/completions` with bearer auth, `stream:false`, normalized messages, and allowed extra options. Validate JSON/choice; map content, model, finish reason, and usage into `CompletionResult`, retaining safe raw metadata. The API reconstructs `chat.completion` (`id`, `created`, choice, usage); malformed responses are 502. | Keeps provider shape at the adapter boundary while preserving OpenAI compatibility. |
| Models | Await each adapter’s local configured catalog in registry order; emit one standard model object per provider/model (`id`, `object:model`, `created:0`, `owned_by`). Do not deduplicate pairs. | Stable and network-free; duplicates remain attributable by `owned_by`. |
| Telemetry | Span `chat.completion`; metrics `chat_completion_requests_total`, `chat_completion_errors_total`, `chat_completion_duration_seconds`. Attributes: `gen_ai.operation.name=chat`, `gen_ai.request.model`, `gen_ai.provider.name`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `llmux.request.duration_ms`, and `error.type`; metric dimensions are provider, model, outcome/error type. | Semantic attributes plus bounded dimensions limit cardinality. Telemetry starts after selection; `stream=true` emits none. |

No new ADR: ADR-0002 already fixes the adapter boundary; this design specializes one vertical slice. `ARCHITECTURE.md` remains unchanged.

## Data Flow

    request → validate → stream=true? 501
                       └→ select first model match → span/metrics → OpenAIAdapter → OpenAI
                                                   ← CompletionResult/error ←

Sequence: lifespan builds tracing then registry; request validation precedes the 501 guard; selection precedes telemetry; the adapter performs exactly one upstream call; the handler records duration/tokens/error and returns 200/400/502/504. Shutdown closes owned clients, then tracing.

## File Changes

| Files | Action | Description |
|---|---|---|
| `src/llmux/config.py`, `.env.example` | Modify | OpenAI env contract and validation. |
| `src/llmux/core/errors.py`, `core/providers/openai.py`, `core/providers/registry.py`, `core/router.py` | Create | Errors, translation, ownership, deterministic selection. |
| `src/llmux/main.py`, `api/chat.py`, `api/models.py` | Modify | Lifespan registry and live endpoints. |
| `src/llmux/observability/metrics.py` | Create | OTel instruments. |
| `tests/test_provider_routing_slice.py`, `tests/test_unit_2.py`, `tests/conftest.py` | Create/modify | MockTransport unit/live-HTTP coverage and fixture updates. |

## Interfaces / Contracts

`ProviderRegistry` is an ordered `Sequence[ProviderAdapter]` with `aclose()`; `build_providers(settings) -> ProviderRegistry`; `select_provider(model, providers) -> Awaitable[ProviderAdapter]`. `LLMuxError` exposes `status_code` and `to_openai_envelope()`. `stream=true` remains one JSON 501 response.

## Testing Strategy

| Layer | RED coverage |
|---|---|
| Unit | Settings defaults/errors; registry order/cleanup; MockTransport request/auth, translation, malformed/HTTP/timeout mapping; first-match/no-match; metric instruments. |
| Integration | TestClient lifespan, populated/empty models, success 200, selection 400, upstream 502, timeout 504, telemetry span/attributes, omitted stream, and no-fake-SSE 501. |
| E2E | No live provider call; full ASGI→MockTransport path, then `pytest` ≥90%, Ruff, and mypy. |

## Threat Matrix

| Boundary | Applicability |
|---|---|
| Documentation-like paths | N/A — no executable classification. |
| Git repository selection | N/A — no VCS execution. |
| Commit state | N/A — no commit automation. |
| Push state | N/A — no push automation. |
| PR commands | N/A — delivery boundaries only; no PR command construction. |

## Migration / Rollout

No data migration. Three autonomous chained PRs, each ≤400 authored lines: (1) config/errors/OpenAI adapter/registry + unit tests; (2) router/lifespan/models + HTTP tests; (3) chat translation/telemetry + HTTP tests. PR1 targets `feat/provider-routing-vertical-slice`; PR2 targets PR1’s branch; PR3 targets PR2’s branch. Roll back 3→2→1.

## Open Questions

None.
