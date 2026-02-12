"""Tests for snapshot save/load/diff/list + CLI integration."""

import json
import os
from unittest.mock import patch

import pytest

from reqcap import core
from reqcap.cli import main
from tests.conftest import make_request_result


@pytest.fixture
def tmp_project(tmp_path):
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


@pytest.fixture
def global_reqcap_dir(tmp_path, monkeypatch):
    fake_global = tmp_path / "fake_home" / ".reqcap"
    fake_global.mkdir(parents=True)
    monkeypatch.setattr(core, "GLOBAL_DIR", fake_global)
    monkeypatch.setattr(core, "GLOBAL_CONFIG", fake_global / "config.yaml")
    monkeypatch.setattr(core, "GLOBAL_TEMPLATES_DIR", fake_global / "templates")
    monkeypatch.setattr(core, "GLOBAL_SNAPSHOTS_DIR", fake_global / "snapshots")
    return fake_global


# ── Unit tests: save/load/diff/list ──────────────────────────────────────


class TestSaveSnapshot:
    def test_creates_file(self, tmp_path):
        result = make_request_result(
            status_code=200,
            body={"message": "ok"},
            headers={"Content-Type": "application/json"},
        )
        path = core.save_snapshot("test1", result, tmp_path / "snaps")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["status_code"] == 200
        assert data["body"] == {"message": "ok"}
        assert "saved_at" in data

    def test_creates_dir_if_missing(self, tmp_path):
        result = make_request_result(body={"ok": True})
        snaps_dir = tmp_path / "deep" / "snaps"
        assert not snaps_dir.exists()
        core.save_snapshot("test2", result, snaps_dir)
        assert snaps_dir.is_dir()

    def test_overwrites_existing(self, tmp_path):
        snaps_dir = tmp_path / "snaps"
        result1 = make_request_result(body={"v": 1})
        core.save_snapshot("overwrite", result1, snaps_dir)
        result2 = make_request_result(body={"v": 2})
        core.save_snapshot("overwrite", result2, snaps_dir)
        data = json.loads((snaps_dir / "overwrite.json").read_text())
        assert data["body"]["v"] == 2


class TestLoadSnapshot:
    def test_loads_existing(self, tmp_project, global_reqcap_dir):
        snaps_dir = tmp_project / "snapshots"
        snaps_dir.mkdir()
        (snaps_dir / "baseline.json").write_text(
            json.dumps(
                {
                    "status_code": 200,
                    "body": {"a": 1},
                    "headers": {},
                    "saved_at": "2024-01-01T00:00:00Z",
                }
            )
        )
        config = {"defaults": {}, "_config_dir": None}
        result = core.load_snapshot("baseline", config)
        assert result is not None
        assert result["status_code"] == 200
        assert result["body"] == {"a": 1}

    def test_returns_none_for_missing(self, tmp_project, global_reqcap_dir):
        config = {"defaults": {}, "_config_dir": None}
        result = core.load_snapshot("nonexistent", config)
        assert result is None

    def test_with_override_dir(self, tmp_project):
        override = tmp_project / "custom_snaps"
        override.mkdir()
        (override / "mine.json").write_text(
            json.dumps(
                {
                    "status_code": 201,
                    "body": "created",
                    "headers": {},
                    "saved_at": "2024-01-01",
                }
            )
        )
        config = {"defaults": {}, "_config_dir": None}
        result = core.load_snapshot("mine", config, str(override))
        assert result is not None
        assert result["status_code"] == 201


class TestDiffSnapshot:
    def test_no_differences(self):
        snapshot = {"status_code": 200, "body": {"a": 1}}
        result = make_request_result(status_code=200, body={"a": 1})
        diffs = core.diff_snapshot(snapshot, result)
        assert diffs == []

    def test_status_code_diff(self):
        snapshot = {"status_code": 200, "body": {"a": 1}}
        result = make_request_result(status_code=404, body={"a": 1})
        diffs = core.diff_snapshot(snapshot, result)
        assert any("status_code" in d for d in diffs)

    def test_body_field_diff(self):
        snapshot = {"status_code": 200, "body": {"name": "alice"}}
        result = make_request_result(status_code=200, body={"name": "bob"})
        diffs = core.diff_snapshot(snapshot, result)
        assert any("name" in d for d in diffs)
        assert any("alice" in d and "bob" in d for d in diffs)

    def test_body_added_field(self):
        snapshot = {"status_code": 200, "body": {"a": 1}}
        result = make_request_result(status_code=200, body={"a": 1, "b": 2})
        diffs = core.diff_snapshot(snapshot, result)
        assert any("b" in d for d in diffs)

    def test_body_removed_field(self):
        snapshot = {"status_code": 200, "body": {"a": 1, "b": 2}}
        result = make_request_result(status_code=200, body={"a": 1})
        diffs = core.diff_snapshot(snapshot, result)
        assert any("b" in d for d in diffs)

    def test_non_dict_body_diff(self):
        snapshot = {"status_code": 200, "body": "hello"}
        result = make_request_result(status_code=200, body="world")
        diffs = core.diff_snapshot(snapshot, result)
        assert len(diffs) == 1
        assert "body" in diffs[0]


