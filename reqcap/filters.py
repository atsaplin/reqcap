"""reqcap filters - response body filtering for minimal token output."""

from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Segment types returned by _parse_path_segments:
#   str              → dict key  (case-insensitive lookup)
#   int              → list index (supports negative)
#   None             → iterate every element in a list
#   (start, stop)    → Python-style slice  e.g. [2:], [:-1], [1:3]
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"^-?\d+$")
_SLICE_RE = re.compile(r"^(-?\d*):(-?\d*)$")


def _parse_path_segments(path: str) -> list[Any]:
    """Parse a filter path into typed segments.

    Supports all of:
      field                  → key
      nested.field           → key, key
      data[].id              → key, iter, key
      data[0].id             → key, 0, key
      data[-1]               → key, -1
      data[2:5]              → key, (2,5)
      data[2:]               → key, (2,None)
      data[:-1]              → key, (None,-1)
      headers[Content-Type]  → key, key   (bracket key access)
      body.items.2           → key, key, 2 (numeric dot segment = index)
    """
    path = path.strip()
    segments: list = []

    for part in path.split("."):
        part = part.strip()
        if not part:
            continue

        # Check for bracket(s) attached to this part: key[...] or just [...]
        # There may be multiple brackets: key[a][0]
        m = re.match(r"^([^\[]*)((?:\[[^\]]*\])+)$", part)
        if m:
            key_part = m.group(1).strip()
            brackets_raw = m.group(2)

            if key_part:
                segments.append(key_part)

            # Extract each [...] group
            for bracket in re.findall(r"\[([^\]]*)\]", brackets_raw):
                bracket = bracket.strip()
                segments.append(_classify_bracket(bracket))
        elif _INT_RE.match(part):
            # Bare numeric segment like body.items.2 → treat as index
            segments.append(int(part))
        else:
            segments.append(part)

    return segments


def _classify_bracket(content: str) -> str | int | tuple[int | None, int | None] | None:
    """Classify the contents of a single [...] bracket."""
    if not content:
        return None  # [] → iterate

    sm = _SLICE_RE.match(content)
    if sm:
        start = int(sm.group(1)) if sm.group(1) else None
        stop = int(sm.group(2)) if sm.group(2) else None
        return (start, stop)

    if _INT_RE.match(content):
        return int(content)

    # Non-numeric → dict key
    return content


# ---------------------------------------------------------------------------
# Case-insensitive dict helpers
# ---------------------------------------------------------------------------


def _ci_get(d: dict[str, Any], key: str) -> tuple[str | None, Any]:
    """Case-insensitive dict lookup.  Returns (actual_key, value)."""
    if key in d:
        return key, d[key]
    lower = key.lower()
    for k, v in d.items():
        if k.lower() == lower:
            return k, v
    return None, None


# ---------------------------------------------------------------------------
# Value extraction
# ---------------------------------------------------------------------------


def _get_value(data: Any, segments: list[Any]) -> tuple[bool, Any]:
    """Walk *simple* segments (str / int) to extract a value.

    Does NOT handle None (iter) or tuple (slice) — those are dealt with at
    a higher level.
    """
    current = data
    for seg in segments:
        if current is None:
            return False, None
        if isinstance(seg, str):
            if isinstance(current, dict):
                actual, val = _ci_get(current, seg)
                if actual is None:
                    return False, None
                current = val
            else:
                return False, None
        elif isinstance(seg, int):
            if isinstance(current, list):
                try:
                    current = current[seg]
                except IndexError:
                    return False, None
            else:
                return False, None
        else:
            # Shouldn't reach here for simple paths
            return False, None
    return True, current


def _resolve_list_segment(arr: list[Any], seg: Any) -> list[tuple[int, Any]]:
    """Given a list and a segment (None / int / slice-tuple), return the
    (index, element) pairs that should be processed.
    """
    if seg is None:
        return list(enumerate(arr))
    if isinstance(seg, int):
        try:
            val = arr[seg]
            # normalise negative index
            idx = seg if seg >= 0 else len(arr) + seg
            return [(idx, val)]
        except IndexError:
            return []
    if isinstance(seg, tuple):
        start, stop = seg
        sl = slice(start, stop)
        items = arr[sl]
        indices = range(*sl.indices(len(arr)))
        return list(zip(indices, items, strict=False))
    return []


