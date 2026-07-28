# ADR-0002: Provider Abstraction Pattern

## Status

Accepted

## Date

2026-07-17

## Deciders

Jonathan Soto

## Context

LLMux must support multiple LLM providers (OpenAI, Anthropic, Google, and future ones) with different API shapes, authentication methods, streaming models, error formats, and pricing models. The core routing and metering logic must be provider-agnostic — adding a new provider should not require changes to routing, auth, metering, or audit modules.

Additionally, provider APIs evolve frequently. An adapter pattern isolates the gateway from upstream API changes.

## Decision

Abstract each provider behind a **stable `ProviderAdapter` protocol** with a common interface covering:

- `complete(model, messages, options)` → `CompletionResult`
- `complete_stream(model, messages, options)` → `AsyncIterator[Chunk]`
- `models()` → `List[ModelInfo]`
- `health()` → `HealthStatus`

Each provider adapter is a single class that implements this protocol and encapsulates:

- Provider-specific HTTP client configuration (base URL, auth header format, timeout)
- Request/response translation (normalize to the gateway's internal schema)
- Token counting and cost calculation logic
- Error mapping (translate provider-specific errors to gateway error types)

Provider-specific configuration (API keys, base URLs, model lists, cost tables) is stored in PostgreSQL as JSONB and injected into the adapter at initialization.

## Consequences

### Positive

- Adding a new provider = writing one adapter class + adding config in DB — no core changes
- Provider API changes are contained within one adapter
- Each adapter is independently unit-testable with mocks
- Cost calculation per provider is explicit and auditable
- Different providers can have different models, streaming behavior, and auth — normalized at the adapter boundary

### Negative

- Adapter interface may need breaking changes if a fundamentally new provider behavior appears (e.g., non-stream-only, function-calling-only providers)
- Duplication across adapters for similar providers (mitigated by shared base class or utilities)
- Testing requires maintaining fixture data for each provider's response format

### Neutral

- Team must agree on the adapter protocol before implementing multiple adapters
- Some providers will have thin adapters (OpenAI-compatible APIs like Together AI, Groq can reuse much of the OpenAI adapter)

## Options Considered

### Option A: ProviderAdapter Protocol (Chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — single interface for heterogeneous providers |
| Testability | High — each adapter independently mockable |
| Maintenance | Low — changes isolated per provider |
| Extensibility | High — new providers add one file |
| Performance | Low overhead — one extra method call per request |

### Option B: Plugin System (Dynamic Loading)

| Dimension | Assessment |
|-----------|------------|
| Complexity | High — plugin discovery, versioning, sandboxing |
| Testability | Medium — plugins tested in isolation |
| Maintenance | Medium — dependency management per plugin |
| Extensibility | Very high — third-party plugins possible |
| Performance | Medium — dynamic loading overhead |

**Why rejected**: A plugin system introduces complexity (plugin discovery, version conflicts, security sandboxing) that is unjustified for the MVP. An adapter protocol with a single class per provider is simple, testable, and sufficient. Plugin system can be added later if third-party provider adapters become a requirement.

### Option C: Lambda/Strategy Pattern (one function per operation)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — one function per variant per provider |
| Testability | Medium — functions are testable but stateful operations spread across functions |
| Maintenance | Low-Medium — operations distributed across many files |
| Extensibility | Medium — each provider needs to implement all strategy functions |
| Performance | No overhead |

**Why rejected**: While simple, the strategy pattern scatters provider-specific logic across many small functions (one per operation). When adding a provider, you must implement every function. The Adapter class groups all provider-specific concerns in one cohesive unit, making it easier to understand, test, and maintain.

## Trade-off Analysis

The stable protocol approach trades some flexibility for simplicity and testability. The risk of protocol-breaking provider features is low (most providers converge on OpenAI-compatible patterns). When such a feature does appear, the protocol can be extended with optional methods and sensible defaults.

Cost calculation is intentionally per-adapter rather than global, because providers price by different units (tokens, characters, image count) and have different rate tiers. Centralizing cost logic would be more complex than distributing it.

## Action Items

1. [ ] Define `ProviderAdapter` protocol in `core/providers/base.py` with abstract methods
2. [ ] Define `CompletionResult`, `Chunk`, `ModelInfo`, `HealthStatus` data classes
3. [ ] Implement OpenAI adapter as the reference implementation
4. [ ] Implement Anthropic adapter (different streaming format, different auth)
5. [ ] Implement Google adapter (Gemini API)
6. [ ] Add adapter factory that reads config from PostgreSQL and instantiates adapters

## References

- [ADR-0001: Modular Monolith Topology](0001-modular-monolith-topology.md) — the overall architecture this adapter pattern lives in
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — provider adapter placement in component diagram
