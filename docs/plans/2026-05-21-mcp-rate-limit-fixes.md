# MCP Rate-Limit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use trycycle-executing to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `HyperpingMcpClient` / `AsyncHyperpingMcpClient` survive Hyperping MCP server rate limits cleanly: detect JSON-RPC rate-limit errors as `HyperpingRateLimitError` with a parsed `retry_after`, stop wasting bucket slots after a rate-limit on `initialize`, close the TOCTOU race in lazy initialization, keep transient-retry semantics narrow, expose an explicit `ensure_initialized()` for startup health checks, and document the operational guidance users need to actually avoid the trap.

**Architecture:** Two-layer change, applied symmetrically to the sync transport (`src/hyperping/_mcp_transport.py`) and async transport (`src/hyperping/_async_mcp_transport.py`). The transport gains (1) JSON-RPC-error classification before the generic `HyperpingAPIError` fallback, (2) a monotonic-clock "initialize cool-off" deadline that short-circuits `call_tool` while still under the server's `Retry-After`, and (3) a double-checked initialization pattern that holds the lock across the entire handshake. The high-level clients (`src/hyperping/mcp_client.py`, `src/hyperping/_async_mcp_client.py`) expose `ensure_initialized()` that delegates to the transport. README gains an "MCP rate limits" subsection. No public API breakage: existing 429 path, existing `HyperpingRateLimitError` shape, and all existing exception types stay backward compatible. The added `retry_after` value and the new `_init_blocked_until` deadline are the only new state.

**Tech Stack:** Python 3.11+, `httpx` (sync `Client` + async `AsyncClient`), `pydantic` (only for `SecretStr` already in use), `threading.Lock` / `asyncio.Lock`, `time.monotonic()` (sync) and `asyncio.get_event_loop().time()` or `time.monotonic()` (async, monotonic is fine in both), `pytest` + `respx` for tests. No new runtime dependencies.

---

## Background, decisions, and what this plan is NOT doing

### What the server actually does (verified from user reproductions and Hyperping docs)

- Hyperping's MCP server is documented at `https://api.hyperping.io/v1/mcp` as "MCP over HTTP, stateless. No persistent connection." Rate limits documented: 300 req/min/key, shared with REST; REST docs add 800 req/hour/project with HTTP 429 + `Retry-After` + `ratelimit` header.
- The server enforces an **undocumented per-verb cap on `initialize`** (observed ~5/min) returned as **HTTP 200 + JSON-RPC `error.code = -32000`** with the message literally containing `Hyperping MCP rate limit exceeded for "initialize" (N/5 per minute). Retry after Xs.`. It does **not** return HTTP 429 for this case. Today the SDK's 429 branch never fires for it; control falls through to the generic JSON-RPC error path at `_mcp_transport.py:114-120` / `_async_mcp_transport.py:113-119` which raises a plain `HyperpingAPIError`, so the caller cannot `except HyperpingRateLimitError`.
- The MCP 2025-03-26 spec does NOT let a client skip `initialize`. The optional `Mcp-Session-Id` header binds *server-side* state to a connection; a fresh transport must always handshake. Hyperping's server is stateless, so there is no session id to capture or persist. **Therefore session-id reuse and on-disk session persistence are out of scope for this plan** (the user reviewed and dropped those ideas).

### What is in scope (locked decisions)

These five workstreams are landed in one cutover. They are independent only at the test level; the production code must ship together because A1 changes which exception type fires and A2/A4 rely on that classification.

1. **A1. JSON-RPC rate-limit detection.** In `_send_rpc`, when the response is HTTP 200 with a JSON-RPC `error` whose `code == -32000` and whose `message` matches the rate-limit pattern, raise `HyperpingRateLimitError(retry_after=..., status_code=resp.status_code)` with the original message preserved and the raw server `error` dict in `response_body`. Parse `Retry after (\d+)s` and `(\d+)/(\d+) per minute` out of the message.
2. **A2. Initialize cool-off latch.** When `HyperpingRateLimitError` is raised from inside `initialize()`, store `self._init_blocked_until = monotonic() + max(retry_after or 30, 1)`. Subsequent `call_tool` calls short-circuit before issuing any HTTP request: they raise `HyperpingRateLimitError` with a recomputed remaining `retry_after` (and a clear message identifying it as an `initialize` cool-off) until the deadline elapses; only then do we attempt `initialize` again. The latch is cleared by a successful initialize.
3. **A3. TOCTOU init race fix.** Replace the leak-pattern (lock to read the flag, unlock, then call `initialize()`) with a double-checked pattern: acquire the lock, re-check `_initialized`, do the handshake while still holding the lock, set the flag, release. This works correctly with `asyncio.Lock` across `await`, and avoids the current "two coroutines/threads both see False, both POST `initialize`" bug.
4. **A4. Narrow auto-retry, explicitly.** The existing `call_tool` retry loop only retries `HyperpingAPIError` with `status_code in {500, 502, 503, 504}`. After A1, a JSON-RPC rate-limit raises `HyperpingRateLimitError` whose `status_code` is 200 (the underlying HTTP code). Two regression tests pin this: rate-limit on `tools/call` is **not** retried by the transport, and the existing 5xx retry path still works. No production code change is strictly required for A4 beyond the tests, but the comment in `call_tool` is updated to say "transient HTTP server errors only; rate-limit errors are never retried at this layer."
5. **A5. `ensure_initialized()` on the high-level clients.** A trivial public method that calls `self._transport.initialize()` if not yet initialized (respecting the cool-off latch). Lets services that want a startup health check do `mcp.ensure_initialized()` and catch `HyperpingRateLimitError` early, instead of discovering it on the first business call. Symmetric on the async client (`await mcp.ensure_initialized()`).
6. **B. Documentation.** A new "MCP rate limits" subsection in `README.md` immediately after the existing "MCP Client" section. CHANGELOG entry under a new `[Unreleased]` heading describing user-visible behavior change.

### What is explicitly out of scope (do not implement)

- **`Mcp-Session-Id` capture/replay.** Server is stateless; no session id is returned and capturing one cannot let us skip `initialize`. The user has reviewed and excluded this.
- **On-disk session persistence.** Same reason; also has a non-trivial security cost.
- **Changing the MCP server's HTTP status code, cap value, or window semantics.** Server-side; tracked separately by the user as upstream feedback. Not this PR.
- **Adding a global asyncio "initialize" semaphore across processes.** Cannot help on the documented limit; out of scope.
- **Refactoring sync/async into a shared base class.** Tempting but introduces an architectural change beyond the rate-limit fix. The two files already mirror each other line-for-line; we maintain that parity by editing both. If a future change benefits from extraction, do it then.

### Why a single cutover

The user asked for "A1 + A2 + A3 + A4 + B + A5" as a single change. The pieces are mutually reinforcing: A1 without A2 still re-thrashes the initialize bucket; A2 without A1 has no typed error to latch on. A3 is a latent bug discovered during the audit and ships in the same PR because it is in the same lock and the same code path. A4 is one comment and two tests. A5 is six lines plus tests. B is documentation. The cutover is small, safe, and behind a typed exception that callers were already advised to catch.

