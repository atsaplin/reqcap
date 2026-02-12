"""reqcap executor - HTTP request execution."""

import json
import time
from typing import Any

import requests


class RequestResult:
    """Result of an HTTP request."""

    def __init__(self):
        self.status_code: int = 0
        self.headers: dict[str, str] = {}
        self.body: Any = None  # parsed JSON or raw text
        self.elapsed_ms: float = 0
        self.error: str | None = None
        self.raw_text: str = ""


def execute_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: int = 30,
    form_data: dict | None = None,
) -> RequestResult:
    """Execute an HTTP request and return structured result.

    - Attempts to parse response as JSON
    - Falls back to raw text
    - Captures timing
    - Catches exceptions gracefully
    - Never raises - always returns RequestResult with error field set

    When form_data is provided (dict with 'data' and 'files' keys),
    sends a multipart/form-data request instead of a raw body.
    """
    result = RequestResult()

    try:
        kwargs: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "timeout": timeout,
            "allow_redirects": True,
        }

        if form_data:
            # Multipart form-data: let requests set the Content-Type boundary
            req_headers = dict(headers) if headers else {}
            # Remove Content-Type so requests sets multipart boundary
            req_headers.pop("Content-Type", None)
            req_headers.pop("content-type", None)
            kwargs["headers"] = req_headers
            kwargs["data"] = form_data.get("data", {})
            kwargs["files"] = form_data.get("files", {})
        else:
            kwargs["headers"] = headers
            kwargs["data"] = body.encode("utf-8") if body else None

        start = time.monotonic()
        resp = requests.request(**kwargs)
        result.elapsed_ms = (time.monotonic() - start) * 1000

        result.status_code = resp.status_code
        result.headers = dict(resp.headers)
        result.raw_text = resp.text

        try:
            result.body = resp.json()
        except (json.JSONDecodeError, ValueError):
            result.body = resp.text

    except requests.exceptions.Timeout:
        result.error = f"Request timed out after {timeout}s"
    except requests.exceptions.ConnectionError as e:
        result.error = f"Connection error: {e}"
    except requests.exceptions.RequestException as e:
        result.error = f"Request failed: {e}"
    except Exception as e:
        result.error = f"Unexpected error: {e}"

    return result
