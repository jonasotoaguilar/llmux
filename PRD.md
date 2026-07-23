# PRD: LLMux — Observable Multi-Provider LLM Gateway

> **Status**: Proposed | **Last updated**: 2026-07-17

## Quick Path

1. Define the problem: teams integrating LLMs into production apps lack visibility, cost control, and reliable fallback across providers.
2. Outcome: a self-hosted gateway that provides unified API, observability, cost attribution, and reliability guarantees.
3. Success criteria: measurable p95 latency overhead < 50ms, per-request cost attribution, automated failover.
4. Non-goals: building a proprietary model, replacing provider SDKs entirely, generic API gateway.

## Details

| Topic | Decision |
|-------|----------|
| Primary user | Platform/backend teams building LLM-powered applications |
| Problem | No unified observability, cost control, or reliability across multiple LLM providers |
| Outcome | Single ingress point with routing, fallback, metering, and OpenTelemetry-native observability |
| Success measure | < 50ms p95 gateway overhead; 100% request cost attribution; automated provider failover under < 5s |

## 1. Executive Summary

### Problem Statement

Production LLM applications face three interconnected challenges: **cost unpredictability** (each provider has unique pricing and no unified view), **reliability gaps** (provider outages, rate limits, and latency spikes require manual fallback), and **observability fragmentation** (each provider emits different telemetry shapes with no correlation to business context).

### Proposed Solution

LLMux is a self-hosted, observable multi-provider gateway that sits between applications and LLM providers. It exposes a single OpenAI-compatible API, routes requests based on policy (cost, latency, capability), tracks usage and cost per API key/tenant, and emits OpenTelemetry traces, metrics, and logs for every request.

### Success Criteria

| KPI | Target | How to measure |
|-----|--------|----------------|
| Gateway latency overhead | p95 < 50ms | OpenTelemetry span duration difference |
| Request cost attribution | 100% of requests | Metering DB row per request |
| Provider failover time | < 5s from detection | Health check interval + failover span |
| Uptime | 99.5% (excl. provider downtime) | Synthetic health check |
| Cost budget control | Within configured budgets | Budget enforcement alerts |

## 2. User Experience & Functionality

### User Personas

- **Platform Engineer**: operates the gateway, configures providers, sets budgets, monitors health.
- **Application Developer**: consumes the unified API, expects OpenAI-compatible interface, wants latency/cost headers.
- **Engineering Manager**: needs per-team cost reports, budget alerts, and reliability SLAs.
- **Compliance Officer**: requires audit logs, data retention policies, and provider data-handling attestations.

### User Stories

- As a **platform engineer**, I want to add or remove an LLM provider without changing application code so that provider changes are transparent.
- As an **application developer**, I want to call a single API endpoint that routes to the best available provider so I don't manage multiple SDKs.
- As an **engineering manager**, I want per-team cost dashboards with budget alerts so I can control spend.
- As a **platform engineer**, I want to configure fallback rules so that if one provider is down, requests automatically route to another.
- As a **compliance officer**, I want an immutable audit log of all requests and responses (with PII redaction) so we meet data governance requirements.

### Acceptance Criteria

- [ ] Gateway exposes an OpenAI-compatible `/v1/chat/completions` endpoint.
- [ ] Provider routing supports priority, latency, and cost-based strategies.
- [ ] Automatic failover to secondary provider on 5xx, timeout, or rate-limit.
- [ ] Each request records provider, model, tokens, latency, and cost.
- [ ] API key authentication with tenant isolation.
- [ ] Budget enforcement: reject or warn when tenant exceeds configured budget.
- [ ] OpenTelemetry traces, metrics, and structured logs for every request.
- [ ] Admin dashboard: provider health, usage charts, cost breakdowns, audit log viewer.

### Non-Goals

- **Building a proprietary LLM**: the gateway routes to existing providers, not serving custom models.
- **Replacing provider SDKs entirely**: the gateway handles routing and observability; advanced provider-specific features (streaming edge cases, fine-tuning APIs) remain accessible through direct SDK use or the gateway pass-through.
- **Model training or fine-tuning**: no training pipeline, no model registry, no weights management.
- **Generic API gateway**: no HTTP routing, load balancing, or service mesh features beyond LLM-specific concerns.
- **Real-time streaming transformations**: streaming pass-through with minimal overhead, no content modification mid-stream (planned for post-MVP).
- **Built-in chat UI**: the gateway provides an API, not a chat interface (dashboard is operational, not conversational).
- **On-premise / air-gapped deployment**: MVP targets Docker Compose on cloud VMs; air-gapped is future scope.

