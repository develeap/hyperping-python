# MCP Rate-Limit Fixes Test Plan

Companion to `docs/plans/2026-05-21-mcp-rate-limit-fixes.md`. Drives quality for the
A1+A2+A3+A4+A5+B cutover that landed JSON-RPC rate-limit detection, an
`initialize` cool-off latch, the TOCTOU fix, narrowed transient retry, the new
`ensure_initialized()` method, and the README/CHANGELOG documentation.

## Strategy reconciliation

No prior testing strategy was approved in the conversation; the implementation
plan itself is prescriptive about the testing approach. This test plan adopts
that prescription (respx-mocked unit tests, sync and async parity, no new
runtime dependencies) and adds the few coverage gaps the plan listed loosely
(idempotency of `initialize()`, concurrent first-call de-duplication via
`threading.Barrier` / `asyncio.gather`, latch short-circuit observed at the
`route.call_count` boundary, a monkeypatched `time.monotonic` to advance the
cool-off deadline, and `ensure_initialized()` propagation tests on both
high-level clients). Two assumptions are documented inline below where they
arise. No cost or scope change versus the plan, so no
`## Strategy changes requiring user approval` section is needed.

## Harness requirements

No new harnesses are built. All tests run inside the existing
`pytest` + `respx` + `pytest-asyncio` setup defined in `pyproject.toml`. The
plan adopts the following conventions for the new tests, each chosen because
the harness it relies on already exists in the suite:

- **respx route handles** (`respx.post(MCP_URL).mock(...)`): the plan uses
  `route.call_count` to assert "no further HTTP traffic" while the latch is
  active. This is the highest-fidelity check available against the real
  transport (`httpx.Client`/`AsyncClient`) without a live server.
- **`monkeypatch` of `hyperping._mcp_transport.time.monotonic` and
  `hyperping._async_mcp_transport.time.monotonic`**: the cool-off deadline is
  a `time.monotonic()` value; monkeypatching the module-level reference lets
  tests advance time without sleeping. The plan explicitly chose this clock so
  the patch path is stable.
- **`threading.Barrier(2)` + two `threading.Thread`s** for the sync TOCTOU
  test; **`asyncio.gather`** for its async mirror. Both exercise the
  double-checked init under genuine concurrency rather than a serialized
  re-entry.
- **`unittest.mock.MagicMock` / `AsyncMock`** swapped onto `client._transport`
  for the high-level `ensure_initialized()` propagation tests, matching the
  pattern already used throughout `tests/unit/test_mcp_client.py` and
  `tests/unit/test_async_mcp_client.py`.

The action space is the SDK's public/observable surface:

- `McpTransport.initialize`, `McpTransport.call_tool`, `McpTransport.close`,
  context-manager entry/exit, and the private `_send_rpc` path responsible
  for HTTP-status and JSON-RPC error classification.
- `AsyncMcpTransport.initialize`, `AsyncMcpTransport.call_tool`,
  `AsyncMcpTransport.close`, async context-manager, and async `_send_rpc`.
- `HyperpingMcpClient.ensure_initialized` (new) plus the rest of its already
  covered tool methods that route through `_transport.call_tool`.
- `AsyncHyperpingMcpClient.ensure_initialized` (new) plus the existing async
  tool methods.
- The `HyperpingRateLimitError` exception shape: `message`, `retry_after`,
  `status_code`, `response_body`.

Sources of truth:

- The implementation plan (`docs/plans/2026-05-21-mcp-rate-limit-fixes.md`)
  for behavioral contracts, invariants, the documented rate-limit message
  format, the cool-off latch contract, and the two-lock structure.
- The MCP 2025-03-26 spec (cited in the plan) for handshake semantics
  (`initialize` then `notifications/initialized`), referenced only to confirm
  test responses are realistic.
- Hyperping's documented rate-limit signal shapes (HTTP 429 + `Retry-After`;
  HTTP 200 + JSON-RPC `error.code = -32000` + message text) per the plan.
