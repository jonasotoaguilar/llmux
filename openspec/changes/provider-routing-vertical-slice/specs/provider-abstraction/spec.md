# Delta for provider-abstraction

## ADDED Requirements

### Requirement: OpenAI Adapter (implemented)

The system MUST provide an `OpenAIAdapter` in `llmux.core.providers.openai` that fulfills the `ProviderAdapter` Protocol using `httpx`. The methods `complete`, `models`, and `health` MUST be implemented; `complete_stream` MUST raise `NotImplementedError` (streaming is deferred to `chat-streaming`). The adapter MUST accept its `httpx.AsyncClient` as a constructor argument so tests can inject `httpx.MockTransport` and avoid live OpenAI calls.

#### Scenario: complete returns a CompletionResult

- GIVEN an `OpenAIAdapter` with an injected `httpx.MockTransport` returning a valid OpenAI completion
- WHEN `complete(request)` is called
- THEN it returns a `CompletionResult`

#### Scenario: models returns advertised ModelInfo entries

- GIVEN an `OpenAIAdapter` configured with models `["gpt-4o-mini"]`
- WHEN `models()` is called
- THEN it returns `ModelInfo` entries matching the configured models

#### Scenario: complete_stream raises NotImplementedError

- GIVEN an `OpenAIAdapter`
- WHEN `complete_stream(request)` is called
- THEN it raises `NotImplementedError`

#### Scenario: health reports adapter status

- GIVEN an `OpenAIAdapter` with an injected mock transport
- WHEN `health()` is called
- THEN it returns a `HealthStatus`