### Backward compatibility contract

- `HyperpingRateLimitError` keeps its existing public attributes (`message`, `retry_after`, `status_code`, `response_body`, `request_id`). The `status_code` for the JSON-RPC rate-limit path is **200** (the HTTP layer), not 429. This is documented in the README and in the exception docstring. Existing callers using `except HyperpingRateLimitError as e: time.sleep(e.retry_after or 30)` are not regressed; they additionally gain coverage for the previously-silent 200/-32000 path.
- Existing tests that mock `respx.Response(429, ...)` continue to pass unchanged.
- `HyperpingMcpClient.__init__`, `close()`, `__enter__`, `__exit__`, and every existing tool method keep their signatures. `ensure_initialized()` is purely additive.
- `McpTransport.__init__` signature is unchanged. The added `_init_blocked_until` is a private attribute.

### Invariants the implementation MUST preserve

1. **Single-flight `initialize` per transport instance.** After A3, no two callers can race a duplicate `initialize`. Verified by a concurrency test that fires N concurrent `call_tool` calls into a transport whose `respx` mock counts how many `initialize` requests it sees: must be exactly 1.
2. **No silent rate-limit.** Any rate-limit signal from the server (HTTP 429 OR HTTP 200 + JSON-RPC -32000 with the documented message) MUST raise `HyperpingRateLimitError`. Verified by a JSON-RPC rate-limit test and the existing 429 test.
3. **`Retry-After` is honored.** Parsed from the HTTP `Retry-After` header on 429, and from the JSON-RPC `error.message` on 200/-32000. Verified by parametrized tests covering integer, missing, malformed, and HTTP-date inputs.
4. **No bucket thrashing while latched.** While `_init_blocked_until > monotonic()`, subsequent `call_tool` invocations issue zero HTTP requests. Verified by a `respx` test that counts `route.call_count == 0` after the latch trips.
5. **Latch is cleared on successful re-init.** After the deadline elapses, the next `call_tool` triggers exactly one new `initialize`. Verified by advancing a monkeypatched monotonic clock and re-mocking the initialize response.
6. **Transient HTTP retries do not catch rate-limit.** `call_tool` retry loop only retries the four documented 5xx codes; a `HyperpingRateLimitError` (whether 429 or 200) propagates immediately without re-invoking the request. Verified by a test that mocks a 429 and asserts the route was called exactly once.
7. **Sync and async parity.** Every test and behavior added in the sync transport has a mirror in the async transport.

---

## File Structure

The change touches a tight, focused set of files. No new files are created in production code. One new test module per transport for the rate-limit-and-init-cooloff behaviors, to keep diffs reviewable. Documentation and changelog updates round it out.

**Production code (modify):**
- `src/hyperping/_mcp_transport.py` — JSON-RPC rate-limit classification in `_send_rpc`; init cool-off latch state and short-circuit in `call_tool` / `initialize`; double-checked init in `call_tool` and `initialize`; comment on `call_tool` retry block; add `time` import already present.
- `src/hyperping/_async_mcp_transport.py` — Mirror of the sync change with `asyncio.Lock` held across the awaitable initialize. Uses `time.monotonic()` for the cool-off deadline (process-wide, event-loop-independent).
- `src/hyperping/mcp_client.py` — Add `ensure_initialized()` method.
- `src/hyperping/_async_mcp_client.py` — Add `async def ensure_initialized()` method.

**Tests (add new + extend):**
- `tests/unit/test_mcp_transport.py` — Extend with: JSON-RPC -32000 rate-limit classification (4 cases: with Retry-After, without, malformed, with N/5 per minute); cool-off latch trips on initialize failure; latch short-circuits subsequent `call_tool` with zero HTTP requests; latch clears after monotonic deadline; concurrent first-call de-duplication (TOCTOU regression); `call_tool` does NOT retry rate-limit; comment-only test ensuring 5xx retry path is preserved.
- `tests/unit/test_async_mcp_transport.py` — Mirror of the above for async, including a concurrent-coroutines test using `asyncio.gather`.
- `tests/unit/test_mcp_client.py` — `ensure_initialized()` calls through to transport and propagates `HyperpingRateLimitError`.
- `tests/unit/test_async_mcp_client.py` — Async mirror.

**Documentation (modify):**
- `README.md` — New "MCP rate limits" subsection immediately after the existing "MCP Client" subsection (around line 190). Mentions: long-lived client per process, undocumented `initialize` cap, the typed exception with `.retry_after`, `ensure_initialized()` for startup checks.
- `CHANGELOG.md` — New `[Unreleased]` heading at the top with `### Added` and `### Fixed` entries.

**Files NOT modified (informative):**
- `src/hyperping/exceptions.py` — `HyperpingRateLimitError` is already shaped correctly. No change needed.
- `src/hyperping/__init__.py` — `HyperpingRateLimitError` and the MCP clients are already exported.
- `src/hyperping/_version.py` — Version bump and CHANGELOG release-line are reserved for a separate release PR; this plan adds an `[Unreleased]` heading instead, matching the project's prior pattern.

---

## Strategy Gate (decision record)

**Is this the right problem to solve?** Yes. The user's bug report is real, reproducible, and not addressable from the SDK by avoiding `initialize` (server is stateless; spec mandates the handshake). The pragmatic value is in (a) detecting the rate-limit signal correctly, (b) not making it worse by thrashing, and (c) documenting the constraint. Everything else requires server changes the user is filing separately.

**Is the proposed architecture right?** Yes, after eliminating alternatives:
- *Alternative: shared session id across processes.* Server is documented stateless; no session id is issued. Even if it were, the MCP spec does not let a client skip `initialize` for a fresh transport. Rejected.
- *Alternative: process-wide singleton `HyperpingMcpClient`.* Would help in one process, doesn't help across processes (cron + watchdog + dev CLI). We document the guidance instead of trying to enforce singletons (which would surprise users).
- *Alternative: silently swallow the first rate-limit and retry with backoff inside `call_tool`.* Surfaces the same symptom (long mysterious blocking) without the typed exception users need to make scheduling decisions. Rejected.
- *Alternative: ship a refactor that unifies sync/async transports.* Out of scope; revisit after this lands.
- *Alternative: detect the rate-limit message only by substring `"rate limit exceeded"` without checking JSON-RPC code.* Fragile against future message changes. We check **both** `code == -32000` AND a regex match on `message`, then prefer the documented format but also accept the substring fallback. Rationale included in the code comment.

**Are there assumptions baked in?** Two, both documented:
1. The JSON-RPC error code for the rate-limit case is `-32000` (server-defined error range). If the server changes this, the substring check on `message` is the safety net. We do NOT match purely on substring without the code check, because `-32000` is the documented "server-defined" range and matching by message alone would also catch e.g. localized future translations or unrelated errors with the word "rate". The code-plus-message double check is intentional.
2. `time.monotonic()` is the right clock for the cool-off latch in both sync and async. It is, because we never compare across processes or persist it.

