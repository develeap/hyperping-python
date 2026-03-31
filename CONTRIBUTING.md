# Contributing

Thank you for your interest in contributing to `hyperping`!

## Setup

```bash
git clone https://github.com/develeap/hyperping-python.git
cd hyperping-python
uv sync --all-extras
```

## Running tests

```bash
uv run pytest -v
```

## Linting and type checking

```bash
uv run ruff check src tests
uv run mypy src
```

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Write tests for any new behaviour.
3. Ensure all checks pass locally.
4. Open a PR — a maintainer will review it.

## Reporting issues

Open an issue at https://github.com/develeap/hyperping-python/issues.
