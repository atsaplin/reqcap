"""Tests for template directory and template file resolution."""

import os

import pytest
import yaml

from reqcap import core


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory and cd into it."""
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


@pytest.fixture
def global_reqcap_dir(tmp_path, monkeypatch):
    """Override the global ~/.reqcap directory to a temp location."""
    fake_global = tmp_path / "fake_home" / ".reqcap"
    fake_global.mkdir(parents=True)
    monkeypatch.setattr(core, "GLOBAL_DIR", fake_global)
    monkeypatch.setattr(core, "GLOBAL_CONFIG", fake_global / "config.yaml")
    monkeypatch.setattr(core, "GLOBAL_TEMPLATES_DIR", fake_global / "templates")
    return fake_global


def _write_template(path, url="/health", method="GET", description="test"):
    """Helper to write a template YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "url": url,
                "method": method,
                "description": description,
            }
        )
    )


def _make_config(config_dir=None, templates_dir=None):
    """Build an in-memory config dict."""
    defaults = {}
    if templates_dir is not None:
        defaults["templates_dir"] = templates_dir
    return {"defaults": defaults, "_config_dir": config_dir}


# ── resolve_templates_dir ────────────────────────────────────────────────


class TestResolveTemplatesDir:
    def test_cli_override_absolute(self, tmp_project):
        """--templates-dir with absolute path wins."""
        tdir = tmp_project / "my_templates"
        tdir.mkdir()
        config = _make_config()
        result = core.resolve_templates_dir(str(tdir), config)
        assert result == tdir.resolve()

    def test_cli_override_relative(self, tmp_project):
        """--templates-dir with relative path resolves from CWD."""
        tdir = tmp_project / "rel_templates"
        tdir.mkdir()
        config = _make_config()
        result = core.resolve_templates_dir("rel_templates", config)
        assert result == tdir.resolve()

    def test_cli_override_nonexistent_returns_none(self, tmp_project):
        """--templates-dir pointing to missing dir returns None."""
        config = _make_config()
        result = core.resolve_templates_dir("/nonexistent/dir", config)
        assert result is None

    def test_config_templates_dir_relative_to_config(self, tmp_project, global_reqcap_dir):
        """templates_dir in config resolves relative to config file."""
        # Config lives in /some/project/, templates_dir: "tpl"
        config_dir = tmp_project / "some" / "project"
        config_dir.mkdir(parents=True)
        tpl_dir = config_dir / "tpl"
        tpl_dir.mkdir()
        config = _make_config(config_dir=config_dir, templates_dir="tpl")

        result = core.resolve_templates_dir(None, config)
        assert result == tpl_dir.resolve()

    def test_config_templates_dir_absolute(self, tmp_project):
        """Absolute templates_dir in config is used as-is."""
        abs_tpl = tmp_project / "absolute_templates"
        abs_tpl.mkdir()
        config = _make_config(
            config_dir=tmp_project / "elsewhere",
            templates_dir=str(abs_tpl),
        )
        result = core.resolve_templates_dir(None, config)
        assert result == abs_tpl.resolve()

    def test_config_templates_dir_missing_falls_through(self, tmp_project, global_reqcap_dir):
        """If config templates_dir doesn't exist, fall through to CWD."""
        cwd_tpl = tmp_project / "templates"
        cwd_tpl.mkdir()
        config = _make_config(
            config_dir=tmp_project / "other",
            templates_dir="nonexistent",
        )
        result = core.resolve_templates_dir(None, config)
        assert result == cwd_tpl.resolve()

    def test_cwd_templates_fallback(self, tmp_project, global_reqcap_dir):
        """./templates/ in CWD is used when no config templates_dir."""
        cwd_tpl = tmp_project / "templates"
        cwd_tpl.mkdir()
        # Also create global to prove CWD wins
        global_tpl = global_reqcap_dir / "templates"
        global_tpl.mkdir()
        config = _make_config()

        result = core.resolve_templates_dir(None, config)
        assert result == cwd_tpl.resolve()

    def test_global_templates_fallback(self, tmp_project, global_reqcap_dir):
        """~/.reqcap/templates/ is used as last resort."""
        global_tpl = global_reqcap_dir / "templates"
        global_tpl.mkdir(exist_ok=True)
        config = _make_config()

        result = core.resolve_templates_dir(None, config)
        assert result == global_tpl.resolve()

    def test_nothing_found_returns_none(self, tmp_project, global_reqcap_dir):
        """Returns None when no templates directory exists anywhere."""
        config = _make_config()
        result = core.resolve_templates_dir(None, config)
        assert result is None

    def test_cli_override_beats_config(self, tmp_project):
        """--templates-dir takes priority over config templates_dir."""
        cli_dir = tmp_project / "cli_tpl"
        cli_dir.mkdir()
        config_tpl = tmp_project / "config_tpl"
        config_tpl.mkdir()
        config = _make_config(
            config_dir=tmp_project,
            templates_dir="config_tpl",
        )
        result = core.resolve_templates_dir(str(cli_dir), config)
        assert result == cli_dir.resolve()

    def test_config_beats_cwd(self, tmp_project):
        """Config templates_dir takes priority over ./templates/."""
        config_tpl = tmp_project / "project" / "tpl"
        config_tpl.mkdir(parents=True)
        cwd_tpl = tmp_project / "templates"
        cwd_tpl.mkdir()
        config = _make_config(
            config_dir=tmp_project / "project",
            templates_dir="tpl",
        )
        result = core.resolve_templates_dir(None, config)
        assert result == config_tpl.resolve()

    def test_cwd_beats_global(self, tmp_project, global_reqcap_dir):
        """./templates/ takes priority over ~/.reqcap/templates/."""
        cwd_tpl = tmp_project / "templates"
        cwd_tpl.mkdir()
        global_tpl = global_reqcap_dir / "templates"
        global_tpl.mkdir(exist_ok=True)
        config = _make_config()

        result = core.resolve_templates_dir(None, config)
        assert result == cwd_tpl.resolve()


