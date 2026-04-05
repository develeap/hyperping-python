# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
