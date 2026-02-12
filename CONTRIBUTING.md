# Contributing to reqcap

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Local development

```bash
cd reqcap

# Install dependencies and create .venv
uv sync

# Run locally
uv run reqcap GET https://httpbin.org/get
uv run reqcap GET https://httpbin.org/json -f "slideshow.title"
```

## Install globally

```bash
uv tool install /path/to/reqcap
```

Now `reqcap` is available everywhere. To reinstall after making changes:

```bash
uv tool install /path/to/reqcap --force
```

## Running tests

```bash
uv run pytest tests/ -v
```

## Project structure

```
reqcap/
  __init__.py
  __main__.py          # uv run python -m reqcap
  cli.py               # CLI entry point (click)
  core.py              # Config, env loading, variable resolution, auth, curl parsing
  executor.py          # HTTP request execution
  filters.py           # Response filtering and output formatting
templates/             # Template files (one .yaml per template)
  login.yaml
  health.yaml
  create-user.yaml
pyproject.toml         # Package metadata and dependencies
config.example.yaml    # Example config (defaults only)
.env.example           # Example environment variables
```