- The existing test suite for fixture/helper patterns (`INIT_RESPONSE`,
  `NOTIFICATION_ACCEPTED`, `_tool_response`).

## Test plan

Tests are numbered in priority order. Each entry lists name, type,
disposition, harness, preconditions, actions, expected outcome, and notable
interactions.

### Acceptance gates (problem-statement red checks)

#### 1. JSON-RPC rate-limit on `initialize` raises `HyperpingRateLimitError` (sync)

- **Name**: A fresh client whose `initialize` is rate-limited via JSON-RPC
  `-32000` surfaces a typed `HyperpingRateLimitError` with the parsed
  `retry_after`.
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + respx, `McpTransport` real instance
- **Preconditions**: respx mocks the MCP endpoint to return HTTP 200 with
  body `{"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message":
  'Hyperping MCP rate limit exceeded for "initialize" (5/5 per minute).
  Retry after 32s.'}}`. `transport._initialized = True` so the test
  exercises the `_send_rpc` classifier directly (the cool-off and TOCTOU
  tests cover the full path).
- **Actions**: `transport.call_tool("some_tool")`.
- **Expected outcome** (sources: implementation plan A1, exception module):
  `HyperpingRateLimitError` is raised. `exc.retry_after == 32`,
  `exc.status_code == 200`, `"rate limit" in exc.message.lower()`,
  `exc.response_body["code"] == -32000`. The exception is NOT a generic
  `HyperpingAPIError` carrying only the message string.
- **Interactions**: `_send_rpc` JSON-RPC error classification path,
  `HyperpingRateLimitError.__init__`.

#### 2. JSON-RPC rate-limit on `initialize` raises `HyperpingRateLimitError` (async)

- **Name**: Async mirror of Test 1.
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest-asyncio + respx, `AsyncMcpTransport` real instance.
- **Preconditions**: same respx body as Test 1; `transport._initialized =
  True`.
- **Actions**: `await transport.call_tool("some_tool")`.
- **Expected outcome**: same as Test 1.
- **Interactions**: async `_send_rpc` classifier.

#### 3. User repro: six fresh clients under JSON-RPC rate-limit fail fast and typed (sync)

- **Name**: Reproducing the exact paste-ready snippet from the user's bug
  report, every iteration raises `HyperpingRateLimitError` with the parsed
  `retry_after` instead of a generic `HyperpingAPIError`.
- **Type**: scenario / regression
- **Disposition**: new (test file:
  `tests/unit/test_mcp_transport.py`)
- **Harness**: pytest + respx, full `McpTransport` constructed inside the
  loop (so each iteration performs its own `initialize`).
- **Preconditions**: respx mocks every POST to MCP_URL with the JSON-RPC
  rate-limit body from Test 1.
- **Actions**: loop `for _ in range(6)`: construct `McpTransport`, call
  `transport.call_tool("list_monitors", {"status": "ssl_expiring"})`,
  capture exception, `transport.close()`.
- **Expected outcome** (source: plan §Completion Standard): every iteration
  raises `HyperpingRateLimitError` with `retry_after == 32` and
  `status_code == 200`. Six exceptions, none generic, none silent. Each
  client closes cleanly.
- **Interactions**: full handshake path including `_initialize_locked`,
  cool-off latch arming (each instance latches its own); `close()`.

#### 4. Existing HTTP 429 detection on `tools/call` still works (sync, regression)

- **Name**: HTTP 429 with `Retry-After: 30` continues to raise
  `HyperpingRateLimitError(retry_after=30, status_code=429)`.
- **Type**: regression (characterization)
- **Disposition**: existing (`test_call_tool_http_429_with_retry_after`,
  `test_call_tool_http_429_no_retry_after`,
  `test_call_tool_http_429_non_integer_retry_after`)
- **Harness**: pytest + respx.
- **Preconditions**: as in current tests.
- **Actions**: as in current tests.
- **Expected outcome**: existing assertions hold unchanged. Backward-compat
  contract (plan §Backward compatibility) verified.
- **Interactions**: HTTP-status branch in `_send_rpc`.