**Ready for task decomposition.** Yes. Architectural direction is stable.

---

## Implementation notes the executor must read

### Regex for parsing the rate-limit message

A single compiled regex covers the observed message format. Define it once at module scope in both transports:

```python
import re

_MCP_RATE_LIMIT_MARKER = "rate limit"
_MCP_RATE_LIMIT_RETRY_AFTER_RE = re.compile(r"[Rr]etry after\s+(\d+)\s*s")
```

The check is:

```python
if (
    isinstance(err, dict)
    and err.get("code") == -32000
    and isinstance(err.get("message"), str)
    and _MCP_RATE_LIMIT_MARKER in err["message"].lower()
):
    retry_after: int | None = None
    m = _MCP_RATE_LIMIT_RETRY_AFTER_RE.search(err["message"])
    if m:
        try:
            retry_after = int(m.group(1))
        except ValueError:  # defensive; regex guarantees digits
            retry_after = None
    raise HyperpingRateLimitError(
        err["message"],
        retry_after=retry_after,
        status_code=resp.status_code,
        response_body=err,
    )
```

Placement: inside `_send_rpc`, immediately after `data = resp.json()`, before the existing generic `if "error" in data:` block. That keeps the generic JSON-RPC error path intact for every other `-32xxx` code.

### Cool-off latch contract

Add to `__init__`:

```python
self._init_blocked_until: float = 0.0  # monotonic seconds; 0.0 means "no cool-off"
```

In `initialize()`, on success after `self._send_rpc("notifications/initialized", is_notification=True)`, set `self._init_blocked_until = 0.0` (clears any prior latch). Wrap the actual handshake calls in try/except so a `HyperpingRateLimitError` arms the latch:

```python
try:
    result = self._send_rpc(
        "initialize",
        {"protocolVersion": _PROTOCOL_VERSION, "capabilities": {},
         "clientInfo": {"name": "hyperping-python", "version": __version__}},
    )
    self._send_rpc("notifications/initialized", is_notification=True)
except HyperpingRateLimitError as exc:
    wait = exc.retry_after if exc.retry_after and exc.retry_after > 0 else 30
    self._init_blocked_until = time.monotonic() + wait
    raise
```

In `call_tool()`, before any HTTP work, after acquiring the double-checked init lock, check the latch:

```python
remaining = self._init_blocked_until - time.monotonic()
if remaining > 0:
    raise HyperpingRateLimitError(
        "MCP initialize rate limit cool-off active; retry later",
        retry_after=int(remaining) + 1,
        status_code=200,
    )
```

Use `int(remaining) + 1` so the advertised value is always >= 1 second and never reports `0` while still blocked. Place this check **after** the double-checked init lock acquisition, **before** the loop. Rationale: a latched transport whose handshake already failed must not silently issue a `tools/call` request; we treat it as "still rate-limited."

### Double-checked init pattern (sync)

Replace the existing TOCTOU pattern in `call_tool`:

```python
# Before (BUG):
with self._lock:
    needs_init = not self._initialized
if needs_init:
    self.initialize()

# After (FIX):
self._ensure_initialized_locked()
```

Where `_ensure_initialized_locked` is a small private helper on the transport:

```python
def _ensure_initialized_locked(self) -> None:
    if self._initialized:
        return
    with self._lock:
        if self._initialized:
            return
        # Latch check while holding lock; raises if cool-off active.
        remaining = self._init_blocked_until - time.monotonic()
        if remaining > 0:
            raise HyperpingRateLimitError(
                "MCP initialize rate limit cool-off active; retry later",
                retry_after=int(remaining) + 1,
                status_code=200,
            )
        self._initialize_locked()  # performs handshake, sets _initialized
```

Splitting `initialize()` into a thin public method that takes the lock and a `_initialize_locked()` that assumes the lock is held keeps the public method idempotent and re-entrant for `ensure_initialized()`.

```python
def initialize(self) -> dict[str, Any]:
    with self._lock:
        if self._initialized:
            # Idempotent: return the cached server result if we still have it,
            # else an empty dict (the only reason to re-call is informational).
            return self._init_result
        return self._initialize_locked()

def _initialize_locked(self) -> dict[str, Any]:
    # Assumes self._lock is held.
    try:
        result = self._send_rpc(...)
        self._send_rpc("notifications/initialized", is_notification=True)
    except HyperpingRateLimitError as exc:
        wait = exc.retry_after if exc.retry_after and exc.retry_after > 0 else 30
        self._init_blocked_until = time.monotonic() + wait
        raise
    self._initialized = True
    self._init_blocked_until = 0.0
    self._init_result = result.get("result", {}) if result else {}
    return self._init_result
```

Add `self._init_result: dict[str, Any] = {}` in `__init__`.

### Double-checked init pattern (async)

Mirror exactly with `async with self._lock:` held across the awaitable handshake. `asyncio.Lock` is safe across `await`. Use the same `time.monotonic()` clock.

```python
async def _ensure_initialized_locked(self) -> None:
    if self._initialized:
        return
    async with self._lock:
        if self._initialized:
            return
        remaining = self._init_blocked_until - time.monotonic()
        if remaining > 0:
            raise HyperpingRateLimitError(
                "MCP initialize rate limit cool-off active; retry later",
                retry_after=int(remaining) + 1,
                status_code=200,
            )
        await self._initialize_locked()
```

Also import `time` at the top of `_async_mcp_transport.py` (currently not imported).

### Interaction with `_next_id` lock

`_next_id` already takes `self._lock` for the request-id counter. The new `_ensure_initialized_locked` also acquires it. There is no deadlock because:
- `_ensure_initialized_locked` runs **before** any `_send_rpc` call in `call_tool`, so the lock is released before `_send_rpc` is invoked. `_send_rpc` re-acquires the lock briefly inside `_next_id`. No nested acquisition.
- `_initialize_locked` calls `_send_rpc`, which calls `_next_id`, which re-acquires `self._lock`. **This is a re-entrancy issue with `threading.Lock` (non-reentrant).**

**Mitigation:** Use `threading.RLock` instead of `threading.Lock` in the sync transport. `asyncio.Lock` is not reentrant either, so for the async transport, restructure `_initialize_locked` to NOT call `_next_id` under the lock — instead, increment the counter directly inside `_initialize_locked` while the lock is already held, by inlining the counter logic. Concretely, in async:

```python
async def _initialize_locked(self) -> dict[str, Any]:
    # self._lock is held by caller. Increment the request id directly
    # rather than awaiting _next_id which would re-acquire the lock.
    self._request_id += 1
    init_id = self._request_id
    # Build and POST the initialize payload inline...
```

This is ugly but correct. The simpler alternative is to use a separate lock for the request id and a separate lock for initialization state. **Adopt that:** add `self._init_lock` (`threading.Lock` / `asyncio.Lock`) for initialization, and keep the existing `self._lock` solely for the request-id counter. This keeps `_send_rpc` callable from within the init critical section without re-entrancy.

