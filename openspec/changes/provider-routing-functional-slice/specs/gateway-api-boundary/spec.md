# Delta for gateway-api-boundary

> **(planned)** Delta against `openspec/specs/gateway-api-boundary/spec.md` (source of truth promoted 2026-07-23). New and changed requirements are `(planned)` per `openspec/config.yaml`: the routed path, registry-backed models, and telemetry do not exist on `main` yet.

## MODIFIED Requirements

### Requirement: OpenAI-Compatible Models Endpoint

**(planned)** The system MUST expose `GET /v1/models` returning HTTP 200 with an OpenAI-shaped envelope: `{"object": "list", "data": [...]}`. `data` MUST contain one entry per configured `(provider, model)` pair sourced from the provider registry. When no provider is configured, `data` MUST be an empty array.

(Previously: `data` was a fixed empty array of length 0.)

#### Scenario: Models returns one entry per configured provider/model pair

- GIVEN the registry holds provider P offering models m1 and m2
- WHEN a client sends `GET /v1/models`
- THEN the response status is 200
- AND `object` equals `"list"`
- AND `data` contains one entry each for m1 and m2

#### Scenario: No configured providers yields an empty list

- GIVEN no provider is configured
- WHEN a client sends `GET /v1/models`
- THEN the response status is 200 and `data` is an empty array

## REMOVED Requirements

### Requirement: Chat Completions Returns 501 For Both Stream Modes (no fake SSE)

(Reason: `stream=false` now routes to the selected provider and returns a 200 envelope or a normalized 400/502/504. Only explicit `stream=true` retains the 501 no-fake-SSE contract, now expressed by the Streaming requirement below; an omitted `stream` field is treated as `stream=false` per the OpenAI-compatible default and routes.)
(Migration: The no-fake-SSE guarantee for explicit `stream=true` is preserved verbatim in "Streaming Chat Completion 501 No-Fake-SSE Contract". Tests that asserted the `stream=false` 501 contract, and the omitted-`stream` 501 contract, MUST be updated to assert routing outcomes — 200 success, or 400/502/504 error envelopes.)

## ADDED Requirements

### Requirement: Non-Streaming Chat Completion Routing (planned)

**(planned)** For `POST /v1/chat/completions` with `stream=false` or with the `stream` field omitted (treated as `stream=false` per the OpenAI-compatible default), the gateway MUST route to the selected provider and return either HTTP 200 with an OpenAI-shaped completion envelope, or a normalized error envelope — 400 on `ProviderSelectionError`, 502 on `ConfigurationError` or `UpstreamError`, 504 on `UpstreamTimeoutError`. `ConfigurationError` is a server/startup configuration fault (the registry fails fast at startup per its own requirement); if one nonetheless surfaces at the routed HTTP mapping, it MUST normalize to 502, never 400. The routed call site MUST catch every `LLMuxError` type: increment the error counter, set the span error status, and emit the sanitized envelope. There MUST be no bare `except: pass` on the routed path.

#### Scenario: stream=false routes and returns 200

- GIVEN the requested model is offered by a configured provider
- WHEN a client posts a `stream=false` request
- THEN the response status is 200
- AND the body is an OpenAI-shaped completion envelope

#### Scenario: Omitted stream defaults to stream=false and routes

- GIVEN the requested model is offered by a configured provider
- WHEN a client posts a chat request with the `stream` field omitted
- THEN the gateway treats it as `stream=false`, routes it, and returns 200
- AND the body is an OpenAI-shaped completion envelope identical to the `stream=false` case

#### Scenario: Selection miss returns 400

- GIVEN no provider offers the requested model
- WHEN a client posts a `stream=false` request
- THEN the response status is 400
- AND the body is a sanitized OpenAI error envelope

#### Scenario: Upstream failure returns 502

- GIVEN the selected provider raises `UpstreamError`
- WHEN a client posts a `stream=false` request
- THEN the response status is 502
- AND the envelope carries no key, upstream payload, or stack trace

### Requirement: Streaming Chat Completion 501 No-Fake-SSE Contract (planned)

**(planned)** For `POST /v1/chat/completions` with `stream` explicitly set to `true`, the gateway MUST return HTTP 501 with an OpenAI-shaped JSON error envelope. The response Content-Type MUST be `application/json` (never `text/event-stream`), the body MUST contain no `data:` SSE frames, and the gateway MUST NOT invoke any provider and MUST NOT emit telemetry for the rejected path. An omitted `stream` field MUST NOT enter this path — it is treated as `stream=false` and routed (see "Non-Streaming Chat Completion Routing").

#### Scenario: stream=true returns 501 with no SSE and no provider invocation

- GIVEN a valid request with `stream=true`
- WHEN the client posts to `/v1/chat/completions`
- THEN the status is 501 and Content-Type is `application/json`
- AND no `data:` SSE frames appear in the body
- AND no provider method is called and no metric is recorded

### Requirement: Bounded Telemetry Per Non-Streaming Hop (planned)

**(planned)** Each non-streaming chat completion hop MUST emit exactly one OpenTelemetry span and three bounded-cardinality metrics (`requests_total`, `errors_total`, `duration_seconds`). Metric label values MUST be drawn from a fixed, bounded set; when provider selection fails, the model label MUST use the `MODEL_UNKNOWN` sentinel constant rather than the raw request model. Metric keys MUST be stable across releases. On any error, the span MUST be set to `Status(StatusCode.ERROR, error_type)` carrying an `error.type` attribute; errors MUST NOT be signaled via a bare `OK` status plus a side-channel attribute.

#### Scenario: Unselected model uses the bounded sentinel label

- GIVEN a request for a model no provider offers
- WHEN the hop records its model label
- THEN the label is the `MODEL_UNKNOWN` constant, not the raw request model

#### Scenario: Error sets an ERROR span status, not a side channel

- GIVEN a hop that ends in `UpstreamError`
- WHEN telemetry is recorded
- THEN the span status is `StatusCode.ERROR` with an `error.type` attribute

### Requirement: Fail-Safe Server Lifespan Teardown (planned)

**(planned)** The FastAPI lifespan MUST own registry resources. On any failure during registry construction inside the lifespan (including `ConfigurationError`), `shutdown_tracer()` MUST still execute, and registry `aclose()` MUST run before tracer shutdown whenever any provider was constructed. Tracer shutdown MUST NOT be skipped because provider construction failed.

#### Scenario: Registry build failure still shuts the tracer down

- GIVEN the lifespan starts and `build_providers` raises `ConfigurationError`
- WHEN startup aborts
- THEN `shutdown_tracer()` still runs
- AND any partially constructed registry is `aclose()`d before tracer shutdown