#### 5. Async HTTP 429 detection regression

- **Name**: Async mirror of Test 4.
- **Type**: regression
- **Disposition**: existing in `tests/unit/test_async_mcp_transport.py` (the
  existing async 429 cases); confirm they still pass.
- **Harness**: pytest-asyncio + respx.
- **Preconditions / Actions / Expected outcome / Interactions**: same as
  Test 4 against `AsyncMcpTransport`.

### High-value scenario and integration tests

#### 6. Concurrent first calls trigger exactly one `initialize` (sync)

- **Name**: Two threads racing the first `call_tool` on the same transport
  produce a single `initialize` POST, not two.
- **Type**: integration / invariant
- **Disposition**: new
- **Harness**: pytest + respx + `threading.Barrier(2)` + two
  `threading.Thread`.
- **Preconditions**: respx mock returns a four-message side_effect
  sequence: `INIT_RESPONSE`, `NOTIFICATION_ACCEPTED`, two `_tool_response`s
  (one per thread).
- **Actions**: Both threads wait on `barrier.wait()`, then call
  `transport.call_tool("some_tool")`. Join both.
- **Expected outcome** (source: plan §Invariant 1, A3): total respx
  `route.call_count == 4` (one `initialize`, one `notifications/initialized`,
  two tool calls). Both threads return `{"ok": True}`. No
  `IndexError`/`StopIteration` from the side_effect being exhausted by a
  duplicate `initialize`.
- **Interactions**: `_init_lock` double-checked pattern; `_send_rpc`;
  `_next_id` under `_lock` (the request-id lock, deliberately separate per
  plan §Final lock structure).
- **Assumption documented in test docstring**: respx's side_effect ordering
  is deterministic for serialized POSTs, but the two `tools/call` responses
  are interchangeable (both `{"ok": True}`), removing any ordering brittleness
  between the two threads.

#### 7. Concurrent first calls trigger exactly one `initialize` (async)

- **Name**: Async mirror of Test 6 via `asyncio.gather`.
- **Type**: integration / invariant
- **Disposition**: new
- **Harness**: pytest-asyncio + respx.
- **Preconditions**: same four-message side_effect on the route.
- **Actions**: `await asyncio.gather(transport.call_tool("some_tool"),
  transport.call_tool("some_tool"))`.
- **Expected outcome**: both results equal `{"ok": True}`; route
  `call_count == 4`. The async `_init_lock` correctly serializes the
  handshake while letting the second coroutine see `_initialized=True` on
  re-acquire.
- **Interactions**: `asyncio.Lock` semantics across `await`; async
  `_initialize_locked`.

#### 8. `initialize()` is idempotent (sync)

- **Name**: Calling `transport.initialize()` twice POSTs only one handshake
  pair (initialize + notification).
- **Type**: invariant
- **Disposition**: new
- **Harness**: pytest + respx.
- **Preconditions**: respx mock with two-message side_effect (`INIT_RESPONSE`,
  `NOTIFICATION_ACCEPTED`).
- **Actions**: `transport.initialize(); transport.initialize();`.
- **Expected outcome** (source: plan §A3, idempotent contract):
  `route.call_count == 2` (initialize + notification, not 4). Second call
  returns the cached `_init_result`.
- **Interactions**: `_init_lock` fast-path return; `_init_result` cache.

#### 9. `initialize()` is idempotent (async)

- **Name**: Async mirror of Test 8.
- **Type**: invariant
- **Disposition**: new
- **Harness**: pytest-asyncio + respx.
- **Preconditions / Actions**: `await transport.initialize()` twice.
- **Expected outcome**: `route.call_count == 2`.
- **Interactions**: async `_init_lock` fast path.

#### 10. Cool-off latch trips on rate-limited `initialize` and blocks further HTTP (sync)

- **Name**: After a rate-limited `initialize`, subsequent `call_tool`
  invocations raise `HyperpingRateLimitError` with no further network
  traffic until the cool-off deadline.
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest + respx + `monkeypatch` of
  `hyperping._mcp_transport.time.monotonic`.
