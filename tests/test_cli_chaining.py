"""Scenario tests for request chaining (--export and template exports)."""

import os
from unittest.mock import patch

import yaml

from reqcap.cli import main
from tests.conftest import make_request_result


def _write_config(path, base_url=None, templates_dir=None):
    defaults = {}
    if base_url:
        defaults["base_url"] = base_url
    if templates_dir is not None:
        defaults["templates_dir"] = templates_dir
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"defaults": defaults}))


def _write_template(path, **fields):
    tpl = {"method": "GET", "url": "/health"}
    tpl.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(tpl))


# ── Scenario 17: Export workflow ──────────────────────────────────────────


class TestExportWorkflow:
    """--export extracts response values as reqcap_* env vars on stderr."""

    @patch("reqcap.executor.execute_request")
    def test_export_statement_in_output(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            body={"access_token": "abc123", "expires_in": 3600},
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api/auth",
                "--export",
                "token=body.access_token",
            ],
        )
        assert result.exit_code == 0
        assert "export reqcap_token=abc123" in result.output

    @patch("reqcap.executor.execute_request")
    def test_multiple_exports(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            body={"id": 42, "name": "Alice"},
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api/me",
                "--export",
                "id=body.id",
                "--export",
                "name=body.name",
            ],
        )
        assert "export reqcap_id=42" in result.output
        assert "export reqcap_name=Alice" in result.output

    @patch("reqcap.executor.execute_request")
    def test_export_shorthand(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """Shorthand: --export token → extracts body.token."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            body={"token": "xyz"},
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api/auth",
                "--export",
                "token",
            ],
        )
        assert "export reqcap_token=xyz" in result.output

    @patch("reqcap.executor.execute_request")
    def test_template_auto_exports(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """Template exports config auto-exports response values."""
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://localhost:3000")
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "login.yaml",
            url="/api/auth/login",
            method="POST",
            body={"email": "", "password": ""},
            exports={"token": "body.access_token"},
        )
        mock_exec.return_value = make_request_result(
            body={"access_token": "jwt_token_here", "user_id": 1},
        )
        result = runner.invoke(main, ["-t", "login"])
        assert "export reqcap_token=jwt_token_here" in result.output


# ── Scenario 18: Failed export ────────────────────────────────────────────


class TestFailedExport:
    """Export behavior on errors and missing fields."""

    @patch("reqcap.executor.execute_request")
    def test_connection_error_no_export(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """Connection error → exit 1, no export statements."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            error="Connection error: [Errno 111] Connection refused",
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:9999/api/auth",
                "--export",
                "token=body.access_token",
            ],
        )
        assert result.exit_code == 1
        assert "export reqcap_" not in result.output

    @patch("reqcap.executor.execute_request")
    def test_missing_field_silent_no_export(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """BUG: 401 with missing exported field → silent no-export (no warning)."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            status_code=401,
            body={"error": "Unauthorized"},
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api/auth",
                "--export",
                "token=body.access_token",
            ],
        )
        assert result.exit_code == 0  # BUG: 401 still exit 0
        # No export for missing field — silent
        assert "export reqcap_token" not in result.output

    @patch("reqcap.executor.execute_request")
    def test_null_body_silent_skip(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """BUG: null body → export silently skipped (no warning)."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            status_code=204,
            body=None,
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api/logout",
                "--export",
                "status=body.status",
            ],
        )
        assert "export reqcap_" not in result.output
