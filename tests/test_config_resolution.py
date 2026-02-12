"""Tests for config file resolution order."""

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


def _write_config(path, base_url="http://localhost:3000", templates_dir=None):
    """Helper to write a config YAML file."""
    defaults = {"base_url": base_url}
    if templates_dir is not None:
        defaults["templates_dir"] = templates_dir
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"defaults": defaults}))


# ── resolve_config_path ─────────────────────────────────────────────────


class TestResolveConfigPath:
    def test_explicit_flag_takes_priority(self, tmp_project, global_reqcap_dir):
        """Explicit -c flag should win over everything else."""
        explicit = tmp_project / "custom" / "my.yaml"
        _write_config(explicit)
        # Also create a CWD config and global config to prove they're ignored
        _write_config(tmp_project / ".reqcap.yaml", base_url="cwd")
        _write_config(global_reqcap_dir / "config.yaml", base_url="global")

        result = core.resolve_config_path(str(explicit))
        assert result == explicit

    def test_explicit_flag_nonexistent_returns_none(self, tmp_project):
        """Explicit -c pointing to missing file returns None."""
        result = core.resolve_config_path("/nonexistent/config.yaml")
        assert result is None

    def test_cwd_config_found(self, tmp_project, global_reqcap_dir):
        """CWD .reqcap.yaml is found when no -c flag."""
        _write_config(tmp_project / ".reqcap.yaml")
        _write_config(global_reqcap_dir / "config.yaml", base_url="global")

        result = core.resolve_config_path(None)
        assert result == (tmp_project / ".reqcap.yaml").resolve()

    def test_cwd_config_yml_variant(self, tmp_project):
        """CWD .reqcap.yml variant is found."""
        _write_config(tmp_project / ".reqcap.yml")

        result = core.resolve_config_path(None)
        assert result == (tmp_project / ".reqcap.yml").resolve()

    def test_cwd_reqcap_yaml_variant(self, tmp_project):
        """CWD reqcap.yaml (no dot) variant is found."""
        _write_config(tmp_project / "reqcap.yaml")

        result = core.resolve_config_path(None)
        assert result == (tmp_project / "reqcap.yaml").resolve()

    def test_cwd_config_priority_order(self, tmp_project):
        """First CWD candidate wins: .reqcap.yaml before reqcap.yaml."""
        _write_config(tmp_project / ".reqcap.yaml", base_url="dotted")
        _write_config(tmp_project / "reqcap.yaml", base_url="undotted")

        result = core.resolve_config_path(None)
        assert result.name == ".reqcap.yaml"

    def test_global_config_fallback(self, tmp_project, global_reqcap_dir):
        """~/.reqcap/config.yaml is used when nothing in CWD."""
        _write_config(global_reqcap_dir / "config.yaml", base_url="global")

        result = core.resolve_config_path(None)
        assert result == global_reqcap_dir / "config.yaml"

    def test_no_config_anywhere(self, tmp_project, global_reqcap_dir):
        """Returns None when no config exists anywhere."""
        result = core.resolve_config_path(None)
        assert result is None


# ── load_config ──────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_none_path_returns_defaults(self):
        config = core.load_config(None)
        assert config["defaults"] == {}
        assert config["_config_dir"] is None

    def test_nonexistent_path_returns_defaults(self):
        config = core.load_config("/nonexistent/path.yaml")
        assert config["defaults"] == {}
        assert config["_config_dir"] is None

    def test_valid_config_loads_defaults(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        _write_config(cfg_path, base_url="http://test:8080")
        config = core.load_config(cfg_path)
        assert config["defaults"]["base_url"] == "http://test:8080"

    def test_config_dir_is_set(self, tmp_path):
        cfg_path = tmp_path / "subdir" / "config.yaml"
        _write_config(cfg_path)
        config = core.load_config(cfg_path)
        assert config["_config_dir"] == (tmp_path / "subdir").resolve()

    def test_empty_yaml_returns_empty_defaults(self, tmp_path):
        cfg_path = tmp_path / "empty.yaml"
        cfg_path.write_text("")
        config = core.load_config(cfg_path)
        assert config["defaults"] == {}
        assert config["_config_dir"] == tmp_path.resolve()
