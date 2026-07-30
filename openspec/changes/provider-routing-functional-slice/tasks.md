# Tasks: Provider Routing Functional Slice

## Review Workload Forecast

Authored src+test: **~1,230–1,300** (PR1 ~250 · PR2 ~210 · PR3 ~200 · PR4 ~185 · PR5 ~145 · PR6 ~230) +~8–12 `tasks.md` lines/PR.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Work Units

| # | Focused test | Harness · Rollback |
|---|--------------|--------------------|
| 1 | `pytest -k "openai_settings or errors_envelope" -q` | empty `OPENAI_API_KEY` → `ConfigurationError` · revert `config.py`, `.env.example`; rm `core/errors.py` |
| 2 | `pytest -k "openai_adapter" -q` | `MockTransport` 200/4xx/5xx/timeout · rm `core/providers/openai.py` |
| 3 | `pytest -k "registry or build_providers" -q` | mid-construct fail → first client closed · rm `core/providers/registry.py` |
| 4 | `pytest -k "router or lifespan or models_aggregate" -q` | `/v1/models` 200 per `(provider,model)`; build fail still `shutdown_tracer` · rm `core/router.py`; revert `main.py`, `api/models.py` |
| 5 | `pytest -k "chat_routing or chat_envelope" -q` | 200/400/502/504; `stream=true` → 501 JSON · revert `api/chat.py` to 501 stub |
| 6 | `pytest -k "telemetry or chat_telemetry" -q` | exporter: span ERROR, sentinel, error counter · rm `observability/metrics.py`; revert `api/chat.py` to PR5 |

## PR1 — Config + Errors (base tracker) ✅

> **Scope (this batch, 2026-07-30)** — narrowed by orchestrator to **config + normalized errors only**; adapter, registry, router, endpoints, and telemetry land in PR2–PR6 to keep this PR ≤400 authored lines.

- [x] 1.1 RED: `openai_settings_{valid,empty_key_raises,empty_models_raises,invalid_url_raises}`
- [x] 1.2 GREEN: extend `config.py` (key/base_url/models/timeout_s); update `.env.example`
- [x] 1.3 RED: `errors_envelope_{selection_400,config_502,upstream_502,timeout_504,sanitized}`
- [x] 1.4 GREEN: create `core/errors.py` (`LLMuxError`+4 subclasses+`to_openai_envelope`)

## PR2 — OpenAI Adapter (base PR1)

- [x] 2.1 RED: `complete_returns_result`, `complete_stream_raises_not_implemented`
- [x] 2.2 RED: `upstream_4xx_5xx→upstream_error`, `timeout→upstream_timeout`
- [x] 2.3 GREEN: create `core/providers/openai.py` (Protocol, injected `httpx.AsyncClient`)

## PR3 — Registry + Partial-Construction Cleanup (base PR2)

- [ ] 3.1 RED: `registry_fail_fast_aborts`, `build_providers_closes_first_client_on_later_failure`
- [ ] 3.2 RED: `aclose_closes_production_only`, `aclose_idempotent_after_success`
- [ ] 3.3 GREEN: create `core/providers/registry.py` (`ProviderRegistry` + `build_providers` w/ cleanup seam)

## PR4 — Router + Lifespan + /v1/models (base PR3)

- [ ] 4.1 RED: `router_first_match`, `router_no_match_raises_provider_selection_error`
- [ ] 4.2 GREEN: create `core/router.py` (async first-match `select_provider`)
- [ ] 4.3 RED: `lifespan_tracer_shutdown_on_build_failure`, `aclose_before_tracer_shutdown`
- [ ] 4.4 GREEN: modify `main.py` lifespan (try/finally; `aclose` then `shutdown_tracer`)
- [ ] 4.5 RED: `models_aggregates_one_per_{provider_model,empty_when_no_providers}`
- [ ] 4.6 GREEN: modify `api/models.py` to source from `app.state.providers`

## PR5 — Chat Routing + Envelopes, no telemetry (base PR4)

- [ ] 5.1 RED: `stream_false_routes_200`, `omitted_stream_defaults_false_routes`
- [ ] 5.2 RED: `stream_true_501_no_provider_no_telemetry` (no `data:` frames)
- [ ] 5.3 GREEN: short-circuit explicit `stream=True` → JSON 501 (before provider/telemetry)
- [ ] 5.4 RED: `chat_{400_selection_miss,502_upstream,504_timeout,502_sanitized}`
- [ ] 5.5 GREEN: modify `api/chat.py` to route when `stream is False` (incl. omitted)

## PR6 — OTel + Metrics + Cardinality + Error Accounting (base PR5)

- [ ] 6.1 RED: `model_unknown_sentinel_on_unselected`, `bounded_label_values`
- [ ] 6.2 RED: `span_error_status_with_error_type_attribute`
- [ ] 6.3 GREEN: create `observability/metrics.py` (span `chat.completion`, 3 metrics, `MODEL_UNKNOWN`)
- [ ] 6.4 GREEN: wire `ChatTelemetry` into `api/chat.py` routed call site
- [ ] 6.5 RED: `unexpected_error_records_error_metric_and_propagates`
- [ ] 6.6 GREEN: re-raise non-`LLMuxError` after error telemetry; mypy strict; update `tasks.md` checklist

## Guardrail Mapping

Fail-safe teardown → PR4 4.3 · Bounded cardinality → PR6 6.1 · Stable OTel error status → PR6 6.2 · Uncaught accounting → PR6 6.5/6.6 · No test-client double-close → PR3 3.2.

Out of scope (per proposal): Anthropic; fallback; retries/backoff; circuit breaking; real streaming/SSE; key/persistence. Threat matrix rows are N/A in design.
