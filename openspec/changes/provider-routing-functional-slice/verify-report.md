```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:683b7aef0d18e813787d43e2450f39553723ea38796a55f9c38b5157c1bef579
verdict: pass
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 24/24
test_command: uv run pytest -q --cov=llmux --cov-fail-under=90
test_exit_code: 0
test_output_hash: sha256:c6a1bd923a0f7b295e097dfa0e3d8d0162653415b2b6007731cec5c69b38cc13
build_command: uv run ruff format --check src tests && uv run ruff check src tests && uv run mypy src tests
build_exit_code: 0
build_output_hash: sha256:2d6b2fd3da664bcd3c10a511fd2cb9bf5f7517722cb0753d911d03540bfa3cbf
```

## Verification Report (Final Pass)

**Change**: `provider-routing-functional-slice`  
**Mode**: Standard (Strict TDD inactive; review-driven development OFF)  
**Evidence revision**: `sha256:683b7aef0d18e813787d43e2450f39553723ea38796a55f9c38b5157c1bef579` (post-remediation source diff)  
**Parent revision**: `sha256:8e48f6f95e57ed8e9c3c6888de530fef682d00f3a2adc0b4d8ebf12bef689a25` (ordinal11 active, parent finishes)

### Completeness

| Metric | Value |
|---|---:|
| Tasks total | 29 |
| Tasks complete | 29 |
| Requirements complete | **10 / 10** (was 9/10 — fail-safe lifespan now compliant) |
| Written scenarios with passing coverage | **24 / 24** (was 23/23 — one behavior-first regression added) |

### Remediation

The previous verification (revision `sha256:43ad9d7…`) failed on one blocker: `src/llmux/main.py` lifespan ran `registry.aclose()` and `shutdown_tracer()` inside a `try/finally` that completed BEFORE `yield`, so the owned `httpx.AsyncClient` was closed before any request was served. The live ASGI harness observed `owned_client_closed_before_request=true; routed POST status=500`.

**Fix (bounded)**: only the lifespan teardown ordering changed. The `try/finally` is now split: the inner `try/except BaseException` handles the build-failure path (factory cleanup already ran, so only `shutdown_tracer()` runs before re-raise — preserving the existing `test_lifespan_tracer_shutdown_on_build_failure` event sequence); the `registry.aclose()` + `shutdown_tracer()` are deferred to a `finally` that runs AFTER `yield`, gated on a `started` flag so the tracer shuts down exactly once on each path. Module docstring updated to match the new contract.

**New behavior-first regression**: `test_lifespan_owned_client_stays_open_while_serving` in `tests/test_provider_routing_slice.py` wires a real `httpx.AsyncClient(transport=MockTransport(handler))` into a real `ProviderRegistry((RegistryEntry(adapter, client=owned),))` (registry-owned, NOT caller-owned), enters the real `lifespan_context` via `TestClient`, and proves:
1. the real owned client is open inside the lifespan,
2. a `POST /v1/chat/completions` returns 200 and the MockTransport handler actually served it,
3. the real owned client is still open after the request,
4. the real owned client is closed exactly once after `TestClient` exit.

The test FAILS against the pre-fix `main.py` (assertion: `not real_owned_client.is_closed` is `False` because the pre-yield `aclose` already closed the client) and PASSES against the fixed `main.py`.

### Build & Tests Execution (all green)

**Tests**: ✅ Passed — **81 tests** (was 80; +1 regression), coverage **97.97%** (threshold 90%).

```text
uv run pytest -q --cov=llmux --cov-fail-under=90
exit: 0
81 passed, 1 warning in 0.20s
coverage: 97.97% (492 statements, 10 missed) — main.py 100% (42/42 stmts)
output hash: sha256:c6a1bd923a0f7b295e097dfa0e3d8d0162653415b2b6007731cec5c69b38cc13
```

**Build / static checks**: ✅ Passed.

```text
uv run ruff format --check src tests
exit: 0
20 files already formatted
hash: sha256:fe255f317557113a1b1c1cb21f7ac9056924a831b6e5bed83a8f07a3119e3885

uv run ruff check src tests
exit: 0
All checks passed!
hash: sha256:f0d0b1081d9d3ebb26c4c93543053ecdc0a58998f22c071dc4ddb26021b57645

uv run mypy src tests
exit: 0
Success: no issues found in 20 source files
hash: sha256:5459bb7b9606483e03ef1ffd853871806fdb8ef7910f38a9d3bec4dc8a203e34
```

**Live ASGI / OTel / lifecycle harness**: ✅ All five contract points satisfied.

