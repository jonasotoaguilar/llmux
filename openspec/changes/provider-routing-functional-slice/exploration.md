# Exploration: provider-routing-functional-slice

> **Change**: `provider-routing-functional-slice` (restart). **Branch**: `feat/provider-routing-functional-slice` from `origin/main` @ `02eade1`. **Delivery**: `auto-chain` / `feature-branch-chain`, 400-line review budget. **Persistence**: hybrid (this file + Engram topic `sdd/provider-routing-functional-slice/explore`).
>
> **Supersedes** (evidence only, not duplicated): blocked change `provider-routing-vertical-slice` on branch `feat/provider-routing-vertical-slice`, plus merged PRs #10, #11, #12. The four bugs the old chain hit — tracer startup cleanup, bounded metric cardinality, stable OTel error status/labels, uncaught-exception telemetry — are referenced here as guard rails so this change does not re-discover them.

## Quick path

1. Add the first functional OpenAI provider hop to the gateway (settings + adapter + registry + priority router).
2. Wire `/v1/models` to the registry and `/v1/chat/completions` (`stream=false`, **and an omitted `stream` field which defaults to `false` per the Pydantic `stream: bool = False` already on `main` and the OpenAI-compatible contract**) to the routed provider with normalized 400/502/504 envelopes; only **explicit** `stream=true` keeps the 501 no-fake-SSE contract (no provider invocation, no telemetry, no `text/event-stream`, no `data:` frames).
3. Emit one OTel span and three bounded-cardinality metrics per non-streaming hop.
4. Defer Anthropic, automatic fallback, retries, circuit breaking, and streaming.
5. Split delivery into three chained PRs, each ≤400 authored lines, target `feat/provider-routing-functional-slice` (then chain).

## Current state (main @ 02eade1)

| Area | State on main | This change adds |
|------|---------------|------------------|
| `src/llmux/core/providers/base.py` | `ProviderAdapter` Protocol + `CompletionResult` / `Chunk` / `ModelInfo` / `HealthStatus` dataclasses (frozen, slots) | Nothing on the port itself; concrete OpenAI adapter must satisfy it |
| `src/llmux/config.py` | `Settings` with `LLMUX_*` + `OTEL_*` only; `LLMUX_PROVIDERS_CONFIGURED` parsed from JSON or CSV | `OPENAI_API_KEY` (SecretStr), `OPENAI_BASE_URL`, `OPENAI_MODELS`, `OPENAI_TIMEOUT_S`; fail-fast `ConfigurationError` when OpenAI enabled with empty key |
| `src/llmux/main.py` | Lifespan: `build_tracer` → yield → `shutdown_tracer`; routers mounted on `/v1` | Build the registry **after** the tracer, **yield**, then `aclose()` the registry in a `finally` **before** `shutdown_tracer()` — so a startup-time build failure still runs tracer cleanup |
| `src/llmux/api/chat.py` | Single sync handler returns 501 for `stream=false`, `stream=true`, and omitted | Async handler: **only explicit `stream=true`** returns 501 (no provider invocation, no telemetry, `Content-Type: application/json`, no `data:` SSE frames); `stream=false` **and omitted `stream` (Pydantic default, treated as `stream=false`)** run the selected adapter, record span + metrics, and return a 200 envelope or normalized 400/502/504 |
| `src/llmux/api/models.py` | Returns `{"object":"list","data":[]}` | Aggregates one OpenAI-shaped entry per `(provider, model)` from the registry |
| `src/llmux/api/health.py` | Gateway-native JSON, lists `llmux_providers_configured` | Unchanged |
| `src/llmux/observability/tracing.py` | Tracer provider build + shutdown only | Unchanged; new `metrics.py` module is a sibling |
| `src/llmux/core/errors.py` | Does not exist | New file with `LLMuxError` base + `ConfigurationError` (502 **if surfaced at the routed HTTP mapping — normally fail-fast at startup, never 400**), `ProviderSelectionError` (400), `UpstreamError` (502), `UpstreamTimeoutError` (504); each maps to OpenAI-shaped envelope |
| `src/llmux/core/providers/{openai,registry}.py` | Do not exist | `OpenAIAdapter` (injected `httpx.AsyncClient`, non-streaming only, `complete_stream` raises `NotImplementedError`); `ProviderRegistry` (`Sequence[ProviderAdapter]` with `aclose()`) |
| `src/llmux/core/router.py` | Does not exist | `select_provider(model, registry)` — async, first exact match, no retry, no fallback |
| `src/llmux/observability/metrics.py` | Does not exist | `chat_completion_requests_total` counter, `chat_completion_errors_total` counter, `chat_completion_duration_seconds` histogram; bounded labels `provider`, `model`, `outcome`, `error_type`; `MODEL_UNKNOWN` constant for unknown-model paths |
| `.env.example` | Runtime + OTLP only | Add OpenAI vars |
| `tests/` | 27 tests across `tests/core/test_provider_protocol.py` and `tests/test_unit_2.py` (settings, tracing, /v1 boundary, app factory) | `tests/test_provider_routing_slice.py` for the new boundary; extend `tests/test_unit_2.py` only where app-factory behavior changes |

