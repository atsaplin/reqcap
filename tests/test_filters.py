"""Scenario tests for response filtering (filter_response + format_output)."""

from reqcap.filters import filter_response, format_output
from tests.conftest import make_request_result

# ── Scenario 4: Filter specific fields ────────────────────────────────────


class TestFilterSpecificFields:
    """filter_response extracts requested fields from JSON bodies."""

    def test_top_level_fields(self):
        data = {"id": 1, "name": "Alice", "email": "a@b.com", "role": "admin"}
        result = filter_response(data, ["id", "name"])
        assert result == {"id": 1, "name": "Alice"}

    def test_nested_field(self):
        data = {"user": {"profile": {"name": "Bob", "age": 30}, "id": 1}}
        result = filter_response(data, ["user.profile.name"])
        assert result == {"user": {"profile": {"name": "Bob"}}}

    def test_array_iteration(self):
        data = {"data": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]}
        result = filter_response(data, ["data[].id"])
        assert result == {"data": [{"id": 1}, {"id": 2}]}

    def test_single_array_index(self):
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
        result = filter_response(data, ["items[0].id"])
        assert result == {"items": [{"id": 1}]}

    def test_wildcard_returns_everything(self):
        data = {"id": 1, "name": "Alice", "extra": True}
        result = filter_response(data, ["*"])
        assert result == data

    def test_empty_list_returns_data(self):
        data = {"id": 1, "name": "Alice"}
        result = filter_response(data, [])
        assert result == data

    def test_top_level_array_not_filtered(self):
        """BUG: top-level JSON array silently bypasses filtering."""
        data = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        result = filter_response(data, ["id"])
        assert result == data  # BUG: returns unchanged, filter silently ignored


# ── Scenario 5: Filter non-existent field (BUG) ──────────────────────────


class TestFilterNonExistentField:
    """BUG: Filtering for non-existent fields returns {} instead of warning."""

    def test_missing_field_returns_empty(self):
        data = {"id": 1, "name": "Alice"}
        result = filter_response(data, ["nonexistent"])
        assert result == {}  # BUG: no warning, just empty dict

    def test_mix_existing_and_missing(self):
        data = {"id": 1, "name": "Alice"}
        result = filter_response(data, ["id", "nonexistent"])
        assert result == {"id": 1}  # only existing field returned

    def test_nested_missing(self):
        data = {"user": {"name": "Bob"}}
        result = filter_response(data, ["user.missing.deep"])
        assert result == {}

    def test_array_missing_field(self):
        data = {"data": [{"id": 1}, {"id": 2}]}
        result = filter_response(data, ["data[].missing"])
        # Array containers are created but fields are empty
        assert result == {"data": [{}, {}]}


# ── Format integration: filter_config in format_output ────────────────────


class TestFormatOutputFiltering:
    """filter_config body_fields are applied during format_output."""

    def test_body_fields_applied(self):
        r = make_request_result(
            status_code=200,
            body={"id": 1, "name": "Alice", "secret": "xyz"},
        )
        fc = {"status": True, "headers": False, "body_fields": ["id", "name"]}
        output = format_output(r, filter_config=fc)
        assert '"id": 1' in output
        assert '"name": "Alice"' in output
        assert "secret" not in output

    def test_non_json_passthrough(self):
        """Non-JSON body is passed through even with body_fields set."""
        r = make_request_result(status_code=200, body="plain text response")
        fc = {"status": True, "headers": False, "body_fields": ["id"]}
        output = format_output(r, filter_config=fc)
        assert "plain text response" in output

    def test_no_filter_config_shows_all(self):
        r = make_request_result(
            status_code=200,
            body={"id": 1, "name": "Alice", "secret": "xyz"},
        )
        output = format_output(r, filter_config=None)
        assert '"secret": "xyz"' in output

    def test_null_body_with_filter(self):
        """Null body skips BODY section entirely even with filter."""
        r = make_request_result(status_code=204, body=None)
        fc = {"status": True, "headers": False, "body_fields": ["id"]}
        output = format_output(r, filter_config=fc)
        assert "STATUS: 204" in output
        assert "BODY:" not in output
