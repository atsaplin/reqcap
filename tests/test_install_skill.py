"""Tests for --install-skill CLI option."""

import os

import pytest
from click.testing import CliRunner

from reqcap.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestInstallSkill:
    def test_claude_agent(self, runner, tmp_path):
        os.chdir(tmp_path)
        result = runner.invoke(main, ["--install-skill", "claude"])
        assert result.exit_code == 0
        target = tmp_path / ".claude" / "skills" / "reqcap-skill"
        assert (target / "SKILL.md").exists()
        assert (target / "references" / "templates.md").exists()
        assert "Installed reqcap skill to" in result.output

    def test_cursor_agent(self, runner, tmp_path):
        os.chdir(tmp_path)
        result = runner.invoke(main, ["--install-skill", "cursor"])
        assert result.exit_code == 0
        assert (tmp_path / ".cursor" / "skills" / "reqcap-skill" / "SKILL.md").exists()

    def test_arbitrary_agent_name(self, runner, tmp_path):
        """Any string works as agent name — not restricted to known agents."""
        os.chdir(tmp_path)
        result = runner.invoke(main, ["--install-skill", "blah"])
        assert result.exit_code == 0
        target = tmp_path / ".blah" / "skills" / "reqcap-skill"
        assert (target / "SKILL.md").exists()
        assert (target / "references" / "templates.md").exists()

    def test_overwrites_cleanly(self, runner, tmp_path):
        """Re-running install overwrites existing files without error."""
        os.chdir(tmp_path)
        runner.invoke(main, ["--install-skill", "claude"])
        result = runner.invoke(main, ["--install-skill", "claude"])
        assert result.exit_code == 0
        assert (tmp_path / ".claude" / "skills" / "reqcap-skill" / "SKILL.md").exists()

    def test_skill_md_has_content(self, runner, tmp_path):
        """Installed SKILL.md is not empty."""
        os.chdir(tmp_path)
        runner.invoke(main, ["--install-skill", "claude"])
        skill_md = tmp_path / ".claude" / "skills" / "reqcap-skill" / "SKILL.md"
        content = skill_md.read_text()
        assert "reqcap" in content
        assert len(content) > 100
