"""Scenario tests for reqcap template mode (-t TEMPLATE)."""

import os
from unittest.mock import patch

import yaml

from reqcap.cli import main
from tests.conftest import make_request_result


def _write_config(path, base_url=None, templates_dir=None, headers=None):
    defaults = {}
    if base_url:
        defaults["base_url"] = base_url
    if templates_dir is not None:
        defaults["templates_dir"] = templates_dir
    if headers:
        defaults["headers"] = headers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"defaults": defaults}))


def _write_template(path, **fields):
    tpl = {"method": "GET", "url": "/health"}
    tpl.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(tpl))


# ── Scenario 8: Template relative URL no base_url ────────────────────────


class TestTemplateRelativeUrlNoBaseUrl:
    """Template with relative URL and no base_url → scheme error."""

    @patch("reqcap.executor.execute_request")
    def test_no_scheme_error(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "health.yaml", url="/api/health", method="GET")
        # No config with base_url
        mock_exec.return_value = make_request_result(
            error="Request failed: Invalid URL '/api/health': No scheme supplied. Perhaps you meant https:///api/health?",
        )
        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 1
        assert "No scheme supplied" in result.output


# ── Scenario 9: Agent invents template ────────────────────────────────────


class TestTemplateNotFoundMessages:
    """Missing template shows search paths, user-created note, and direct mode hint."""

    def test_shows_search_paths(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        result = runner.invoke(main, ["-t", "invented"])
        assert result.exit_code == 1
        assert "invented.yaml" in result.output

    def test_suggests_direct_mode(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        result = runner.invoke(main, ["-t", "ghost"])
        assert "reqcap GET <url>" in result.output

    def test_user_created_note(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        result = runner.invoke(main, ["-t", "phantom"])
        assert "user-created" in result.output


# ── Scenario 11: Global config base_url works ────────────────────────────


class TestGlobalConfigBaseUrl:
    """Global config base_url is used for template relative URLs."""

    @patch("reqcap.executor.execute_request")
    def test_global_base_url_applied(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        # Global config with base_url
        _write_config(
            global_reqcap_dir / "config.yaml",
            base_url="http://global-api:8080",
        )
        # Global template
        global_tpl = global_reqcap_dir / "templates"
        _write_template(global_tpl / "status.yaml", url="/status", method="GET")

        mock_exec.return_value = make_request_result(body={"status": "ok"})
        result = runner.invoke(main, ["-t", "status"])
        assert result.exit_code == 0
        _, kwargs = mock_exec.call_args
        assert kwargs["url"] == "http://global-api:8080/status"


# ── Scenario 12: Project config overrides global ─────────────────────────


class TestProjectOverridesGlobal:
    """CWD config base_url takes precedence over global."""

    @patch("reqcap.executor.execute_request")
    def test_cwd_base_url_wins(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        # Global config
        _write_config(
            global_reqcap_dir / "config.yaml",
            base_url="http://global:9999",
        )
        # CWD config overrides
        _write_config(
            tmp_path / ".reqcap.yaml",
            base_url="http://local:3000",
        )
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "health.yaml", url="/health", method="GET")

        mock_exec.return_value = make_request_result(body={"ok": True})
        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 0
        _, kwargs = mock_exec.call_args
        assert kwargs["url"] == "http://local:3000/health"

    @patch("reqcap.executor.execute_request")
    def test_headers_from_config_sent(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(
            tmp_path / ".reqcap.yaml",
            base_url="http://local:3000",
            headers={"X-Custom": "from-config"},
        )
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "health.yaml", url="/health", method="GET")

        mock_exec.return_value = make_request_result(body={})
        runner.invoke(main, ["-t", "health"])
        _, kwargs = mock_exec.call_args
        assert "X-Custom" in kwargs["headers"]
        assert kwargs["headers"]["X-Custom"] == "from-config"


# ── Scenario 16: Explicit -c nonexistent silent (BUG) ────────────────────


class TestExplicitConfigNonexistentSilent:
    """BUG: -c pointing to nonexistent file silently proceeds with empty config."""

    @patch("reqcap.executor.execute_request")
    def test_no_error_for_missing_config(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """BUG: No error emitted when -c points to a missing file."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={"ok": True})
        result = runner.invoke(
            main,
            [
                "-c",
                "/nonexistent/config.yaml",
                "GET",
                "http://localhost:3000/health",
            ],
        )
        # No error about the missing config — it silently uses empty defaults
        assert result.exit_code == 0
        assert "STATUS: 200" in result.output

    @patch("reqcap.executor.execute_request")
    def test_missing_config_then_relative_url_fails(
        self,
        mock_exec,
        runner,
        tmp_path,
        global_reqcap_dir,
    ):
        """Missing config → no base_url → relative URL fails."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            error="Request failed: Invalid URL '/api/health': No scheme supplied. Perhaps you meant https:///api/health?",
        )
        result = runner.invoke(
            main,
            [
                "-c",
                "/nonexistent/config.yaml",
                "GET",
                "/api/health",
            ],
        )
        assert result.exit_code == 1
        assert "No scheme supplied" in result.output
