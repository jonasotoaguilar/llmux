# provider-routing

## Purpose

Construct the provider registry from `Settings` at startup and select the serving provider per chat request by priority (first enabled adapter that advertises the requested model). Defines the normalized `LLMuxError` hierarchy and the per-provider configuration contract the registry consumes. Fallback, retry, and circuit-breaking are deferred to `provider-fallback-and-retries`.

## Requirements

### Requirement: Provider Configuration Contract (implemented)

The system MUST read provider configuration from `Settings`. For the OpenAI provider it MUST expose `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1`), `OPENAI_MODELS` (default `["gpt-4o-mini", "gpt-4o"]`), and `OPENAI_TIMEOUT_S` (default `30.0`). `LLMUX_PROVIDERS_CONFIGURED` list order MUST define priority and presence MUST mean enabled. An enabled provider slug whose required `<PROVIDER>_API_KEY` is empty MUST raise `ConfigurationError`; the system MUST NOT silently skip it.

#### Scenario: Enabled provider without API key is a configuration error

- GIVEN `LLMUX_PROVIDERS_CONFIGURED=["openai"]` and `OPENAI_API_KEY` unset
- WHEN the registry is built at startup
- THEN `ConfigurationError` is raised
- AND its envelope identifies the missing key for the `openai` provider

#### Scenario: Defaults apply when optional fields are omitted

- GIVEN `LLMUX_PROVIDERS_CONFIGURED=["openai"]` and a valid `OPENAI_API_KEY`
- WHEN the registry is built
- THEN the OpenAI adapter uses base URL `https://api.openai.com/v1` and models `["gpt-4o-mini", "gpt-4o"]`

#### Scenario: Priority follows configured list order

- GIVEN more than one provider configured in `LLMUX_PROVIDERS_CONFIGURED`
- WHEN the router selects a provider for a model more than one adapter serves
- THEN the provider appearing first in the list is selected

### Requirement: Provider Registry Construction (implemented)

The system MUST build the provider registry once at startup via `build_providers(settings)` and store it on `app.state.providers`. The registry MUST instantiate one adapter per enabled, correctly-configured slug and MUST be empty when no slug is enabled.

#### Scenario: Registry is built from enabled providers

- GIVEN Settings with `openai` enabled and configured
- WHEN `build_providers(settings)` runs
- THEN `app.state.providers` contains one OpenAI adapter
- AND its `models()` lists the configured models

#### Scenario: Empty configuration yields an empty registry

- GIVEN `LLMUX_PROVIDERS_CONFIGURED=[]`
- WHEN the registry is built
- THEN `app.state.providers` is an empty collection

### Requirement: Priority Provider Router (implemented)

The system MUST provide `select_provider(model, providers)` returning the first adapter whose advertised models include the requested model. When no enabled adapter lists the model, it MUST raise `ProviderSelectionError`.

#### Scenario: First matching provider is selected

- GIVEN a registry containing an adapter advertising `gpt-4o-mini`
- WHEN `select_provider("gpt-4o-mini", providers)` is called
- THEN that adapter is returned

#### Scenario: No provider serves the requested model

- GIVEN a registry with no adapter advertising `gpt-5`
- WHEN `select_provider("gpt-5", providers)` is called
- THEN `ProviderSelectionError` is raised

### Requirement: Normalized Error Hierarchy (implemented)

The system MUST define an `LLMuxError` base with subclasses `ConfigurationError`, `ProviderSelectionError`, `UpstreamError`, and `UpstreamTimeoutError`. Each MUST implement `to_openai_envelope()` returning an OpenAI-shaped error body and MUST map to a deterministic status: `ProviderSelectionError`→400, `ConfigurationError`→502, `UpstreamError`→502, `UpstreamTimeoutError`→504.

#### Scenario: Each error class maps to its status code

- GIVEN each `LLMuxError` subclass
- WHEN `to_openai_envelope()` is produced
- THEN the mapped HTTP status is 400, 502, or 504 per the class

#### Scenario: Envelopes are OpenAI-shaped

- GIVEN any `LLMuxError`
- WHEN its envelope is serialized
- THEN the body carries `error.message` and `error.type` in the OpenAI error shape

## Non-Goals (Explicit)

This spec MUST NOT introduce: fallback, retry, or circuit-breaker selection; any provider other than OpenAI; streaming (`complete_stream` is deferred); persistence of provider state or health history.
