"""Tests for template auto-snapshot (snapshot: key)."""

import json
import os
from unittest.mock import patch

import yaml

from reqcap.cli import main
from tests.conftest import make_request_result


def _write_config(path, base_url=None, snapshots_dir=None):
    defaults = {}
    if base_url:
        defaults["base_url"] = base_url
    if snapshots_dir is not None:
        defaults["snapshots_dir"] = snapshots_dir
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"defaults": defaults}))


def _write_template(path, **fields):
    tpl = {"method": "GET", "url": "/health"}
    tpl.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(tpl))


class TestAutoSnapshotEnabled:
    """snapshot.enabled: true auto-saves a snapshot."""

    @patch("reqcap.executor.execute_request")
    def test_creates_snapshot_file(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            method="GET",
            url="/health",
            snapshot={"enabled": True},
        )

        mock_exec.return_value = make_request_result(body={"status": "ok"}, elapsed_ms=15)

        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 0

        # Snapshot file should exist named after template
        snap_file = snap_dir / "health.json"
        assert snap_file.exists()
        data = json.loads(snap_file.read_text())
        assert data["status_code"] == 200
        assert data["body"] == {"status": "ok"}

        # Stderr should report snapshot saved
        assert "Snapshot saved" in result.output


class TestAutoSnapshotCustomName:
    """snapshot.name overrides the template name for the snapshot file."""

    @patch("reqcap.executor.execute_request")
    def test_uses_custom_name(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            method="GET",
            url="/health",
            snapshot={"enabled": True, "name": "health-baseline"},
        )

        mock_exec.return_value = make_request_result(body={"ok": True})

        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 0

        # Custom name used for snapshot file
        assert (snap_dir / "health-baseline.json").exists()
        # Template name NOT used
        assert not (snap_dir / "health.json").exists()


class TestAutoSnapshotDisabled:
    """snapshot.enabled: false does not save a snapshot."""

    @patch("reqcap.executor.execute_request")
    def test_no_snapshot_when_disabled(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            method="GET",
            url="/health",
            snapshot={"enabled": False},
        )

        mock_exec.return_value = make_request_result(body={"ok": True})

        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 0
        assert not (snap_dir / "health.json").exists()
        assert "Snapshot saved" not in result.output


class TestAutoSnapshotNoKey:
    """Templates without snapshot key work unchanged."""

    @patch("reqcap.executor.execute_request")
    def test_no_snapshot_without_key(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            method="GET",
            url="/health",
        )

        mock_exec.return_value = make_request_result(body={"ok": True})

        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 0
        assert not (snap_dir / "health.json").exists()


class TestAutoSnapshotCreatesDir:
    """Auto-snapshot creates the snapshots directory if it doesn't exist."""

    @patch("reqcap.executor.execute_request")
    def test_creates_snapshots_dir(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        # Do NOT create snapshots/ dir — auto-snapshot should create it
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            method="GET",
            url="/health",
            snapshot={"enabled": True},
        )

        mock_exec.return_value = make_request_result(body={"ok": True})

        result = runner.invoke(main, ["-t", "health"])
        assert result.exit_code == 0

        snap_dir = tmp_path / "snapshots"
        assert snap_dir.exists()
        assert (snap_dir / "health.json").exists()


class TestAutoSnapshotWithManualSnapshot:
    """--snapshot and snapshot: both work together."""

    @patch("reqcap.executor.execute_request")
    def test_both_snapshots_saved(self, mock_exec, runner, tmp_path, global_reqcap_dir):
        os.chdir(tmp_path)
        _write_config(tmp_path / ".reqcap.yaml", base_url="http://api:3000")
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        tpl_dir = tmp_path / "templates"

        _write_template(
            tpl_dir / "health.yaml",
            name="health",
            method="GET",
            url="/health",
            snapshot={"enabled": True, "name": "auto"},
        )

        mock_exec.return_value = make_request_result(body={"ok": True})

        result = runner.invoke(main, ["-t", "health", "--snapshot", "manual"])
        assert result.exit_code == 0

        # Both snapshots should exist
        assert (snap_dir / "manual.json").exists()
        assert (snap_dir / "auto.json").exists()
