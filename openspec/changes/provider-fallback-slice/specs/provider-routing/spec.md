# Delta for provider-routing

> **(planned)** Delta against the `provider-routing` capability established by `openspec/changes/provider-routing-functional-slice/specs/provider-routing/spec.md` (not yet archived to `openspec/specs/`; the Anthropic adapter slice did not modify the selection requirement). This slice replaces first-match no-fallback selection with candidate-ordered selection; the fallback behavior itself lives in the new `provider-fallback` capability. The requirement below is copied in full from the prior spec and edited, with unchanged scenarios preserved verbatim so archive replacement loses nothing.

## MODIFIED Requirements

### Requirement: First-Match Priority Provider Selection (planned)

The system MUST expose an async `select_candidates` that returns, in configured order, every provider whose model list contains the requested model. The first provider in configured order offering the model MUST be the primary candidate; the remaining matching providers MUST be fallback candidates. If no provider offers the model, the system MUST raise `ProviderSelectionError`. The router MUST attempt fallback candidates only on retryable failures (see `provider-fallback` "Retry Eligibility Classification"); it MUST NOT perform same-provider retries, backoff, or health-state pre-selection.

(Previously: `select_provider` returned only the first matching provider, and the router performed NO fallback, retries, backoff, or failover on any failure.)

#### Scenario: First matching provider is the primary candidate

- GIVEN providers ordered A then B, both offering model m
- WHEN `select_candidates` is called for m
- THEN A is returned as the primary candidate followed by B as fallback

#### Scenario: Providers not offering the model are excluded

- GIVEN provider A offers model m and provider B offers only model n
- WHEN `select_candidates` is called for m
- THEN only A is returned

#### Scenario: No provider offers the model

- GIVEN no configured provider offers model m
- WHEN `select_candidates` is called for m
- THEN a `ProviderSelectionError` is raised, which maps to 400 per the Normalized Error Hierarchy
