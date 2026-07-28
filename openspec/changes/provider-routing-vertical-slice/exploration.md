# Exploration: `provider-routing-vertical-slice` — first real provider hop

> **Status**: Proposed — exploration artifact for change `provider-routing-vertical-slice`.
> **Branch**: `feat/provider-routing-vertical-slice` (base: `main` @ 02eade1, PR #8 merged).
> **Session**: `execution_mode=auto`, `artifact_store.mode=hybrid` (OpenSpec + Engram),
> `delivery_strategy=auto-chain`, `review_budget_lines=400`.
> **No production code is implemented in this exploration.**

## 1. Goal of this slice

Replace the Phase 0 "stub-only" surface (`/v1/chat/completions` returns 501, `/v1/models`
returns empty) with the **smallest functional end-to-end provider hop** in ROADMAP
Phase 1. Concretely:

1. One concrete `ProviderAdapter` — **OpenAI** — backed by `httpx`.
2. A **priority router** that picks the highest-priority enabled provider for a
   request. (No fallback yet — see §5.)
3. **Real non-streaming `POST /v1/chat/completions`** returning an OpenAI-shaped
   completion envelope.
4. **`GET /v1/models`** populated from the configured models across enabled
   providers (not the empty `data: []` stub).
5. **Normalized errors and timeouts** — gateway returns OpenAI-shaped error
   envelopes for upstream 4xx/5xx, timeouts → 504, and structured provider
   classification.
6. **Request telemetry** — every `/v1/chat/completions` call produces an OTel
   span (`chat.completion`) with model / provider / latency / token attributes,
   plus a small set of metrics (request count, error count, latency histogram).

This slice is **explicitly narrower than ROADMAP Phase 1**. It is the
first *functional* phase-1 sub-slice; the full Phase 1 (Anthropic, fallback,
API-key auth, metering persistence, dashboard) is intentionally deferred
to subsequent changes (see §5 and §7).

## 2. Detected repository facts

All facts below are observed in the working tree of `feat/provider-routing-vertical-slice`
at exploration time. None is an assumption.

| Fact | Evidence |
|------|----------|
| Branch created from `main` | `git branch --show-current` → `feat/provider-routing-vertical-slice`; `main` HEAD = `02eade1` (PR #8) |
| Working tree is clean | `git status --short` is empty |
| Prior slice (`core-gateway-mvp`) merged | `openspec/changes/archive/2026-07-23-core-gateway-mvp/` exists; PR #8 commit `02eade1` |
| `ProviderAdapter` Protocol already in code | `src/llmux/core/providers/base.py` — `complete`, `complete_stream`, `models`, `health` declared; `@runtime_checkable` |
| Normalized dataclasses already in code | Same file — `CompletionResult`, `Chunk`, `ModelInfo`, `HealthStatus` (frozen, slots) |
| `/v1/chat/completions` is a 501 stub | `src/llmux/api/chat.py:36-38` returns `JSONResponse(501, NOT_IMPLEMENTED_ERROR)` for every body |
| `/v1/models` is a literal empty list | `src/llmux/api/models.py:11` returns `{"object": "list", "data": []}` |
| `/v1/health` works | `src/llmux/api/health.py` — returns `{"status", "version", "providers_configured"}`; live HTTP test in `tests/test_unit_2.py:128-143` |
| `Settings.llmux_providers_configured` already exists | `src/llmux/config.py:19-23` — list[str], parses JSON or CSV, defaults `[]` |
| `httpx` is already a dependency | `pyproject.toml:13` — `httpx>=0.27.0` |
| OTel is wired but lazy | `src/llmux/observability/tracing.py:17-25` — `build_tracer()` only installs an SDK `TracerProvider` when `OTEL_EXPORTER_OTLP_ENDPOINT` is non-empty; otherwise returns `trace.get_tracer(_INSTRUMENTATION_MODULE)` (no-op) |
| Test harness uses FastAPI `TestClient` | `tests/conftest.py` — `app` + `client` fixtures; per-router `_client()` helper in `tests/test_unit_2.py:49-54` |
| Strict TDD is on | `openspec/config.yaml:18-27` — `strict_tdd: true`, `coverage_threshold: 90`, `test_command: uv run pytest -q --cov=llmux --cov-fail-under=90` |
| Two specs are source of truth | `openspec/specs/gateway-api-boundary/spec.md` (501 stub) and `openspec/specs/provider-abstraction/spec.md` (Protocol only, no concrete adapter) — both now **incorrect** for the real slice |
| No persistence in scope | `.env.example` has no DB / Redis URL; `ARCHITECTURE.md` calls for them but PRD/ROADMAP keep this slice POST-free |
| No API-key auth in scope | Phase 0 explicitly excluded; `gateway-api-boundary/spec.md` non-goals enumerate it as deferred |
| `pytest-asyncio` available | `pyproject.toml:19` — `pytest-asyncio>=0.23.0`; `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` |
| `.env.example` exposes provider slug list | `LLMUX_PROVIDERS_CONFIGURED=[]` — today it's just a list of slugs; new slice must extend the env contract to carry per-provider config (see §4) |

## 3. Current state (what the gateway does today)

- `POST /v1/chat/completions` is a synchronous function that returns
  `501 not_implemented_error` for both `stream=true` and `stream=false`. No
  request is ever forwarded. No OTel span is opened for the request. The
  function signature is `def post_chat_completion(_: ChatCompletionRequest) ->
  JSONResponse` — the request is discarded.
- `GET /v1/models` returns `{"object": "list", "data": []}` regardless of
  `Settings.llmux_providers_configured`. The setting is currently **only
  surfaced via `/v1/health`**.
- `GET /v1/health` is the only operational surface; it reports
  `providers_configured` from settings but does **not** probe any provider.
- There is no provider registry, no router, no per-request span, no metric,
  no error mapping, and no httpx client. The Protocol from ADR-0002 is
  declared but unfulfilled.
- `Settings` carries `LLMUX_PROVIDERS_CONFIGURED` (a list of slugs in
  priority order) but no API keys, base URLs, or per-provider model lists.

## 4. The new env contract (decisions this slice must lock in)

Today the env contract is `LLMUX_PROVIDERS_CONFIGURED=[…]`. The smallest
extension that lets an OpenAI adapter actually run is:

| New env var | Default | Purpose |
|-------------|---------|---------|
| `OPENAI_API_KEY` | empty (slice must refuse to start if provider enabled and key missing) | Bearer token for OpenAI HTTP calls |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override for proxies / Azure-OpenAI-style endpoints |
| `OPENAI_MODELS` | `["gpt-4o-mini", "gpt-4o"]` (comma-separated; parses same as `LLMUX_PROVIDERS_CONFIGURED`) | Models this OpenAI instance advertises in `/v1/models` |
| `OPENAI_TIMEOUT_S` | `30.0` | Per-request httpx timeout (covers connect+read); normalized to 504 on expiry |

These four additions are the **minimum surface** needed for the slice.
They are deliberately per-provider (not a JSON blob) so the
`Settings` model stays greppable and the change review stays narrow.
Naming convention is `<PROVIDER>_<FIELD>` — consistent with the existing
`LLMUX_*` and `OTEL_*` prefix style.

`LLMUX_PROVIDERS_CONFIGURED` keeps its current shape (list[str]) and gains
an interpretation: **order = priority, presence = enabled**. A provider
slug in the list that has no matching `<PROVIDER>_API_KEY` is a
configuration error and MUST be surfaced as a 502 on first use with a
clear OpenAI-shaped error message — never a silent skip.

## 5. Approaches for the slice boundary

### Approach A — single change, three chained PRs (RECOMMENDED)

Deliver the whole functional hop in one change, split across three chained
PRs sized to fit the 400-line budget.

| PR | Scope | Approx authored lines |
|----|-------|-----------------------|
| **PR #1 (Settings + OpenAI adapter + registry)** | New `Settings` fields; new `core/providers/openai.py` with `OpenAIAdapter` (httpx + JSON translation); new `core/providers/registry.py` (build a list of adapters from `Settings`); tests for the adapter against `httpx.MockTransport`; test for the registry. | ~250–300 |
| **PR #2 (priority router + `/v1/models` real)** | New `core/router.py` with `select_provider(model, configured)` returning the highest-priority enabled adapter that lists the model; rewrite `GET /v1/models` to aggregate from the registry; tests. | ~150–200 |
| **PR #3 (`/v1/chat/completions` real + errors + telemetry)** | Rewrite the chat route to call `router.select_provider().complete(...)`; map httpx / provider errors to OpenAI-shaped envelopes (400/502/504); open an OTel span per request with model/provider/latency/tokens attributes; add metrics (`chat_completion_requests_total`, `chat_completion_errors_total`, `chat_completion_duration_seconds`); tests. | ~250–300 |

**Pros**

- Each PR is reviewable under the 400-line budget; orchestrator can gate
  with `chained_pr_strategy=auto-forecast`.
- Settings/contract work lands first, so PR #2 and PR #3 don't refactor
  each other.
- Telemetry wiring lands last, so OTel attribute shape is informed by the
  real adapter output, not invented upfront.
- Each PR is independently mergeable; the previous Phase 0 stub slice
  proves the chained-PR discipline works in this repo (see archive
  `core-gateway-mvp`).

**Cons**

- Three PRs to merge for a single feature; orchestrator overhead.
- `/v1/chat/completions` stays 501 until PR #3 lands — but the existing
  spec is the source of truth and that is fine because the spec is
  updated in the same change.

**Effort**: Medium (3 PRs).

### Approach B — single change, single big PR

| Field | Value |
|-------|-------|
| Scope | Everything above in one PR. |
| Approx authored lines | ~600–800 — over budget. |

**Pros**: One PR; no chained orchestration.
**Cons**: **Violates the 400-line review budget**; cannot be merged under
the configured `chained_pr.strategy=auto-forecast` without an explicit
size exception. Rejected by repo convention (see prior slice where
`core-gateway-mvp` Unit 2 was deliberately split on the same grounds).
**Effort**: Low for author, high for reviewer.

### Approach C — split into two changes: (1) OpenAI + router, (2) chat completion rewrite

| Field | Value |
|-------|-------|
| Scope | Change 1 = PR #1 + PR #2 from Approach A. Change 2 = PR #3 alone. |
| Approx authored lines | Same per PR, but two SDD change folders, two sets of artifacts. |

**Pros**: Decouples the OpenTelemetry wiring change from the router
change.
**Cons**: Double orchestration overhead for a tightly-coupled feature
where the telemetry attributes depend on the adapter output. The two
slices are not independently valuable (the chat route rewrite depends
on the router). Rejected — adds ceremony without insight.

## 6. What is explicitly **out of scope** (deferred, not dropped)

The current ROADMAP Phase 1 lists OpenAI + Anthropic + fallback + auth +
metering. This slice covers OpenAI only and **does not** ship:

| Deferred item | Target | Why deferred |
|---------------|--------|--------------|
| Anthropic adapter | Separate change, e.g. `provider-anthropic-adapter` | Different auth header, different request shape (system as first message), different SSE format — adds ~150 lines on top of the OpenAI adapter. Including it now would push PR #1 over budget and force another split. |
| Fallback / retry / circuit breaker | Separate change, e.g. `provider-fallback-and-retries` | Adds error classifier, retry-with-backoff, multi-adapter selection, possibly circuit-breaker state. The `Router` in this slice returns the first enabled provider only; the fallback policy is a new method on the same module. |
| Streaming (`stream=true`) | Separate change, e.g. `chat-streaming` | OpenAI SSE framing + FastAPI `StreamingResponse` is its own contract. The current `ProviderAdapter.complete_stream` is declared but unused; the slice does not touch it. `POST /v1/chat/completions` with `stream=true` continues to return 501 — the existing 501 contract is preserved for streaming only. |
| API-key auth (tenant + scopes) | Phase 0 spec explicitly deferred; separate change in Phase 1.1 of the ROADMAP | Adds bcrypt hashing, key store, middleware, `Auth` context. The 400 error envelope on missing/expired keys is straightforward; the lookup, hashing, and rotation logic is not. |
| Metering persistence (PostgreSQL) | Phase 1 of ROADMAP, separate change | Telemetry in this slice is OTel-only; no DB writes. ARCHITECTURE.md places this in the Metering module — its own slice. |
| Redis-backed rate limit / budget | Phase 2 of ROADMAP | Per the ROADMAP explicitly. |
| Admin dashboard | Phase 1 of ROADMAP, separate change | Already has its own design doc; not coupled. |

**Key decision: Anthropic and fallback are deferred — see §7 for
rationale.** The OpenAI adapter alone is the minimum that lets the
gateway actually return a 200 to a real provider; the priority router
gives a stable mount point for the next provider.

## 7. Recommendation

**Pick Approach A. Defer Anthropic and fallback to subsequent changes.**

Why this combination:

1. **Budget.** Three PRs each ≤300 authored lines fit the 400-line review
   budget cleanly. The prior `core-gateway-mvp` slice proved the
   `auto-forecast` + chained-PR pattern works on this repo, and a single
   big PR (Approach B) was already rejected for the same reason there.
2. **Value per PR.** PR #1 alone is reviewable and mergeable: an OpenAI
   adapter with a registry and passing tests, no router, no chat
   rewrites. The slice never has a "broken intermediate" PR.
3. **Anthropic is a separate adapter class, not a router change.** Adding
   the Anthropic adapter in this change would inflate PR #1 by ~150 lines
   (header format, system-prompt extraction, max_tokens naming) and
   require an `_anthropic/` model-list update, without changing the
   router's contract. The router's contract is "first enabled provider
   that lists the requested model" — which works for any future adapter
   for free.
4. **Fallback is a router behavior change.** It requires a multi-adapter
   return type, an error classifier, and retry policy — all things that
   belong to the Router module. Trying to bolt them onto PR #2 (which
   introduces the Router) would conflate two distinct design decisions
   in a single review.
5. **Telemetry belongs with the chat rewrite.** PR #3's OTel attributes
   (model, provider, prompt_tokens, completion_tokens, latency_ms,
   error_class) only make sense once the adapter is producing real
   values. Tying telemetry to the chat rewrite is also where the
   NFR-overhead guarantee (`< 50ms p95` per ARCHITECTURE.md) can be
   measured.

**Tracker branch:** `feat/provider-routing-vertical-slice` (already
created in this session from `main` @ 02eade1). Child PRs target
`feat/provider-routing-vertical-slice` in chain order.

**Provider-of-record in this slice:** OpenAI only. The
`ProviderAdapter` Protocol is generic; the registry is constructed
once at app startup and the router consults it. The next change
(`provider-anthropic-adapter`) drops a new file into
`core/providers/anthropic.py` and the registry grows a single new branch
— no other code changes.

## 8. Affected areas (what the slice will touch)

The slice modifies or extends:

- `src/llmux/config.py` — add `openai_api_key`, `openai_base_url`,
  `openai_models`, `openai_timeout_s` fields. Existing fields unchanged.
- `src/llmux/core/providers/openai.py` (NEW) — `OpenAIAdapter(ProviderAdapter)`
  using `httpx.AsyncClient`. Implements `complete`, `models`, `health`.
  `complete_stream` declared but raises `NotImplementedError` (the
  Protocol contract is honored; the streaming slice is its own work).
- `src/llmux/core/providers/registry.py` (NEW) — `build_providers(settings) -> list[ProviderAdapter]`
  reading `Settings.llmux_providers_configured` and instantiating the
  matching adapter. Stashes the built list on `app.state.providers`.
- `src/llmux/core/router.py` (NEW) — `select_provider(model, providers) -> ProviderAdapter`
  that returns the first adapter whose `models()` includes the requested
  model. Raises a structured `ProviderSelectionError` (subclass of
  `LLMuxError`) when no provider matches.
- `src/llmux/core/errors.py` (NEW) — `LLMuxError` hierarchy:
  `ConfigurationError`, `ProviderSelectionError`, `UpstreamError`,
  `UpstreamTimeoutError`. Each has a `.to_openai_envelope()` method
  producing the standard error body.
- `src/llmux/api/chat.py` (MODIFIED) — route now `async`, opens OTel
  span, calls router + adapter, normalizes exceptions to OpenAI error
  envelopes, returns the completion as an OpenAI-shaped JSON response.
  `stream=true` STILL returns 501 (existing contract).
- `src/llmux/api/models.py` (MODIFIED) — route now async, aggregates
  `ModelInfo` from `app.state.providers`, returns OpenAI-shaped
  envelope with one entry per (provider, model).
- `src/llmux/main.py` (MODIFIED) — `lifespan` calls
  `build_providers(resolved)` and stashes on `app.state.providers`;
  `create_app` becomes async-lifespan only (the existing
  `TestClient` flow is preserved because `lifespan` already runs on
  the sync client).
- `src/llmux/observability/metrics.py` (NEW) — small helper that
  exposes the three counters/histograms using
  `opentelemetry-api` directly (no SDK dependency in tests).
- `tests/test_provider_routing_slice.py` (NEW) — covers the new
  behavior end-to-end against `httpx.MockTransport`.
- `tests/test_unit_2.py` (MODIFIED) — the two assertions
  `test_chat_501_for_all_stream_modes` and
  `test_models_returns_openai_envelope_with_empty_data` are
  **inverted** (or moved) to assert the new contract for the
  `stream=false` and `models` cases, and a new test asserts
  `stream=true` still returns 501. Existing 501 contract for
  streaming is preserved exactly.
- `openspec/specs/gateway-api-boundary/spec.md` (MODIFIED delta) —
  the 501-stub requirements for `/v1/chat/completions` and
  `/v1/models` are replaced by the real contracts. Streaming
  remains 501.
- `openspec/specs/provider-abstraction/spec.md` (MODIFIED delta) —
  add `(implemented)` mark to the Protocol section; add a new
  requirement covering the OpenAI adapter (not the Anthropic one,
  which stays in the deferred spec change).
- `openspec/changes/provider-routing-vertical-slice/specs/...` (NEW) —
  delta specs for the new behaviors. Archive folder follows the
  same `2026-07-23-core-gateway-mvp/` precedent.
- `.env.example` (MODIFIED) — add the four `OPENAI_*` vars with
  safe defaults.
- `docs/adr/` — no new ADR required. The `ProviderAdapter` Protocol
  in `core/providers/base.py` is the contract; the
  priority-router behavior is captured in the slice's `design.md`,
  not a new ADR. (If the user later wants ADR-0003, the orchestrator
  can lift the design section.)

## 9. Test & contract impact (what existing tests must change)

- `test_chat_501_for_all_stream_modes` (`tests/test_unit_2.py:155-168`)
  is the **only** test that asserts 501 for `stream=false`. It is
  parametrized over `[False, True, None]`. After this slice, only
  `True` (and the no-stream-field case that still defaults to
  `stream=False`) should hit the stream-false 501 path. The test must
  be split or parametrized: `stream=false` and `stream=None` now
  return either 200 (success) or 502/504 (provider error) — never
  501. The `stream=true` case stays 501. A clean migration is to
  keep the existing test for the `stream=true` case and add a new
  parametrized test for the success/error envelope of the
  `stream=false` and `stream=None` cases.
- `test_models_returns_openai_envelope_with_empty_data`
  (`tests/test_unit_2.py:146-149`) is **inverted**: `/v1/models` now
  returns at least one entry when `openai` is enabled with default
  models. The test is updated to seed `llmux_providers_configured`
  and assert the new shape.
- `test_health_returns_required_fields_json_envelope` and the
  `providers_configured` assertions stay unchanged.
- `test_create_app_mounts_all_three_v1_routes` is updated to assert
  that `/v1/chat/completions` with `stream=false` now returns 200 or
  502 (with a mock provider), not 501.
- New test module `tests/test_provider_routing_slice.py` covers the
  registry, router, adapter, error mapping, and telemetry attributes
  in isolation. Coverage threshold (90%) is enforced by the existing
  `verify.test_command` in `openspec/config.yaml`.

## 10. Risks

- **Live OpenAI calls in tests.** The OpenAI adapter must use
  `httpx.MockTransport` (or `respx`) for tests. A naive
  `httpx.AsyncClient(base_url=...)` in the adapter is a real risk for
  CI if any test path forgets to patch it. Mitigation: the adapter
  accepts the `httpx.AsyncClient` as a constructor argument; the
  registry wires a real client only in production and the test
  fixtures inject mocks. This is the standard pattern; the
  test_unit_2.py harness already shows how to wire Settings.
- **OTel attribute shape drift.** The OTel span and metric names are
  chosen in PR #3 with no prior consumer. Mitigation: names follow
  OpenTelemetry semantic conventions where possible
  (`gen_ai.*` attributes; `gen_ai.client.request.duration` metric is
  planned but **not** the first metric emitted — the slice emits a
  simple `llmux.chat.duration` histogram for now to avoid premature
  coupling to the semantic-convention alpha).
- **`LLMUX_PROVIDERS_CONFIGURED` misconfiguration.** Enabling a
  provider without an API key silently fell through before. The slice
  makes this a 502 with a clear error message. **Risk:** existing
  deployments that list a provider without a key (no-op today) will
  start returning 502 on `/v1/chat/completions`. Acceptable because
  the gateway is pre-MVP and the error is clear.
- **Pydantic v2 settings reload.** The new `OPENAI_*` fields are added
  with safe defaults; an env file without them still parses. Tests
  that use `Settings.model_construct(**_BASE)` must add the new
  fields to `_BASE` or accept the defaults. Mitigation: the new
  defaults make `_BASE` backward-compatible.
- **Reviewer cognitive load across three PRs.** Three chained PRs is
  more orchestration than one PR. Mitigation: the
  `chained_pr_strategy=auto-forecast` flag and the prior
  `core-gateway-mvp` precedent both prove the discipline works; the
  tracker branch lets reviewers see the whole chain in one diff if
  they want to.
- **No streaming coverage in this slice.** `stream=true` keeps the 501
  contract. The `ProviderAdapter.complete_stream` method is declared
  but the OpenAI adapter raises `NotImplementedError` for it. The
  existing `provider-abstraction/spec.md` already labels streaming
  as deferred; this slice doesn't change that.

## 11. Ready for proposal?

**Yes.** The slice is well-bounded, the budget fits, the contract
changes are explicit, and the test impact is well-understood. The
proposal phase can pick up the §5/§7 decision and turn it into
`proposal.md`.

Hand the orchestrator this answer to the user: *"Pick the three-PR
chain (Approach A), defer Anthropic and fallback to subsequent
changes, and proceed to `sdd-propose`."* If the user prefers
single-PR (Approach B), a size exception is required; the orchestrator
should ask before recommending it.

## 12. Cross-references

- `openspec/specs/gateway-api-boundary/spec.md` — current 501 stub
  contract; needs `MODIFIED` delta in this change.
- `openspec/specs/provider-abstraction/spec.md` — Protocol source of
  truth; needs `MODIFIED` delta adding "OpenAI adapter (implemented)".
- `src/llmux/api/chat.py:13-20` — `NOT_IMPLEMENTED_ERROR` literal to
  be replaced.
- `src/llmux/api/models.py:7-12` — empty-list stub to be replaced.
- `src/llmux/main.py:17-31` — `create_app`/`lifespan` to gain a
  registry build step.
- `src/llmux/observability/tracing.py` — existing OTel wiring
  (unchanged; the slice consumes it from the chat route).
- `docs/adr/0002-provider-abstraction-pattern.md` — Protocol contract
  this slice fulfills.
- `ROADMAP.md` Phase 1 — scope this slice is the smallest functional
  subset of.
- `ARCHITECTURE.md` §"Failure Modes" — confirms the 502/504 envelope
  shape used by the error mapping.
- `openspec/changes/archive/2026-07-23-core-gateway-mvp/` — the
  prior slice; this change is the direct successor.