## 3. Technical Specifications

### Architecture Overview

[See ARCHITECTURE.md for the full architectural specification.]

High-level: a FastAPI application with ports/adapters architecture. Inbound adapters (REST API, health checks) → core routing/metering/fallback logic → outbound provider adapters (OpenAI, Anthropic, Google, etc.). Persistence in PostgreSQL (usage, config, audit), Redis (rate limits, caching, health state). OpenTelemetry SDK for observability.

### Integration Points

- **Inbound**: OpenAI-compatible REST API (`/v1/chat/completions`, `/v1/models`).
- **Outbound provider adapters**: OpenAI, Anthropic, Google (planned: AWS Bedrock, Azure OpenAI, Mistral, Cohere).
- **Observability**: OpenTelemetry gRPC/HTTP exporter to any OTLP-compatible backend.
- **Persistence**: PostgreSQL for configuration, usage records, audit log; Redis for rate-limit counters, budget cache, provider health state, request cache.
- **Authentication**: API keys stored as hashed values in PostgreSQL, validated via middleware.

### Security & Privacy

- **Data in transit**: TLS 1.3 required for all external communication.
- **Data at rest**: PostgreSQL storage encryption; API key hashing (bcrypt).
- **PII redaction**: configurable patterns for request/response content in audit logs and tracing.
- **Data retention**: configurable TTL per data category (audit logs, usage records, traces).
- **Compliance**: audit log immutability (append-only via database triggers or separate write-once store); data locality via deployment region choice.

## 4. Risks & Roadmap

### Phased Rollout

| Phase | Scope | Timing |
|-------|-------|--------|
| **MVP** | OpenAI-compatible API, 2+ providers, routing/fallback, API key auth, metering, basic dashboard, OpenTelemetry traces | Proposed |
| **v0.2** | Budget enforcement, cost dashboards, rate limiting, provider health monitoring | Proposed |
| **v0.3** | Multi-tenancy improvements, audit log viewer, PII redaction, eval framework scaffold | Proposed |
| **v1.0** | Production hardening, Helm chart, performance benchmarks, SOC2 readiness documentation | Proposed |


### Rollout ↔ Roadmap

| PRD Label | ROADMAP Phase |
|-----------|---------------|
| MVP | Phase 1 — MVP: Core Gateway |
| v0.2 | Phase 2 — Cost & Rate Control |
| v0.3 | Phase 3 — Production Hardening / Phase 4 — Advanced Features |
| v1.0 | Phase 3 — Production Hardening (completion) |

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Provider API changes break adapters | Degraded service for that provider | Adapter abstraction with integration tests; provider-specific adapter per provider |
| Cost tracking drift due to streaming token counting | Inaccurate billing | Server-sent token count from provider API when available; fallback to estimated count |
| Rate-limit contention across tenants | False positives | Redis-based sliding window with per-tenant bucket; configurable burst factor |
| Observability overhead | Latency regression | Sampling for traces (head-based); metrics always on; benchmark p95 overhead per release |
| Vendor lock-in to specific provider SDK | Hard to add new providers | All providers behind port/adapter boundary; provider SDK is an implementation detail per adapter |

| Streaming cost attribution | Under-counting tokens | Deferred cost calculation on stream completion; emit usage event at end of stream |
| OpenTelemetry exporter back-pressure | Gateway latency | Async batch exporter with non-blocking queue; drop telemetry under back-pressure |
| PostgreSQL write throughput at scale | Request latency under high volume | Batch usage writes; separate write path for metering (async queue to DB writes) |
| Redis failure | Rate-limit and health-state loss | Circuit breaker falls open on Redis failure (allow all requests); health probes fall back to direct provider health checks |

## 5. Reference

- [ARCHITECTURE.md](./ARCHITECTURE.md) — full architecture, decisions, NFRs, failure modes
- [ROADMAP.md](./ROADMAP.md) — phased delivery timeline
- [docs/adr/](./docs/adr/) — architecture decision records
