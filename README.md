# LLMux

**Observable multi-provider AI gateway for reliable, cost-aware LLM applications.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Status: Planning](https://img.shields.io/badge/Status-Planning-blue)](/ROADMAP.md)

LLMux is a self-hosted gateway that sits between your application and LLM providers (OpenAI, Anthropic, Google, and more). It provides a single OpenAI-compatible API, intelligent routing with automatic fallback, per-request cost attribution, and OpenTelemetry-native observability — all with minimal latency overhead.

## Quick Path

1. Deploy with Docker Compose.
2. Configure providers in the admin API.
3. Point your application to the gateway's endpoint.
4. Monitor cost, latency, and health on the dashboard.

## Quick Start

> **⚠️ Planned — none of the files below exist yet.** The `.env.example`, `docker-compose.yml`, and `Dockerfile` listed in the commands are not in this repository. When implementation begins, the intended workflow will be:

```bash
git clone https://github.com/jonasotoaguilar/llmux.git
cd llmux
cp .env.example .env
docker compose up -d
curl http://localhost:4000/v1/health
```

## Details

| Topic | Decision |
|-------|----------|
| Audience | Platform/backend teams building LLM-powered apps |
| Runtime | Python 3.12+ (FastAPI), Node.js 22+ (Next.js dashboard) |
| API style | OpenAI-compatible REST (drop-in replacement) |
| Deep docs | [Architecture](./ARCHITECTURE.md) · [Design](./DESIGN.md) · [PRD](./PRD.md) · [Contributing](./CONTRIBUTING.md) |

## What Is This?

**LLMux** (LLM + multiplexer) solves three problems teams face when integrating LLMs into production:

1. **Cost unpredictability** — track spend per request, per team, per model across all providers.
2. **Reliability gaps** — automatic failover when a provider is down, slow, or rate-limited.
3. **Observability fragmentation** — every request emits OpenTelemetry traces, metrics, and structured logs regardless of provider.

The gateway exposes an OpenAI-compatible `/v1/chat/completions` endpoint. If your app works with OpenAI, it works with LLMux — just change the base URL and API key.

## Features

### MVP Scope

- **Unified API** — OpenAI-compatible endpoint, drop-in replacement for existing integrations
- **Multi-provider routing** — route by priority
- **Automatic fallback** — transparent failover on 5xx errors, timeouts, or rate limits
- **Cost attribution** — per-request token and cost tracking, aggregated by API key and tenant
- **Observability** — OpenTelemetry traces, metrics (request duration, tokens, cost, errors), structured logs
- **API key auth** — scoped API keys with tenant isolation
- **Basic admin API** — provider and key management

### Post-MVP

- **Cost-optimized routing** — route by cost, latency, or capability requirements (Phase 4)
- **Rate limiting** — per-key and per-tenant sliding window rate limits (Phase 2)
- **Budget enforcement** — hard and soft budget caps with configurable action (Phase 2)
- **Admin dashboard** — provider health, usage analytics, cost breakdowns, audit log viewer (Phase 1–3)
- **Audit log** — immutable, searchable request log with configurable PII redaction (Phase 3)
- **Evaluation framework** — run eval suites against any provider through the gateway (Phase 4)

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `LLMUX_HOST` | `0.0.0.0` | Gateway bind address |
| `LLMUX_PORT` | `4000` | Gateway HTTP port |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `REDIS_URL` | — | Redis connection string |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OpenTelemetry collector endpoint |

*Full reference documented when implementation begins.*

## Project Status

LLMux is in **planning phase**. The architecture, product requirements, and design documentation are being established before any implementation begins.

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full architectural specification, including component details, data model, NFRs, failure modes, and architecture decision records.

## Design

See [DESIGN.md](./DESIGN.md) for the dashboard design system, component states, accessibility, responsive layout, and design tokens.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the contribution workflow, code standards, and PR process.

## Security

See [SECURITY.md](./SECURITY.md) for the security policy and vulnerability reporting process.

## License

MIT — see [LICENSE](./LICENSE) for details.
