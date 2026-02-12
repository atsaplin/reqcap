"""CLI integration tests for config and template resolution."""

import os

import pytest
import yaml
from click.testing import CliRunner

from reqcap import core
from reqcap.cli import main


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
    return fake_global


def _write_config(path, base_url="http://localhost:3000", templates_dir=None):
    defaults = {"base_url": base_url}
    if templates_dir is not None:
        defaults["templates_dir"] = templates_dir
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"defaults": defaults}))


def _write_template(path, url="/health", method="GET", description="test"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "url": url,
                "method": method,
                "description": description,
            },
        ),
    )


# ── --list-templates CLI ─────────────────────────────────────────────────


class TestListTemplatesCli:
    def test_no_templates_anywhere(self, runner, tmp_path, global_reqcap_dir):
        """Shows helpful message when no templates found."""
        os.chdir(tmp_path)
        result = runner.invoke(main, ["--list-templates"])
        assert "No templates directory found" in result.output
        assert "user-created .yaml files" in result.output

    def test_shows_directory_path(self, runner, tmp_path, global_reqcap_dir):
        """Shows resolved directory path at the top."""
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        _write_template(tpl_dir / "health.yaml")
        result = runner.invoke(main, ["--list-templates"])
        assert f"Templates from: {tpl_dir.resolve()}" in result.output
        assert "health" in result.output

    def test_templates_dir_override(self, runner, tmp_path, global_reqcap_dir):
        """--templates-dir override is used for listing."""
        os.chdir(tmp_path)
        custom = tmp_path / "custom"
        _write_template(custom / "alpha.yaml", url="/alpha")
        # Also create CWD templates
        _write_template(tmp_path / "templates" / "beta.yaml")

        result = runner.invoke(
            main,
            ["--templates-dir", str(custom), "--list-templates"],
        )
        assert f"Templates from: {custom.resolve()}" in result.output
        assert "alpha" in result.output
        assert "beta" not in result.output

    def test_global_templates_listed(self, runner, tmp_path, global_reqcap_dir):
        """Global templates are listed when no local ones exist."""
        os.chdir(tmp_path)
        global_tpl = global_reqcap_dir / "templates"
        _write_template(global_tpl / "global.yaml", description="from global")

        result = runner.invoke(main, ["--list-templates"])
        assert f"Templates from: {global_tpl.resolve()}" in result.output
        assert "global" in result.output


# ── -t template not found ───────────────────────────────────────────────


class TestTemplateNotFound:
    def test_error_message(self, runner, tmp_path, global_reqcap_dir):
        """Shows helpful error with search paths for missing template."""
        os.chdir(tmp_path)
        result = runner.invoke(main, ["-t", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output
        assert "user-created .yaml files" in result.output
        assert "reqcap GET <url>" in result.output

    def test_error_shows_searched_paths(self, runner, tmp_path, global_reqcap_dir):
        """Error message includes paths that were checked."""
        os.chdir(tmp_path)
        result = runner.invoke(main, ["-t", "status"])
        assert "status" in result.output
        assert "status.yaml" in result.output

    def test_error_with_templates_dir(self, runner, tmp_path, global_reqcap_dir):
        """Error message shows the templates dir candidate path."""
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        result = runner.invoke(main, ["-t", "missing"])
        assert "templates" in result.output
        assert "missing.yaml" in result.output


# ── Config resolution via CLI ────────────────────────────────────────────


class TestConfigResolutionCli:
    def test_explicit_config_flag(self, runner, tmp_path, global_reqcap_dir):
        """Explicit -c flag uses the specified config."""
        os.chdir(tmp_path)
        cfg = tmp_path / "myconfig.yaml"
        tpl_dir = tmp_path / "mytemplates"
        _write_config(cfg, templates_dir=str(tpl_dir))
        _write_template(tpl_dir / "test.yaml", url="/test")

        result = runner.invoke(main, ["-c", str(cfg), "--list-templates"])
        assert "test" in result.output

    def test_cwd_config_auto_discovered(self, runner, tmp_path, global_reqcap_dir):
        """CWD .reqcap.yaml is auto-discovered."""
        os.chdir(tmp_path)
        tpl_dir = tmp_path / "my_tpl"
        _write_config(tmp_path / ".reqcap.yaml", templates_dir=str(tpl_dir))
        _write_template(tpl_dir / "endpoint.yaml", url="/endpoint")

        result = runner.invoke(main, ["--list-templates"])
        assert "endpoint" in result.output

    def test_global_config_used_as_fallback(self, runner, tmp_path, global_reqcap_dir):
        """Global config is used when no local config exists."""
        os.chdir(tmp_path)
        global_tpl = global_reqcap_dir / "templates"
        global_tpl.mkdir(exist_ok=True)
        _write_config(
            global_reqcap_dir / "config.yaml",
            templates_dir=str(global_tpl),
        )
        _write_template(global_tpl / "health.yaml")

        result = runner.invoke(main, ["--list-templates"])
        assert "health" in result.output

    def test_config_relative_templates_dir(self, runner, tmp_path, global_reqcap_dir):
        """templates_dir in config resolves relative to config file."""
        os.chdir(tmp_path)
        # Config in a subdirectory, templates_dir: "tpl" relative to it
        project = tmp_path / "project"
        project.mkdir()
        _write_config(project / ".reqcap.yaml", templates_dir="tpl")
        _write_template(project / "tpl" / "api.yaml", url="/api")

        result = runner.invoke(
            main,
            [
                "-c",
                str(project / ".reqcap.yaml"),
                "--list-templates",
            ],
        )
        assert "api" in result.output
        assert str((project / "tpl").resolve()) in result.output
