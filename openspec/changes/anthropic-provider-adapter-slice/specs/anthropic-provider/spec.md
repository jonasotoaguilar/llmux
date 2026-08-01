# anthropic-provider

> **(planned)** New capability — first slice of the Anthropic provider. Specializes [ADR-0002](../../../../docs/adr/0002-provider-abstraction-pattern.md) (`ProviderAdapter` Protocol); introduces no new architectural decision. All requirements are `(planned)` per `openspec/config.yaml` `rules.specs`: no Anthropic code exists on `main` yet. Plugs into the `provider-routing-functional-slice` surfaces (merged `12a32ae`).

## Purpose

Define the second concrete `ProviderAdapter` (ADR-0002): an Anthropic Messages-API adapter for non-streaming chat completions. Translates the OpenAI-shaped gateway request into Anthropic's Messages request, maps the Anthropic response back into the normalized `CompletionResult`, and normalizes upstream failures into the existing `LLMuxError` hierarchy. The adapter participates unchanged in the existing first-match router, non-streaming chat path, and bounded telemetry (see `gateway-api-boundary`). No streaming, no tool use, no multimodal, no prompt caching, no fallback.

## Requirements

### Requirement: Anthropic Adapter Contract (planned)

The system MUST provide an `AnthropicAdapter` implementing the `ProviderAdapter` Protocol (ADR-0002). Its `complete` method MUST return a `CompletionResult` for a non-streaming Messages-API call. Its `complete_stream` method MUST raise `NotImplementedError` (real streaming is explicitly deferred). The adapter MUST accept an injected `httpx.AsyncClient` and MUST NOT construct its own client.

#### Scenario: Adapter conforms to the ProviderAdapter Protocol

- GIVEN `AnthropicAdapter` is imported
- WHEN a test instantiates it with an injected client and accesses it as a `ProviderAdapter`
- THEN it satisfies the Protocol and `complete` is callable

#### Scenario: Streaming is explicitly bypassed

- GIVEN an `AnthropicAdapter`
- WHEN `complete_stream` is called
- THEN it raises `NotImplementedError`

### Requirement: Anthropic Auth Headers And Endpoint (planned)

The adapter MUST send the header pair `x-api-key: <api_key>` and `anthropic-version: <version>` on every Messages request, and MUST `POST` to `<base_url>/v1/messages`. It MUST NOT use the OpenAI-style `Authorization: Bearer` scheme for Anthropic.

#### Scenario: Request carries the auth header pair and endpoint

- GIVEN an `AnthropicAdapter` configured with key, version, and base URL
- WHEN `complete` is called
- THEN the outbound request is `POST <base_url>/v1/messages`
- AND carries `x-api-key` and `anthropic-version` headers and no `Authorization` header

### Requirement: System Message Extraction (planned)

Anthropic rejects `role:"system"` entries inside `messages`. The adapter MUST extract `system` messages from the gateway message list and MUST place them in the top-level Anthropic `system` field. Multiple system messages MUST be joined with `\n\n`. A message whose role is neither `system`, `user`, nor `assistant` (e.g. `tool`, `function`) MUST raise `ConfigurationError`. System-message cache-control MUST NOT be preserved (prompt caching is deferred).

#### Scenario: System message moves to the top-level field

- GIVEN a message list beginning with one `system` message
- WHEN `complete` translates the request
- THEN the Anthropic payload has a top-level `system` field
- AND the `messages` array contains no `system` role

#### Scenario: Multiple system messages are joined

- GIVEN two consecutive `system` messages
- WHEN `complete` translates the request
- THEN the `system` field joins them with `\n\n`

#### Scenario: Unsupported role is rejected

- GIVEN a message with role `tool`
- WHEN `complete` translates the request
- THEN a `ConfigurationError` is raised

### Requirement: Max Tokens Default And Override (planned)

Anthropic requires `max_tokens`. The adapter MUST default `max_tokens` to `1024` when the caller omits it, and MUST honor a caller-supplied `options["max_tokens"]` override.

#### Scenario: Omitted max_tokens defaults to 1024

- GIVEN a request that omits `max_tokens`
- WHEN `complete` translates the request
- THEN the Anthropic payload sets `max_tokens` to `1024`

#### Scenario: Caller override is honored

- GIVEN a request with `options["max_tokens"] = 512`
- WHEN `complete` translates the request
- THEN the Anthropic payload sets `max_tokens` to `512`

### Requirement: Response Content Translation (planned)

The adapter MUST join the `type:"text"` content blocks of the Anthropic response into the gateway completion content, in order. A response containing any non-text block (e.g. `tool_use`) MUST raise `UpstreamError`.

#### Scenario: Text blocks are joined into content

- GIVEN an Anthropic response with two `type:"text"` blocks
- WHEN `complete` maps the response
- THEN the completion content is the ordered join of the block texts

#### Scenario: Non-text block is rejected

- GIVEN an Anthropic response containing a `tool_use` block
- WHEN `complete` maps the response
- THEN an `UpstreamError` is raised

### Requirement: Token Count And Stop-Reason Mapping (planned)

The adapter MUST map Anthropic usage and stop reason into the gateway fields:

| Anthropic field | Gateway field |
|-----------------|---------------|
| `usage.input_tokens` | `prompt_tokens` |
| `usage.output_tokens` | `completion_tokens` |
| `stop_reason` `end_turn` | finish `stop` |
| `stop_reason` `max_tokens` | finish `length` |
| `stop_reason` `stop_sequence` | finish `stop` |

