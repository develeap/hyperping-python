# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-05

First stable release. The public API is production-ready and covered by semver
guarantees going forward.

### Added

- **Typed `Outage` model** with `extra="ignore"`, `frozen=True`. `list_outages()`
  now returns `list[Outage]` instead of raw dicts.
- **`_validate_id()` guard** on all resource ID parameters before URL interpolation,
  preventing path-traversal attacks.
- **`_parse_list()` / `_unwrap_list()` helpers** in `_utils.py`, eliminating ~65 lines
  of duplicated parse-and-skip logic across all five mixins.
- **`_ClientProtocol` base class** in `_protocols.py`, replacing 5 duplicate
  `_request` stubs with a single source of truth.
- **`expect_dict()` helper** for safe response type narrowing (replaces bare `assert`
  calls that would vanish under `python -O`).
- **`LocalizedText.get(lang, default)`** accessor method.
- **DNS cross-field validation** on `MonitorCreate` via `@model_validator(mode="after")`.
- **`period` parameter** typed as `Literal["1h","24h","7d","30d","90d"]` with
  `ValueError` guard on `get_all_reports()` / `get_monitor_report()`.
- **Client-side email validation** in `add_subscriber()`.
- **API key validation** at `HyperpingClient` init (rejects empty/whitespace keys).
- **`DeprecationWarning`** for legacy aliases `IncidentStatus`, `IncidentUpdateCreate`,
  `HYPERPING_API_BASE`, `API_PATHS` (removal planned for v2.0.0).
- **SLSA build provenance** attestation in the publish workflow.
- **Dependabot** configuration for weekly GitHub Actions and pip dependency updates.
- **`pip-audit`** added to dev dependencies for reproducible vulnerability scanning.
- **`.env` / `.env.*` / `.env.local`** added to `.gitignore`.
- Missing test coverage: `update_incident`, `update_monitor`, `pause_monitor`,
  `resume_monitor`, `get_all_reports`, `get_monitor_report`.

### Changed

- **`models.py` split** into `models/` subpackage (`_monitor_models.py`,
  `_incident_models.py`, `_maintenance_models.py`, `_statuspage_models.py`,
  `_outage_models.py`). All imports from `hyperping.models` remain unchanged.
- **`CircuitBreaker`** extracted to `_circuit_breaker.py`; re-exported from
  `client.py` for backward compatibility.
- **`_request()` return type** corrected to `dict[str, Any] | list[dict[str, Any]]`.
- **`_request()` helpers** extracted: `_compute_sleep_time()`, `_should_retry()`,
  `_parse_error_body()`, `_parse_retry_after()`.
- **`CircuitBreaker.state`** return type changed from `str` to `CircuitState`.
- **`CircuitBreaker.state` / `failure_count`** reads now acquire the lock (thread safety).
- **`_remap_legacy_fields` / `Monitor.__init__`** no longer mutate input dicts.
- **`_MONITOR_WRITABLE_FIELDS`** moved from class variable to module-level `frozenset`.
- **`_incidents_mixin.py`** uses canonical `IncidentUpdateType` / `AddIncidentUpdateRequest`
  instead of legacy aliases.
- **All mixin list methods** use `_parse_list()` / `_unwrap_list()` with `%`-style
  logging (no f-strings in logger calls).
- **`conftest.py` fixture** converted to `yield`-based to close the HTTP client after
  each test.
- **All test files** migrated from `HYPERPING_API_BASE + API_PATHS[...]` to
  `API_BASE + Endpoint.*`.
- **Dependency bounds** narrowed: `httpx>=0.27,<1.0`, `pydantic>=2.0,<3.0`.
- **All GitHub Actions** pinned to full 40-char commit SHAs.
- **Sdist** trimmed: excludes `.github/`, `uv.lock`, `BACKLOG.md`.

### Fixed

- **Bare `except Exception`** in `_parse_error_body` narrowed to
  `(ValueError, httpx.DecodingError)`.
- **`HyperpingAuthError`** now omits `response_body` to prevent credential leakage
  through observability stacks.
- **Circuit breaker error message** references `recovery_timeout` (was incorrectly
  using `retry_config.initial_delay`).
- **`Retry-After` header parsing** guarded with `try/except` to handle RFC 7231
  HTTP-date values without crashing the retry loop.
- **Debug logs** sanitize sensitive fields (`request_headers`, `request_body`)
  via `_sanitize_for_log()`.
- **Parse failure logs** no longer include raw API response data (could contain
  subscriber emails or custom auth headers).
- **Shadow `from datetime import datetime as dt`** inside `Maintenance.is_active()`
  removed; uses module-level import.
- **`params if params else None`** simplified to `params or None`.
- **Internal symbols** (`EndpointConfig`, `ENDPOINTS`, `get_endpoint_url`,
  `get_version_for_endpoint`, `API_PATHS`, `HYPERPING_API_BASE`) removed from
  `__all__`; still accessible via `__getattr__` for backward compatibility.
- **`APIErrorResponse`** removed from `__all__` (intentionally internal).
- **Publish workflow audit step** is now blocking (no `continue-on-error`).
- **CI permissions** set to `contents: read` (least privilege).

### Security

- All resource IDs validated against `^[a-zA-Z0-9_-]+$` before URL interpolation.
- Auth error responses omit `response_body` to prevent token leakage.
- Debug logs redact sensitive field values.
- GitHub Actions pinned to commit SHAs (supply chain hardening).
- SLSA provenance attestation on all published artifacts.
- Dependency vulnerability audit gates the publish pipeline.
- OIDC trusted publishing (no stored PyPI tokens).

## [0.1.0] - 2026-03-31

### Added

- Initial release of the `hyperping` Python SDK.
- `HyperpingClient` with full support for Monitors, Incidents, Maintenance Windows, Outages, and Status Pages.
- Automatic retry with exponential backoff and jitter on transient errors (5xx, 429).
- Circuit breaker pattern to prevent cascading failures.
- Typed Pydantic v2 models for all API resources.
- `py.typed` marker for PEP 561 compliance.
- CI matrix across Python 3.11, 3.12, 3.13.
- OIDC trusted publisher workflow for PyPI releases (no stored secrets).
