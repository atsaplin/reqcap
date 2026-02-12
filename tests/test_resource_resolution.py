"""Tests for generic resolve_resource_dir."""

import os

import pytest

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
    monkeypatch.setattr(core, "GLOBAL_SNAPSHOTS_DIR", fake_global / "snapshots")
    return fake_global


def _make_config(config_dir=None, **extra_defaults):
    defaults = dict(extra_defaults)
    return {"defaults": defaults, "_config_dir": config_dir}


class TestResolvePath:
    """Tests for the generic resolve_path primitive."""

    def test_returns_first_existing(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        b.mkdir()
        result = core.resolve_path([a, b])
        assert result == b.resolve()

    def test_returns_none_when_nothing_exists(self, tmp_path):
        result = core.resolve_path([tmp_path / "x", tmp_path / "y"])
        assert result is None

    def test_returns_default_when_nothing_exists(self, tmp_path):
        default = tmp_path / "fallback"
        result = core.resolve_path([tmp_path / "x"], default=default)
        assert result == default

    def test_works_for_files(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("test: true")
        result = core.resolve_path([tmp_path / "missing.yaml", f])
        assert result == f.resolve()

    def test_works_for_dirs(self, tmp_path):
        d = tmp_path / "templates"
        d.mkdir()
        result = core.resolve_path([d])
        assert result == d.resolve()

    def test_first_wins_when_multiple_exist(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        result = core.resolve_path([a, b])
        assert result == a.resolve()


class TestResolveResourceDir:
    def test_cli_override_absolute(self, tmp_project):
        d = tmp_project / "my_snapshots"
        d.mkdir()
        result = core.resolve_resource_dir("snapshots", str(d), _make_config())
        assert result == d.resolve()

    def test_cli_override_relative(self, tmp_project):
        d = tmp_project / "snaps"
        d.mkdir()
        result = core.resolve_resource_dir("snapshots", "snaps", _make_config())
        assert result == d.resolve()

    def test_cli_override_nonexistent_returns_none(self, tmp_project):
        result = core.resolve_resource_dir("snapshots", "/nonexistent", _make_config())
        assert result is None

    def test_config_value_relative_to_config_dir(self, tmp_project, global_reqcap_dir):
        config_dir = tmp_project / "project"
        config_dir.mkdir()
        snaps = config_dir / "my_snaps"
        snaps.mkdir()
        config = _make_config(config_dir=config_dir, snapshots_dir="my_snaps")
        result = core.resolve_resource_dir("snapshots", None, config)
        assert result == snaps.resolve()

    def test_config_value_absolute(self, tmp_project):
        abs_dir = tmp_project / "abs_snapshots"
        abs_dir.mkdir()
        config = _make_config(
            config_dir=tmp_project / "elsewhere",
            snapshots_dir=str(abs_dir),
        )
        result = core.resolve_resource_dir("snapshots", None, config)
        assert result == abs_dir.resolve()

    def test_config_value_missing_falls_to_cwd(self, tmp_project, global_reqcap_dir):
        cwd_snaps = tmp_project / "snapshots"
        cwd_snaps.mkdir()
        config = _make_config(
            config_dir=tmp_project / "other",
            snapshots_dir="nonexistent",
        )
        result = core.resolve_resource_dir("snapshots", None, config)
        assert result == cwd_snaps.resolve()

    def test_cwd_fallback(self, tmp_project, global_reqcap_dir):
        cwd_snaps = tmp_project / "snapshots"
        cwd_snaps.mkdir()
        global_snaps = global_reqcap_dir / "snapshots"
        global_snaps.mkdir()
        result = core.resolve_resource_dir("snapshots", None, _make_config())
        assert result == cwd_snaps.resolve()

    def test_global_fallback(self, tmp_project, global_reqcap_dir):
        global_snaps = global_reqcap_dir / "snapshots"
        global_snaps.mkdir()
        result = core.resolve_resource_dir("snapshots", None, _make_config())
        assert result == global_snaps.resolve()

    def test_nothing_found_returns_none(self, tmp_project, global_reqcap_dir):
        result = core.resolve_resource_dir("snapshots", None, _make_config())
        assert result is None

    def test_cli_override_beats_config(self, tmp_project):
        cli_dir = tmp_project / "cli_snaps"
        cli_dir.mkdir()
        config_dir = tmp_project / "config_snaps"
        config_dir.mkdir()
        config = _make_config(config_dir=tmp_project, snapshots_dir="config_snaps")
        result = core.resolve_resource_dir("snapshots", str(cli_dir), config)
        assert result == cli_dir.resolve()

    def test_templates_still_works_via_generic(self, tmp_project, global_reqcap_dir):
        """resolve_templates_dir should still work as a wrapper."""
        tdir = tmp_project / "templates"
        tdir.mkdir()
        config = _make_config()
        result = core.resolve_templates_dir(None, config)
        assert result == tdir.resolve()


class TestResourceSearchPaths:
    def test_with_resolved_dir(self, tmp_project):
        sdir = tmp_project / "snapshots"
        sdir.mkdir()
        config = _make_config()
        paths = core.resource_search_paths("snapshots", "baseline", ".json", config)
        assert "baseline" in paths
        assert "baseline.json" in paths
        assert any("snapshots" in p and "baseline.json" in p for p in paths)

    def test_without_resolved_dir(self, tmp_project, global_reqcap_dir):
        config = _make_config()
        paths = core.resource_search_paths("snapshots", "baseline", ".json", config)
        assert "baseline" in paths
        assert "baseline.json" in paths
        assert any("snapshots" in p and "baseline.json" in p for p in paths)

    def test_template_search_paths_still_works(self, tmp_project, global_reqcap_dir):
        config = _make_config()
        paths = core.template_search_paths("login", config)
        assert "login" in paths
        assert "login.yaml" in paths
        assert any("templates" in p and "login.yaml" in p for p in paths)