```text
command: isolated TestClient + MockTransport + monkey-patched build_providers returning a real ProviderRegistry with a registry-owned httpx.AsyncClient
exit: 0
harness output: LIVE ASGI LIFECYCLE HARNESS OK
harness hash: sha256:e47443cfb864b33cfada22b17f485742694ab408a0c9012f292e828f31b57094
lifecycle: owned_client_open_pre_request=true; routed POST status=200; owned_client_open_during_serving=true; owned_client_closed_post_exit=true; events=[build_tracer, build_providers, shutdown_tracer]
```

The harness FAILS against the pre-fix `main.py` (assertion: `not real_owned_client.is_closed` fails on the pre-request check) and PASSES against the fixed `main.py`.

### Spec Compliance Matrix (updated)

| Requirement | Scenario | Covering runtime test | Result |
|---|---|---|---|
| … (rows 1–22 unchanged — see previous report) | … | … | ✅ |
| Lifespan | Successful lifespan keeps registry-owned clients open during request serving | `test_lifespan_owned_client_stays_open_while_serving` (NEW) | ✅ COMPLIANT |
| Lifespan | Build failure still shuts tracer down | `test_lifespan_tracer_shutdown_on_build_failure` | ✅ COMPLIANT |
| Lifespan | `aclose` runs exactly once on the success path | `test_lifespan_aclose_before_tracer_shutdown` (existing) | ✅ COMPLIANT |

**Compliance summary**: 24/24 written scenarios have passing runtime coverage, including the new behavior-first regression. The previously-failing lifespan requirement is now compliant.

### Correctness (Static + Runtime Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Provider configuration and fail-fast construction | ✅ Implemented | Settings validation and registry construction tests pass. |
| OpenAI non-streaming adapter | ✅ Implemented | Injected client, typed upstream mapping, and no-stream contract pass. |
| Ordered registry and ownership | ✅ Implemented | Factory cleanup and caller-owned-client behavior pass. |
| First-match priority selection | ✅ Implemented | Async, ordered, no-fallback behavior passes. |
| Sanitized error hierarchy | ✅ Implemented | Stable 400/502/504 envelopes pass without raw exception data. |
| Models endpoint | ✅ Implemented | Registry aggregation and empty response pass. |
| Non-streaming chat routing | ✅ Implemented | Explicit/omitted false paths and error mappings pass. |
| Streaming 501 contract | ✅ Implemented | Explicit true is JSON-only and bypasses provider/telemetry. |
| Bounded telemetry | ✅ Implemented | Full suite plus independent OTel harness observed one span and success metrics. |
| **Fail-safe server lifespan teardown** | ✅ **Fixed** | `src/llmux/main.py:64-89` — `aclose` + `shutdown_tracer` now run AFTER `yield`; build-failure path still calls `shutdown_tracer` once before re-raise. Behavior-first regression in `tests/test_provider_routing_slice.py::test_lifespan_owned_client_stays_open_while_serving`. |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| Transactional provider construction | ✅ Yes | `build_providers` cleans partial clients and transfers a completed registry. |
| First-match selection without fallback | ✅ Yes | Router walks configured order. |
| Typed sanitized HTTP errors | ✅ Yes | Handler translates `LLMuxError`; unexpected errors propagate. |
| Public OTel dependency injection | ✅ Yes | `ChatTelemetry` accepts tracer/meter and live in-memory harness works. |
| **Lifespan owns resources through request serving** | ✅ **Yes** | Cleanup now runs AFTER `yield`; design lifecycle diagram and ownership contract are honored. |

### Changed Paths / Lines Reviewed (this remediation)

- `src/llmux/main.py:64-89` — `try/except BaseException` inside `try/finally`; the `finally` defers `aclose` + `shutdown_tracer` to after `yield`; `started` flag prevents double-shutdown on the build-failure path. Module docstring (lines 1–23) updated to match.
- `tests/test_provider_routing_slice.py:778-866` — new behavior-first regression `test_lifespan_owned_client_stays_open_while_serving`.
- `openspec/changes/provider-routing-functional-slice/apply-progress.md` — PR7 remediation section appended.
- `openspec/changes/provider-routing-functional-slice/verify-report.md` — replaced with this final pass evidence.

### Verdict

**PASS**

All 24 scenarios pass, coverage is 97.97% (gate 90% met), Ruff format / check / mypy strict pass, the live ASGI / OTel / lifecycle harness confirms the owned client stays open during request serving and closes exactly once after shutdown. Archive readiness: **ready**.