#### Scenario: Token counts are mapped

- GIVEN a response with `input_tokens=10, output_tokens=20`
- WHEN `complete` maps the response
- THEN `prompt_tokens=10` and `completion_tokens=20`

#### Scenario: Stop reason is mapped

- GIVEN a response with `stop_reason=max_tokens`
- WHEN `complete` maps the response
- THEN the finish reason is `length`

### Requirement: Upstream Error And Timeout Normalization (planned)

The adapter MUST translate a non-2xx Anthropic HTTP response into `UpstreamError` and a request/transport timeout into `UpstreamTimeoutError`. It MUST discard the Anthropic error body (it MUST NOT surface upstream payload, keys, or stack traces) and MUST NOT introduce error classes beyond the existing `LLMuxError` hierarchy.

#### Scenario: Upstream HTTP failure maps to UpstreamError and discards body

- GIVEN Anthropic returns HTTP 500 with a JSON body
- WHEN `complete` is called
- THEN an `UpstreamError` is raised and the Anthropic body is not carried into any envelope

#### Scenario: Timeout maps to UpstreamTimeoutError

- GIVEN the Anthropic call exceeds the configured timeout
- WHEN `complete` is called
- THEN an `UpstreamTimeoutError` is raised

### Requirement: Anthropic Configuration Validation (planned)

The system MUST load Anthropic settings (`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_VERSION`, configured model list) from configuration. When Anthropic is enabled, the system MUST raise `ConfigurationError` if the API key is empty, the model list is empty, or the base URL is invalid — mirroring the OpenAI fail-fast contract (see `provider-routing` "Provider Configuration And Fail-Fast Construction").

#### Scenario: Valid Anthropic settings construct an adapter

- GIVEN Anthropic is enabled with a non-empty key, valid base URL, and non-empty model list
- WHEN the adapter is constructed
- THEN construction succeeds

#### Scenario: Empty key or model list fails fast

- GIVEN Anthropic is enabled with an empty API key or an empty model list
- WHEN the adapter is constructed
- THEN a `ConfigurationError` is raised

### Requirement: Configured Model Listing (planned)

The adapter's `models()` method MUST return the configured Anthropic model list as `List[ModelInfo]`.

#### Scenario: models() returns configured models

- GIVEN an adapter configured with models `claude-3` and `claude-3.5`
- WHEN `models()` is called
- THEN it returns one `ModelInfo` per configured model

### Requirement: Reachability Health (planned)

The adapter's `health()` method MUST probe reachability via `GET <base_url>/` only. It MUST NOT perform an auth-validity probe (auth-validity health is deferred). It MUST return a `HealthStatus`.

#### Scenario: Reachable base URL reports healthy

- GIVEN `GET <base_url>/` returns 2xx
- WHEN `health()` is called
- THEN it returns a healthy `HealthStatus`

#### Scenario: Unreachable base URL reports unhealthy without auth probing

- GIVEN `GET <base_url>/` fails or times out
- WHEN `health()` is called
- THEN it returns an unhealthy `HealthStatus` and no authenticated request is sent

### Requirement: Chat Completion Routing Conformance (planned)

A configured Anthropic model MUST route through the existing first-match router and non-streaming chat path unchanged (see `gateway-api-boundary` "Non-Streaming Chat Completion Routing"), returning HTTP 200 with an OpenAI-shaped envelope, or the unchanged normalized error envelopes (400 selection miss, 502 upstream/config, 504 timeout). `stream=true` MUST yield HTTP 501 with no provider invocation and no telemetry (inherited no-fake-SSE contract). The router MUST retain first-match, NO-fallback semantics for Anthropic models.

#### Scenario: Configured Anthropic model returns 200 via the unchanged path

- GIVEN an Anthropic model is configured and offered
- WHEN a client posts a `stream=false` chat request for that model
- THEN the response is 200 with an OpenAI-shaped completion envelope

#### Scenario: Explicit stream=true returns 501 with no invocation

- GIVEN a configured Anthropic model
- WHEN a client posts `stream=true`
- THEN the response is 501, Content-Type is `application/json`, and no Anthropic method is called

#### Scenario: No-fallback semantics are preserved

- GIVEN no provider offers the requested Anthropic model
- WHEN a client posts the request
- THEN a `ProviderSelectionError` maps to 400 with no retry or failover

### Requirement: Bounded Telemetry Conformance (planned)

When an Anthropic hop is routed, telemetry MUST conform to the existing bounded-cardinality contract (see `gateway-api-boundary` "Bounded Telemetry Per Non-Streaming Hop"). The `provider` label value MUST be `"anthropic"` — a new member of the existing bounded set. No new label dimension, metric name, or cardinality axis MUST be introduced. On Anthropic errors the span MUST be `Status(StatusCode.ERROR, error_type)`.

#### Scenario: Anthropic hop records the bounded provider label

- GIVEN a routed Anthropic completion
- WHEN telemetry is recorded
- THEN the `provider` label is `"anthropic"` and no new metric name or label dimension appears

## Non-Goals (Explicit)

**(planned)** This spec MUST NOT introduce: streaming/SSE, tool use, prompt caching (or system cache-control), image/multimodal inputs, model alias resolution, cost/token metering, auth-validity health probing, automatic fallback, retries/backoff/circuit breaking, new `LLMuxError` subclasses, new telemetry metrics, or any new ADR.
