# Exploration: `anthropic-provider-adapter-slice`

> **Change**: `anthropic-provider-adapter-slice` (first slice of a new chain).
> **Branch (planned)**: `feat/anthropic-provider-adapter-slice` from `origin/main` @ `12a32ae` (post-OpenAI-routing merge via PR #19).
> **Delivery**: `auto-chain` / `feature-branch-chain`, 400-line review budget, `size:exception` available per PR.
> **Persistence**: hybrid (this file + Engram topic `sdd/anthropic-provider-adapter-slice/explore`).
> **Architectural anchor**: [ADR-0002](../../../docs/adr/0002-provider-abstraction-pattern.md) (the `ProviderAdapter` Protocol). **No new ADR** is required for this slice.
> **Receipt-driven development**: globally disabled by user decision; delivery stays `disabled/unmanaged` under ordinary repository policy.

## Quick path

1. Add Anthropic settings (`ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODELS` / `ANTHROPIC_TIMEOUT_S` / `ANTHROPIC_VERSION`) with the same fail-fast `ConfigurationError` contract as OpenAI.
2. Implement `AnthropicAdapter` over the same injected-`httpx.AsyncClient` boundary as `OpenAIAdapter`: `POST /v1/messages` with `x-api-key` + `anthropic-version` headers; pull system messages out of the `messages` array into the top-level `system` field; require a `max_tokens` default when the caller omits it; translate `content: [{type:"text", text:"..."}, ...]` into a joined `CompletionResult.content`; map `input_tokens`/`output_tokens` → `prompt_tokens`/`completion_tokens`. `complete_stream` raises `NotImplementedError` (parity with OpenAI).
3. Extend `build_providers` to dispatch by slug to `AnthropicAdapter` for `"anthropic"` — preserve the transaction-like cleanup and `aclose()` ownership invariants from the OpenAI slice.
4. Keep the chat handler, router, telemetry, and error hierarchy unchanged: the first-match `select_provider` is provider-agnostic, the bounded `provider` label set just grows by `"anthropic"`, and the existing `UpstreamError`/`UpstreamTimeoutError` mapping already covers Anthropic's transport + 4xx/5xx/429/529 surface.
5. **Explicitly defer** streaming (SSE), tool use, prompt caching, image inputs, model alias resolution, cost tracking, automatic fallback, retries/backoff, and circuit breaking. None of these ship in this slice.

## Current state (main @ 12a32ae)

The OpenAI provider-routing slice (PRs #10–#19, merged at `12a32ae`) is the dependency for this work. Everything the Anthropic slice needs to plug into already exists and is green on `main`:

| Area | State on main | What the Anthropic slice adds / changes |
|------|---------------|------------------------------------------|
| `src/llmux/core/providers/base.py` | `ProviderAdapter` Protocol (runtime-checkable) + `CompletionResult` / `Chunk` / `ModelInfo` / `HealthStatus` frozen-slotted dataclasses | **No change.** The Anthropic adapter satisfies the existing Protocol without Protocol changes. |
| `src/llmux/core/providers/openai.py` | `OpenAIAdapter` (injected `httpx.AsyncClient`, non-streaming only, Bearer auth to `/chat/completions`); `complete_stream` raises `NotImplementedError`; `_parse_completion` normalizes `choices[0].message.content` + `usage.{prompt,completion}_tokens` | **No change.** The OpenAI adapter is the reference; the Anthropic adapter mirrors its shape and ownership model. |
| `src/llmux/core/providers/registry.py` | `ProviderRegistry(entries)` (idempotent `aclose()`, only closes factory-owned clients); `build_providers(settings, *, client_factory)` with transaction-like cleanup; slug dispatch is currently hard-coded to `openai` | **Extend** the `if slug != "openai": raise ConfigurationError(...)` branch to dispatch `"anthropic"` to a new `AnthropicAdapter`. Keep the `seen` / duplicate / fail-fast semantics identical. |
| `src/llmux/core/router.py` | `async select_provider(model, registry)` — first exact-match across `await adapter.models()`, no fallback, raises `ProviderSelectionError` (400) on no match | **No change.** The router is provider-agnostic by design; Anthropic is selected the same way as OpenAI. |
| `src/llmux/api/chat.py` | Async handler: explicit `stream=true` → JSON 501 (no provider call, no telemetry); `stream=False` / omitted → routed `await adapter.complete(...)` with bounded telemetry, 200 envelope on success or sanitized 400/502/504 on `LLMuxError` | **No change.** The chat handler reads `getattr(adapter, "name", PROVIDER_NONE)`; the bounded `provider` label automatically grows to include `"anthropic"`. |
| `src/llmux/api/models.py` | `GET /v1/models` aggregates one entry per `(provider, model)` from the registry | **No change.** `AnthropicAdapter.models()` returns the configured list, registry concatenates in order. |
| `src/llmux/observability/metrics.py` | `ChatTelemetry` (span `chat.completion` + 3 bounded instruments); `MODEL_UNKNOWN` / `PROVIDER_NONE` / `INTERNAL_ERROR_TYPE` / `ALLOWED_OUTCOMES` / `ALLOWED_ERROR_TYPES` sentinels | **No production change.** The bounded set `{"openai", "none"}` already constrains `provider`; adding `"anthropic"` is a documentation-level update in the spec and test assertions. The `provider` label is read via `getattr(adapter, "name", PROVIDER_NONE)` so the bounded contract is preserved by construction. |
| `src/llmux/core/errors.py` | `LLMuxError` → 4 subclasses with stable `status_code` / `code` / `safe_message`; `to_openai_envelope` sanitizes (no keys, no upstream bodies, no traces) | **No change.** Anthropic's `{"type":"error","error":{"type":...,"message":...}}` envelope is discarded at the adapter boundary; only the class-level `safe_message` reaches the wire — same sanitization rule as OpenAI. |
| `src/llmux/config.py` | `Settings` with `LLMUX_*` + `OTEL_*` + OpenAI env (key, base_url, models, timeout_s); `_validate_openai_when_enabled` raises `ConfigurationError` on empty key / empty models / non-http(s) URL | **Extend** with Anthropic env: `anthropic_api_key: SecretStr \| None`, `anthropic_base_url`, `anthropic_models`, `anthropic_timeout_s`, `anthropic_version`. Add `_validate_anthropic_when_enabled` (or a single composite validator) with the same fail-fast contract. |
| `src/llmux/main.py` | Lifespan: `build_tracer` → `build_chat_telemetry` → `await build_providers` (transaction-like) → `app.state.providers = registry` → `yield` → `aclose()` then `shutdown_tracer` (the pre-yield `aclose` bug was fixed in PR7) | **No change.** Lifespan already handles arbitrary adapter counts and slug orders. |
| `.env.example` | OpenAI env documented + fail-fast notes | **Add** Anthropic env block with the same fail-fast notes. |
| `tests/test_provider_routing_slice.py` | 81 tests covering OpenAI adapter, registry, router, lifespan, models, chat, telemetry | **Extend** with the Anthropic-shaped surface (mirrored patterns). The PR1 / PR2 mapping of the OpenAI chain → the smaller 2-PR chain for Anthropic is detailed in the **Approaches** section. |
| `openspec/changes/provider-routing-functional-slice/` | Delivered; `verify-report.md` and `apply-progress.md` document the six-guardrail discovery (lifespan teardown, bounded cardinality, OTel error status, uncaught-error accounting, no test-client double-close, no partial registry) | **Reference only.** All six guardrails apply to the Anthropic slice unchanged. |

## API compatibility boundaries (Anthropic Messages API ↔ OpenAI Chat Completions)

The Anthropic adapter is a **provider of the same OpenAI-shaped `CompletionResult`** (per `provider-abstraction` spec), so the gateway's chat handler, router, and telemetry never see Anthropic-specific shapes. The translation work is concentrated at the adapter boundary. The table below lists every Anthropic Messages API difference that affects this slice.

| Boundary | OpenAI (existing) | Anthropic Messages API | Slice's translation rule |
|---|---|---|---|
| Auth header | `Authorization: Bearer <key>` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` (or configured) | Adapter builds the `x-api-key` + `anthropic-version` header pair from `anthropic_api_key` + `anthropic_version`. **No Bearer header.** |
| Endpoint | `POST {base_url}/chat/completions` | `POST {base_url}/v1/messages` | Adapter POSTs to `{base_url}/v1/messages` (base URL is the API root, e.g. `https://api.anthropic.com`). |
| `system` message | `messages: [{role:"system", content:"…"}, …]` (system as a message) | `system: "…"` (top-level, optional) + `messages` containing only `user` / `assistant` | Adapter pops messages with `role == "system"`, concatenates their `content` (string or list-of-text-blocks) with `\n\n` separators, and emits the joined string as the top-level `system` field. Messages with `role` not in `{user, assistant}` after the pop are rejected with `ConfigurationError` (502 — server-side shape violation, not a caller 400). |
| `max_tokens` | Optional | **Required** | Adapter defaults `max_tokens` to a configured `anthropic_default_max_tokens` (proposed default: `1024`) when the caller omits it via `options`. Caller can override through `options["max_tokens"]`. |
| `stream` field | `{"stream": false}` in non-streaming calls | **Not used in non-streaming** (SSE is a separate path) | Adapter does NOT emit a `stream` field on the wire. The slice's `complete_stream` raises `NotImplementedError`, mirroring the OpenAI adapter. |
| Tool use (`tools` / `tool_choice`) | Supported | Supported, different field shape (`tools: [{name, description, input_schema}, …]`, `tool_use` content blocks) | **Deferred.** Out of scope for this slice. If the caller sends `tools` in `options`, the adapter ignores them for now and a follow-up slice (`anthropic-tool-use-federation`) wires them through. |
| Prompt caching | Not supported by OpenAI Chat Completions | `cache_control` blocks on messages / system / tools | **Deferred.** The cache-control annotations are silently dropped in this slice; no cost attribution, no cache hit/miss telemetry. |
| Image inputs | `content: [{type:"image_url", image_url:{url:…}}]` (Chat Completions) | `content: [{type:"image", source:{type:"url"|"base64", ...}}]` | **Deferred.** Out of scope; callers passing images in this slice get `CompletionResult` with the text content only (or `UpstreamError` if Anthropic rejects the call). |
| Response content shape | `choices[0].message.content` is a string | `content` is an array of blocks: `[{type:"text", text:"…"}, {type:"tool_use", …}, …]` | Adapter extracts every block with `type == "text"`, joins them with `\n`, and assigns the result to `CompletionResult.content`. If a non-text block (`tool_use`, `image`, etc.) is present, the adapter raises `UpstreamError` (502) with a sanitized message — tool-use support lands in a follow-up slice. |
| Token usage | `usage: {prompt_tokens, completion_tokens, total_tokens}` | `usage: {input_tokens, output_tokens, cache_creation_input_tokens?, cache_read_input_tokens?}` | Adapter maps `input_tokens → prompt_tokens`, `output_tokens → completion_tokens`. The Anthropic cache fields are ignored in this slice. |
| Stop reason | `finish_reason: "stop" \| "length" \| "tool_calls" \| "content_filter"` | `stop_reason: "end_turn" \| "max_tokens" \| "stop_sequence" \| "tool_use"` | Adapter maps `end_turn → "stop"`, `max_tokens → "length"`, `stop_sequence → "stop"`, `tool_use → "tool_use"`. Unknown values fall back to `"stop"` (defensive). |
| Error envelope | `{"error": {"message", "type", "param", "code"}}` | `{"type": "error", "error": {"type": "…", "message": "…", "details": …}}` | Adapter raises `UpstreamError` (4xx/5xx) or `UpstreamTimeoutError` (timeout) based on HTTP status; the JSON body is **discarded** — only the class-level `safe_message` reaches the wire (no keys, no upstream bodies, no traces). |
| Rate limit / status | `429` rate-limit, `5xx` | `429` rate-limit, `529` overloaded, `408` request timeout, `5xx` | All non-2xx responses map to `UpstreamError` (502 for 4xx/5xx, 504 for 408 timeouts). No retry/backoff in this slice. |
| `models()` listing | `GET {base_url}/models` returns `{"data": [{id, ...}, ...]}` | **Anthropic has no public `GET /v1/models` listing** | Adapter returns the configured list verbatim (Anthropic does not provide a programmatic model list). `health()` probes `POST /v1/messages` with a `max_tokens: 1` minimal call (or a HEAD/GET on the base URL — design decision documented in **Approaches**). |
| Health probe | `GET {base_url}/models` | (no public listing) | See "Health probe" in **Approaches** — there are three reasonable options; the recommended one is documented there. |

## SDK / client injection strategy

The OpenAI slice chose raw `httpx.AsyncClient` (injected) over an SDK. The Anthropic slice follows the same boundary for the same reasons — and adds one new consideration specific to Anthropic.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Raw `httpx.AsyncClient` (injected), same as OpenAI** (recommended) | Same test pattern (`httpx.MockTransport`); same registry `aclose` ownership semantics; no new dep; no SDK version-pinning; no Python type stubs to maintain; consistent adapter shape across providers | No built-in retry helpers, no type hints on the wire, manual JSON construction | **Chosen.** This is what the OpenAI slice did and the established pattern. |
| `anthropic-sdk-python` official SDK | Type-safe; handles retries; tracks `anthropic-version` defaults | New dep with version churn risk; the SDK's async client creates its own `httpx.AsyncClient` which conflicts with the registry's ownership model; harder to inject `MockTransport`; pulls in retry / streaming we explicitly defer | **Rejected.** Breaks the established adapter shape and the registry's client-ownership contract. |
| `httpx` + a small custom helper module (`_anthropic.py`) for shared parsing | Same as raw httpx but isolates the Anthropic-specific shape quirks (system message pop, content-block join, token mapping) | Slightly more files; tiny duplication if Google is added later | **Deferred** (not needed in this slice — keep parsing inside `AnthropicAdapter._parse_completion` for now, mirror the OpenAI layout; refactor to a shared helper in a later `provider-parsing-helpers` slice if Google or Bedrock land). |

The injected-client rule is preserved: the adapter accepts an optional `httpx.AsyncClient`; production gets one from `build_providers`'s factory and the registry closes it on `aclose()`. Tests pass a `MockTransport`-backed client they own.

## Error normalization

The slice reuses the existing `LLMuxError` hierarchy verbatim. No new error classes, no new HTTP status codes, no new envelope shapes.

| Anthropic response | Adapter raises | Mapped HTTP | Sanitized envelope |
|---|---|---|---|
| 2xx with `content: [{type:"text", text:"…"}]` | (returns `CompletionResult`) | 200 | OpenAI-shaped completion envelope via `_completion_envelope(result)` (PR5) |
| 2xx with non-text blocks (`tool_use`, `image`, …) | `UpstreamError` | 502 | `upstream_error` (class-level `safe_message`; no upstream body) |
| 2xx with malformed JSON or missing `content` / `usage` | `UpstreamError` | 502 | `upstream_error` |
| 400 / 401 / 403 | `UpstreamError` | 502 | `upstream_error` (sanitized) |
| 404 | `UpstreamError` | 502 | `upstream_error` |
| 408 | `UpstreamTimeoutError` | 504 | `upstream_timeout` |
| 429 | `UpstreamError` | 502 | `upstream_error` (no retry in this slice) |
| 5xx (500 / 502 / 503 / 504 / 529) | `UpstreamError` | 502 | `upstream_error` |
| `httpx.TimeoutException` | `UpstreamTimeoutError` | 504 | `upstream_timeout` |
| `httpx.HTTPError` (other transport) | `UpstreamError` | 502 | `upstream_error` |
| Caller passes `role: "function"` or other unsupported role | `ConfigurationError` (via the slice's own validation) | 502 | `provider_configuration_error` (server-side shape violation, NOT a caller 400) |
| Builder-failure (empty key, empty models, invalid URL when `anthropic` enabled) | `ConfigurationError` at startup | (fail-fast, never reaches HTTP) | (no envelope — startup abort) |

**Why no new error class:** the existing `LLMuxError` taxonomy was designed to be provider-agnostic; an adapter-specific `AnthropicError` would break the abstraction. The same sanitization invariant holds: the class-level `safe_message` is the only thing that reaches the wire, and the existing `to_openai_envelope` test in PR1 already covers the no-leak invariant.

## Model mapping

This slice passes the requested model id through verbatim. There is **no alias resolution, no normalization, no fallback table** in this slice.

- Configured model list (`ANTHROPIC_MODELS`) is a JSON-or-CSV list of strings; e.g. `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`.
- `await adapter.models()` returns one `ModelInfo(id=<configured>, provider="anthropic", supports_streaming=False)` per entry.
- `await select_provider(model, registry)` matches on the exact string — first adapter in configured order whose list contains the id wins.
- `CompletionResult.model` is `data.get("model", default_model)` — i.e. Anthropic's response model id echoed back (may include a date suffix Anthropic adds).
- Telemetry `provider` label is `getattr(adapter, "name", PROVIDER_NONE)` = `"anthropic"` (the slice's `AnthropicAdapter` sets `name = "anthropic"`).
- Telemetry `model` label uses the bounded `MODEL_UNKNOWN` sentinel only on selection miss; on success it uses `result.model` (the canonical Anthropic response model id); the bounded-set test from PR6 (`test_telemetry_bounded_label_values`) gains `"anthropic"` to its `bounded_providers` set, but the bounded cardinality guarantee is preserved (the set is fixed, not caller-driven).

**Deferred to follow-up slices:** alias resolution (`claude-sonnet` → `claude-3-5-sonnet-20241022`); canonical-model normalization across providers; cost tracking; per-model capability metadata.

## Health / resource ownership

### Health probe

Anthropic has no public `GET /v1/models` listing, so the OpenAI adapter's `health()` shape (probe `GET /models`, 2xx ⇒ healthy) does not translate directly. Three reasonable options:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Probe `GET {base_url}/` (Anthropic API root)** (recommended) | Free (no token cost); proves reachability; `404` or any non-5xx response ⇒ healthy; 5xx or transport error ⇒ unhealthy | Does NOT verify the API key; an invalid key is reported as "healthy" until the first real call | **Chosen for this slice.** Health is reachability, not auth-validity; the chat path's `UpstreamError` is the actual signal of a bad key. Documented in spec. |
| B. Probe `POST /v1/messages` with `max_tokens: 1` and a 1-char prompt | Verifies the full request shape end-to-end (auth + model + reachability) | Costs ~a few tokens per probe; the prompt's cost is non-zero in steady state; race condition with rate limits | **Deferred.** Auth-validity probing is a separate concern from health probing. Could land in a `provider-health-probe-rewrite` slice alongside equivalent probes for OpenAI / Google. |
| C. Use `anthropic-version` header on a `GET /` and check for 400/401 (distinguishes auth errors from reachability) | Cheap; distinguishes auth from reachability | Two classes of "unhealthy" conflated in the current `HealthStatus.healthy: bool` | **Deferred.** Requires a richer `HealthStatus` model (not planned in this slice). |

The slice's `AnthropicAdapter.health()` returns `HealthStatus(healthy=<status < 400 and not 5xx>, error=<type name on transport error>)` — same shape as the OpenAI adapter.

### Resource ownership

The OpenAI slice's resource-ownership invariant carries over verbatim:

- Production HTTP client is created by `build_providers`'s default factory; the registry `aclose()` closes it exactly once.
- Test client (caller-owned, `MockTransport`-backed) is recorded as `RegistryEntry(adapter, client=None)` and is never re-closed by the registry.
- Lifespan teardown order is unchanged: `aclose()` (only on success) runs **after** `yield`, **before** `shutdown_tracer`; on `build_providers` failure the factory's `except BaseException` cleanup owns the partial clients and the outer `finally` does not re-close them.

**No double-close guardrail** (PR3): `_CountingClient.aclose_count == 1` is asserted for any test that constructs an `AnthropicAdapter` and exercises `aclose` or the `build_providers` failure path.

**No lifespan teardown guardrail** (PR7): the new `AnthropicAdapter` is a drop-in for `OpenAIAdapter` inside the registry; the lifespan's behavior-first contract (real `httpx.AsyncClient` open during serving, closed exactly once after `TestClient` exit) does not need new tests — the existing `test_lifespan_owned_client_stays_open_while_serving` covers the registry shape, and a new analogous test in this slice uses an `AnthropicAdapter` to prove the Anthropic entry participates in the same contract.

## Tests

The slice's test surface mirrors the OpenAI slice's PR2 / PR3 / PR4 / PR5 / PR6 test patterns. The `tests/test_provider_routing_slice.py` file is extended (not duplicated). New tests follow the same `httpx.MockTransport` + caller-owned client pattern established in the OpenAI slice.

| Test group | Coverage |
|---|---|
| **Settings** (PR1-shaped) | `anthropic_settings_{valid,empty_key_raises,empty_models_raises,invalid_url_raises,default_when_no_provider_configured}`; `ANTHROPIC_VERSION` default; JSON/CSV parse parity with `OPENAI_MODELS` |
| **Adapter — protocol** | `anthropic_adapter_satisfies_protocol`; `anthropic_complete_stream_raises_not_implemented` (sync, not awaited) |
| **Adapter — success** | `anthropic_complete_returns_result_with_expected_fields` (text content + token mapping); `anthropic_complete_sends_correct_request` (URL, headers, body, system-message pop, `max_tokens` default, options merge); `anthropic_complete_extracts_system_messages_from_array`; `anthropic_complete_joins_multiple_text_blocks`; `anthropic_complete_uses_default_max_tokens_when_options_omit_it`; `anthropic_complete_maps_stop_reason_{end_turn,max_tokens,stop_sequence,tool_use,unknown}` |
| **Adapter — failure map** | Parametrized: 4xx (400/401/403/404), 408 timeout, 429, 5xx (500/502/503/529), `httpx.TimeoutException`, `httpx.ConnectError`, malformed JSON, missing `content`, missing `usage`, non-text content block (tool_use) → all raise typed `LLMuxError` |
| **Adapter — `models()`** | `anthropic_models_returns_configured_models` (one `ModelInfo` per id, `provider="anthropic"`, `supports_streaming=False`) |
| **Adapter — `health()`** | Parametrized: 2xx from `GET /` ⇒ healthy; 5xx ⇒ unhealthy; transport error ⇒ unhealthy (caught, no raise) |
| **Registry** | `build_providers_with_anthropic_only_constructs_anthropic_adapter`; `build_providers_with_openai_and_anthropic_constructs_both_in_order`; `build_providers_unknown_slug_anthropic_unknown_fails_fast`; `build_providers_closes_first_client_when_anthropic_fails_after_openai` (deterministic factory seam, mirrors PR3); `build_providers_cleans_up_on_anthropic_ctor_failure` (BaseException path); `aclose_closes_anthropic_production_only`; `aclose_idempotent_after_anthropic_success` (5× aclose, count==1) |
| **Lifespan** | `test_lifespan_owned_client_stays_open_while_serving_anthropic` (mirrors PR7's behavior-first regression with an `AnthropicAdapter` registry-owned client — proves the PR7 invariant holds for a second provider) |
| **Models endpoint** | `models_aggregates_across_openai_and_anthropic` (one entry per `(provider, model)` in registry order); `models_includes_anthropic_with_owned_by_anthropic` |
| **Chat end-to-end** | `chat_routes_anthropic_model_to_anthropic_adapter_and_returns_200` (live ASGI via `TestClient` with real `ProviderRegistry`); `chat_400_selection_miss_when_no_provider_offers_claude_model`; `chat_502_when_anthropic_upstream_4xx`; `chat_504_when_anthropic_upstream_times_out`; `chat_502_when_anthropic_upstream_5xx`; `chat_omitted_stream_routes_to_anthropic_default_false`; `chat_explicit_stream_true_returns_501_no_provider_no_telemetry_anthropic` (verifies Anthropic is NOT invoked on the 501 path) |
| **Telemetry** | `telemetry_provider_label_anthropic_in_bounded_set` (extends the PR6 `bounded_label_values` test with `"anthropic"` in `bounded_providers`); `telemetry_anthropic_success_records_request_with_provider_anthropic`; `telemetry_anthropic_400_records_error_with_provider_anthropic` |
| **Configuration / env** | `.env.example` includes the Anthropic env block; `LLMUX_PROVIDERS_CONFIGURED="openai,anthropic"` builds both adapters in order |

The test file stays `tests/test_provider_routing_slice.py` (no new file). The fixture `app` / `client` from `tests/conftest.py` continues to work (no registry by default ⇒ an Anthropic-only request hits selection miss ⇒ 400).

## Dependencies

- **No new runtime dep.** `httpx` (already in `pyproject.toml`) is the only HTTP layer; no Anthropic SDK is added.
- **No new test dep.** `pytest`, `pytest-asyncio`, `httpx.MockTransport`, OTel `InMemorySpanExporter` / `InMemoryMetricReader` — all already present.
- **No `ARCHITECTURE.md` change.** The component diagram already lists `ADPT_ANTHROPIC["Anthropic Adapter"]` and `PROVIDERS["LLM Providers\nOpenAI / Anthropic / Google"]`. The slice turns one of those boxes from planned to real.
- **No ADR.** ADR-0002 is the source of truth for the `ProviderAdapter` Protocol. The Anthropic adapter is one concrete implementation of that accepted pattern; no new architectural decision is being made.
- **No new env var conventions.** Anthropic env vars are mirror-shaped on the OpenAI ones (prefix `ANTHROPIC_` instead of `OPENAI_`); the parse + fail-fast pattern is identical.

## Scope and non-goals (explicit)

### In scope (this slice)

1. `AnthropicAdapter` implementing `ProviderAdapter` (non-streaming `complete` only; `complete_stream` raises `NotImplementedError`).
2. `Settings` extension: `anthropic_api_key`, `anthropic_base_url`, `anthropic_models`, `anthropic_timeout_s`, `anthropic_version`, with fail-fast `ConfigurationError` when `anthropic` is enabled with an empty key, empty model list, or non-http(s) URL.
3. `build_providers` slug dispatch for `"anthropic"`, preserving the transaction-like cleanup and `aclose()` ownership invariants.
4. System message → top-level `system` field translation; `max_tokens` default; response content block join; token mapping (`input_tokens` / `output_tokens` → `prompt_tokens` / `completion_tokens`); stop reason mapping.
5. Mirrored test surface in `tests/test_provider_routing_slice.py` (no new test file).
6. `.env.example` update with the Anthropic env block.
7. End-to-end live ASGI proof that `POST /v1/chat/completions` with a configured Anthropic model id routes to the Anthropic adapter and returns a 200 OpenAI-shaped envelope, with bounded telemetry.

### Out of scope (deferred to follow-up slices)

- **Streaming / SSE** (Anthropic's `message_start` / `content_block_delta` / `message_stop` event stream). The slice's `complete_stream` raises `NotImplementedError`, mirroring the OpenAI adapter. A future `provider-streaming-federation` slice (which will handle both OpenAI and Anthropic streaming in one chain) will replace the raise with a real implementation.
- **Tool use** (`tools` / `tool_choice` / `tool_use` content blocks).
- **Prompt caching** (`cache_control` annotations; `cache_creation_input_tokens` / `cache_read_input_tokens` accounting).
- **Image / multi-modal inputs** (`type: "image"` content blocks).
- **Model alias resolution** (`claude-sonnet` → `claude-3-5-sonnet-20241022`) and cross-provider canonical model normalization.
- **Per-model cost tracking** (input/output/cache pricing tables).
- **Auth-validity health probe** (the slice's `health()` is reachability-only; a richer `HealthStatus` model is a separate slice).
- **Automatic fallback** (the slice does **not** change `select_provider` — first-match only). Fallback is explicitly deferred to the next planned slice (`provider-fallback-and-retries` per the original ROADMAP Phase 1 plan), which will be ordered AFTER the Anthropic slice so it can test fallback across both providers.
- **Retries / backoff / circuit breaking** (the slice's `UpstreamError` mapping surfaces every failure immediately; no internal retry inside the adapter).
- **Per-tenant key management** (single key per provider; the persistence-driven multi-key / per-tenant rotation is a Phase 3 / production-hardening concern).
- **Google, Bedrock, Azure OpenAI, Mistral, Cohere adapters** (ROADMAP Phase 1 lists "OpenAI + Anthropic" as the MVP providers; Google and others are post-MVP).
- **ARCHITECTURE.md or ADR-0002 changes** (the existing docs already cover the Anthropic adapter at the diagram level).

## Approaches (with recommendation)

| Decision | Option A (recommended) | Option B | Option C (rejected) |
|---|---|---|---|
| **Adapter surface** | `AnthropicAdapter` (raw `httpx.AsyncClient`, injected, non-streaming only; `complete_stream` raises `NotImplementedError`). Mirror the OpenAI adapter's shape and ownership model. | `AnthropicAdapter` + a shared `_anthropic.py` parsing helper for system-message pop, content-block join, and token mapping. | `AnthropicAdapter` using the `anthropic-sdk-python` official SDK. |
| | Pros: smallest possible adapter (~120 LoC); zero new dep; established pattern; same `MockTransport` test story. Cons: a small amount of code that would be shared with a future Google adapter is duplicated. | Pros: prepares for the next provider. Cons: YAGNI — Google is post-MVP; the helper can land in a `provider-parsing-helpers` slice when the second non-OpenAI adapter is green, not before. | Pros: type-safe upstream. Cons: SDK's async client creates its own `httpx.AsyncClient` (breaks registry `aclose` ownership); no `MockTransport` injection; version-pinning risk; conflicts with the established `httpx`-only boundary. |
| | **Chosen.** | Deferred until a second non-OpenAI adapter lands. | **Rejected.** |
| **Health probe** | `GET {base_url}/` (Anthropic API root). 2xx/3xx/404 ⇒ healthy; 5xx or transport error ⇒ unhealthy. Reachability-only, no key validation. | `POST /v1/messages` with `max_tokens: 1` and a 1-char prompt. Proves auth + reachability. | `GET /v1/messages` (HEAD-style) with the `anthropic-version` header. |
| | Pros: zero token cost; matches the OpenAI adapter's "reachability" semantics; no new dep. Cons: invalid key is reported as healthy until the first real call (the chat path's `UpstreamError` is the actual signal of a bad key). | Pros: full end-to-end verification. Cons: per-probe cost; race with rate limits; inverts the OpenAI health-probe semantics (which is reachability-only). | Pros: explicit auth header. Cons: not all Anthropic endpoints accept HEAD; behavior is undocumented. |
| | **Chosen for this slice.** Auth-validity probing is a separate concern. | Deferred to a `provider-health-probe-rewrite` slice. | **Rejected** (undocumented behavior). |
| **System message handling** | Pop `role == "system"` messages out of the `messages` array, concatenate `content` with `\n\n`, emit as the top-level `system` field. Reject other unsupported roles (`function`, `tool`, …) with `ConfigurationError` (502 — server-side shape violation). | Pass the `messages` array as-is and require callers to use the Anthropic-native shape (no system-as-message). | Convert system messages to a synthetic first `user` turn with a `[SYSTEM]: …` prefix. |
| | Pros: gateway stays OpenAI-compatible at the public surface; callers keep using the OpenAI shape; matches `provider-abstraction`'s "all providers share the same `messages` input" contract. Cons: a 2-message system policy is concatenated, not nested. | Pros: zero translation. Cons: breaks OpenAI compatibility at the public surface (the slice would not be usable from a client that sends `role:"system"`). | Pros: works for simple cases. Cons: changes semantic content; Anthropic may apply different processing to user-vs-system turns (e.g., cache control). |
| | **Chosen.** | **Rejected.** | **Rejected.** |
| **`max_tokens` default** | `anthropic_default_max_tokens = 1024` (configurable via env, default 1024). Adapter uses the value when `options["max_tokens"]` is missing. | Reject the call with `ConfigurationError` if `max_tokens` is missing. | Hardcode `1024` with no override. |
| | Pros: callers can omit `max_tokens` and get a sane default; overrides via `options["max_tokens"]`; documented in spec. Cons: callers who care about the exact ceiling must set it. | Pros: forces callers to be explicit. Cons: rejects valid OpenAI-shaped requests that worked fine on the OpenAI adapter; breaks the public "drop-in OpenAI replacement" contract. | Pros: zero config. Cons: no override path; surprising for callers who need a different ceiling. |
| | **Chosen.** | **Rejected.** | **Rejected.** |
| **Non-text content blocks** (e.g., `tool_use`) | Raise `UpstreamError` (502) with a sanitized message; do not attempt to render or skip. | Silently drop non-text blocks; concatenate only the text blocks. | Pass the content array through unchanged in `CompletionResult.content` (it would not be a string). |
| | Pros: explicit failure mode; the `provider-streaming-federation` / `anthropic-tool-use-federation` follow-up slices can replace the raise with a real implementation. Cons: callers sending prompts that trigger tool use today get a 502. | Pros: works for plain chat. Cons: silent semantic loss; a follow-up slice would have to introduce a new `CompletionResult` field, breaking compat. | **Rejected** (violates `CompletionResult.content: str`). |
| | **Chosen.** | **Rejected.** | **Rejected.** |
| **PR structure** | **2-PR chain** (recommended): **PR1** settings + `AnthropicAdapter` + unit tests (PR1 + PR2 of the OpenAI chain compressed; ~200 LoC src + ~150 LoC tests = ~350 LoC); **PR2** registry dispatch + chat + telemetry end-to-end proof (~100 LoC src + ~150 LoC tests = ~250 LoC). Each PR ≤400 authored lines. | **Single PR** combining everything. | **3-PR chain** (settings / adapter / registry+chat) with smaller per-PR scope. |
| | Pros: 2 review surfaces; each PR has a clear "what it proves" outcome (PR1 proves the adapter works in isolation; PR2 proves it works in the full chain). Cons: PR1's tests cannot exercise the chat path (deferred to PR2). | Pros: one PR to land. Cons: ~600 LoC exceeds the 400-line review budget; would need `size:exception`. | Pros: smaller per-PR reviews. Cons: PR2 (adapter) has no chat-path proof; PR3 (registry + chat) is the largest; more ceremony for a smaller delta. |
| | **Chosen.** | Deferred to a single-PR path only if the total stays under 400 (it does not). | **Rejected** (more PRs than necessary for a provider-parity slice). |
| **Fallback** | **Explicitly deferred to a later slice.** `select_provider` is first-match only — no change in this slice. The next planned slice is `provider-fallback-and-retries`, which will introduce a fallback chain across both OpenAI and Anthropic. | Implement fallback in this slice. | Implement fallback as a side-effect of adding the second provider. |
| | Pros: keeps the slice's review surface small; lets the fallback slice validate the cross-provider contract with both adapters green; matches the original ROADMAP Phase 1 plan. Cons: a request to a downed Anthropic provider still 502s until the fallback slice lands. | Pros: shipping the MVP Phase 1 outcome in one go. Cons: mixes two orthogonal concerns (new provider + new routing policy); increases the blast radius of review. | **Rejected** (fallback is a contract change to the router; it must be a deliberate, reviewable slice). |
| | **Chosen.** | Deferred to `provider-fallback-and-retries`. | **Rejected.** |
| **Streaming** | `complete_stream` raises `NotImplementedError`, mirroring the OpenAI adapter. The chat handler's `stream=true` short-circuit to 501 covers the public surface unchanged. | Implement Anthropic SSE in this slice. | Drop the `complete_stream` method from the Protocol for the Anthropic slice. |
| | Pros: keeps parity with the OpenAI slice; the `provider-streaming-federation` slice handles both providers in one chain. Cons: explicit `stream=true` requests to an Anthropic model still 501. | Pros: shipping streaming in one go. Cons: doubles the slice's review surface; mixes provider addition with streaming federation. | **Rejected** (breaks the Protocol). |
| | **Chosen.** | Deferred to `provider-streaming-federation`. | **Rejected.** |
| **ARCHITECTURE.md / ADR** | **No change.** The existing `ARCHITECTURE.md` already lists `ADPT_ANTHROPIC["Anthropic Adapter"]` in the system diagram. ADR-0002 already covers the adapter boundary. | Add ADR-0003 for the second adapter's auth shape, system message handling, and `max_tokens` default. | Update `ARCHITECTURE.md` to document the Anthropic-specific translation rules. |
| | Pros: the slice is a concrete implementation of an already-decided pattern; no new architecture decision. Cons: none for this slice. | Pros: explicit documentation. Cons: ADR-0002 already says "Anthropic has a different auth + different streaming" — re-deciding it now is ceremonial. | Pros: discoverable translation rules. Cons: ADR-0002 + this exploration.md already document the shape differences; the slice-level detail belongs in the spec, not the architecture doc. |
| | **Chosen.** | **Rejected.** | **Rejected.** |
| **Telemetry cardinality** | Reuse the existing `MODEL_UNKNOWN` / `PROVIDER_NONE` sentinels and the `ALLOWED_OUTCOMES` / `ALLOWED_ERROR_TYPES` bounded sets. The `provider` label is `getattr(adapter, "name", PROVIDER_NONE)` = `"anthropic"` on success; the bounded test from PR6 (`test_telemetry_bounded_label_values`) is extended to include `"anthropic"` in `bounded_providers`. No new instruments, no new attributes. | Add a new `provider_family` label (e.g., `"anthropic"`, `"openai"`) decoupled from the `provider` label. | Per-Anthropic-model cost labels (input/output/cache token histograms). |
| | Pros: the bounded-cardinality contract is preserved by construction (the `provider` set is fixed at the adapter boundary); no metric schema change. Cons: `provider` is the only label that distinguishes providers — a future slice that needs provider-family analytics can add a second bounded label. | Pros: future-proofs the schema. Cons: doubles the cardinality; not needed in this slice. | Pros: enables cost tracking. Cons: cost tracking is explicitly out of scope; per-model labels explode cardinality. |
| | **Chosen.** | Deferred until a slice needs provider-family analytics. | **Rejected.** |

## Recommendation

Adopt the recommended option in every row above. Concretely:

1. **2-PR chain** on a tracker branch `feat/anthropic-provider-adapter-slice` from `origin/main` @ `12a32ae`. Child PRs target the tracker (feature-branch-chain), each ≤400 authored lines.
2. **PR1** (`feat/anthropic-provider-adapter-slice-01-adapter-and-settings`): extend `config.py` (Anthropic env + fail-fast validator); create `core/providers/anthropic.py` (raw httpx, `x-api-key` + `anthropic-version`, `POST /v1/messages`, system-message pop, `max_tokens` default, content-block join, token mapping, stop-reason mapping); update `.env.example`. Tests cover the settings, the adapter in isolation (success, request shape, system extraction, content join, stop-reason map, 8-case failure map, `models()`, `health()`), and `complete_stream` raise. Estimated ~200 LoC src + ~150 LoC tests.
3. **PR2** (`feat/anthropic-provider-adapter-slice-02-registry-chat-e2e`): extend `core/providers/registry.py` (slug dispatch for `"anthropic"`, preserving transaction-like cleanup); add the live-ASGI chat end-to-end test (routed 200, 400 selection miss, 502 sanitized, 504 timeout, 501 no-telemetry); add the lifespan behavior-first regression for an Anthropic-owned client; add the bounded-label telemetry test (extend the PR6 `bounded_label_values` assertion). Estimated ~100 LoC src + ~150 LoC tests.
4. **Fallback, streaming, tool use, prompt caching, alias resolution, cost tracking, auth-validity health probe** are all explicitly **deferred** to their own follow-up slices. The slice does not touch `select_provider` (no fallback), `complete_stream` (raises), or any new `LLMuxError` subclass (reuse existing).
5. **No new ADR**, no `ARCHITECTURE.md` change, no new env prefix beyond `ANTHROPIC_*`, no new dependency. The slice is a concrete implementation of the already-decided `ProviderAdapter` pattern from ADR-0002.
6. **No review artifacts.** Review-driven development remains globally disabled by user decision; the slice delivers under ordinary `disabled/unmanaged` policy and the OpenSpec + Engram artifacts are the only audit trail.

## Risks

- **System message semantic loss** (PR1, low): a system policy that relies on Anthropic's prompt-caching control over a system block is silently degraded (no `cache_control` annotation survives the pop). Acceptable because prompt caching is explicitly deferred; documented in the spec.
- **`max_tokens` default under-shoots long responses** (PR1, low): a caller that omits `max_tokens` and sends a long-context prompt may hit the 1024 ceiling and get a `stop_reason="max_tokens"` result with truncated text. Acceptable because the caller can override via `options["max_tokens"]`; documented in the spec and `.env.example`.
- **Bounded `provider` label cardinality** (PR2, low): adding `"anthropic"` to the bounded set grows the set by one, which is fine; but a future slice that adds a third provider (e.g., Google) will do the same, and a provider-family dimension is not modeled. Acceptable because the slice is no worse than the PR6 baseline; the set is still bounded and fixed.
- **Anthropic SDK not used** (PR1, low): the slice's raw httpx adapter is a maintenance burden if Anthropic's wire shape changes (e.g., new required header). Mitigated by `httpx.MockTransport` integration tests against the canonical Anthropic fixtures used in this slice's tests; the integration surface is small.
- **Auth-validity health probe is deferred** (PR1, low): `AnthropicAdapter.health()` reports "reachable" but a bad key is invisible until the first real call. Acceptable because the chat path's `UpstreamError` is the actual signal; documented in the spec and the **Approaches** table.
- **No automatic fallback** (deferred, low for this slice): a request to a downed Anthropic provider returns 502. This is the same behavior as the OpenAI slice; the next planned slice (`provider-fallback-and-retries`) introduces the cross-provider fallback chain. The slice does not worsen the status quo.
- **Test-client double-close** (PR2, low): if the new `AnthropicAdapter` is ever constructed with a caller-owned client AND the registry's `aclose()` re-closes it, the regression window from PR3 reopens. Mitigated by the existing `RegistryEntry(adapter, client=None)` ownership contract and the `_CountingClient.aclose_count == 1` assertion pattern (mirrored in the new tests).
- **Lifespan teardown** (PR2, low): the PR7 invariant (owned client open during serving, closed exactly once after `TestClient` exit) must hold for an Anthropic-owned client as well. Mitigated by the new behavior-first regression (`test_lifespan_owned_client_stays_open_while_serving_anthropic`), which is the same shape as the PR7 OpenAI test and uses a real `AnthropicAdapter` registry entry.
- **PR1's tests do not exercise the chat path** (PR1, low): if PR1 lands but PR2 is blocked, the adapter is green in isolation but unreachable from `/v1/chat/completions`. Acceptable because PR1 is explicitly the "adapter works in isolation" surface; PR2 is the "adapter works in the full chain" surface. The feature-branch-chain target ordering (PR2 → PR1) ensures PR2 is the merge-tracker child and is always reviewed after PR1 lands.

## Ready for proposal

Yes. The orchestrator can hand off to `sdd-propose` with the change name `anthropic-provider-adapter-slice`. The proposal should:

- Cite ADR-0002 as the architectural anchor and explicitly state no new ADR is needed (the Anthropic adapter is one concrete implementation of the accepted `ProviderAdapter` pattern).
- Reference the OpenAI slice's `provider-routing-functional-slice` (PRs #10–#19, merged at `12a32ae`) as the dependency: every shared component (`ProviderAdapter`, `ProviderRegistry`, `build_providers`, `select_provider`, `LLMuxError`, `ChatTelemetry`, chat handler, `/v1/models` endpoint, lifespan) is already in place on `main` and is the contract the Anthropic slice satisfies.
- Scope the change to Anthropic non-streaming only; explicitly **defer** streaming, tool use, prompt caching, image inputs, alias resolution, cost tracking, automatic fallback, retries/backoff, circuit breaking, and auth-validity health probing.
- Cite the original ROADMAP Phase 1 plan (`Provider adapters: OpenAI, Anthropic`) and the original core-gateway-mvp slice plan (slice 12 in the archived exploration) to make clear the Anthropic adapter is the second of two MVP providers, not a stretch goal.
- Forecast the 2-PR chain and explicitly call out the per-PR authored-line budget (~350 + ~250).
- Re-state the four OpenAI guardrails that the slice must honor (test-client double-close, lifespan teardown ordering, bounded metric cardinality, no partial registry) so the proposal's "Reliability Guardrails" section is the natural anchor for PR-by-PR review.

**Do not implement code in this phase. Do not start, recover, validate, or fabricate any native review — review-driven development is OFF by user decision and delivery stays disabled/unmanaged under ordinary repository policy.**