# ---------------------------------------------------------------------------
# Building the result tree (set with case-insensitive awareness)
# ---------------------------------------------------------------------------


def _ensure_container(target: Any, segments: list[Any]) -> Any:
    """Walk segments in the *result* tree, creating dicts/lists as needed."""
    for i, seg in enumerate(segments[:-1]):
        next_seg = segments[i + 1]
        next_wants_list = not isinstance(next_seg, str)
        if isinstance(seg, str) and isinstance(target, dict):
            actual, child = _ci_get(target, seg)
            if actual is None:
                child: Any = [] if next_wants_list else {}
                target[seg] = child
            target = child
        elif isinstance(seg, int) and isinstance(target, list):
            while len(target) <= seg:
                target.append({})
            target = target[seg]
    return target


def _set_in_result(result: dict[str, Any], segments: list[Any], value: Any) -> None:
    """Set a scalar value at the given segment path in the result dict."""
    if not segments:
        return
    target = _ensure_container(result, segments)
    last = segments[-1]
    if isinstance(last, str) and isinstance(target, dict):
        target[last] = value
    elif isinstance(last, int) and isinstance(target, list):
        while len(target) <= last:
            target.append(None)
        target[last] = value


# ---------------------------------------------------------------------------
# Applying a single filter spec
# ---------------------------------------------------------------------------


def _apply_spec(data: Any, spec: str, result: dict) -> None:
    """Apply one field-path spec to *data*, merging into *result*."""
    segments = _parse_path_segments(spec)
    if not segments:
        return

    # Find the first "collection" segment: None (iter), tuple (slice), or
    # a negative int (can't build result tree at negative index, must normalise).
    coll_idx = None
    for i, seg in enumerate(segments):
        if seg is None or isinstance(seg, tuple):
            coll_idx = i
            break
        if isinstance(seg, int) and seg < 0:
            coll_idx = i
            break

    if coll_idx is None:
        # Simple scalar path — no iteration / slicing
        found, value = _get_value(data, segments)
        if found:
            _set_in_result(result, segments, value)
        return

    # --- collection path ---
    prefix = segments[:coll_idx]  # path to the list
    coll_seg = segments[coll_idx]  # None | (start,stop) | negative int
    suffix = segments[coll_idx + 1 :]  # path inside each element

    # Resolve prefix
    found, arr = _get_value(data, prefix)
    if not found or not isinstance(arr, list):
        return

    pairs = _resolve_list_segment(arr, coll_seg)
    if not pairs:
        return

    # Navigate / create the list container in result
    container: Any = result
    for idx_p, seg in enumerate(prefix):
        if isinstance(seg, str) and isinstance(container, dict):
            actual, child = _ci_get(container, seg)
            if actual is None:
                is_last = idx_p == len(prefix) - 1
                child: Any = [] if is_last else {}
                container[seg] = child
            container = child
        elif isinstance(seg, int) and isinstance(container, list):
            while len(container) <= seg:
                container.append({})
            container = container[seg]

    if not isinstance(container, list):
        return

    # For iteration (None), we keep indices aligned to original array
    # For slices, we produce a compact list
    if coll_seg is None:
        # Ensure container is at least as long as the source array
        while len(container) < len(arr):
            container.append({})
        for j, item in pairs:
            if suffix:
                found, value = _get_value(item, suffix)
                if found:
                    if not isinstance(container[j], dict):
                        container[j] = {}
                    _set_in_result(container[j], suffix, value)
            else:
                container[j] = item
    else:
        # Slice — produce compact result list
        for _j, item in pairs:
            if suffix:
                found, value = _get_value(item, suffix)
                if found:
                    entry: dict = {}
                    _set_in_result(entry, suffix, value)
                    container.append(entry)
            else:
                container.append(item)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_response(data: Any, field_specs: list[str]) -> Any:
    """Filter response data to include only specified fields.

    Field specs are stripped and matched case-insensitively.
    Supports dot paths, bracket notation, negative indices, and slices.

    Examples:
        filter_response(data, ["id", "name"])
        filter_response(data, ["data[].id", "data[].name"])
        filter_response(data, ["headers[Content-Type]"])
        filter_response(data, ["items[-1].name"])
        filter_response(data, ["items[2:5].id"])
    """
    if not field_specs:
        return data

    cleaned = [s.strip() for s in field_specs if s.strip()]
    if not cleaned or "*" in cleaned:
        return data

    if not isinstance(data, dict):
        return data

    result: dict = {}
    for spec in cleaned:
        _apply_spec(data, spec, result)

    return result