- **Preconditions**: monkeypatched monotonic clock starts at `t = 1000.0`.
  respx mock returns the JSON-RPC rate-limit body (`Retry after 30s.`) for
  every POST.
- **Actions**:
  1. `transport.call_tool("some_tool")` -> expect
     `HyperpingRateLimitError`; assert `route.call_count == 1`.
  2. `transport.call_tool("some_tool")` (clock unchanged) -> expect
     `HyperpingRateLimitError`; assert `route.call_count == 1` (no extra
     HTTP request).
- **Expected outcome** (source: plan §A2, §Invariant 4): second call raises
  typed error with `retry_after >= 1`, route `call_count` stays at 1.
- **Interactions**: `_initialize_locked` arms `_init_blocked_until`; the
  next `initialize()` call observes the remaining cool-off and raises before
  any `_send_rpc`.

#### 11. Cool-off latch trips and blocks further HTTP (async mirror of Test 10)

- **Name**: Async mirror.
- **Type**: scenario
- **Disposition**: new
- **Harness**: pytest-asyncio + respx +
  `monkeypatch` of `hyperping._async_mcp_transport.time.monotonic`.
- **Preconditions / Actions / Expected outcome / Interactions**: same shape
  as Test 10.

#### 12. Cool-off clears after deadline elapses; next call re-initializes (sync)

- **Name**: Once the monotonic clock advances past `_init_blocked_until`,
  the next `call_tool` performs a fresh `initialize` and the tool call
  succeeds.
- **Type**: scenario / invariant
- **Disposition**: new
- **Harness**: pytest + respx + monkeypatched `time.monotonic`.
- **Preconditions**: respx side_effect sequence: rate-limit response,
  successful `INIT_RESPONSE`, `NOTIFICATION_ACCEPTED`, successful tool
  response.
- **Actions**:
  1. `transport.call_tool("some_tool")` -> latch arms; expect
     `HyperpingRateLimitError`.
  2. `transport.call_tool("some_tool")` (clock unchanged) -> still latched.
  3. Advance `fake_now["t"] += 100.0`.
  4. `result = transport.call_tool("some_tool")` -> succeeds.
- **Expected outcome** (source: plan §Invariant 5): final result is
  `{"ok": True}`. The cool-off was cleared (`_init_blocked_until == 0.0`
  after success), and exactly one re-initialize occurred.
- **Interactions**: `_initialize_locked` clears `_init_blocked_until` on
  success.

#### 13. Cool-off clears after deadline (async mirror of Test 12)

- **Name**: Async mirror of Test 12.
- **Type**: scenario / invariant
- **Disposition**: new
- **Harness**: pytest-asyncio + respx + monkeypatched
  `_async_mcp_transport.time.monotonic`.
- **Preconditions / Actions / Expected outcome / Interactions**: same as
  Test 12.

#### 14. `ensure_initialized()` performs the handshake and is idempotent (sync, transport-integrated)

- **Name**: Calling `client.ensure_initialized()` triggers `initialize` then
  `notifications/initialized`; calling it a second time is a no-op.
- **Type**: integration
- **Disposition**: new (`tests/unit/test_mcp_client.py`)
- **Harness**: pytest + respx with a real `HyperpingMcpClient` (do NOT
  swap `_transport` for this case so that we exercise the real path
  end-to-end through the transport).
- **Preconditions**: respx mock returns `INIT_RESPONSE` and
  `NOTIFICATION_ACCEPTED` in sequence.
- **Actions**: `client = HyperpingMcpClient(api_key="sk_test",
  base_url=MCP_URL); client.ensure_initialized();
  client.ensure_initialized(); client.close()`.
- **Expected outcome** (source: plan §A5): `route.call_count == 2` (one
  initialize, one notification). No exception. The second call is a no-op.
- **Interactions**: `HyperpingMcpClient.ensure_initialized` delegates to
  `transport.initialize`; the transport's `_init_lock` provides idempotency.
