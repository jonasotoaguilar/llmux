# Delta for provider-routing

> **(planned)** Delta against the `provider-routing` capability currently established by `openspec/changes/provider-routing-functional-slice/specs/provider-routing/spec.md` (not yet archived to `openspec/specs/`). Changes are `(planned)` per `openspec/config.yaml`: this slice is pre-implementation. Only the two requirements whose behavior changes for Anthropic config/registry integration are MODIFIED. First-match selection, the no-fallback router, and the normalized error hierarchy are intentionally UNCHANGED — Anthropic merely participates in and reuses them.

## MODIFIED Requirements

### Requirement: Provider Configuration And Fail-Fast Construction (planned)

The system MUST load provider settings from configuration for each enabled provider slug and MUST raise `ConfigurationError` during provider construction when any enabled provider is misconfigured. The supported slugs are `"openai"` and `"anthropic"`; `build_providers` MUST dispatch each configured slug to its adapter constructor. For `"openai"` the system MUST fail fast when the API key is empty, the model list is empty, or the base URL is invalid; for `"anthropic"` it MUST fail fast on the same conditions against the `ANTHROPIC_*` settings (see `anthropic-provider` "Anthropic Configuration Validation"). A single invalid setting in ANY provider MUST prevent the registry from starting.

(Previously: only the OpenAI slug was recognized; the fail-fast contract was described solely in OpenAI terms.)

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

#### Scenario: The anthropic slug dispatches to the Anthropic adapter

- GIVEN configuration contains the `"anthropic"` slug with valid settings
- WHEN `build_providers` constructs providers
- THEN the Anthropic adapter is constructed and registered alongside any OpenAI adapter

#### Scenario: Anthropic misconfiguration fails fast like OpenAI

- GIVEN Anthropic is enabled with an empty API key, an empty model list, or an invalid base URL
- WHEN `build_providers` constructs providers
- THEN a `ConfigurationError` is raised before the registry starts

### Requirement: Ordered Provider Registry And Lifecycle (planned)

The system MUST construct providers in configured order via a `ProviderRegistry` built by `build_providers`. Construction MUST be fail-fast: any provider failing to construct MUST abort the whole registry (no partial registry is returned). When construction aborts after one or more earlier providers have already been constructed (e.g. OpenAI succeeds, then Anthropic fails), `build_providers` MUST perform transaction-like cleanup — it MUST `aclose()` every already-constructed adapter before propagating the `ConfigurationError`, so no production HTTP client is leaked on a partial build. The registry MUST expose `aclose()` for graceful shutdown. `aclose()` MUST close only production HTTP clients it owns; clients injected with `MockTransport` (or otherwise caller-supplied), including the Anthropic test client, MUST NOT be re-closed by the registry. The test-client double-close regression is guarded by recording the injected client as caller-owned (e.g. via a `RegistryEntry(client=None)` marker) and asserting the injected client's `aclose_count` stays at exactly one.

(Previously: fail-fast abort was specified, but mid-build cleanup of already-constructed adapters and the explicit test-client ownership guard were not.)

#### Scenario: Fail-fast aborts the registry

- GIVEN two providers configured and the second fails to construct
- WHEN `build_providers` runs
- THEN a `ConfigurationError` is raised and no partial registry is returned

#### Scenario: aclose closes production clients only

- GIVEN a registry holding a production client and a MockTransport test client
- WHEN `aclose()` is called
- THEN the production client is closed
- AND the MockTransport client is NOT re-closed (it remains caller-owned)

#### Scenario: Mid-build failure cleans up already-constructed adapters

- GIVEN OpenAI is configured to construct successfully and Anthropic is configured to fail
- WHEN `build_providers` constructs providers and Anthropic raises `ConfigurationError`
- THEN every already-constructed adapter (e.g. OpenAI) is `aclose()`d before the error propagates
- AND no production HTTP client is left open

#### Scenario: Injected Anthropic test client is not double-closed

- GIVEN the Anthropic adapter is constructed with a caller-injected `MockTransport` client
- WHEN the registry is constructed and then `aclose()`d
- THEN the injected client's `aclose_count` is exactly one (the registry does not re-close it)