def extract_value(data: Any, path: str) -> Any:
    """Extract a value from data at the given path.

    Used for --export (extracting values from response for chaining).
    Strips a leading ``body.`` prefix for convenience.
    Case-insensitive key matching.
    """
    path = path.strip()
    if path.lower().startswith("body."):
        path = path[5:]

    segments = _parse_path_segments(path)

    # Check for collection segment
    coll_idx = None
    for i, seg in enumerate(segments):
        if seg is None or isinstance(seg, tuple):
            coll_idx = i
            break

    if coll_idx is not None:
        prefix = segments[:coll_idx]
        coll_seg = segments[coll_idx]
        suffix = segments[coll_idx + 1 :]

        found, arr = _get_value(data, prefix)
        if not found or not isinstance(arr, list):
            return None

        pairs = _resolve_list_segment(arr, coll_seg)
        results = []
        for _, item in pairs:
            if suffix:
                ok, val = _get_value(item, suffix)
                if ok:
                    results.append(val)
            else:
                results.append(item)
        return results

    found, value = _get_value(data, segments)
    return value if found else None


def parse_assert(expr: str) -> tuple[str, str, str]:
    """Parse an assertion expression like 'status=200' or 'body.field!=value'.

    Returns (path, operator, expected_str).
    Checks for != first (2-char), then = (1-char).
    """
    # Check for != first
    idx = expr.find("!=")
    if idx != -1:
        return (expr[:idx].strip(), "!=", expr[idx + 2 :].strip())
    # Then =
    idx = expr.find("=")
    if idx != -1:
        return (expr[:idx].strip(), "=", expr[idx + 1 :].strip())
    raise ValueError(f"Invalid assert expression (no = or !=): {expr}")


def evaluate_assert(expr: str, result) -> tuple[bool, str]:
    """Evaluate an assertion against a request result.

    Returns (passed, message).
    On failure, message is 'ASSERT FAILED: expr (actual: val)'.
    On success, message is 'ASSERT PASSED: expr'.
    """
    path, op, expected = parse_assert(expr)

    # Resolve actual value
    if path == "status":
        actual = result.status_code
    elif path.startswith("body."):
        actual = extract_value(result.body, path)
    elif path == "body":
        actual = result.body
    else:
        actual = extract_value(result.body, path)

    # Compare as strings
    actual_str = str(actual) if actual is not None else ""

    if op == "=":
        passed = actual_str == expected
    else:  # !=
        passed = actual_str != expected

    if passed:
        return (True, f"ASSERT PASSED: {expr}")
    return (False, f"ASSERT FAILED: {expr} (actual: {actual_str})")


def format_output(
    result,  # RequestResult from executor.py
    filter_config: dict | None = None,
    verbose: bool = False,
    raw: bool = False,
) -> str:
    """Format the request result for CLI output.

    filter_config keys:
        status      - bool, show STATUS line (default True)
        headers     - bool, show HEADERS section (default False)
        body_fields - list[str], fields to extract (empty = full body)
    """
    if result.error:
        return f"ERROR: {result.error}"

    if raw:
        body = result.body
        if isinstance(body, dict | list):
            return json.dumps(body, indent=2)
        return str(body) if body is not None else ""

    show_status = True
    show_headers = verbose
    body_fields: list[str] = []

    if filter_config:
        show_status = filter_config.get("status", True)
        show_headers = verbose or filter_config.get("headers", False)
        body_fields = filter_config.get("body_fields", [])

    lines: list[str] = []

    if show_status:
        lines.append(f"STATUS: {result.status_code}")

    lines.append(f"TIME: {int(result.elapsed_ms)}ms")

    if show_headers and result.headers:
        lines.append("HEADERS:")
        for key, value in result.headers.items():
            lines.append(f"  {key}: {value}")

    body = result.body
    if body is not None:
        if body_fields and isinstance(body, dict | list):
            body = filter_response(body, body_fields)

        lines.append("BODY:")
        if isinstance(body, dict | list):
            lines.append(json.dumps(body, indent=2))
        else:
            lines.append(str(body))

    return "\n".join(lines)