**Final lock structure (adopted):**
- `self._id_lock` — protects `self._request_id` counter only. Renamed from `_lock` if convenient; the executor should rename for clarity but keep the rename localized. To minimize diff, the executor MAY keep `self._lock` for the id counter and introduce `self._init_lock` for initialization. This is the recommended minimal-diff path.

The plan locks in: **two locks, one for the id counter (existing `self._lock`), one for initialization (`self._init_lock`).** Use `threading.Lock` and `asyncio.Lock` respectively. No RLock; we prefer non-reentrant locks for clarity.

### `ensure_initialized()` on high-level clients

Trivial delegation. On sync `HyperpingMcpClient`:

```python
def ensure_initialized(self) -> None:
    """Perform the MCP handshake now if it hasn't happened yet.

    Useful for startup health checks: call this once on boot and catch
    :class:`HyperpingRateLimitError` so you can decide whether to start
    the rest of your service. Subsequent tool calls reuse the handshake.

    Raises:
        HyperpingRateLimitError: If the server rate-limits ``initialize``,
            either via HTTP 429 or via the JSON-RPC ``-32000`` rate-limit
            payload. Inspect ``.retry_after`` to back off.
        HyperpingAuthError: If the API key is invalid.
    """
    self._transport.initialize()
```

On async `AsyncHyperpingMcpClient`:

```python
async def ensure_initialized(self) -> None:
    """Async counterpart to :meth:`HyperpingMcpClient.ensure_initialized`."""
    await self._transport.initialize()
```

Both rely on `initialize()` being idempotent (no-op if already initialized) after the A3 refactor. Tests cover idempotency and rate-limit propagation.

### Documentation copy (final)

The new README subsection text is fixed in this plan (do not paraphrase):

````markdown
### MCP rate limits and connection lifecycle

The Hyperping MCP server (`https://api.hyperping.io/v1/mcp`) is stateless over HTTP
and rate-limits per API key. The publicly documented limit is 300 requests per
minute shared with the REST API, but the server also enforces a separate, low cap
on the `initialize` handshake (observed around 5/minute). Because every new
`HyperpingMcpClient` instance must perform the MCP `initialize` handshake on its
first call, instantiating the client in a hot path or running several short-lived
processes against one key will trip this cap.

Operational guidance:

- **Create one `HyperpingMcpClient` per process and reuse it.** Do not instantiate
  it inside a loop. The first call performs the handshake; subsequent calls reuse
  it for the life of the client.
- **Catch `HyperpingRateLimitError` and honour `retry_after`.** Rate-limit signals
  arrive two ways: as HTTP 429 (with a standard `Retry-After` header) and as a
  JSON-RPC server error (`code: -32000`, HTTP 200) on `initialize`. Both surface as
  `HyperpingRateLimitError` with `retry_after` parsed from whichever signal was
  used. The `status_code` attribute is `429` or `200` respectively.
- **Use `ensure_initialized()` for startup health checks.** Calling it once on
  service boot lets you fail fast if the key is already at the `initialize` cap,
  instead of failing on the first business call.
- **Several workloads on one key collide on the `initialize` cap.** A weekly cron,
  a watchdog daemon, and a developer running the CLI cannot all warm up the same
  API key inside one minute. Use one long-lived process per workload, or separate
  API keys per workload if your plan allows.
- **After a rate-limit on `initialize`, the SDK latches a cool-off** so that
  subsequent `call_tool` invocations on the same client fail fast with
  `HyperpingRateLimitError` (no extra HTTP traffic) until `retry_after` elapses.
  This prevents accidentally burning more slots from the bucket.

```python
from hyperping import HyperpingMcpClient, HyperpingRateLimitError

mcp = HyperpingMcpClient(api_key="sk_...")
try:
    mcp.ensure_initialized()
except HyperpingRateLimitError as e:
    print(f"MCP cold-start rate-limited; retry in {e.retry_after}s")
    raise

summary = mcp.get_status_summary()
```
````

The CHANGELOG entry text (final):

```markdown
## [Unreleased]

### Added

- `ensure_initialized()` on `HyperpingMcpClient` and `AsyncHyperpingMcpClient` for
  startup health checks. Performs the MCP handshake now if it hasn't happened yet
  and raises `HyperpingRateLimitError` if the server's `initialize` cap is hit.
- New "MCP rate limits and connection lifecycle" section in README documenting
  Hyperping's stateless MCP server, the undocumented `initialize` cap, and the
  recommended client lifetime per process.

### Fixed

- MCP rate-limit errors that the server returns as HTTP 200 with JSON-RPC
  `error.code = -32000` (notably the `initialize` per-minute cap) are now
  classified as `HyperpingRateLimitError` with `retry_after` parsed from the
  message, instead of a generic `HyperpingAPIError`. Existing HTTP 429 handling is
  unchanged.
- After a rate-limit on `initialize`, the MCP transport latches a cool-off so
  subsequent `call_tool` invocations short-circuit with `HyperpingRateLimitError`
  until the advertised `retry_after` elapses, instead of issuing further HTTP
  requests that would burn more slots from the bucket.
- TOCTOU race in lazy `initialize` where two concurrent first calls on the same
  `HyperpingMcpClient` could each POST `initialize`. The handshake is now
  performed under a dedicated lock with a double-checked flag.
```

---

## Completion Standard

Done means:

- The full project test suite (`pytest`) passes, including the new tests, with `--cov-fail-under=85` still green.
- `ruff check src tests` is clean.
- `mypy --strict src` is clean (the codebase is configured for strict mypy via `pyproject.toml`).
- No public symbol has been removed or renamed. `ensure_initialized` is the only addition. `HyperpingRateLimitError` shape is unchanged.
- The README and CHANGELOG changes render correctly (manual visual is fine; no docs site).
- The user's exact paste-ready repro snippet (six fresh-client iterations under rate-limit) now raises `HyperpingRateLimitError` on the first hit and, on a sixth iteration that creates yet another client, raises the same typed exception immediately (because the latch is per-transport-instance, the new client will hit the server cap on its own `initialize`, raise typed, and latch its own instance). The behavior improvement is: each instance fails fast and predictably with `.retry_after`. The user can build retry logic around that.

---

## Task Breakdown

Each task is a small, committable unit. Tasks are ordered for safe incremental commits. Run the full project suite after each commit; do not weaken tests.

### Task 1: Add lock-separation and shared regex constants

**Files:**
- Modify: `src/hyperping/_mcp_transport.py:23-55`
- Modify: `src/hyperping/_async_mcp_transport.py:22-54`

- [ ] **Step 1: Identify or write the failing test**

This task is a structural refactor that does not change observable behavior. The "failing test" is the existing transport suite which must continue to pass after the lock split.

```bash
pytest tests/unit/test_mcp_transport.py tests/unit/test_async_mcp_transport.py -v
```

Expected before refactor: all PASS (no behavior change yet). This is the regression baseline.

- [ ] **Step 2: Run the suite to confirm baseline green**

