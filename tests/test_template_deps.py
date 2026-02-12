"""Tests for template dependency chaining (depends: key)."""

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


class TestSingleDependency:
    """A depends on B, B's exports available in A."""

    @patch("reqcap.executor.execute_request")
    def test_dep_exports_flow_to_parent(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        # B: login template that exports token
        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            method="POST",
            url="/auth/login",
            exports={"token": "body.access_token"},
        )

        # A: get-users depends on login, uses {{token}}
        _write_template(
            tpl_dir / "get-users.yaml",
            name="get-users",
            method="GET",
            url="/users",
            depends=["login"],
            headers={"Authorization": "Bearer {{token}}"},
        )

        # First call = login dep, second call = get-users
        mock_exec.side_effect = [
            make_request_result(
                status_code=200,
                body={"access_token": "tok123"},
                elapsed_ms=45,
            ),
            make_request_result(
                status_code=200,
                body={"users": [{"id": 1}]},
                elapsed_ms=32,
            ),
        ]

        result = runner.invoke(main, ["-t", "get-users"])
        assert result.exit_code == 0

        # Dep status line printed
        assert "[dep: login] STATUS: 200" in result.output

        # Main request used the exported token
        _, kwargs = mock_exec.call_args_list[1]
        assert kwargs["headers"]["Authorization"] == "Bearer tok123"

        # Main output present
        assert "STATUS: 200" in result.output


class TestMultipleDependencies:
    """A depends on [B, C], both run in order."""

    @patch("reqcap.executor.execute_request")
    def test_multiple_deps_run_in_order(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "get-csrf.yaml",
            name="get-csrf",
            method="GET",
            url="/csrf",
            exports={"csrf": "body.csrf_token"},
        )
        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            method="POST",
            url="/auth/login",
            exports={"token": "body.access_token"},
        )
        _write_template(
            tpl_dir / "dashboard.yaml",
            name="dashboard",
            method="GET",
            url="/dashboard",
            depends=["get-csrf", "login"],
            headers={
                "X-CSRF": "{{csrf}}",
                "Authorization": "Bearer {{token}}",
            },
        )

        mock_exec.side_effect = [
            make_request_result(body={"csrf_token": "abc"}, elapsed_ms=10),
            make_request_result(body={"access_token": "tok"}, elapsed_ms=20),
            make_request_result(body={"dashboard": "data"}, elapsed_ms=30),
        ]

        result = runner.invoke(main, ["-t", "dashboard"])
        assert result.exit_code == 0
        assert "[dep: get-csrf] STATUS: 200" in result.output
        assert "[dep: login] STATUS: 200" in result.output

        # Both exports available in main request
        _, kwargs = mock_exec.call_args_list[2]
        assert kwargs["headers"]["X-CSRF"] == "abc"
        assert kwargs["headers"]["Authorization"] == "Bearer tok"


class TestNestedDependencies:
    """A → B → C, depth-first execution, exports accumulate."""

    @patch("reqcap.executor.execute_request")
    def test_nested_depth_first(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        # C: deepest dep
        _write_template(
            tpl_dir / "get-config.yaml",
            name="get-config",
            method="GET",
            url="/config",
            exports={"api_version": "body.version"},
        )

        # B: depends on C
        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            method="POST",
            url="/auth",
            depends=["get-config"],
            exports={"token": "body.token"},
        )

        # A: depends on B
        _write_template(
            tpl_dir / "fetch-data.yaml",
            name="fetch-data",
            method="GET",
            url="/data",
            depends=["login"],
            headers={"Authorization": "Bearer {{token}}"},
        )

        mock_exec.side_effect = [
            make_request_result(body={"version": "v2"}, elapsed_ms=5),
            make_request_result(body={"token": "deep-tok"}, elapsed_ms=15),
            make_request_result(body={"items": []}, elapsed_ms=25),
        ]

        result = runner.invoke(main, ["-t", "fetch-data"])
        assert result.exit_code == 0

        # Execution order: get-config → login → fetch-data
        output_lines = result.output.strip().split("\n")
        dep_lines = [line for line in output_lines if line.startswith("[dep:")]
        assert len(dep_lines) == 2
        assert "get-config" in dep_lines[0]
        assert "login" in dep_lines[1]


