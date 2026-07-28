# gateway-api-boundary

## Purpose

Define the HTTP surface of the `llmux` gateway under the `/v1` version prefix. The boundary is **partially OpenAI-compatible** (`/v1/models`, `/v1/chat/completions`) and **partially gateway-native** (`/v1/health` — OpenAI defines no such endpoint). The slice closes only the gateway API boundary stub; provider implementation, persistence, auth, streaming, metering, and admin surfaces remain out of scope.

Source: `openspec/changes/archive/2026-07-23-core-gateway-mvp/specs/gateway-api-boundary/spec.md` (delta promoted to source of truth on 2026-07-23).

## Requirements

### Requirement: Gateway-Native Health Endpoint

The system MUST expose `GET /v1/health` returning HTTP 200 with a JSON body shaped as `{"status": <string>, "version": <string>, "providers_configured": <array-of-strings>}`. This route is **gateway-native** — it MUST NOT be advertised or documented as OpenAI-compatible (OpenAI defines no such endpoint).

#### Scenario: Health returns 200 with required fields

- GIVEN the gateway is running
- WHEN a client sends `GET /v1/health`
- THEN the response status is 200
- AND the body has non-empty `status` and `version` strings
- AND `providers_configured` is a JSON array (empty array permitted in this slice)

### Requirement: OpenAI-Compatible Models Endpoint

The system MUST expose `GET /v1/models` returning HTTP 200 with an OpenAI-shaped envelope: `{"object": "list", "data": [...]}`. In this slice, `data` MUST be a JSON array of length 0.

#### Scenario: Models returns 200 with empty OpenAI-shaped list

- GIVEN the gateway is running
- WHEN a client sends `GET /v1/models`
- THEN the response status is 200
- AND `object` equals `"list"`
- AND `data` is a JSON array of length 0

### Requirement: Chat Completions Returns 501 For Both Stream Modes (no fake SSE)

The system MUST expose `POST /v1/chat/completions` returning HTTP 501 with an OpenAI-shaped error envelope. The response MUST be identical in status code, content type, and body shape for `stream=false` and `stream=true`. The system MUST NOT emit Server-Sent Events, chunked transfer encoding for streaming, or any partial-response framing — both stream modes return the same 501 contract.

#### Scenario: stream=false returns 501

- GIVEN a valid OpenAI-shaped chat request with `"stream": false`
- WHEN the client posts to `/v1/chat/completions`
- THEN the response status is 501
- AND the body is a single JSON OpenAI error envelope (not SSE, not chunked)

#### Scenario: stream=true returns identical 501, no fake SSE

- GIVEN a valid OpenAI-shaped chat request with `"stream": true`
- WHEN the client posts to `/v1/chat/completions`
- THEN the response status is 501
- AND the response Content-Type is `application/json` (NOT `text/event-stream`)
- AND the body shape is identical to the `stream=false` 501 case
- AND no `data:` SSE frames are present in the body

#### Scenario: stream field omitted returns 501

- GIVEN a valid OpenAI-shaped chat request with the `stream` field omitted
- WHEN the client posts to `/v1/chat/completions`
- THEN the response status is 501
- AND the envelope matches the `stream=false` 501 contract

### Requirement: Routes Mounted Under /v1

All routes defined in this spec MUST be reachable at the exact paths `/v1/health`, `/v1/models`, and `/v1/chat/completions`. Future breaking changes MUST introduce a new version prefix; routes under `/v1` MUST remain contract-stable within the v1 contract.

#### Scenario: Each route is reachable at its declared /v1 path

- GIVEN the gateway is running
- WHEN a client requests `/v1/health`, `/v1/models`, and `/v1/chat/completions`
- THEN each route returns its defined response shape

### Requirement: Strict Testability Of HTTP Boundary

Every endpoint defined in this spec MUST be covered by automated tests that exercise the live HTTP boundary (e.g. FastAPI TestClient). Tests MUST assert status code, response shape, and the no-fake-SSE invariant.

#### Scenario: Tests assert the no-fake-SSE invariant on stream=true

- GIVEN the FastAPI app is constructed
- WHEN a test issues `POST /v1/chat/completions` with `stream=true`
- THEN the test asserts status 501
- AND asserts Content-Type is NOT `text/event-stream`
- AND asserts the body parses as a single JSON error envelope

## Non-Goals (Explicit)

This spec MUST NOT introduce: real provider integration, API-key authentication, any persistence layer, real streaming, router/fallback/metering/cost/rate-limiting/audit/admin surfaces, Docker Compose, architecture-fitness tests, or closure of ROADMAP Phase 1, issue #1, or any downstream slice.