Run: `pytest tests/unit/test_mcp_transport.py tests/unit/test_async_mcp_transport.py -v`
Expected: all PASS.

- [ ] **Step 3: Apply the refactor**

In `src/hyperping/_mcp_transport.py`:
- Add the module-level constants after `_PROTOCOL_VERSION`:

```python
import re

_MCP_RATE_LIMIT_MARKER = "rate limit"
_MCP_RATE_LIMIT_RETRY_AFTER_RE = re.compile(r"[Rr]etry after\s+(\d+)\s*s")
```

- In `McpTransport.__init__`, after `self._lock = threading.Lock()`, add:

```python
self._init_lock = threading.Lock()
self._init_blocked_until: float = 0.0
self._init_result: dict[str, Any] = {}
```

In `src/hyperping/_async_mcp_transport.py`:
- Add `import re` and `import time` at the top alongside the existing imports.
- Add the same two module-level constants after `_PROTOCOL_VERSION`.
- In `AsyncMcpTransport.__init__`, after `self._lock = asyncio.Lock()`, add:

```python
self._init_lock = asyncio.Lock()
self._init_blocked_until: float = 0.0
self._init_result: dict[str, Any] = {}
```

- [ ] **Step 4: Run the suite to confirm no regression**

Run: `pytest -q`
Expected: all PASS, coverage >= 85%.

- [ ] **Step 5: Refactor and verify**

Inspect both files for symmetry: identical constants, identical attribute names. Re-run `pytest -q` and `ruff check src tests`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_mcp_transport.py src/hyperping/_async_mcp_transport.py
git commit -m "refactor(mcp): split init lock from request-id lock, add cool-off scaffolding"
```

---

### Task 2: JSON-RPC rate-limit classification in sync `_send_rpc` (A1)

**Files:**
- Modify: `src/hyperping/_mcp_transport.py:113-121`
- Test: `tests/unit/test_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Add these tests at the bottom of `tests/unit/test_mcp_transport.py`:

```python
@respx.mock
def test_jsonrpc_rate_limit_classified_as_rate_limit_error():
    """200 + JSON-RPC code=-32000 with rate-limit message -> HyperpingRateLimitError."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": 'Hyperping MCP rate limit exceeded for "initialize" '
                               "(5/5 per minute). Retry after 32s.",
                },
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True  # bypass handshake to exercise _send_rpc directly
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 32
    assert exc_info.value.status_code == 200
    assert "rate limit" in exc_info.value.message.lower()
    assert exc_info.value.response_body["code"] == -32000
    transport.close()


@respx.mock
def test_jsonrpc_rate_limit_without_retry_after_seconds():
    """JSON-RPC rate-limit message without parseable seconds -> retry_after=None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Hyperping MCP rate limit exceeded. Try again later.",
                },
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after is None
    transport.close()


@respx.mock
def test_jsonrpc_non_ratelimit_error_still_generic_api_error():
    """Non -32000 JSON-RPC error continues to raise plain HyperpingAPIError."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Method not found"},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        transport.call_tool("nonexistent_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    transport.close()


@respx.mock
def test_jsonrpc_32000_but_not_ratelimit_message_is_generic():
    """code=-32000 without 'rate limit' substring stays a generic HyperpingAPIError."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": "Some other server error"},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        transport.call_tool("some_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    transport.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mcp_transport.py -v -k "jsonrpc_rate_limit or jsonrpc_non_ratelimit or jsonrpc_32000"`
Expected: 2-3 FAIL (the rate-limit ones; the negative test that expects a generic error may already pass). Confirm the failing tests fail with `HyperpingAPIError` raised instead of `HyperpingRateLimitError`.

- [ ] **Step 3: Implement the classification in `_send_rpc`**

In `src/hyperping/_mcp_transport.py`, modify `_send_rpc` so the JSON-RPC error handling section becomes:

```python
data = resp.json()
if "error" in data:
    err = data["error"]
    if (
        isinstance(err, dict)
        and err.get("code") == -32000
        and isinstance(err.get("message"), str)
        and _MCP_RATE_LIMIT_MARKER in err["message"].lower()
    ):
        retry_after: int | None = None
        match = _MCP_RATE_LIMIT_RETRY_AFTER_RE.search(err["message"])
        if match:
            try:
                retry_after = int(match.group(1))
            except ValueError:
                retry_after = None
        raise HyperpingRateLimitError(
            err["message"],
            retry_after=retry_after,
            status_code=resp.status_code,
            response_body=err,
        )
    raise HyperpingAPIError(
        f"MCP error {err.get('code', '?')}: {err.get('message', 'unknown')}",
        status_code=resp.status_code,
        response_body=err,
    )
return data  # type: ignore[no-any-return]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_mcp_transport.py -v`
Expected: all PASS, including the four new tests.

- [ ] **Step 5: Refactor and verify**

Inspect: the `_send_rpc` change is the only edit to the sync transport in this task. Re-run `pytest -q` and `ruff check src tests`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_mcp_transport.py tests/unit/test_mcp_transport.py
git commit -m "feat(mcp): classify JSON-RPC -32000 rate-limit as HyperpingRateLimitError (sync)"
```

---

### Task 3: JSON-RPC rate-limit classification in async `_send_rpc` (A1 mirror)

**Files:**
- Modify: `src/hyperping/_async_mcp_transport.py:112-120`
- Test: `tests/unit/test_async_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Add the async mirrors of the four tests from Task 2 at the bottom of `tests/unit/test_async_mcp_transport.py`. Use `async def` and `await transport.call_tool(...)`. Same response bodies; same assertions on `exc_info.value.retry_after`, `.status_code`, `.message`, `.response_body`.

```python
@respx.mock
async def test_jsonrpc_rate_limit_classified_as_rate_limit_error():
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": 'Hyperping MCP rate limit exceeded for "initialize" '
                               "(5/5 per minute). Retry after 32s.",
                },
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 32
    assert exc_info.value.status_code == 200
    await transport.close()
```

Repeat for the three other cases. Mirror exactly.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_async_mcp_transport.py -v -k "jsonrpc"`
Expected: FAIL.

- [ ] **Step 3: Implement in async `_send_rpc`**

Apply the same edit as Task 2 to `src/hyperping/_async_mcp_transport.py`, in the JSON-RPC error block (lines 112-120). Identical logic. No `await`s introduced inside the new branch.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_async_mcp_transport.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor and verify**

Compare the sync and async `_send_rpc` JSON-RPC blocks line by line — they must be structurally identical. Run: `pytest -q && ruff check src tests`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_async_mcp_transport.py tests/unit/test_async_mcp_transport.py
git commit -m "feat(mcp): classify JSON-RPC -32000 rate-limit as HyperpingRateLimitError (async)"
```

---

### Task 4: Sync TOCTOU init fix and idempotent `initialize()` (A3)

**Files:**
- Modify: `src/hyperping/_mcp_transport.py` (`initialize`, `call_tool`)
- Test: `tests/unit/test_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_mcp_transport.py`:

```python
import threading


@respx.mock
def test_concurrent_first_call_single_initialize():
    """Two concurrent first-callers must trigger exactly one initialize POST."""
    # respx counts calls per route; one mock for initialize, one for notification,
    # one tool reply that can be served twice.
    init_route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
            ),
            httpx.Response(202),  # notifications/initialized
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
                },
            ),
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
                },
            ),
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    barrier = threading.Barrier(2)
    results = []

    def hit():
        barrier.wait()
        results.append(transport.call_tool("some_tool"))

    t1 = threading.Thread(target=hit)
    t2 = threading.Thread(target=hit)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Expected: exactly 4 POSTs total — one initialize, one notification, two tool calls.
    assert init_route.call_count == 4
    assert results == [{"ok": True}, {"ok": True}]
    transport.close()


@respx.mock
def test_initialize_is_idempotent():
    """Calling initialize() twice does not POST twice."""
    route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
            ),
            httpx.Response(202),
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport.initialize()
    transport.initialize()  # second call must be a no-op
    assert route.call_count == 2  # initialize + notification, not 4
    transport.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mcp_transport.py -v -k "concurrent_first_call or initialize_is_idempotent"`
Expected: at minimum `test_initialize_is_idempotent` FAILs (current code POSTs twice). The concurrent test may be flaky on current code; document the observed failure mode.

- [ ] **Step 3: Implement the double-checked init**

Refactor `initialize()` and `call_tool()` in `src/hyperping/_mcp_transport.py`:

```python
def initialize(self) -> dict[str, Any]:
    """Perform MCP handshake if not yet performed. Idempotent and thread-safe."""
    with self._init_lock:
        if self._initialized:
            return self._init_result
        return self._initialize_locked()

def _initialize_locked(self) -> dict[str, Any]:
    """Perform the handshake. Assumes self._init_lock is held."""
    remaining = self._init_blocked_until - time.monotonic()
    if remaining > 0:
        raise HyperpingRateLimitError(
            "MCP initialize rate limit cool-off active; retry later",
            retry_after=int(remaining) + 1,
            status_code=200,
        )
    try:
        result = self._send_rpc(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hyperping-python", "version": __version__},
            },
        )
        self._send_rpc("notifications/initialized", is_notification=True)
    except HyperpingRateLimitError as exc:
        wait = exc.retry_after if exc.retry_after and exc.retry_after > 0 else 30
        self._init_blocked_until = time.monotonic() + wait
        raise
    self._init_result = result.get("result", {}) if result else {}
    self._initialized = True
    self._init_blocked_until = 0.0
    return self._init_result
```

In `call_tool`, replace the TOCTOU block (lines 151-154) with:

```python
self.initialize()
```

That single call is now safe to invoke unconditionally because `initialize()` is idempotent and acquires `_init_lock` internally. The fast path (already initialized) does a single lock acquire and an attribute read — measurably cheap.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_mcp_transport.py -v`
Expected: all PASS, including the new two.

- [ ] **Step 5: Refactor and verify**

Run the full suite: `pytest -q`. Verify coverage hasn't dropped below 85%. Run `ruff check src tests` and `mypy --strict src`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_mcp_transport.py tests/unit/test_mcp_transport.py
git commit -m "fix(mcp): close TOCTOU race in lazy initialize; make initialize() idempotent (sync)"
```

---

### Task 5: Async TOCTOU init fix and idempotent `initialize()` (A3 mirror)

**Files:**
- Modify: `src/hyperping/_async_mcp_transport.py`
- Test: `tests/unit/test_async_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_async_mcp_transport.py`:

```python
import asyncio


@respx.mock
async def test_concurrent_first_call_single_initialize():
    respx.post(MCP_URL).mock(
        side_effect=[
            INIT_RESPONSE,
            NOTIFICATION_ACCEPTED,
            _tool_response({"ok": True}, req_id=2),
            _tool_response({"ok": True}, req_id=3),
        ],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    r1, r2 = await asyncio.gather(
        transport.call_tool("some_tool"),
        transport.call_tool("some_tool"),
    )
    assert r1 == {"ok": True}
    assert r2 == {"ok": True}
    await transport.close()


@respx.mock
async def test_initialize_is_idempotent():
    route = respx.post(MCP_URL).mock(
        side_effect=[INIT_RESPONSE, NOTIFICATION_ACCEPTED],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    await transport.initialize()
    await transport.initialize()
    assert route.call_count == 2
    await transport.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_async_mcp_transport.py -v -k "concurrent_first_call or initialize_is_idempotent"`
Expected: FAIL.

- [ ] **Step 3: Implement double-checked async init**

Mirror Task 4 in `src/hyperping/_async_mcp_transport.py`:

```python
async def initialize(self) -> dict[str, Any]:
    """Async idempotent and concurrency-safe MCP handshake."""
    async with self._init_lock:
        if self._initialized:
            return self._init_result
        return await self._initialize_locked()

async def _initialize_locked(self) -> dict[str, Any]:
    remaining = self._init_blocked_until - time.monotonic()
    if remaining > 0:
        raise HyperpingRateLimitError(
            "MCP initialize rate limit cool-off active; retry later",
            retry_after=int(remaining) + 1,
            status_code=200,
        )
    try:
        result = await self._send_rpc(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hyperping-python", "version": __version__},
            },
        )
        await self._send_rpc("notifications/initialized", is_notification=True)
    except HyperpingRateLimitError as exc:
        wait = exc.retry_after if exc.retry_after and exc.retry_after > 0 else 30
        self._init_blocked_until = time.monotonic() + wait
        raise
    self._init_result = result.get("result", {}) if result else {}
    self._initialized = True
    self._init_blocked_until = 0.0
    return self._init_result
```

Replace the TOCTOU block in `call_tool` (lines 150-153) with `await self.initialize()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_async_mcp_transport.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor and verify**

`pytest -q && ruff check src tests && mypy --strict src`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_async_mcp_transport.py tests/unit/test_async_mcp_transport.py
git commit -m "fix(mcp): close TOCTOU race in lazy initialize; make initialize() idempotent (async)"
```

---

### Task 6: Initialize cool-off latch behavior — sync (A2)

**Files:**
- Modify: `src/hyperping/_mcp_transport.py` (`call_tool`)
- Test: `tests/unit/test_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_mcp_transport.py`:

```python
@respx.mock
def test_initialize_rate_limit_latches_cooloff(monkeypatch):
    """After a rate-limited initialize, further call_tool calls short-circuit."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
    )

    rl_response = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32000,
                "message": 'Hyperping MCP rate limit exceeded for "initialize" '
                           "(5/5 per minute). Retry after 30s.",
            },
        },
    )
    route = respx.post(MCP_URL).mock(return_value=rl_response)

    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")  # triggers initialize, gets latched
    assert route.call_count == 1  # only the initialize POST was made

    # Subsequent call_tool must not hit the network.
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert route.call_count == 1  # still 1 — no further HTTP requests
    assert exc_info.value.retry_after is not None
    assert exc_info.value.retry_after >= 1

    transport.close()


@respx.mock
def test_initialize_cooloff_clears_after_deadline(monkeypatch):
    """Once the cool-off elapses, initialize is attempted again."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
    )

    rl_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32000,
            "message": "Hyperping MCP rate limit exceeded. Retry after 10s.",
        },
    }
    ok_init = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
    )
    ok_tool = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
        },
    )

    respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(200, json=rl_msg),  # first initialize: rate-limited
            ok_init,                            # second initialize: success
            httpx.Response(202),                # notifications/initialized
            ok_tool,                            # tool call
        ]
    )

    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")

    # Still latched.
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")

    # Advance past the deadline.
    fake_now["t"] += 100.0
    result = transport.call_tool("some_tool")
    assert result == {"ok": True}
    transport.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mcp_transport.py -v -k "latches_cooloff or cooloff_clears"`
Expected: FAIL. The first test fails because today the second `call_tool` would re-attempt `initialize` and POST again.

- [ ] **Step 3: Implement the short-circuit in `call_tool`**

In `src/hyperping/_mcp_transport.py`, the `call_tool` block now reads:

```python
def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    self.initialize()  # idempotent, latch-aware, raises HyperpingRateLimitError
                       # if init is rate-limited or still under cool-off
    ...
```

Because `_initialize_locked` already checks `_init_blocked_until` and raises before any HTTP work, and `initialize()` is now idempotent, no further change is needed inside `call_tool`. The two new tests must pass.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_mcp_transport.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor and verify**

`pytest -q && ruff check src tests && mypy --strict src`. Expected: clean. Confirm route.call_count assertions are exact, not >=, to nail down the no-HTTP-during-cooloff invariant.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_mcp_transport.py tests/unit/test_mcp_transport.py
git commit -m "feat(mcp): latch initialize cool-off after rate-limit to stop bucket thrashing (sync)"
```

---

### Task 7: Initialize cool-off latch behavior — async (A2 mirror)

**Files:**
- Modify: `src/hyperping/_async_mcp_transport.py`
- Test: `tests/unit/test_async_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Mirror Task 6 tests in `tests/unit/test_async_mcp_transport.py`. Monkeypatch path: `"hyperping._async_mcp_transport.time.monotonic"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_async_mcp_transport.py -v -k "latches_cooloff or cooloff_clears"`
Expected: FAIL.

- [ ] **Step 3: Implement (already done by Task 5's `_initialize_locked`)**

The async cool-off behavior is already implemented in Task 5's `_initialize_locked`. Verify by running the new tests. Replace the `call_tool` TOCTOU block (already done) with `await self.initialize()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_async_mcp_transport.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor and verify**

`pytest -q && ruff check src tests && mypy --strict src`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_async_mcp_transport.py tests/unit/test_async_mcp_transport.py
git commit -m "feat(mcp): latch initialize cool-off after rate-limit to stop bucket thrashing (async)"
```

---

### Task 8: Pin "transient retry does not catch rate-limit" with explicit tests (A4)

**Files:**
- Modify: `src/hyperping/_mcp_transport.py` (comment only)
- Modify: `src/hyperping/_async_mcp_transport.py` (comment only)
- Test: `tests/unit/test_mcp_transport.py`
- Test: `tests/unit/test_async_mcp_transport.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_mcp_transport.py`:

```python
@respx.mock
def test_rate_limit_is_not_retried_by_call_tool():
    """call_tool's transient retry loop must NOT retry HyperpingRateLimitError."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429, text="Rate limited", headers={"retry-after": "5"},
        ),
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=3)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    assert route.call_count == 1  # NOT 4 — no retry attempts
    transport.close()


@respx.mock
def test_jsonrpc_rate_limit_is_not_retried_by_call_tool():
    """JSON-RPC -32000 rate-limit (HTTP 200) must NOT trigger retries either."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Hyperping MCP rate limit exceeded. Retry after 5s.",
                },
            },
        ),
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=3)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    assert route.call_count == 1
    transport.close()
```

Mirror both in `tests/unit/test_async_mcp_transport.py`.

- [ ] **Step 2: Run tests to verify they pass (current behavior already correct)**

Run: `pytest tests/unit/test_mcp_transport.py tests/unit/test_async_mcp_transport.py -v -k "not_retried"`
Expected: PASS already (the existing `except HyperpingAPIError as exc:` only retries 5xx; `HyperpingRateLimitError` is a subclass of `HyperpingAPIError` but its `status_code` is 429 or 200, neither of which is in the retry set). These tests pin the behavior.

If for any reason they fail, the existing retry filter needs the explicit `and not isinstance(exc, HyperpingRateLimitError)` guard. The plan permits adding that guard if needed.

- [ ] **Step 3: Tighten the comment**

In `src/hyperping/_mcp_transport.py`, update the `call_tool` docstring lines:

```python
"""Call an MCP tool and return parsed response data.

Auto-initializes on first call. Extracts and parses the JSON
string from ``result.content[0].text``.

Retries automatically on transient HTTP server errors (500, 502, 503, 504)
up to ``max_retries`` times with exponential back-off. Rate-limit errors
(HTTP 429 or JSON-RPC -32000) are NEVER retried at this layer; they raise
:class:`HyperpingRateLimitError` immediately so callers can honour
``retry_after``.
"""
```

Mirror in the async transport.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q`. Expected: all PASS.

- [ ] **Step 5: Refactor and verify**

`ruff check src tests && mypy --strict src`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/_mcp_transport.py src/hyperping/_async_mcp_transport.py \
       tests/unit/test_mcp_transport.py tests/unit/test_async_mcp_transport.py
git commit -m "test(mcp): pin that call_tool retry never catches rate-limit; clarify docstring"
```

---

### Task 9: `ensure_initialized()` on high-level clients (A5)

**Files:**
- Modify: `src/hyperping/mcp_client.py`
- Modify: `src/hyperping/_async_mcp_client.py`
- Test: `tests/unit/test_mcp_client.py`
- Test: `tests/unit/test_async_mcp_client.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_mcp_client.py`:

```python
from hyperping.exceptions import HyperpingRateLimitError


def test_ensure_initialized_delegates_to_transport():
    client = make_client()
    client.ensure_initialized()
    client._transport.initialize.assert_called_once_with()


def test_ensure_initialized_propagates_rate_limit():
    client = make_client()
    client._transport.initialize.side_effect = HyperpingRateLimitError(
        "rate limited on initialize", retry_after=30, status_code=200,
    )
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        client.ensure_initialized()
    assert exc_info.value.retry_after == 30
```

(Add `import pytest` at the top of the test file if not already imported.)

Mirror for `tests/unit/test_async_mcp_client.py` with an async `make_client` and `await client.ensure_initialized()`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mcp_client.py tests/unit/test_async_mcp_client.py -v -k "ensure_initialized"`
Expected: FAIL with `AttributeError: 'HyperpingMcpClient' object has no attribute 'ensure_initialized'`.