- **Assumption documented in test docstring**: We allow `MCP_URL` import
  via `tests/unit/test_mcp_transport.MCP_URL` (already a re-export of the
  module URL); using the same base_url keeps the existing transport tests'
  pattern.

#### 15. `ensure_initialized()` delegates to transport and propagates `HyperpingRateLimitError` (sync, mocked transport)

- **Name**: With `_transport` replaced by a `MagicMock`,
  `client.ensure_initialized()` calls `_transport.initialize` exactly once,
  and a `HyperpingRateLimitError` raised by the transport propagates
  unchanged.
- **Type**: unit
- **Disposition**: new (`tests/unit/test_mcp_client.py`)
- **Harness**: pytest + `unittest.mock.MagicMock` (matches existing
  `make_client()` pattern in that file).
- **Preconditions**: `client._transport = MagicMock()`.
- **Actions**:
  1. `client.ensure_initialized()` then assert
     `client._transport.initialize.assert_called_once_with()`.
  2. Set `client._transport.initialize.side_effect =
     HyperpingRateLimitError("rate limited on initialize", retry_after=30,
     status_code=200)`; call `client.ensure_initialized()`.
- **Expected outcome**: First action invokes `initialize` exactly once.
  Second action raises `HyperpingRateLimitError` with
  `retry_after == 30` and `status_code == 200`.
- **Interactions**: delegation contract; exception propagation through the
  high-level client.

#### 16. `ensure_initialized()` propagates `HyperpingRateLimitError` (async)

- **Name**: Async mirror of Test 15.
- **Type**: unit
- **Disposition**: new (`tests/unit/test_async_mcp_client.py`)
- **Harness**: pytest-asyncio + `unittest.mock.AsyncMock`.
- **Preconditions / Actions / Expected outcome / Interactions**: same as
  Test 15 with `AsyncHyperpingMcpClient` and `await
  client.ensure_initialized()`.

### Boundary, differential, and negative tests

#### 17. JSON-RPC rate-limit without parseable seconds yields `retry_after=None` (sync)

- **Name**: A `-32000` message without a `Retry after Xs` substring still
  classifies as rate-limit with `retry_after=None`.
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + respx.
- **Preconditions**: respx returns body `{"code": -32000, "message":
  "Hyperping MCP rate limit exceeded. Try again later."}`.
- **Actions**: `transport.call_tool("some_tool")` with
  `transport._initialized = True`.
- **Expected outcome**: `HyperpingRateLimitError` raised, `retry_after is
  None`. Classification still fires on the substring + code combo.

#### 18. JSON-RPC rate-limit without parseable seconds (async)

- **Name**: Async mirror of Test 17.
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest-asyncio + respx.

#### 19. Non-rate-limit JSON-RPC error stays a generic `HyperpingAPIError` (sync)

- **Name**: A JSON-RPC error with `code == -32601` ("Method not found") is
  NOT misclassified as a rate-limit; it raises plain `HyperpingAPIError`.
- **Type**: boundary / regression
- **Disposition**: new (negative classification check; the existing
  `test_call_tool_jsonrpc_error` is similar but the new test explicitly
  asserts `not isinstance(exc, HyperpingRateLimitError)`).
- **Harness**: pytest + respx.
- **Preconditions / Actions / Expected outcome**: see plan Task 2 Step 1
  test verbatim. Verifies the classifier checks both code AND message.

#### 20. `-32000` without rate-limit substring stays generic (sync)

- **Name**: A `-32000` error whose message does not contain "rate limit"
  raises generic `HyperpingAPIError`, not `HyperpingRateLimitError`.
- **Type**: boundary
- **Disposition**: new
- **Harness**: pytest + respx.
- **Preconditions**: body `{"code": -32000, "message": "Some other server
  error"}`.
- **Expected outcome** (source: plan §Strategy Gate alternative 5, intentional
  double-check): generic `HyperpingAPIError`. `isinstance(exc,
  HyperpingRateLimitError)` is False.

#### 21. Non-rate-limit JSON-RPC error stays generic (async)