class TestCycleDetection:
    """A → B → A errors with clear message."""

    @patch("reqcap.executor.execute_request")
    def test_direct_cycle(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "a.yaml",
            name="a",
            method="GET",
            url="/a",
            depends=["b"],
        )
        _write_template(
            tpl_dir / "b.yaml",
            name="b",
            method="GET",
            url="/b",
            depends=["a"],
        )

        result = runner.invoke(main, ["-t", "a"])
        assert result.exit_code == 1
        assert "Circular dependency" in result.output

    @patch("reqcap.executor.execute_request")
    def test_self_cycle(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "self.yaml",
            name="self",
            method="GET",
            url="/self",
            depends=["self"],
        )

        result = runner.invoke(main, ["-t", "self"])
        assert result.exit_code == 1
        assert "Circular dependency" in result.output


class TestDepLoadFailure:
    """Depends on nonexistent template → error."""

    def test_missing_dep_template(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "main.yaml",
            name="main",
            method="GET",
            url="/main",
            depends=["nonexistent"],
        )

        result = runner.invoke(main, ["-t", "main"])
        assert result.exit_code == 1
        assert "nonexistent" in result.output
        assert "not found" in result.output


class TestDepRequestFailure:
    """Dep returns connection error → abort."""

    @patch("reqcap.executor.execute_request")
    def test_dep_error_aborts(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            method="POST",
            url="/auth",
            exports={"token": "body.token"},
        )
        _write_template(
            tpl_dir / "protected.yaml",
            name="protected",
            method="GET",
            url="/protected",
            depends=["login"],
        )

        mock_exec.return_value = make_request_result(error="Connection error: refused")

        result = runner.invoke(main, ["-t", "protected"])
        assert result.exit_code == 1
        assert "login" in result.output
        assert "Connection error" in result.output


class TestVariableOverride:
    """-v token=manual overrides dep export of token."""

    @patch("reqcap.executor.execute_request")
    def test_cli_var_overrides_dep_export(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            method="POST",
            url="/auth",
            exports={"token": "body.token"},
        )
        _write_template(
            tpl_dir / "api.yaml",
            name="api",
            method="GET",
            url="/api",
            depends=["login"],
            headers={"Authorization": "Bearer {{token}}"},
        )

        mock_exec.side_effect = [
            make_request_result(body={"token": "from-dep"}, elapsed_ms=10),
            make_request_result(body={"ok": True}, elapsed_ms=20),
        ]

        # -v token=manual should override the dep export
        result = runner.invoke(main, ["-t", "api", "-v", "token=manual"])
        assert result.exit_code == 0

        # The dep still runs but its export of `token` is skipped
        # because -v token=manual takes precedence
        _, kwargs = mock_exec.call_args_list[1]
        assert kwargs["headers"]["Authorization"] == "Bearer manual"


class TestNoDependsKey:
    """Existing templates without depends work unchanged."""

    @patch("reqcap.executor.execute_request")
    def test_no_depends_works_normally(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "simple.yaml",
            name="simple",
            method="GET",
            url="/health",
        )

        mock_exec.return_value = make_request_result(body={"status": "ok"})

        result = runner.invoke(main, ["-t", "simple"])
        assert result.exit_code == 0
        assert "STATUS: 200" in result.output
        # No dep lines
        assert "[dep:" not in result.output


class TestStringDepends:
    """depends: can be a single string instead of a list."""

    @patch("reqcap.executor.execute_request")
    def test_string_depends(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "dep.yaml",
            name="dep",
            method="GET",
            url="/dep",
            exports={"val": "body.x"},
        )
        _write_template(
            tpl_dir / "consumer.yaml",
            name="consumer",
            method="GET",
            url="/consume",
            depends="dep",
        )

        mock_exec.side_effect = [
            make_request_result(body={"x": "42"}, elapsed_ms=10),
            make_request_result(body={"ok": True}, elapsed_ms=20),
        ]

        result = runner.invoke(main, ["-t", "consumer"])
        assert result.exit_code == 0
        assert "[dep: dep] STATUS: 200" in result.output