- [ ] **Step 3: Implement on both clients**

Add to `src/hyperping/mcp_client.py`, in the `HyperpingMcpClient` class, immediately after `_call`:

```python
def ensure_initialized(self) -> None:
    """Perform the MCP handshake now if it hasn't happened yet.

    Useful for startup health checks: call this once on boot and catch
    :class:`HyperpingRateLimitError` so you can decide whether to start
    the rest of your service. Subsequent tool calls reuse the handshake.

    Raises:
        HyperpingRateLimitError: If the server rate-limits ``initialize``,
            either via HTTP 429 or via the JSON-RPC ``-32000`` rate-limit
            payload. Inspect ``.retry_after`` to back off.
        HyperpingAuthError: If the API key is invalid.
    """
    self._transport.initialize()
```

Add to `src/hyperping/_async_mcp_client.py`, in `AsyncHyperpingMcpClient`, immediately after `_call`:

```python
async def ensure_initialized(self) -> None:
    """Async counterpart to :meth:`HyperpingMcpClient.ensure_initialized`."""
    await self._transport.initialize()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_mcp_client.py tests/unit/test_async_mcp_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Refactor and verify**

`pytest -q && ruff check src tests && mypy --strict src`. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/hyperping/mcp_client.py src/hyperping/_async_mcp_client.py \
       tests/unit/test_mcp_client.py tests/unit/test_async_mcp_client.py
git commit -m "feat(mcp): add ensure_initialized() on HyperpingMcpClient and async counterpart"
```

---

### Task 10: README "MCP rate limits" subsection (B)

**Files:**
- Modify: `README.md` (insert after the existing "MCP Client" section, around line 195)

- [ ] **Step 1: Identify the insertion point**

The new subsection goes immediately after the paragraph ending in `use the exported Pydantic models (e.g.,`OnCallSchedule`,`EscalationPolicy`) for validation if needed.` (around line 194). Insert before `### Healthchecks`.

- [ ] **Step 2: Insert the new subsection**

Paste the exact copy from the "Documentation copy (final)" section of this plan. Do not paraphrase. The block begins with `### MCP rate limits and connection lifecycle` and ends with the fenced Python example showing `mcp.ensure_initialized()`.

- [ ] **Step 3: Verify markdown renders cleanly**

Run any local markdown linter if available, or visually inspect for unbalanced fences. `ruff` does not lint markdown; rely on inspection.

- [ ] **Step 4: Run the full project suite**

Run: `pytest -q`
Expected: PASS (no code changes in this task, but confirms nothing else regressed).

- [ ] **Step 5: Refactor and verify**

Re-read the new subsection in context. Confirm it flows from the prior MCP Client section and that the example uses an already-imported symbol (`HyperpingMcpClient`, `HyperpingRateLimitError`).

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: add MCP rate limits and connection lifecycle section"
```

---

### Task 11: CHANGELOG `[Unreleased]` entry (B)

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Insert new heading at the top**

Above the existing `## [1.6.0] - 2026-05-06` heading, insert the exact `[Unreleased]` block from the "Documentation copy (final)" section.

- [ ] **Step 2: Verify file structure**

The file now begins with the existing preamble, then `## [Unreleased]`, then the 1.6.0 section. No version bump is performed (release versioning is a separate PR per project convention).

- [ ] **Step 3: Run the full project suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 4: Refactor and verify**

Inspect: the `[Unreleased]` block lists `### Added` and `### Fixed`, both matching the changes in this PR. No stale entries.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add Unreleased CHANGELOG entry for MCP rate-limit fixes"
```

---

### Task 12: Final integration sweep

**Files:**
- All previously modified.

- [ ] **Step 1: Run full project verification**

Run in sequence:

```bash
ruff check src tests
mypy --strict src
pytest -q
```

Expected: all green. `pytest` enforces `--cov-fail-under=85` from `pyproject.toml`; coverage must remain at or above that threshold.

- [ ] **Step 2: Manually verify the user's repro pattern**

Open a Python REPL inside the worktree (after `pip install -e .` in a venv if not already done) and exercise the user's snippet against a `respx` mock that returns the JSON-RPC rate-limit on `initialize`:

```python
import respx, httpx
from hyperping import HyperpingMcpClient, HyperpingRateLimitError

with respx.mock:
    respx.post("https://api.hyperping.io/v1/mcp").mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0", "id": 1,
                "error": {
                    "code": -32000,
                    "message": 'Hyperping MCP rate limit exceeded for "initialize" '
                               "(5/5 per minute). Retry after 32s.",
                },
            },
        ),
    )
    for i in range(6):
        with HyperpingMcpClient(api_key="sk_test") as mcp:
            try:
                mcp.ensure_initialized()
            except HyperpingRateLimitError as e:
                print(i, "rate-limited; retry_after=", e.retry_after)
                break
```

Expected output: `0 rate-limited; retry_after= 32`. The exception is the typed one, with the parsed `retry_after`. (This manual check is not added to the suite; the per-test coverage above is the canonical verification.)

- [ ] **Step 3: Sanity-check the diff**

```bash
git diff --stat main...HEAD
```

Expected files changed:
- `src/hyperping/_mcp_transport.py`
- `src/hyperping/_async_mcp_transport.py`
- `src/hyperping/mcp_client.py`
- `src/hyperping/_async_mcp_client.py`
- `tests/unit/test_mcp_transport.py`
- `tests/unit/test_async_mcp_transport.py`
- `tests/unit/test_mcp_client.py`
- `tests/unit/test_async_mcp_client.py`
- `README.md`
- `CHANGELOG.md`
- `docs/plans/2026-05-21-mcp-rate-limit-fixes.md` (this plan)

No other files. Verify.

- [ ] **Step 4: Final commit (if anything was left)**

If steps 1-3 surfaced no additional changes, this task closes without a new commit. Otherwise:

```bash
git add -p   # carefully stage only the residual fixes
git commit -m "chore(mcp): final cleanup after rate-limit fixes"
```

- [ ] **Step 5: Confirm completion criteria**

Re-verify against the "Completion Standard" section above:

- pytest green with coverage >= 85%.
- ruff clean.
- mypy --strict clean.
- Public API unchanged except for the additive `ensure_initialized()`.
- README and CHANGELOG updated.

Done.

---

## Remember

- Sync and async transports must remain symmetric. Every behavior change lands in both.
- The two locks (`self._lock` for the id counter, `self._init_lock` for initialization state) are intentional. Do not collapse them back into one.
- `time.monotonic()` is the cool-off clock. Do not switch to wall clock or event-loop time.
- The JSON-RPC rate-limit classifier checks BOTH `code == -32000` AND the message substring. Do not match on one alone.
- `HyperpingRateLimitError.status_code` is the underlying HTTP code (429 for HTTP rate-limits, 200 for JSON-RPC rate-limits). This is intentional and documented.
- No new runtime dependencies. Tests already have `respx` and `pytest-asyncio`.
- DRY, YAGNI, Red/Green/Refactor TDD, frequent commits.
