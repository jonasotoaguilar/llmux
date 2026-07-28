# ADR-0001: Modular Monolith Topology

## Status

Accepted

## Date

2026-07-17

## Deciders

Jonathan Soto

## Context

LLMux needs to serve as a gateway between applications and multiple LLM providers, handling routing, metering, auth, rate limiting, audit, and observability. These are distinct concerns with clear boundaries, but the initial team size (1-3 people), operational capacity, and lack of independent scaling evidence make microservices premature.

The key trade-off: we need module-level isolation for maintainability and future extractability, but we don't want the operational burden of distributed systems until proven necessary.

## Decision

Adopt a **modular monolith with ports/adapters (hexagonal architecture)** for the gateway component. All internal modules (routing, metering, auth, rate limiting, audit, budget enforcement) run in the same process but communicate through defined interfaces. Provider adapters implement a stable `ProviderAdapter` protocol. Storage adapters implement `UsageStore`, `ConfigStore`, `KeyStore` interfaces.

The admin dashboard (Next.js) remains a separate process — it is a read-heavy UI, not part of the gateway request path.

## Consequences

### Positive

- Operational simplicity: single deployment, single process to monitor, no inter-service networking
- Module boundaries enforced by interfaces, not network calls — easier to refactor and test
- Provider adapters are independently testable and swappable without touching core logic
- Extraction to microservices is possible per-module when evidence supports it (e.g., scale metering writes independently)
- Shared-nothing modules prevent accidental coupling

### Negative

- Cannot scale modules independently without extracting them first
- Single process resource limits (can be mitigated by running multiple gateway instances behind a load balancer)
- Language lock-in: all gateway modules must run in the same Python process
- Deployment coordination: a change to any module requires redeploying the whole gateway

### Neutral

- Team must enforce module boundaries through code review and architecture tests — no network boundary to prevent cheating
- Ports/adapters pattern adds indirection that is unnecessary for modules that will never be extracted

## Options Considered

### Option A: Modular Monolith with Ports/Adapters (Chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — interface indirection pays off long-term |
| Cost | Low — single process, single DB, single deploy |
| Scalability | Medium — horizontal via process count; vertical within each module |
| Team familiarity | High — well-known patterns |
| Ecosystem / Tooling | Strong — Python typing supports interface enforcement |
| Operational overhead | Low — single deployment unit |

### Option B: Microservices

| Dimension | Assessment |
|-----------|------------|
| Complexity | High — service discovery, inter-service auth, eventual consistency, N+1 databases |
| Cost | High — multiple processes, per-service monitoring, CI/CD pipelines |
| Scalability | High — per-module independent scaling |
| Team familiarity | Medium — requires distributed systems knowledge |
| Ecosystem / Tooling | Strong — but each service needs full observability setup |
| Operational overhead | Very high — for 1-3 person initial team |

### Option C: Layered Monolith

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — well understood |
| Cost | Lowest — simplest structure |
| Scalability | Low — module coupling makes extraction harder |
| Team familiarity | High — most developers know this pattern |
| Ecosystem / Tooling | Strong |
| Operational overhead | Low |

**Why layered monolith was rejected**: While simpler initially, provider adapters and cross-cutting concerns (observability, auth, metering) don't layer well. Every provider call must go through metering, audit, and rate limiting — a layered approach would either couple these concerns or duplicate them across layers. Ports/adapters let us inject these cross-cutting concerns as middleware around the adapter interfaces.

### Option D: Serverless (Lambda + API Gateway + DynamoDB)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — event-driven architecture, cold starts |
| Cost | Variable — pay per request, but streaming LLM responses are long-running |
| Scalability | Very high — auto-scaling per function |
| Team familiarity | Low — streaming over Lambda is non-trivial |
| Ecosystem / Tooling | Medium — cold starts conflict with latency targets |
| Operational overhead | Medium — managed infrastructure |

**Why serverless was rejected**: Streaming LLM responses can last minutes per request. AWS Lambda max execution time (15 minutes) conflicts with streaming connection management, and the pricing model penalizes long-running connections. Cold starts add unpredictable latency overhead.

## Trade-off Analysis

The modular monolith gives us module isolation without distributed system complexity. The primary risk — inability to scale modules independently — is acceptable because:

1. The gateway is CPU-light (most time is waiting on providers)
2. Horizontal scaling of the entire gateway is simple (add workers/containers)
3. Evidence-based extraction preserves the migration path to microservices if needed

## Action Items

1. [ ] Enforce module boundaries with Python abstract base classes or Protocols
2. [ ] Add architecture tests that verify cross-module import restrictions
3. [ ] Extract dashboard to separate process (already planned as separate Next.js app)
4. [ ] Document extraction criteria per module in ARCHITECTURE.md

## References

- [ARCHITECTURE.md](../../ARCHITECTURE.md) — system overview and component details
- Ports/adapters pattern: Alistair Cockburn's Hexagonal Architecture
