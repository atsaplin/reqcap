"""Shared fixtures for reqcap scenario tests."""

import json

import pytest
from click.testing import CliRunner

from reqcap import core
from reqcap.executor import RequestResult


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def global_reqcap_dir(tmp_path, monkeypatch):
    """Override the global ~/.reqcap directory to a temp location."""
    fake_global = tmp_path / "fake_home" / ".reqcap"
    fake_global.mkdir(parents=True)
    monkeypatch.setattr(core, "GLOBAL_DIR", fake_global)
    monkeypatch.setattr(core, "GLOBAL_CONFIG", fake_global / "config.yaml")
    monkeypatch.setattr(core, "GLOBAL_TEMPLATES_DIR", fake_global / "templates")
    monkeypatch.setattr(core, "GLOBAL_SNAPSHOTS_DIR", fake_global / "snapshots")
    return fake_global


@pytest.fixture(autouse=True)
def isolate_history(tmp_path, monkeypatch):
    """Prevent tests from polluting ~/.reqcap_history.json."""
    from reqcap import cli

    monkeypatch.setattr(cli, "HISTORY_FILE", tmp_path / "test_history.json")


def make_request_result(
    status_code=200,
    body=None,
    headers=None,
    elapsed_ms=42.0,
    error=None,
    raw_text="",
):
    """Factory for mock RequestResult objects."""
    r = RequestResult()
    r.status_code = status_code
    r.headers = headers or {}
    r.body = body
    r.elapsed_ms = elapsed_ms
    r.error = error
    r.raw_text = raw_text or (
        json.dumps(body) if isinstance(body, dict | list) else str(body or "")
    )
    return r
