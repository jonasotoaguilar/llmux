# LLMux Roadmap

> **Status**: Proposed — dates and scope are planning estimates, not commitments.

## Overview

LLMux follows iterative delivery with clearly scoped phases. Each phase delivers a usable increment. Scope adjustments are expected based on feedback and operational experience.

---

## Phase 0: Foundation (Current)

**Status**: 🟡 In progress

**Goal**: Establish project baseline — architecture, design, and development environment.

### Deliverables

- [x] Repository setup with LICENSE
- [x] Architecture decisions (modular monolith, provider abstraction)
- [x] Product requirements document (PRD)
- [x] GitHub project configuration (templates, workflows)
- [ ] Development environment (Docker Compose skeleton)
- [ ] CI/CD pipeline scaffolding

---

## Phase 1: MVP — Core Gateway

**Status**: 🔲 Planned

**Goal**: A working gateway that can route chat completion requests to OpenAI and a second provider, with basic observability.

### Scope

- OpenAI-compatible `/v1/chat/completions` and `/v1/models` endpoints
- Provider adapters: OpenAI, Anthropic
- Router with priority-based provider selection
- Automatic fallback on 5xx / timeout / rate-limit
- API key authentication with PostgreSQL-backed key store
- Per-request usage recording (tokens, latency, cost)
- OpenTelemetry traces and metrics for every request
- Structured JSON logging
- Docker Compose deployment
- Basic admin API for provider and key management
- Minimal dashboard: provider health, recent requests, cost overview

### Non-Goals

- Streaming optimization (pass-through only)
- Rate limiting
- Budget enforcement
- Audit log viewer
- PII redaction
- Multi-region deployment
- Helm chart

### NFR Targets

- Gateway overhead p95 < 50ms
- Concurrent requests: 100
- Uptime: 99.5% (excluding providers)

---

## Phase 2: Cost & Rate Control

**Status**: 🔲 Planned

**Goal**: Add metering, rate limiting, budget enforcement, and cost dashboards.

### Scope — Cost & Rate Control

- Sliding window rate limiting (per API key and per tenant)
- Budget configuration (monthly/quarterly caps, soft/hard enforcement)
- Cost dashboard with per-team, per-provider, per-model breakdowns
- Usage export (CSV)
- Provider health monitoring and status history
- Alert configuration (webhook, email) for budget thresholds and provider health
- Rate limit and budget headers in API responses

---

## Phase 3: Production Hardening

**Status**: 🔲 Planned

**Goal**: Security, compliance, and operational maturity for production use.

### Scope — Production Hardening

- Audit log viewer (searchable, filterable, immutable)
- Configurable PII redaction for audit logs and traces
- Data retention policies with automated cleanup
- Role-based access control for dashboard
- Idempotency key support
- Performance benchmark suite
- Helm chart for Kubernetes deployment
- Terraform module for cloud deployment
- SOC2-type controls documentation
- Load testing and optimization

---

## Phase 4: Advanced Features

**Status**: 🔲 Proposed

**Goal**: Differentiated capabilities beyond basic proxying.

### Scope — Advanced Features

- Evaluation framework: run eval suites against any provider through the gateway
- Latency-based routing: route to the fastest provider for the given model
- Cost-optimized routing: automatically select cheapest provider meeting capability requirements
- Provider capability inference: model selection based on task requirements
- Multi-region active-active deployment
- Usage forecasts and anomaly detection
- Third-party adapter plugin system
- Custom prompt templates and pre/post-processing pipelines
- Webhook notifications for important events

---

## Future Considerations (Post v1)

- **Open source community governance**
- **Provider marketplace**: community-contributed adapters
- **Self-hosted model support**: vLLM, Ollama, TGI
- **Multi-modal support**: image, audio, video inputs
- **Real-time streaming transformations**: content filtering, moderation, enrichment mid-stream
- **Advanced caching**: semantic cache for repeated queries

---

## Key Milestones

| Milestone | Target | Dependency |
|-----------|--------|------------|
| Architecture approved | Q3 2026 | — |
| MVP functional | Q4 2026 | Architecture approved |
| Rate & cost control | Q1 2027 | MVP shipped |
| Production hardening | Q2 2027 | Rate & cost control |
| Public release (v1.0) | Q3 2027 | Production hardening |

## How to Influence the Roadmap

Open a Discussion or feature request with `enhancement` label. Community feedback directly shapes priority of Phase 4 and future features.
