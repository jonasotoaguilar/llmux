# request-telemetry

## Purpose

Emit one OpenTelemetry span and three metrics for every non-streaming `POST /v1/chat/completions` request that reaches a provider, so the gateway's provider hop is observable. Streaming requests (`stream=true`) return 501 before reaching any provider and therefore emit no provider telemetry in this slice.

## Requirements

### Requirement: Chat Completion Span (implemented)

The system MUST open one OTel span named `chat.completion` for each non-streaming `/v1/chat/completions` request that reaches a provider. The span MUST record attributes for the requested model, the selected provider, the request latency, token counts when available, and an error class when the request fails.

#### Scenario: Successful completion records latency and tokens

- GIVEN a non-streaming request reaching a serving OpenAI adapter
- WHEN the request completes successfully
- THEN a `chat.completion` span is emitted
- AND it carries model, provider, latency, and token attributes

#### Scenario: Failed completion records the error class

- GIVEN a non-streaming request whose provider call raises `UpstreamError`
- WHEN the request fails
- THEN the span records the error class as an attribute
- AND the span status reflects the error

### Requirement: Chat Completion Metrics (implemented)

The system MUST emit three metrics for non-streaming chat completions: `chat_completion_requests_total` (counter), `chat_completion_errors_total` (counter), and `chat_completion_duration_seconds` (histogram). Metrics MUST use `opentelemetry-api` directly so tests run without an SDK exporter.

#### Scenario: Each request increments the request counter

- GIVEN the metrics are initialized
- WHEN a non-streaming chat completion is processed
- THEN `chat_completion_requests_total` increments by one

#### Scenario: Errors increment the error counter and record duration

- GIVEN a non-streaming request that fails at the provider
- WHEN the request returns an error envelope
- THEN `chat_completion_errors_total` increments by one
- AND `chat_completion_duration_seconds` records the elapsed time

## Non-Goals (Explicit)

This spec MUST NOT introduce: persistence of telemetry to a database; metrics for endpoints other than `/v1/chat/completions`; streaming telemetry (`stream=true` stays 501); cost, token-budget, or quota metering.
