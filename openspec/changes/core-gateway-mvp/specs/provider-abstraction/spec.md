# Delta for provider-abstraction

> All requirements in this spec are **(planned)** per `openspec/config.yaml` rules.specs: no concrete provider adapter is implemented in this slice. ADR-0002 is the source of truth for the surface; this spec only fixes the contracts the provider slice must satisfy later.

## ADDED Requirements

### Requirement: ProviderAdapter Protocol (planned)

The system MUST define a `ProviderAdapter` Protocol in `llmux.core.providers.base` declaring the methods `complete`, `complete_stream`, `models`, and `health` (per ADR-0002). The Protocol MUST be subclassable so future concrete adapters can implement it. No concrete adapter is required in this slice.

#### Scenario: Protocol is importable and subclassable

- GIVEN Python 3.12+ with the package installed
- WHEN a test imports `ProviderAdapter` from `llmux.core.providers.base`
- AND subclasses it with stub implementations
- THEN the import succeeds
- AND the subclass can be instantiated without error

### Requirement: CompletionResult Dataclass (planned)

The system MUST define a `CompletionResult` dataclass in `llmux.core.providers.base` carrying the fields required by ADR-0002 to represent a single non-streaming chat completion response from a provider. The dataclass MUST be constructible in tests with required fields only.

#### Scenario: CompletionResult is constructible with required fields

- GIVEN the module is imported
- WHEN a test constructs `CompletionResult` with required fields
- THEN construction succeeds and the fields are readable

### Requirement: Chunk Dataclass (planned)

The system MUST define a `Chunk` dataclass in `llmux.core.providers.base` representing a single streaming chunk per ADR-0002. The dataclass MUST be constructible in tests with required fields only.

#### Scenario: Chunk is constructible with required fields

- GIVEN the module is imported
- WHEN a test constructs `Chunk` with required fields
- THEN construction succeeds and the fields are readable

### Requirement: ModelInfo Dataclass (planned)

The system MUST define a `ModelInfo` dataclass in `llmux.core.providers.base` carrying the fields required by ADR-0002 to describe a model offered by a provider. The dataclass MUST be constructible in tests with required fields only.

#### Scenario: ModelInfo is constructible with required fields

- GIVEN the module is imported
- WHEN a test constructs `ModelInfo` with required fields
- THEN construction succeeds and the fields are readable

### Requirement: HealthStatus Dataclass (planned)

The system MUST define a `HealthStatus` dataclass in `llmux.core.providers.base` carrying the fields required by ADR-0002 to describe a provider's health. The dataclass MUST be constructible in tests with required fields only.

#### Scenario: HealthStatus is constructible with required fields

- GIVEN the module is imported
- WHEN a test constructs `HealthStatus` with required fields
- THEN construction succeeds and the fields are readable

### Requirement: Strict Testability Of Provider Contracts (planned)

Every Protocol method and dataclass declared in `llmux.core.providers.base` MUST be covered by tests asserting importability, constructibility, and Protocol subclassability. Tests MUST NOT assume any concrete adapter exists.

#### Scenario: Protocol declares the four adapter methods

- GIVEN `ProviderAdapter` is imported
- WHEN a test inspects the declared members of the Protocol
- THEN `complete`, `complete_stream`, `models`, and `health` are present

## Non-Goals (Explicit)

This spec MUST NOT introduce:
- Any concrete provider adapter (OpenAI, Anthropic, local, or otherwise)
- API-key handling, secret storage, or credential loading
- HTTP client code, retry/backoff, or rate-limit handling
- Real streaming emission (`complete_stream` is declared, unimplemented)
- Provider registry, router, or fallback selection
- Persistence of models, keys, usage, or health history
