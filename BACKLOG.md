# Backlog

Items discovered during the enterprise-grade review (2026-04-02).
Agents: Security, Architecture, Code Quality, Refactor/Dead Code.

---

## CRITICAL

- [x] **C1** `models.py` split into `models/` subpackage: `_monitor_models.py`, `_incident_models.py`, `_maintenance_models.py`, `_statuspage_models.py`, `_outage_models.py`. Re-exported via `models/__init__.py` — zero public API breakage.
- [x] **C2** `_request` helpers extracted: `_compute_sleep_time(response, delay)` and `_should_retry(status_code, attempt)` (`client.py`).
- [x] **C3** `_handle_response_error` helpers extracted: `_parse_error_body(response)` and `_parse_retry_after(response)` (`client.py`).
- [x] **C4** `_remap_legacy_fields` and `Monitor.__init__` no longer mutate input — both operate on `{**data}` copies. `MonitorCreate` uses `@model_validator(mode="before")` for clean remapping.
- [x] **C5** `Outage` model defined in `models/_outage_models.py` with `extra="ignore"`, `frozen=True`. `list_outages()` now returns `list[Outage]`.
- [x] **C6** Shadow `from datetime import datetime as dt` inside `Maintenance.is_active()` removed. Uses module-level `datetime` import directly.

---

## HIGH

### Structural

- [x] **H1** `_request` return type corrected to `dict[str, Any] | list[dict[str, Any]]`.
- [x] **H2** `_parse_list(raw, model_cls, label)` extracted to `_utils.py`; used by all 5 mixin list methods (~65 lines eliminated).
- [x] **H3** `_unwrap_list(response, key)` extracted to `_utils.py`; used by all 5 mixins.
- [x] **H4** `_ClientProtocol(Protocol)` defined in `_protocols.py`; all mixin classes inherit from it, eliminating 5 `# type: ignore[empty-body]` stubs.
- [x] **H5** Internal symbols (`EndpointConfig`, `ENDPOINTS`, `get_endpoint_url`, `get_version_for_endpoint`, `API_PATHS`, `HYPERPING_API_BASE`) removed from `__all__`. Deprecated symbols `HYPERPING_API_BASE` and `API_PATHS` emit `DeprecationWarning` via `__getattr__`.
- [x] **H6** `update_monitor` and `update_maintenance` document the race condition in docstrings; `raise_on_conflict: bool = False` parameter added as ETag placeholder.
- [x] **H7** `get_monitor_report` documents O(n) fetch cost in docstring; notes the `monitor_uuid=` query param to check for.
- [x] **H8** `_validate_id(value, name)` helper in `_utils.py` calls before every f-string URL build in all 5 mixins.
- [x] **H9** Bare `except Exception` narrowed to `except (ValueError, httpx.DecodingError)` in `_parse_error_body`.
- [x] **H10** `response_body` risk documented. For `HyperpingAuthError`, `response_body=None` to prevent token leakage through observability stacks.
- [ ] **H11** GitHub Actions workflows need pinning to full 40-char commit SHAs (supply chain risk). TODO comments added in both workflow files. **Requires manual SHA lookup per release tag.**

### Security

- [x] **H8** (see above)
- [x] **H9** (see above)
- [x] **H10** (see above)

---

## MEDIUM

### Architecture / API Design

- [x] **M1** Async client (`AsyncHyperpingClient`) — shipped in PR #13 (feature/sdk-py-03-async-client).
- [x] **M2** Pagination (`page` param, `hasNextPage` auto-pagination via `collect_all_pages` / `collect_all_pages_async`) — shipped in PR #12 (merged) and PR #13.
- [x] **M3** Per-endpoint circuit breaker (`per_endpoint_circuit_breaker: bool = False` option) on `HyperpingClient` and `AsyncHyperpingClient`. Per-path state via `circuit_breaker_state_for(path)`. Default off; existing single-shared-breaker behaviour preserved.
- [x] **M4** `MonitorCreate` now has `@model_validator(mode="after")` that raises `ValueError` if DNS fields are set on non-DNS monitors.
- [x] **M5** `MonitorListResponse` is in `__all__` — retained but documented as not returned by any client method. Will be used once pagination lands.
- [x] **M6** `APIErrorResponse` removed from `__all__` (documented as intentionally internal in comment).
- [x] **M7** `DEFAULT_RETRY_CONFIG` / `DEFAULT_CIRCUIT_BREAKER_CONFIG` — added explicit `# intentionally internal` comment in `_circuit_breaker.py`.
- [x] **M8** `ping()` docstring clarified: explicitly states it fetches the monitor list and suggests using a dedicated `/health` endpoint if available.

