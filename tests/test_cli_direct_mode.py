"""Scenario tests for reqcap direct mode (METHOD URL)."""

import os
from unittest.mock import patch

import yaml

from reqcap.cli import main
from tests.conftest import make_request_result

# ── Scenario 1: Health check happy path ───────────────────────────────────


class TestHealthCheckHappyPath:
    """GET /health returns STATUS/TIME/BODY output."""

    @patch("reqcap.executor.execute_request")
    def test_output_format(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            status_code=200,
            body={"status": "ok"},
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/health"])
        assert result.exit_code == 0
        assert "STATUS: 200" in result.output
        assert "TIME: 42ms" in result.output
        assert "BODY:" in result.output
        assert '"status": "ok"' in result.output

    @patch("reqcap.executor.execute_request")
    def test_correct_args_passed(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={"status": "ok"})
        runner.invoke(main, ["GET", "http://localhost:3000/health"])
        mock_exec.assert_called_once()
        _, kwargs = mock_exec.call_args
        assert kwargs["method"] == "GET"
        assert kwargs["url"] == "http://localhost:3000/health"
        assert kwargs["timeout"] == 30


# ── Scenario 2: Connection refused ────────────────────────────────────────


class TestConnectionRefused:
    """Connection errors produce exit code 1 and error message."""

    @patch("reqcap.executor.execute_request")
    def test_exit_code_1(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            error="Connection error: [Errno 111] Connection refused",
        )
        result = runner.invoke(main, ["GET", "http://localhost:9999/health"])
        assert result.exit_code == 1

    @patch("reqcap.executor.execute_request")
    def test_error_message(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            error="Connection error: [Errno 111] Connection refused",
        )
        result = runner.invoke(main, ["GET", "http://localhost:9999/health"])
        assert "ERROR: Connection error" in result.output


# ── Scenario 3: Relative URL without and with config ──────────────────────


class TestRelativeUrl:
    """Relative URLs need base_url from config."""

    @patch("reqcap.executor.execute_request")
    def test_no_config_passes_bare_path(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """Without config, relative URL has no scheme — executor gets bare path."""
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            error="Request failed: Invalid URL '/api/health': No scheme supplied. Perhaps you meant https:///api/health?",
        )
        result = runner.invoke(main, ["GET", "/api/health"])
        # The CLI passes the bare path through; executor reports the error
        assert result.exit_code == 1
        assert "No scheme supplied" in result.output

    @patch("reqcap.executor.execute_request")
    def test_with_base_url_in_config(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        """With base_url in config, relative URL is resolved."""
        os.chdir(tmp_path)
        cfg = tmp_path / ".reqcap.yaml"
        cfg.write_text(yaml.dump({"defaults": {"base_url": "http://localhost:3000"}}))
        mock_exec.return_value = make_request_result(body={"ok": True})
        result = runner.invoke(main, ["GET", "/api/health"])
        assert result.exit_code == 0
        _, kwargs = mock_exec.call_args
        assert kwargs["url"] == "http://localhost:3000/api/health"


# ── Scenario 6: Large response no filter ──────────────────────────────────


class TestLargeResponseNoFilter:
    """Large responses are output in full without truncation."""

    @patch("reqcap.executor.execute_request")
    def test_full_output(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        large_body = {"items": [{"id": i, "name": f"item_{i}"} for i in range(500)]}
        mock_exec.return_value = make_request_result(body=large_body)
        result = runner.invoke(main, ["GET", "http://localhost:3000/api/items"])
        assert result.exit_code == 0
        assert '"id": 0' in result.output
        assert '"id": 499' in result.output
        assert "truncat" not in result.output.lower()
        assert "warning" not in result.output.lower()


# ── Scenario 7: 4xx/5xx exit code 0 (BUG) ────────────────────────────────


class TestHttpErrorExitCode:
    """BUG: HTTP errors (4xx/5xx) return exit code 0."""

    @patch("reqcap.executor.execute_request")
    def test_404_exit_code_0(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            status_code=404,
            body={"error": "Not found"},
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/api/missing"])
        assert result.exit_code == 0  # BUG: should arguably be non-zero
        assert "STATUS: 404" in result.output

    @patch("reqcap.executor.execute_request")
    def test_500_exit_code_0(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            status_code=500,
            body={"error": "Internal server error"},
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/api/crash"])
        assert result.exit_code == 0  # BUG: should arguably be non-zero
        assert "STATUS: 500" in result.output

    @patch("reqcap.executor.execute_request")
    def test_401_exit_code_0(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            status_code=401,
            body={"error": "Unauthorized"},
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/api/protected"])
        assert result.exit_code == 0  # BUG: should arguably be non-zero
        assert "STATUS: 401" in result.output


# ── Scenario 10: Non-JSON response ───────────────────────────────────────


class TestNonJsonResponse:
    """Non-JSON bodies are dumped raw; -f is silently ignored on non-JSON."""

    @patch("reqcap.executor.execute_request")
    def test_html_dumped_raw(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        html = "<html><body><h1>Hello</h1></body></html>"
        mock_exec.return_value = make_request_result(
            status_code=200,
            body=html,
            raw_text=html,
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/"])
        assert result.exit_code == 0
        assert "<html>" in result.output
        assert "<h1>Hello</h1>" in result.output

    @patch("reqcap.executor.execute_request")
    def test_filter_silently_ignored_on_non_json(
        self, mock_exec, runner, tmp_path, global_reqcap_dir
    ):
        """BUG: -f flag has no effect on non-JSON responses — no warning."""
        os.chdir(tmp_path)
        html = "<html><body>plain</body></html>"
        mock_exec.return_value = make_request_result(
            status_code=200,
            body=html,
            raw_text=html,
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/", "-f", "title"])
        assert result.exit_code == 0
        # The filter is silently ignored; full body still shown
        assert "plain" in result.output


# ── Scenario 19: Method casing ────────────────────────────────────────────


class TestMethodCasing:
    """Methods are uppercased before sending."""

    @patch("reqcap.executor.execute_request")
    def test_lowercase_get_uppercased(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={})
        runner.invoke(main, ["get", "http://localhost:3000/health"])
        _, kwargs = mock_exec.call_args
        assert kwargs["method"] == "GET"

    @patch("reqcap.executor.execute_request")
    def test_mixed_case_post_uppercased(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={})
        runner.invoke(main, ["Post", "http://localhost:3000/api/users", "-b", '{"name":"test"}'])
        _, kwargs = mock_exec.call_args
        assert kwargs["method"] == "POST"


# ── Scenario 20: POST without body ───────────────────────────────────────


class TestPostBody:
    """POST with and without -b body."""

    @patch("reqcap.executor.execute_request")
    def test_post_no_body(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={})
        runner.invoke(main, ["POST", "http://localhost:3000/api/trigger"])
        _, kwargs = mock_exec.call_args
        assert kwargs["body"] is None

    @patch("reqcap.executor.execute_request")
    def test_post_with_body(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={"id": 1})
        runner.invoke(main, ["POST", "http://localhost:3000/api/users", "-b", '{"name":"test"}'])
        _, kwargs = mock_exec.call_args
        assert kwargs["body"] == '{"name":"test"}'


# ── Scenario 21: No args ─────────────────────────────────────────────────


class TestNoArgs:
    """No arguments shows help and exits non-zero."""

    def test_shows_help(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        result = runner.invoke(main, [])
        assert result.exit_code != 0
        # Help text includes mode descriptions
        assert "MODES" in result.output or "Direct" in result.output

    def test_exit_code_1(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        result = runner.invoke(main, [])
        assert result.exit_code == 1


# ── Scenario 22: Timeout ─────────────────────────────────────────────────


class TestTimeout:
    """--timeout is passed through to executor; default is 30."""

    @patch("reqcap.executor.execute_request")
    def test_custom_timeout_passed(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={})
        runner.invoke(main, ["GET", "http://localhost:3000/slow", "--timeout", "5"])
        _, kwargs = mock_exec.call_args
        assert kwargs["timeout"] == 5

    @patch("reqcap.executor.execute_request")
    def test_timeout_error_message(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(
            error="Request timed out after 5s",
        )
        result = runner.invoke(main, ["GET", "http://localhost:3000/slow", "--timeout", "5"])
        assert result.exit_code == 1
        assert "timed out" in result.output

    @patch("reqcap.executor.execute_request")
    def test_default_timeout_is_30(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        mock_exec.return_value = make_request_result(body={})
        runner.invoke(main, ["GET", "http://localhost:3000/health"])
        _, kwargs = mock_exec.call_args
        assert kwargs["timeout"] == 30
