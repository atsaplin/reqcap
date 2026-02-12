"""Tests for parse_form_fields + executor form_data + CLI integration."""

import os
from unittest.mock import patch

import pytest

from reqcap.cli import main
from reqcap.core import parse_form_fields
from tests.conftest import make_request_result


@pytest.fixture
def tmp_project(tmp_path):
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


# ── parse_form_fields ────────────────────────────────────────────────────


class TestParseFormFields:
    def test_text_field(self):
        result = parse_form_fields(("name=test",))
        assert result["data"] == {"name": "test"}
        assert result["files"] == {}

    def test_multiple_text_fields(self):
        result = parse_form_fields(("name=test", "email=a@b.com"))
        assert result["data"] == {"name": "test", "email": "a@b.com"}

    def test_file_field(self, tmp_path):
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"\xff\xd8\xff\xe0")
        result = parse_form_fields((f"image=@{test_file}",))
        assert "image" in result["files"]
        name, fh, mime = result["files"]["image"]
        assert name == "photo.jpg"
        assert mime == "image/jpeg"
        fh.close()

    def test_mixed_fields(self, tmp_path):
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"%PDF")
        result = parse_form_fields(("title=My Doc", f"file=@{test_file}"))
        assert result["data"] == {"title": "My Doc"}
        assert "file" in result["files"]
        result["files"]["file"][1].close()

    def test_value_with_equals(self):
        result = parse_form_fields(("url=http://example.com?a=1",))
        assert result["data"]["url"] == "http://example.com?a=1"

    def test_no_equals_ignored(self):
        result = parse_form_fields(("invalid_spec",))
        assert result["data"] == {}
        assert result["files"] == {}

    def test_empty_value(self):
        result = parse_form_fields(("key=",))
        assert result["data"] == {"key": ""}


# ── Executor form_data ───────────────────────────────────────────────────


class TestExecutorFormData:
    @patch("reqcap.executor.requests.request")
    def test_form_data_passed(self, mock_req, tmp_path):

        from reqcap.executor import execute_request

        mock_resp = type(
            "Response",
            (),
            {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "text": '{"ok":true}',
                "json": lambda self: {"ok": True},
            },
        )()
        mock_req.return_value = mock_resp

        form_data = {"data": {"name": "test"}, "files": {}}
        execute_request(
            method="POST",
            url="http://localhost:3000/upload",
            headers={"Content-Type": "application/json"},
            form_data=form_data,
        )
        # Content-Type should have been stripped for multipart
        call_kwargs = mock_req.call_args[1]
        assert "Content-Type" not in call_kwargs.get("headers", {})
        assert call_kwargs["data"] == {"name": "test"}

    @patch("reqcap.executor.requests.request")
    def test_no_form_data_uses_body(self, mock_req):
        from reqcap.executor import execute_request

        mock_resp = type(
            "Response",
            (),
            {
                "status_code": 200,
                "headers": {},
                "text": "{}",
                "json": lambda self: {},
            },
        )()
        mock_req.return_value = mock_resp

        execute_request(method="POST", url="http://localhost:3000/api", body='{"a":1}')
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["data"] == b'{"a":1}'


# ── CLI integration ──────────────────────────────────────────────────────


class TestFormCLI:
    @patch("reqcap.executor.execute_request")
    def test_form_basic(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(body={"ok": True})
        result = runner.invoke(
            main,
            [
                "POST",
                "http://localhost:3000/api",
                "--form",
                "name=test",
                "--form",
                "email=a@b.com",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_exec.call_args[1]
        assert call_kwargs["form_data"] is not None
        assert call_kwargs["form_data"]["data"]["name"] == "test"

    @patch("reqcap.executor.execute_request")
    def test_form_with_file(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        test_file = tmp_project / "readme.md"
        test_file.write_text("# Hello")
        mock_exec.return_value = make_request_result(body={"ok": True})
        result = runner.invoke(
            main,
            [
                "POST",
                "http://localhost:3000/upload",
                "--form",
                "name=test",
                "--form",
                f"file=@{test_file}",
            ],
        )
        assert result.exit_code == 0
        call_kwargs = mock_exec.call_args[1]
        assert "file" in call_kwargs["form_data"]["files"]

    def test_form_and_body_mutually_exclusive(self, runner, tmp_project, global_reqcap_dir):
        result = runner.invoke(
            main,
            [
                "POST",
                "http://localhost:3000/api",
                "--form",
                "name=test",
                "-b",
                '{"name":"test"}',
            ],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output