### Validation / Type Safety

- [x] **M9** `period` param in `get_all_reports` / `get_monitor_report` typed `Literal[...]` + `ValueError` guard.
- [x] **M10** `add_subscriber` validates email format with `_EMAIL_RE` before sending to API; raises `ValueError` on mismatch.
- [ ] **M11** `url` field URL scheme validation deferred: HTTP monitors use URLs but DNS/ICMP/port monitors use hostnames/IPs, requiring protocol-aware cross-field validation. **Deferred — implement alongside M4 long-term discriminated-union work.**
- [ ] **M12** DateTime coercion for `start_date`, `end_date`, `date` fields — **deferred, breaking change requires semver bump.** The fragile `.replace("Z", "+00:00")` workaround remains; a future 0.2.0 migration guide should cover this.
- [x] **M13** `CircuitBreaker.state` return type changed to `CircuitState` (was `str`).
- [x] **M14** `CircuitBreaker.state` and `failure_count` reads now hold `_lock`.

### Thread Safety

- [x] **M14** (see above)

### Security

- [x] **M15** Debug log sanitizes `json` and `params` dicts before logging; `_SENSITIVE_LOG_KEYS` redacts known sensitive field names.

### Code Organization

- [x] **M16** `CircuitBreaker` + configs extracted to `_circuit_breaker.py`; re-exported from `client.py` for backward compat.
- [x] **M17** All test files migrated from `HYPERPING_API_BASE + API_PATHS[...]` to `API_BASE + Endpoint.*`.
- [x] **M18** `_incidents_mixin.py` uses canonical `IncidentUpdateType` and `AddIncidentUpdateRequest` (legacy aliases removed).
- [x] **M19** `_MONITOR_WRITABLE_FIELDS` moved to module-level `frozenset` constant in `_monitors_mixin.py`.
- [x] **M20** `params if params else None` simplified to `params or None` in `_incidents_mixin.py` and `_maintenance_mixin.py`.

### Testing

- [x] **M21** `update_incident` tests added: `test_update_incident_changes_title` and `test_update_incident_not_found` in `test_incidents.py`.
- [x] **M22** `update_monitor`, `pause_monitor`, `resume_monitor` targeted tests added to `test_monitors.py`.
- [x] **M23** `get_all_reports` / `get_monitor_report` tests added including `outages.details` nested list parsing.
- [x] **M24** `conftest.py` `client` fixture converted to `yield`-based; calls `client.close()` after each test.
- [ ] **M25** Request models (`MonitorCreate`, `IncidentCreate`, etc.) validated as mutable in `test_sdk_surface.py`. **Deliberate exception to immutability rule** — request models that accept legacy field remapping via `__init__` cannot easily be frozen. Annotated in test. Revisit if/when `__init__` remapping is replaced by `@model_validator`.

---

## LOW

- [x] **L1** `LocalizedText.get(lang, default="")` accessor method added (alongside C1 split).
- [x] **L2** f-string logging replaced with `%`-style args in all mixin and client files.
- [x] **L3** `IncidentStatus` / `IncidentUpdateCreate` legacy aliases now emit `DeprecationWarning` via `models/__init__.__getattr__`; removal planned for v0.3.0.
- [x] **L4** `ci.yml` now has `permissions: { contents: read }` at job level.
- [x] **L5** `uv audit` step added to both `ci.yml` and `publish.yml` (`pip-audit` fallback for compatibility).
- [x] **L6** Dependency bounds narrowed: `httpx>=0.27,<1.0` and `pydantic>=2.0,<3.0`.
- [x] **L7** Circuit breaker error message now references `recovery_timeout` (was incorrectly referencing `retry_config.initial_delay`).

---

## Deferred / Future Work

The following items require either a semver bump, a separate PR, or manual work:

- ~~**M1** Async client~~ — shipped
- ~~**M2** Pagination~~ — shipped
- ~~**M3** Per-endpoint circuit breaker option~~ — shipped
- **M11** URL validation for HTTP-protocol monitors (cross-field, needs discriminated union work)
- **M12** DateTime coercion (breaking change — v0.2.0)
- **H11** Pin all GitHub Actions `uses:` to 40-char commit SHAs (requires per-tag SHA lookup)
- **M25** Frozen request models (revisit after `@model_validator` remapping is complete)