# ── load_template ────────────────────────────────────────────────────────


class TestLoadTemplate:
    def test_exact_path(self, tmp_project):
        """Direct file path loads the template."""
        tpl = tmp_project / "my_template.yaml"
        _write_template(tpl, url="/exact")
        config = _make_config()

        result = core.load_template(str(tpl), config)
        assert result is not None
        assert result["url"] == "/exact"

    def test_name_with_yaml_extension_in_cwd(self, tmp_project):
        """Name + .yaml extension auto-appended in CWD."""
        _write_template(tmp_project / "health.yaml", url="/health")
        config = _make_config()

        result = core.load_template("health", config)
        assert result is not None
        assert result["url"] == "/health"

    def test_name_with_yml_extension(self, tmp_project):
        """Name + .yml extension auto-appended."""
        _write_template(tmp_project / "check.yml", url="/check")
        config = _make_config()

        result = core.load_template("check", config)
        assert result is not None
        assert result["url"] == "/check"

    def test_name_in_templates_dir(self, tmp_project):
        """Name resolved via templates directory."""
        tpl_dir = tmp_project / "templates"
        _write_template(tpl_dir / "login.yaml", url="/api/login", method="POST")
        config = _make_config()

        result = core.load_template("login", config)
        assert result is not None
        assert result["url"] == "/api/login"
        assert result["method"] == "POST"

    def test_name_in_config_relative_templates_dir(self, tmp_project):
        """Template found via config-relative templates_dir."""
        project_dir = tmp_project / "myproject"
        tpl_dir = project_dir / "api_templates"
        _write_template(tpl_dir / "users.yaml", url="/api/users")
        config = _make_config(config_dir=project_dir, templates_dir="api_templates")

        result = core.load_template("users", config)
        assert result is not None
        assert result["url"] == "/api/users"

    def test_name_in_global_templates(self, tmp_project, global_reqcap_dir):
        """Template found in ~/.reqcap/templates/."""
        global_tpl = global_reqcap_dir / "templates"
        _write_template(global_tpl / "health.yaml", url="/health", description="global")
        config = _make_config()

        result = core.load_template("health", config)
        assert result is not None
        assert result["description"] == "global"

    def test_not_found_returns_none(self, tmp_project, global_reqcap_dir):
        """Returns None when template doesn't exist anywhere."""
        config = _make_config()
        result = core.load_template("nonexistent", config)
        assert result is None

    def test_templates_dir_override(self, tmp_project):
        """templates_dir_override parameter is used."""
        override_dir = tmp_project / "override"
        _write_template(override_dir / "special.yaml", url="/special")
        config = _make_config()

        result = core.load_template("special", config, str(override_dir))
        assert result is not None
        assert result["url"] == "/special"

    def test_default_name_from_filename(self, tmp_project):
        """Template name defaults to filename stem."""
        _write_template(tmp_project / "my-endpoint.yaml")
        config = _make_config()

        result = core.load_template("my-endpoint", config)
        assert result is not None
        assert result["name"] == "my-endpoint"

    def test_absolute_path_template(self, tmp_project):
        """Absolute path to template file works."""
        tpl = tmp_project / "somewhere" / "deep" / "tpl.yaml"
        _write_template(tpl, url="/deep")
        config = _make_config()

        result = core.load_template(str(tpl), config)
        assert result is not None
        assert result["url"] == "/deep"


