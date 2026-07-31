# provider-routing

> **(planned)** All requirements are `(planned)` per `openspec/config.yaml` `rules.specs`: none of these files exist on `main` yet. Specializes [ADR-0002](../../../../docs/adr/0002-provider-abstraction-pattern.md) (`ProviderAdapter` protocol); introduces no new architectural decision.

## Purpose

Define the first concrete provider hop behind the ADR-0002 `ProviderAdapter` port: an OpenAI non-streaming adapter, an ordered startup registry with fail-fast construction and lifecycle ownership, a first-match async router with no fallback, and the normalized `LLMuxError` hierarchy that maps internal failures to sanitized OpenAI-shaped error envelopes. No Anthropic, no retries, no real streaming.

## Requirements

### Requirement: Provider Configuration And Fail-Fast Construction (planned)

The system MUST load OpenAI provider settings (API key, base URL, model list) from configuration and MUST raise `ConfigurationError` during provider construction when OpenAI is enabled but the API key is empty, the model list is empty, or the base URL is invalid. Construction MUST fail fast — a single invalid setting MUST prevent the registry from starting.

#### Scenario: Valid OpenAI settings construct a provider

- GIVEN OpenAI is enabled with a non-empty key, a valid base URL, and a non-empty model list
- WHEN `build_providers` constructs the OpenAI adapter
- THEN construction succeeds and the adapter is registered

#### Scenario: Empty key fails fast

- GIVEN OpenAI is enabled with an empty API key
- WHEN `build_providers` constructs providers
- THEN a `ConfigurationError` is raised before any provider is registered

#### Scenario: Invalid base URL fails fast

- GIVEN OpenAI is enabled with a malformed base URL
- WHEN `build_providers` constructs providers
- THEN a `ConfigurationError` is raised

### Requirement: OpenAI Non-Streaming Adapter (planned)

The system MUST provide an OpenAI adapter implementing the `ProviderAdapter` Protocol (ADR-0002). Its `complete` method MUST return a `CompletionResult` for a non-streaming chat completion. Its `complete_stream` method MUST raise `NotImplementedError` (real streaming is out of scope). The adapter MUST accept an injected `httpx.AsyncClient` and MUST translate upstream HTTP failures into `UpstreamError` or `UpstreamTimeoutError`.

#### Scenario: Non-streaming completion returns a result

- GIVEN an OpenAI adapter with an injected client
- WHEN `complete` is called with a model, messages, and options
- THEN it returns a `CompletionResult`

#### Scenario: Streaming is explicitly unsupported

- GIVEN an OpenAI adapter
- WHEN `complete_stream` is called
- THEN it raises `NotImplementedError`

### Requirement: Ordered Provider Registry And Lifecycle (planned)

The system MUST construct providers in configured order via a `ProviderRegistry` built by `build_providers`. Construction MUST be fail-fast: any provider failing to construct MUST abort the whole registry (no partial registry is returned). The registry MUST expose `aclose()` for graceful shutdown. `aclose()` MUST close only production HTTP clients it owns; clients injected with `MockTransport` (or otherwise caller-supplied) MUST NOT be re-closed by the registry.

#### Scenario: Fail-fast aborts the registry

- GIVEN two providers configured and the second fails to construct
- WHEN `build_providers` runs
- THEN a `ConfigurationError` is raised and no partial registry is returned

#### Scenario: aclose closes production clients only

- GIVEN a registry holding a production client and a MockTransport test client
- WHEN `aclose()` is called
- THEN the production client is closed
- AND the MockTransport client is NOT re-closed (it remains caller-owned)

### Requirement: First-Match Priority Provider Selection (planned)

The system MUST expose an async `select_provider` that returns the first provider (in configured order) whose model list contains the requested model. Selection MUST be first-match with NO fallback: if no provider offers the model, it MUST raise `ProviderSelectionError`. The router MUST NOT perform retries, backoff, or automatic failover.

#### Scenario: First matching provider is selected

- GIVEN providers ordered A then B, both offering model m
- WHEN `select_provider` is called for m
- THEN provider A is returned

#### Scenario: No provider offers the model

- GIVEN no configured provider offers model m
- WHEN `select_provider` is called for m
- THEN a `ProviderSelectionError` is raised

### Requirement: Normalized Error Hierarchy And Sanitized Envelopes (planned)

The system MUST define an `LLMuxError` base with subclasses `ConfigurationError`, `ProviderSelectionError`, `UpstreamError`, and `UpstreamTimeoutError`. A `to_openai_envelope()` mapping MUST translate these into OpenAI-shaped error envelopes with stable status codes per the table below. Envelopes MUST NOT include API keys, upstream response bodies, or stack traces. `ProviderSelectionError` is the only caller-input fault and maps to 400; `ConfigurationError` is a server/startup configuration fault — the registry fails fast at startup, and if one nonetheless reaches the routed HTTP mapping it MUST normalize to 502, never 400.

| Error class | Mapped HTTP status | Fault origin |
|-------------|--------------------|--------------|
| `ProviderSelectionError` | 400 | caller input (requested model) |
| `ConfigurationError` | 502 | server/startup config (fail-fast at startup; 502 if surfaced at HTTP) |
| `UpstreamError` | 502 | upstream provider |
| `UpstreamTimeoutError` | 504 | upstream provider timeout |

#### Scenario: Provider selection miss maps to 400

- GIVEN no provider offers the requested model
- WHEN `ProviderSelectionError` is converted to an OpenAI envelope
- THEN the mapped status is 400
- AND the body contains no key, upstream payload, or stack trace

#### Scenario: Configuration surfaced at the HTTP boundary maps to 502, not 400

- GIVEN a `ConfigurationError` reaches the routed HTTP mapping
- WHEN the error is converted to an OpenAI envelope
- THEN the mapped status is 502 (never 400)
- AND the body contains no key, upstream payload, or stack trace

#### Scenario: Upstream error maps to 502 with a sanitized body

- GIVEN an adapter raises `UpstreamError`
- WHEN the error is converted to an OpenAI envelope
- THEN the mapped status is 502
- AND the body contains no key, upstream payload, or stack trace

#### Scenario: Timeout maps to 504

- GIVEN an adapter raises `UpstreamTimeoutError`
- WHEN the error is converted to an OpenAI envelope
- THEN the mapped status is 504

## Non-Goals (Explicit)

**(planned)** This spec MUST NOT introduce: Anthropic or other providers, automatic fallback/retry/backoff/circuit-breaking, real streaming/SSE, token metering or cost calculation, or persistence of usage/keys/models/health.