## Affected areas

- `src/llmux/config.py` — extend settings; do **not** silently accept missing OpenAI key when provider is enabled.
- `src/llmux/core/errors.py` (new) — `LLMuxError` hierarchy + `to_openai_envelope()`; bodies must never carry keys, upstream payloads, or stack traces.
- `src/llmux/core/providers/openai.py` (new) — implements `ProviderAdapter` for OpenAI Chat Completions (non-streaming). `complete_stream` raises `NotImplementedError`. Accepts injected `httpx.AsyncClient` for `MockTransport`-based tests.
- `src/llmux/core/providers/registry.py` (new) — `ProviderRegistry` (ordered `Sequence[ProviderAdapter]` + `aclose()`) and `build_providers(settings)` factory. Owns production clients; injected clients stay caller-owned.
- `src/llmux/core/router.py` (new) — `select_provider(model, providers)`. First match by `models()`. No retry, no fallback. Raises `ProviderSelectionError` (400) when nothing serves the model.
- `src/llmux/main.py` — wire the registry into lifespan with the failure-safe teardown order: tracer → build registry → yield → `aclose()` → shutdown tracer.
- `src/llmux/api/chat.py` — async `stream=false` path; **omitted `stream` defaults to `false` (Pydantic `stream: bool = False`) and routes through the same async path**; **only explicit** `stream=true` returns 501 before any provider or telemetry activity (no provider call, no span, no metric, no SSE).
- `src/llmux/api/models.py` — pull from `request.app.state.providers`; emit `id`, `object`, `created:0`, `owned_by`.
- `src/llmux/observability/metrics.py` (new) — three instruments; bounded labels; no raw upstream payloads.
- `.env.example` — document the OpenAI env contract and the `LLMUX_PROVIDERS_CONFIGURED=["openai"]` enablement.
- `tests/test_provider_routing_slice.py` (new) — MockTransport-based unit + live-ASGI coverage for the four slices.
- `openspec/changes/provider-routing-functional-slice/{proposal,specs/*,design,tasks,apply-progress}.md` — fresh artifacts under the new change name; no carry-over from the blocked tracker.

## Approaches (with old-PR evidence attached)

| Decision | Option A (chosen) | Option B | Evidence from the old chain |
|----------|-------------------|----------|-----------------------------|
| **Lifespan teardown order** | Build tracer → build registry in `try` → `yield` → `finally { if providers: aclose(); shutdown_tracer() }` | Build registry first, then tracer; teardown in reverse | PR #11 review caught a startup-failure tracer leak; the chosen order is the one the review landed on |
| **Registry failure model** | Fail-fast: any unknown slug, duplicate slug, empty key/models, or invalid URL aborts startup with `ConfigurationError` | Best-effort: skip invalid slugs, log warning | Fail-fast matches ADR-0002 and the existing `ConfigurationError` contract; "silent skip" is explicitly forbidden in the old spec and would re-introduce the original 501-stub footgun |
| **Selection policy** | Async `select_provider` — first adapter whose `models()` includes the requested model; raise `ProviderSelectionError` (400) on no match | Random/weighted; with fallback | First-match is deterministic and observable; automatic fallback is the `provider-fallback-and-retries` follow-up change |
| **Error → HTTP status** | `ProviderSelectionError`→400 (`invalid_request_error`), `ConfigurationError`→502 (**only if surfaced at the routed HTTP mapping — normally fail-fast at startup, never 400**), `UpstreamError`→502, `UpstreamTimeoutError`→504 (timeout) | 503 for "provider unavailable" | 400 fits "model not served" (client-fixable, not transient capacity); 503 would falsely promise a retry that this change does not implement; `ConfigurationError` is a server/startup configuration fault, not a caller input fault, so 502 (never 400) is the only correct surface if one ever escapes startup |
| **Telemetry cardinality** | Counter `requests_total{provider, model, outcome, error_type}`, Counter `errors_total{...}`, Histogram `duration_seconds{provider, model}`; `MODEL_UNKNOWN = "unknown"` for unselected-model 400s | Per-model histogram with no constant fallback | Old PR #12 review corrected unknown-model cardinality; the chosen label set is the one the review landed on |
| **OTel error reporting** | `span.set_status(Status(StatusCode.ERROR, err.error_type))` plus `error.type` attribute; metric label `error_type` on the error counter | Plain `set_status(ERROR)` with no description | Old PR #12 review corrected OTel error status; the chosen form is the one the review landed on |
| **Uncaught-exception accounting** | Wrap the routed call site so any `LLMuxError` increments the error counter, sets span status, and emits the envelope — no bare `except: pass` | Trust downstream try/except to record | Old PR #12 review corrected uncaught-exception accounting; the design above is the one the review landed on |
| **Test client ownership** | Production clients in registry are closed by `aclose()`; injected test clients (e.g. `MockTransport`) stay caller-owned and are not double-closed | Always close any client the adapter holds | Old PR #12 review corrected a test-client leak; ownership rules above are the one the review landed on |
| **Omitted `stream` field** | Treat omitted as `stream=false` (Pydantic `stream: bool = False` is already on the request model on `main`) and route through the async path; emit telemetry; return 200 or normalized 400/502/504 | Treat omitted as `stream=true` (501), or surface a 400 "missing field" | The Pydantic default is already `False` on `main`; keeping the default at `false` matches the OpenAI-compatible contract, routes every omitted-field request through telemetry and the routed call site (so the four guardrails — span status, error counter, sanitized envelope, no bare `except: pass` — apply uniformly), and avoids reintroducing the silent 501 path the old chain explicitly removed in the `gateway-api-boundary` spec's REMOVED section |
| **OpenAI `complete_stream`** | Raises `NotImplementedError`; chat handler returns 501 before any provider call when `stream=true` | Stub returning an empty async iterator | The first option keeps the no-fake-SSE contract enforced at the adapter boundary, not just at the handler |