- **Name**: Async mirror of Test 19.
- **Type**: boundary / regression
- **Disposition**: new.

#### 22. `-32000` without rate-limit substring stays generic (async)

- **Name**: Async mirror of Test 20.
- **Type**: boundary
- **Disposition**: new.

### Invariant tests

#### 23. `call_tool` retry loop never retries `HyperpingRateLimitError` from HTTP 429 (sync)

- **Name**: With `max_retries=3` and a permanent HTTP 429 response,
  `call_tool` makes exactly one HTTP request before raising.
- **Type**: invariant
- **Disposition**: new
- **Harness**: pytest + respx, `transport._initialized = True`.
- **Preconditions**: respx returns `httpx.Response(429, text="Rate limited",
  headers={"retry-after": "5"})` for every POST.
- **Actions**: `transport.call_tool("some_tool")` raises.
- **Expected outcome** (source: plan §Invariant 6, §A4): exception is
  `HyperpingRateLimitError`; `route.call_count == 1` (NOT 4).
- **Interactions**: retry filter in `call_tool` (only retries 500/502/503/504);
  exception hierarchy (`HyperpingRateLimitError` inherits from
  `HyperpingAPIError` but its `status_code` is outside the retry set).

#### 24. `call_tool` retry loop never retries JSON-RPC rate-limit (sync)

- **Name**: With `max_retries=3` and a permanent JSON-RPC `-32000`
  rate-limit response, `call_tool` makes exactly one HTTP request before
  raising.
- **Type**: invariant
- **Disposition**: new
- **Harness**: pytest + respx, `transport._initialized = True`.
- **Preconditions**: respx returns HTTP 200 with the rate-limit JSON-RPC body.
- **Actions**: `transport.call_tool("some_tool")` raises.
- **Expected outcome**: `HyperpingRateLimitError` raised;
  `route.call_count == 1`.
- **Interactions**: the `status_code=200` on the JSON-RPC path must NOT
  satisfy the `in (500, 502, 503, 504)` filter even though
  `HyperpingRateLimitError` is a subclass of `HyperpingAPIError`.

#### 25. `call_tool` rate-limit retry invariants (async)

- **Name**: Async mirrors of Tests 23 and 24.
- **Type**: invariant
- **Disposition**: new (two new tests).
- **Harness**: pytest-asyncio + respx.

#### 26. 5xx retry path still functions after the refactor (sync, regression)

- **Name**: A persistent HTTP 502 still raises `HyperpingAPIError` after
  exactly `max_retries + 1` attempts.
- **Type**: regression
- **Disposition**: existing (`test_call_tool_retry_exhausted`); confirm
  unchanged behavior.
- **Harness**: pytest + respx + `patch("hyperping._mcp_transport.time.sleep")`.
- **Expected outcome**: existing assertions hold; the comment-only change
  in `call_tool` does not alter behavior. Implicitly verifies that the
  refactor and the new `_init_lock` did not regress transient-retry
  semantics.

#### 27. 5xx retry path still functions (async)

- **Name**: Equivalent of Test 26 against `AsyncMcpTransport`.
- **Type**: regression
- **Disposition**: existing async retry test (if present) or new minimal
  mirror.

### Coverage gates and meta-checks

#### 28. Coverage threshold preserved

- **Name**: `pytest --cov-fail-under=85` still passes after the change.
- **Type**: invariant (project-level)
- **Disposition**: existing (`pyproject.toml` `[tool.pytest.ini_options]`).
- **Harness**: pytest's coverage plugin (already configured).
- **Expected outcome**: full project run is green and coverage is at or
  above 85%.

#### 29. Static checks clean

- **Name**: `ruff check src tests` and `mypy --strict src` are clean after
  the change.
- **Type**: invariant
- **Disposition**: existing (project linters).
- **Harness**: `ruff`, `mypy` configured in `pyproject.toml`.
- **Expected outcome**: zero findings. Catches accidental imports,
  unused names, or type-annotation drift introduced by the new lock and
  cool-off attributes.

