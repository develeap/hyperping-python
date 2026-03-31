# Task: Build the `hyperping` Python SDK

## Who you are

You are a Claude Code agent working in `/home/khaleds/projects/hyperping-python/`.
This repo will become the `hyperping` PyPI package — a standalone Python SDK that
`hyperping-automation` (and anyone else) can `pip install hyperping` and build on top of.

## Step 0 — Git identity (do this first)

```bash
git config user.name "Khaled Salhab"
git config user.email "Khaled.salhab@develeap.com"
```

## Step 1 — Read the plan

Read the full implementation plan:
`/home/khaleds/projects/hyperping-automation/docs/plans/sdk-extraction.md`

It covers: repo structure, pyproject.toml, CI workflows, code steps C1–C4.
Follow it exactly.

## Step 2 — Source files

The source to transplant lives at:
`/home/khaleds/projects/hyperping-automation/src/hyp_status/client/`

Read every file there before writing anything here.

### Import substitution rules (apply to ALL files you write)

| Old (source) | New (this repo) |
|---|---|
| `from hyp_status.client.api import` | `from hyperping.client import` |
| `from hyp_status.client.X import` | `from hyperping.X import` |
| `from hyp_status import __version__` | hardcode `"hyperping-python/0.1.0"` in `_DEFAULT_USER_AGENT` (avoids circular import) |
| `api.py` | `client.py` (rename) |

### Files to write under `src/hyperping/`

- `__init__.py` — version, `__all__`, module docstring (update quick-start to `from hyperping import`)
- `py.typed` — empty file (PEP 561)
- `client.py` — from `api.py`; add `StatusPagesMixin` to the inheritance chain
- `models.py` — from `models.py`; append the new StatusPage models (see plan § C2)
- `endpoints.py` — from `endpoints.py`; add `STATUSPAGES = "/v2/statuspages"` to enum + dict
- `exceptions.py` — from `exceptions.py` (copy verbatim, no changes)
- `_monitors_mixin.py` — from `_monitors_mixin.py` (import paths only)
- `_incidents_mixin.py` — from `_incidents_mixin.py` (import paths only)
- `_maintenance_mixin.py` — from `_maintenance_mixin.py` (import paths only)
- `_outages_mixin.py` — from `_outages_mixin.py` (import paths only)
- `_statuspages_mixin.py` — **new file** (see plan § C2)

## Step 3 — Tests

Port the following from `hyperping-automation/tests/unit/`:
- `test_sdk_surface.py` — apply the same import substitutions; update `py.typed` path to
  `Path(__file__).resolve().parents[2] / "src" / "hyperping" / "py.typed"`; add `StatusPage`
  types to `EXPECTED_EXPORTS`; move the `client` fixture to `conftest.py`
- `test_client_monitors.py` → `test_monitors.py`
- `test_client_incidents.py` → `test_incidents.py`
- `test_client_maintenance.py` → `test_maintenance.py`
- `test_client_outages.py` → `test_outages.py`

Write `tests/unit/conftest.py` with the shared `client` fixture.

Write `tests/unit/test_statuspages.py` — new tests for all 8 StatusPages endpoints (see plan § C2).

## Step 4 — Verify

```bash
uv sync --all-extras
uv run ruff check src tests
uv run mypy src
uv run pytest -v
```

All must pass, coverage ≥ 85%.
Fix any issues before committing.

## Step 5 — Commit and push

```bash
git add -A
git commit -m "feat: initial SDK release — v0.1.0"
git push -u origin main
```

Do NOT push a tag. The user will review and tag manually for PyPI publish.
