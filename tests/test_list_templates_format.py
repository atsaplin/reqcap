"""Tests for LLM-friendly --list-templates output format."""

import os

import yaml

from reqcap.cli import main


def _write_template(path, **fields):
    tpl = {"method": "GET", "url": "/health"}
    tpl.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(tpl))


class TestListTemplatesFormat:
    """--list-templates output is compact and LLM-scannable."""

    def test_shows_count(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "a.yaml", name="a")
        _write_template(tpl_dir / "b.yaml", name="b")
        result = runner.invoke(main, ["--list-templates"])
        assert "2 available" in result.output

    def test_name_and_description_on_one_line(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            description="Authenticate user",
            method="POST",
            url="/auth/login",
        )
        result = runner.invoke(main, ["--list-templates"])
        # Name and description on same line with dash separator
        assert "login — Authenticate user" in result.output

    def test_name_without_description(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "simple.yaml", name="simple")
        result = runner.invoke(main, ["--list-templates"])
        assert "simple" in result.output

    def test_shows_method_and_url(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "users.yaml",
            name="users",
            method="GET",
            url="/api/users",
        )
        result = runner.invoke(main, ["--list-templates"])
        assert "GET /api/users" in result.output

    def test_shows_vars(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "create.yaml",
            name="create",
            method="POST",
            url="/users",
            fields=[
                {"name": "name", "path": "name"},
                {"name": "email", "path": "email"},
            ],
        )
        result = runner.invoke(main, ["--list-templates"])
        assert "vars: name, email" in result.output

    def test_shows_exports(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "login.yaml",
            name="login",
            method="POST",
            url="/auth",
            exports={"token": "body.access_token"},
        )
        result = runner.invoke(main, ["--list-templates"])
        assert "exports: token" in result.output

    def test_shows_depends(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "dep.yaml", name="dep")
        _write_template(
            tpl_dir / "main.yaml",
            name="main",
            depends=["dep"],
        )
        result = runner.invoke(main, ["--list-templates"])
        assert "depends: dep" in result.output

    def test_shows_snapshot(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            snapshot={"enabled": True, "name": "health-baseline"},
        )
        result = runner.invoke(main, ["--list-templates"])
        assert "snapshot: health-baseline" in result.output

    def test_shows_filter(self, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "users.yaml",
            name="users",
            filter={"body_fields": ["id", "name"]},
        )
        result = runner.invoke(main, ["--list-templates"])
        assert "filter: id, name" in result.output

    def test_detail_parts_pipe_separated(self, runner, tmp_path, global_reqcap_dir):
        """Method/url, vars, exports shown pipe-separated on detail line."""
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(
            tpl_dir / "full.yaml",
            name="full",
            description="Full example",
            method="POST",
            url="/api/data",
            fields=[{"name": "key", "path": "key"}],
            exports={"id": "body.id"},
        )
        result = runner.invoke(main, ["--list-templates"])
        # All parts on one detail line separated by |
        assert "POST /api/data | vars: key | exports: id" in result.output