#### 30. Documentation artifacts present and well-formed

- **Name**: README contains the new "MCP rate limits and connection
  lifecycle" subsection, and CHANGELOG contains an `[Unreleased]` block with
  `### Added` and `### Fixed`.
- **Type**: regression (artifact)
- **Disposition**: new lightweight assertion (one test or one CI grep step;
  prefer a pytest assertion to keep the gate in the suite).
- **Harness**: pytest reading the repo files via `pathlib`.
- **Preconditions**: working directory is the repo root.
- **Actions**: read `README.md` and assert the literal heading
  `### MCP rate limits and connection lifecycle` appears; read
  `CHANGELOG.md` and assert `## [Unreleased]` appears as a top-level
  heading and is followed somewhere in the file by `### Added` and
  `### Fixed`.
- **Expected outcome** (source: plan §B, §Documentation copy (final)):
  both assertions pass. Catches accidental removal during merges.
- **Interactions**: none; pure file content check.
- **Note**: this is the smallest reliable replacement for human review of
  the docs change; the alternative ("a person reads the README") is
  forbidden by the test-plan rules.

## Coverage summary

### Covered

- **A1 (JSON-RPC -32000 rate-limit classification)**: sync Tests 1, 17, 19,
  20; async Tests 2, 18, 21, 22.
- **A2 (cool-off latch)**: sync Tests 10, 12; async Tests 11, 13.
- **A3 (TOCTOU init race + idempotent `initialize`)**: sync Tests 6, 8;
  async Tests 7, 9.
- **A4 (transient retry never catches rate-limit)**: sync Tests 23, 24;
  async Test 25 (two cases). Test 26/27 protect the 5xx retry path.
- **A5 (`ensure_initialized` on high-level clients)**: sync Tests 14, 15;
  async Test 16.
- **B (docs)**: Test 30 pins the README and CHANGELOG artifacts.
- **Backward compatibility (HTTP 429 path, existing exception shape)**:
  Tests 4, 5 (existing) plus the meta-tests 28 and 29.
- **User repro fidelity**: Test 3 reproduces the user's paste-ready snippet
  shape verbatim, and is the single most important acceptance gate for the
  bug report.

### Explicitly excluded per strategy

- **Live integration against the real Hyperping MCP server**: the plan
  forbids this (no live calls, no paid resources). Tests use `respx`
  mocks; the user's repro fidelity is verified by mirroring the documented
  rate-limit body shape.
- **Cross-process session-id reuse and on-disk session persistence**:
  removed from scope by the plan (server is stateless; spec mandates
  handshake). No tests written.
- **Server-side fixes (HTTP 429 vs 200, real rolling window, honest
  Retry-After arithmetic, separate cap on `initialize`)**: tracked
  separately as upstream feedback to Hyperping. Not testable from this
  repo.
- **Performance benchmarks**: the change is small and the fast path
  (`initialize` already done) is a single lock acquire and attribute read.
  Risk is low; the plan does not request perf tests. A latent regression
  would surface as a wall-clock blowup in the existing suite.

### Risks the exclusions carry

- **Server message drift**: if Hyperping changes the rate-limit message to
  drop the word "rate limit" or change the JSON-RPC code, the classifier
  silently falls back to generic `HyperpingAPIError`. Mitigation: the
  classifier checks BOTH code and substring (plan §Strategy Gate), so a
  partial change still works; a total change would be caught the next time
  a user reports the bug. Adding a probe test would require a live server.
- **MCP spec churn**: a future MCP protocol version might change handshake
  semantics. Out of scope for this PR; the `_PROTOCOL_VERSION` constant
  pins the negotiated version and any drift will surface in the existing
  `test_initialize` (Test 14's transport-integrated path).
- **Server returns 429 + JSON-RPC `-32000` simultaneously**: undefined by
  the spec. Current implementation handles 429 first (HTTP-status branch
  runs before the JSON-RPC error branch), which is the desirable
  precedence. Not tested explicitly; would be a follow-up if observed.
