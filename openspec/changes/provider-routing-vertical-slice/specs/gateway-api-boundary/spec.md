# Delta for gateway-api-boundary

## MODIFIED Requirements

### Requirement: OpenAI-Compatible Models Endpoint

The system MUST expose `GET /v1/models` returning HTTP 200 with `{"object": "list", "data": [...]}`. `data` MUST aggregate one entry per (provider, model) advertised by the enabled providers in the startup registry. When no provider is enabled, `data` MUST be an empty array.

(Previously: `data` was always an empty array regardless of configuration.)

#### Scenario: Models lists configured provider models

- GIVEN the gateway is running with `openai` enabled and configured
- WHEN a client sends `GET /v1/models`
- THEN the status is 200, `object` is `"list"`, and `data` has ≥1 entry for a configured model

#### Scenario: Models returns empty list when no provider is enabled

- GIVEN the gateway is running with `LLMUX_PROVIDERS_CONFIGURED=[]`
- WHEN a client sends `GET /v1/models`
- THEN the status is 200 and `data` is a JSON array of length 0

### Requirement: Strict Testability Of HTTP Boundary

Every endpoint MUST be covered by live-HTTP tests (e.g. FastAPI TestClient) asserting status, response shape, the real-completion path for `stream=false` against a mocked provider, and the no-fake-SSE invariant for `stream=true`.

(Previously: tests asserted 501 for all stream modes plus the no-fake-SSE invariant.)

#### Scenario: Tests assert the no-fake-SSE invariant on stream=true

- GIVEN the FastAPI app is constructed
- WHEN a test issues `POST /v1/chat/completions` with `stream=true`
- THEN it asserts status 501, Content-Type NOT `text/event-stream`, and a single JSON error body

#### Scenario: Tests assert the stream=false success and error contracts

- GIVEN the FastAPI app constructed with a mocked provider
- WHEN a test issues `POST /v1/chat/completions` with `stream=false`
- THEN it asserts 200 on a mocked success and a normalized 502 or 504 envelope on failure

## REMOVED Requirements

### Requirement: Chat Completions Returns 501 For Both Stream Modes

(Reason: `stream=false` now forwards to a real provider returning 200 or a normalized 502/504; only `stream=true` retains 501.)
(Migration: see replacement below. `tests/test_unit_2.py` 501/empty assertions are split/inverted; a dedicated case asserts `stream=true` still returns 501.)

## ADDED Requirements

### Requirement: Chat Completions Non-Streaming Returns Real Response

The system MUST expose `POST /v1/chat/completions`. For `stream=false` (and when `stream` is omitted, defaulting to false) it MUST forward to the selected provider: HTTP 200 with an OpenAI-shaped completion envelope on success, or a normalized OpenAI-shaped error envelope on failure (502 for upstream/configuration errors, 504 for upstream timeout). For `stream=true` it MUST return HTTP 501 with the OpenAI-shaped error envelope and MUST NOT emit Server-Sent Events, chunked transfer encoding, or any partial-response framing.

#### Scenario: stream=false returns 200 with a completion

- GIVEN a valid request with `"stream": false` and a serving provider returning success
- WHEN the client posts to `/v1/chat/completions`
- THEN the status is 200 and the body is an OpenAI-shaped completion envelope

#### Scenario: stream=false upstream error returns 502

- GIVEN a valid request with `"stream": false` and the provider returning an upstream error
- WHEN the client posts to `/v1/chat/completions`
- THEN the status is 502 and the body is an OpenAI-shaped error envelope

#### Scenario: stream=false timeout returns 504

- GIVEN a valid request with `"stream": false` whose provider call exceeds the timeout
- WHEN the client posts to `/v1/chat/completions`
- THEN the status is 504 and the body is an OpenAI-shaped error envelope

#### Scenario: stream=true returns 501 with no fake SSE

- GIVEN a valid request with `"stream": true`
- WHEN the client posts to `/v1/chat/completions`
- THEN the status is 501, Content-Type is `application/json` (NOT `text/event-stream`), and no `data:` SSE frames appear

#### Scenario: stream field omitted defaults to the stream=false contract

- GIVEN a valid request with the `stream` field omitted
- WHEN the client posts to `/v1/chat/completions`
- THEN the response follows the `stream=false` contract (200 or 502/504), never 501