## Recommendation

Adopt Option A in every row above. The product outcome is identical to the blocked chain, but the artifacts, the runtime ledger, and the OpenSpec change folder are fresh; the four corrections from the old reviews are baked in as design-time constraints, not discovered at review time.

Sequencing for delivery (each PR ≤400 authored lines, target = previous PR's branch):

1. **PR1 — config + errors + OpenAI adapter + registry** (~165 lines src + 8 unit tests). Fail-fast `ConfigurationError` in settings + registry; injected `httpx.AsyncClient`; `complete_stream` raises `NotImplementedError`; ordered `ProviderRegistry` with `aclose()`.
2. **PR2 — router + lifespan + models endpoint** (~25 src + 6 tests). Lifespan builds tracer → registry → yield → registry `aclose()` → tracer shutdown. `/v1/models` aggregates from the registry.
3. **PR3 — chat handler + telemetry** (~110 src + 11 tests). **Only explicit** `stream=true` short-circuits to 501 (no provider invocation, no telemetry, no SSE). `stream=false` **and omitted `stream` (treated as `stream=false` per the Pydantic default)** run the adapter inside `start_as_current_span("chat.completion")` with bounded `requests_total` / `errors_total` / `duration_seconds`. Live-ASGI MockTransport harness covers success 200, selection 400, upstream 502, timeout 504, **omitted `stream` → 200 (routes) — same envelope as `stream=false`**, and explicit `stream=true` no-fake-SSE (no `data:` frames, no provider call, no metric).

No new ADR: ADR-0002 already fixes the adapter boundary; this change specializes one vertical slice. `ARCHITECTURE.md` remains unchanged.

## Risks

- **Tracer startup leak** (regression risk for PR2): if `build_providers` raises inside the lifespan, `shutdown_tracer()` must still run. Evidence: caught in old PR #11.
- **Unbounded metric cardinality** (PR3): using the raw request `model` string on every label position explodes time series when callers hit unknown models. Evidence: caught in old PR #12 — use `MODEL_UNKNOWN` whenever selection fails.
- **Unstable OTel error status / labels** (PR3): an `OK` status with a `set_attribute("error.type", ...)` side-channel is invisible to APM backends; a `Status(StatusCode.ERROR, description)` is not. Evidence: caught in old PR #12.
- **Uncaught-exception accounting** (PR3): a `try/except` that only covers one LLMux error type lets unhandled exceptions fall through with no metric. Evidence: caught in old PR #12.
- **Test-client double-close** (PR1): a `finally` that always closes the adapter's client will also close `MockTransport`-backed test clients. Evidence: caught in old PR #12.
- **Multi-provider construction failure** (future-only, out of scope): when a second provider is added, partial construction must close already-built clients. Already noted as a non-blocking warning in old PR #10; the chosen registry API must support that future fix without breaking this slice.

## Ready for proposal

Yes. The orchestrator can hand off to `sdd-propose` with the change name `provider-routing-functional-slice`. The proposal should:

- Cite ADR-0002 as the architectural anchor and explicitly state no new ADR is needed.
- Scope the change to OpenAI non-streaming only; defer Anthropic, fallback, retries, circuit breaking, and streaming.
- Reference PRs #10, #11, #12 of the blocked chain as evidence of the four pre-discovered bugs, but use a fresh runtime ledger and fresh artifacts under `openspec/changes/provider-routing-functional-slice/`.
- Forecast the three-PR chain and explicitly call out the per-PR authored-line budget.

Do not implement code in this phase. Do not start, recover, validate, or fabricate any native review — review-driven development is OFF by user decision and delivery stays disabled/unmanaged under ordinary repository policy.