# ── list_templates ───────────────────────────────────────────────────────


class TestListTemplates:
    def test_lists_from_resolved_dir(self, tmp_project):
        """Lists all templates in the resolved directory."""
        tpl_dir = tmp_project / "templates"
        _write_template(tpl_dir / "alpha.yaml", url="/alpha")
        _write_template(tpl_dir / "beta.yaml", url="/beta")
        _write_template(tpl_dir / "gamma.yml", url="/gamma")
        config = _make_config()

        resolved_dir, templates = core.list_templates(config)
        assert resolved_dir == tpl_dir.resolve()
        names = [t["name"] for t in templates]
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names

    def test_returns_empty_when_no_dir(self, tmp_project, global_reqcap_dir):
        """Returns empty list when no templates directory found."""
        config = _make_config()
        resolved_dir, templates = core.list_templates(config)
        assert resolved_dir is None
        assert templates == []

    def test_returns_empty_for_empty_dir(self, tmp_project):
        """Returns empty list when templates dir exists but is empty."""
        (tmp_project / "templates").mkdir()
        config = _make_config()
        resolved_dir, templates = core.list_templates(config)
        assert resolved_dir is not None
        assert templates == []

    def test_ignores_non_yaml_files(self, tmp_project):
        """Non-YAML files in templates dir are ignored."""
        tpl_dir = tmp_project / "templates"
        _write_template(tpl_dir / "valid.yaml", url="/valid")
        (tpl_dir / "readme.txt").write_text("not a template")
        (tpl_dir / "script.py").write_text("not a template")
        config = _make_config()

        _, templates = core.list_templates(config)
        assert len(templates) == 1
        assert templates[0]["name"] == "valid"

    def test_override_dir(self, tmp_project):
        """templates_dir_override is used for listing."""
        override = tmp_project / "custom"
        _write_template(override / "one.yaml", url="/one")
        # Also create CWD templates to prove override wins
        cwd_tpl = tmp_project / "templates"
        _write_template(cwd_tpl / "two.yaml", url="/two")
        config = _make_config()

        resolved_dir, templates = core.list_templates(config, str(override))
        assert resolved_dir == override.resolve()
        assert len(templates) == 1
        assert templates[0]["name"] == "one"

    def test_lists_from_global_dir(self, tmp_project, global_reqcap_dir):
        """Lists templates from ~/.reqcap/templates/ when nothing else exists."""
        global_tpl = global_reqcap_dir / "templates"
        _write_template(global_tpl / "global-health.yaml", url="/health")
        config = _make_config()

        resolved_dir, templates = core.list_templates(config)
        assert resolved_dir == global_tpl.resolve()
        assert len(templates) == 1
        assert templates[0]["name"] == "global-health"

    def test_sorted_alphabetically(self, tmp_project):
        """Templates are returned sorted by filename."""
        tpl_dir = tmp_project / "templates"
        _write_template(tpl_dir / "zebra.yaml", url="/z")
        _write_template(tpl_dir / "alpha.yaml", url="/a")
        _write_template(tpl_dir / "middle.yaml", url="/m")
        config = _make_config()

        _, templates = core.list_templates(config)
        names = [t["name"] for t in templates]
        assert names == ["alpha", "middle", "zebra"]


# ── template_search_paths ────────────────────────────────────────────────


class TestTemplateSearchPaths:
    def test_with_resolved_dir(self, tmp_project):
        """Shows all candidate paths including CWD templates."""
        tpl_dir = tmp_project / "templates"
        tpl_dir.mkdir()
        config = _make_config()

        paths = core.template_search_paths("login", config)
        assert "login" in paths
        assert "login.yaml" in paths
        # CWD candidate is shown as relative
        assert any("templates" in p and "login.yaml" in p for p in paths)

    def test_without_resolved_dir(self, tmp_project, global_reqcap_dir):
        """Shows all candidate paths when no dir resolves."""
        config = _make_config()

        paths = core.template_search_paths("status", config)
        assert "status" in paths
        assert "status.yaml" in paths
        assert any("templates" in p and "status.yaml" in p for p in paths)
        assert str(core.GLOBAL_TEMPLATES_DIR / "status.yaml") in paths

    def test_with_config_templates_dir_unresolved(self, tmp_project, global_reqcap_dir):
        """Shows config-relative path even when dir doesn't exist."""
        config_dir = tmp_project / "project"
        config_dir.mkdir()
        config = _make_config(config_dir=config_dir, templates_dir="tpl")

        paths = core.template_search_paths("mytemplate", config)
        assert str(config_dir / "tpl" / "mytemplate.yaml") in paths
