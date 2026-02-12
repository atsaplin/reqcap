"""Tests for --init scaffolding, framework detection, skip-if-exists."""

import os

import pytest

from reqcap.cli import _detect_base_url, main


@pytest.fixture
def tmp_project(tmp_path):
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


# ── _detect_base_url ─────────────────────────────────────────────────────


class TestDetectBaseUrl:
    def test_node_project(self, tmp_project):
        (tmp_project / "package.json").write_text("{}")
        assert _detect_base_url() == "http://localhost:3000"

    def test_python_pyproject(self, tmp_project):
        (tmp_project / "pyproject.toml").write_text("[project]")
        assert _detect_base_url() == "http://localhost:8000"

    def test_python_requirements(self, tmp_project):
        (tmp_project / "requirements.txt").write_text("flask")
        assert _detect_base_url() == "http://localhost:8000"

    def test_go_project(self, tmp_project):
        (tmp_project / "go.mod").write_text("module example.com/myapp")
        assert _detect_base_url() == "http://localhost:8080"

    def test_ruby_project(self, tmp_project):
        (tmp_project / "Gemfile").write_text('gem "rails"')
        assert _detect_base_url() == "http://localhost:3000"

    def test_rust_project(self, tmp_project):
        (tmp_project / "Cargo.toml").write_text("[package]")
        assert _detect_base_url() == "http://localhost:8080"

    def test_default_fallback(self, tmp_project):
        assert _detect_base_url() == "http://localhost:3000"


# ── --init CLI ───────────────────────────────────────────────────────────


class TestInitCLI:
    def test_scaffolds_all(self, runner, tmp_project):
        result = runner.invoke(main, ["--init"])
        assert result.exit_code == 0
        assert (tmp_project / ".reqcap.yaml").exists()
        assert (tmp_project / "templates").is_dir()
        assert (tmp_project / "snapshots").is_dir()
        assert "created" in result.output

    def test_config_content(self, runner, tmp_project):
        runner.invoke(main, ["--init"])
        content = (tmp_project / ".reqcap.yaml").read_text()
        assert "defaults:" in content
        assert "base_url:" in content
        assert "templates_dir:" in content
        assert "snapshots_dir:" in content

    def test_detects_node(self, runner, tmp_project):
        (tmp_project / "package.json").write_text("{}")
        runner.invoke(main, ["--init"])
        content = (tmp_project / ".reqcap.yaml").read_text()
        assert "3000" in content

    def test_detects_python(self, runner, tmp_project):
        (tmp_project / "pyproject.toml").write_text("[project]")
        runner.invoke(main, ["--init"])
        content = (tmp_project / ".reqcap.yaml").read_text()
        assert "8000" in content

    def test_skip_existing_config(self, runner, tmp_project):
        (tmp_project / ".reqcap.yaml").write_text("existing: true")
        runner.invoke(main, ["--init"])
        # Should not overwrite
        assert (tmp_project / ".reqcap.yaml").read_text() == "existing: true"

    def test_skip_existing_dirs(self, runner, tmp_project):
        (tmp_project / "templates").mkdir()
        (tmp_project / "templates" / "keep.yaml").write_text("keep: true")
        result = runner.invoke(main, ["--init"])
        assert result.exit_code == 0
        assert "skipped" in result.output
        # Original file preserved
        assert (tmp_project / "templates" / "keep.yaml").exists()

    def test_idempotent(self, runner, tmp_project):
        """Running init twice doesn't error or overwrite."""
        result1 = runner.invoke(main, ["--init"])
        assert result1.exit_code == 0
        result2 = runner.invoke(main, ["--init"])
        assert result2.exit_code == 0
        assert "skipped" in result2.output
