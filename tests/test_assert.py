"""Tests for parse_assert, evaluate_assert + CLI integration."""

import os
from unittest.mock import patch

import pytest

from reqcap.cli import main
from reqcap.filters import evaluate_assert, parse_assert
from tests.conftest import make_request_result


@pytest.fixture
def tmp_project(tmp_path):
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


# ── parse_assert ─────────────────────────────────────────────────────────


class TestParseAssert:
    def test_simple_equals(self):
        path, op, expected = parse_assert("status=200")
        assert path == "status"
        assert op == "="
        assert expected == "200"

    def test_not_equals(self):
        path, op, expected = parse_assert("body.error!=null")
        assert path == "body.error"
        assert op == "!="
        assert expected == "null"

    def test_body_path(self):
        path, op, expected = parse_assert("body.data.count=5")
        assert path == "body.data.count"
        assert op == "="
        assert expected == "5"

    def test_value_with_equals(self):
        """Value itself can contain = sign."""
        path, op, expected = parse_assert("body.url=http://example.com?a=1")
        assert path == "body.url"
        assert op == "="
        assert expected == "http://example.com?a=1"

    def test_not_equals_takes_priority(self):
        """!= is checked before = so 'a!=b' isn't parsed as 'a!' = 'b'."""
        path, op, expected = parse_assert("status!=500")
        assert path == "status"
        assert op == "!="
        assert expected == "500"

    def test_invalid_expression(self):
        with pytest.raises(ValueError, match="no = or !="):
            parse_assert("status200")


# ── evaluate_assert ──────────────────────────────────────────────────────


class TestEvaluateAssert:
    def test_status_equals_pass(self):
        result = make_request_result(status_code=200)
        passed, msg = evaluate_assert("status=200", result)
        assert passed
        assert "PASSED" in msg

    def test_status_equals_fail(self):
        result = make_request_result(status_code=404)
        passed, msg = evaluate_assert("status=200", result)
        assert not passed
        assert "FAILED" in msg
        assert "404" in msg

    def test_status_not_equals_pass(self):
        result = make_request_result(status_code=200)
        passed, _msg = evaluate_assert("status!=500", result)
        assert passed

    def test_status_not_equals_fail(self):
        result = make_request_result(status_code=500)
        passed, _msg = evaluate_assert("status!=500", result)
        assert not passed

    def test_body_field_equals(self):
        result = make_request_result(body={"name": "alice"})
        passed, _msg = evaluate_assert("body.name=alice", result)
        assert passed

    def test_body_field_not_equals(self):
        result = make_request_result(body={"count": 0})
        passed, msg = evaluate_assert("body.count!=0", result)
        assert not passed
        assert "FAILED" in msg

    def test_body_nested_field(self):
        result = make_request_result(body={"data": {"id": 42}})
        passed, _msg = evaluate_assert("body.data.id=42", result)
        assert passed

    def test_missing_field_empty_string(self):
        result = make_request_result(body={"a": 1})
        passed, _msg = evaluate_assert("body.missing=", result)
        assert passed  # None → "" matches ""


# ── CLI integration ──────────────────────────────────────────────────────


class TestAssertCLI:
    @patch("reqcap.executor.execute_request")
    def test_assert_pass_exit_0(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(status_code=200, body={"ok": True})
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/health",
                "--assert",
                "status=200",
            ],
        )
        assert result.exit_code == 0

    @patch("reqcap.executor.execute_request")
    def test_assert_fail_exit_1(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(status_code=500, body={})
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/health",
                "--assert",
                "status=200",
            ],
        )
        assert result.exit_code == 1
        assert "ASSERT FAILED" in result.output

    @patch("reqcap.executor.execute_request")
    def test_multiple_asserts_all_pass(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(
            status_code=200,
            body={"name": "test", "active": "true"},
        )
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api",
                "--assert",
                "status=200",
                "--assert",
                "body.name=test",
            ],
        )
        assert result.exit_code == 0

    @patch("reqcap.executor.execute_request")
    def test_first_assert_fails_stops(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(status_code=500, body={})
        result = runner.invoke(
            main,
            [
                "GET",
                "http://localhost:3000/api",
                "--assert",
                "status=200",
                "--assert",
                "status!=500",
            ],
        )
        assert result.exit_code == 1
        assert "status=200" in result.output

    @patch("reqcap.executor.execute_request")
    def test_body_field_assert(self, mock_exec, runner, tmp_project, global_reqcap_dir):
        mock_exec.return_value = make_request_result(
            status_code=200,
            body={"token": "abc123"},
        )
        result = runner.invoke(
            main,
            [
                "POST",
                "http://localhost:3000/login",
                "-b",
                '{"user":"test"}',
                "--assert",
                "body.token!=",
            ],
        )
        assert result.exit_code == 0