class TestListSnapshots:
    def test_lists_all(self, tmp_project, global_reqcap_dir):
        snaps_dir = tmp_project / "snapshots"
        snaps_dir.mkdir()
        for name in ["alpha", "beta"]:
            (snaps_dir / f"{name}.json").write_text(
                json.dumps(
                    {
                        "status_code": 200,
                        "body": {},
                        "headers": {},
                        "saved_at": f"2024-{name}",
                    }
                )
            )
        config = {"defaults": {}, "_config_dir": None}
        sdir, snapshots = core.list_snapshots(config)
        assert sdir is not None
        names = [s["name"] for s in snapshots]
        assert "alpha" in names
        assert "beta" in names

    def test_empty_dir(self, tmp_project, global_reqcap_dir):
        (tmp_project / "snapshots").mkdir()
        config = {"defaults": {}, "_config_dir": None}
        sdir, snapshots = core.list_snapshots(config)
        assert sdir is not None
        assert snapshots == []

    def test_no_dir(self, tmp_project, global_reqcap_dir):
        config = {"defaults": {}, "_config_dir": None}
        sdir, snapshots = core.list_snapshots(config)
        assert sdir is None
        assert snapshots == []


# ── CLI integration tests ────────────────────────────────────────────────


class TestSnapshotCLI:
    @patch("reqcap.executor.execute_request")
    def test_save_creates_snapshot(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(
            status_code=200,
            body={"id": 1, "name": "test"},
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api/users",
                "--snapshot",
                "users_baseline",
            ],
        )
        assert result.exit_code == 0
        assert "Snapshot saved" in result.output
        snap_file = tmp_project / "snapshots" / "users_baseline.json"
        assert snap_file.exists()

    @patch("reqcap.executor.execute_request")
    def test_diff_no_differences(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        # First save
        mock_exec.return_value = make_request_result(
            status_code=200,
            body={"id": 1},
        )
        runner.invoke(main, ["GET", "http://localhost:3000/api", "--snapshot", "base"])
        # Then diff (same response)
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api",
                "--diff",
                "base",
            ],
        )
        assert result.exit_code == 0
        assert "No differences" in result.output

    @patch("reqcap.executor.execute_request")
    def test_diff_with_differences_exits_1(
        self, mock_exec, runner, tmp_project, global_reqcap_dir
    ):
        # Save with status 200
        mock_exec.return_value = make_request_result(status_code=200, body={"v": 1})
        runner.invoke(main, ["GET", "http://localhost:3000/api", "--snapshot", "v1"])
        # Diff with different body
        mock_exec.return_value = make_request_result(status_code=200, body={"v": 2})
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api",
                "--diff",
                "v1",
            ],
        )
        assert result.exit_code == 1
        assert "Differences found" in result.output

    @patch("reqcap.executor.execute_request")
    def test_diff_missing_snapshot_exits_1(
        self, mock_exec, runner, tmp_project, global_reqcap_dir
    ):
        mock_exec.return_value = make_request_result(body={})
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api",
                "--diff",
                "nonexistent",
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("reqcap.executor.execute_request")
    def test_list_snapshots(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        # Create a snapshot first
        mock_exec.return_value = make_request_result(body={"ok": True})
        runner.invoke(main, ["GET", "http://localhost:3000/api", "--snapshot", "first"])
        # List
        result = runner.invoke(main, ["--list-snapshots"])
        assert result.exit_code == 0
        assert "first" in result.output

    def test_list_snapshots_empty(self, runner, tmp_project, global_reqcap_dir):
        result = runner.invoke(main, ["--list-snapshots"])
        assert result.exit_code == 0
        assert "No snapshots" in result.output
