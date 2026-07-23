# Security Policy

## Supported Versions

LLMux is in planning phase — no releases yet. Security guidance applies to the `main` branch and all release candidates once published.

| Version | Supported |
|---------|-----------|
| main (development) | ✅ Security review applies |
| < 1.0 (pre-release) | 🟡 Best-effort |

## Reporting a Vulnerability

**Do not report security vulnerabilities via public GitHub issues.**

Contact the maintainer directly:

- **Email**: jonasotoaguilar (at) protonmail (dot) com
- **Response time**: within 48 hours
- **PGP key**: available on request

### What to include

- Description of the vulnerability
- Steps to reproduce (PoC preferred)
- Affected version(s) and components
- Suggested fix or mitigation (optional)

### Process

1. Report is received and acknowledged within 48 hours.
2. Maintainer triages and validates the report within 5 business days.
3. A fix is developed and released within 14 days of confirmation (critical issues receive expedited handling).
4. Vulnerability is disclosed publicly after the fix is released.

## Security Design (Planned)

The following security controls are architectural decisions that will be implemented during development:

### Authentication & Authorization

- **API key-based auth** for gateway access: keys are hashed with bcrypt before storage, only the prefix and last 4 characters are exposed
- **Scoped API keys**: each key has a tenant and granular permissions (read, write, admin)
- **No session cookies**: the gateway is API-first; the dashboard will use a separate auth provider (planned: OAuth2 with GitHub/GitLab)

### Data Protection

- **TLS 1.3** for all external communication (gateway ↔ provider, gateway ↔ dashboard)
- **Encryption at rest**: PostgreSQL TDE or filesystem encryption for the data directory
- **API key isolation**: keys are never logged, never returned in API responses, never included in traces
- **Audit log**: append-only with configurable PII redaction patterns for request/response content
- **Data retention**: configurable TTL per data type (audit logs, usage records, traces)

### Network Security

- Run behind a reverse proxy (nginx, Caddy) for TLS termination and DDoS protection
- No direct database exposure to the internet
- Redis requires authentication (AUTH command) and binds to private network only
- Regular security updates for base Docker images

### Secrets Management

- Provider API keys stored in PostgreSQL (encrypted at rest) or environment variables (MVP)
- Planned: integration with HashiCorp Vault or AWS Secrets Manager for production deployments

## Responsible Disclosure

If you discover a vulnerability, we appreciate responsible disclosure. We will:

- Acknowledge receipt within 48 hours
- Keep you informed of progress
- Credit you in the release notes (unless you prefer anonymity)
- Not take legal action against good-faith security research
