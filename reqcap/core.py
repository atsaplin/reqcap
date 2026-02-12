"""reqcap core - config loading, variable resolution, auth."""

import base64
import datetime
import json
import os
import re
import shlex
import time as _time
import uuid
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

GLOBAL_DIR = Path.home() / ".reqcap"
GLOBAL_CONFIG = GLOBAL_DIR / "config.yaml"
GLOBAL_TEMPLATES_DIR = GLOBAL_DIR / "templates"
GLOBAL_SNAPSHOTS_DIR = GLOBAL_DIR / "snapshots"

CWD_CONFIG_CANDIDATES = [
    ".reqcap.yaml",
    ".reqcap.yml",
    "reqcap.yaml",
    "reqcap.yml",
]


def resolve_path(
    candidates: list[Path],
    default: Path | None = None,
) -> Path | None:
    """Return the first existing path from candidates.

    Works for both files and directories — just checks .exists().
    If none exist, returns default (which the caller can create).
    """
    for p in candidates:
        if p.exists():
            return p.resolve()
    return default


def resolve_config_path(config_file: str | None) -> Path | None:
    """Find the config file to use.

    Resolution order:
      1. Explicit -c flag (hard — no fallthrough if missing)
      2. .reqcap.yaml (variants) in CWD
      3. ~/.reqcap/config.yaml
    """
    if config_file:
        return resolve_path([Path(config_file)])
    return resolve_path([Path(c) for c in CWD_CONFIG_CANDIDATES] + [GLOBAL_CONFIG])


def load_config(config_path: str | Path | None) -> dict:
    """Load YAML config file. Returns empty dict sections if not found.

    Stores '_config_dir' in the returned dict so template resolution
    can resolve paths relative to the config file.
    """
    if config_path is None:
        return {"defaults": {}, "_config_dir": None}
    path = Path(config_path)
    if not path.exists():
        return {"defaults": {}, "_config_dir": None}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return {
        "defaults": data.get("defaults") or {},
        "_config_dir": path.resolve().parent,
    }


def load_env(env_file: str | None, base_dir: str = ".") -> dict[str, str]:
    """Load .env file and merge with os.environ.

    Returns combined dict with .env values taking precedence over os.environ
    for explicit vars, but os.environ available as fallback.
    """
    env = dict(os.environ)
    if env_file:
        dotenv_path = Path(base_dir) / env_file
        if dotenv_path.exists():
            dotenv_vars = dotenv_values(str(dotenv_path))
            env.update({k: v for k, v in dotenv_vars.items() if v is not None})
    return env


def resolve_value(value: str | None, env: dict[str, str]) -> str | None:
    """Resolve $VAR and ${VAR} references in a string value.

    $VAR or ${VAR} -> look up in env dict, then os.environ.
    Returns the resolved value or original if no match.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    def _replace(m: re.Match) -> str:
        var_name = m.group(1) or m.group(2)
        return env.get(var_name, os.environ.get(var_name, m.group(0)))

    return re.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _replace, value)


def resolve_placeholders(
    text: str,
    env: dict[str, str],
    extra_vars: dict[str, str] | None = None,
) -> str:
    """Resolve {{...}} placeholders in text.

    Supported:
    - {{env.VAR}} -> environment variable
    - {{uuid}} or {{uuidv4}} -> random UUID v4
    - {{timestamp}} -> unix timestamp seconds
    - {{timestamp_ms}} -> unix timestamp milliseconds
    - {{date}} -> ISO date string
    - {{VAR}} -> look up in extra_vars dict (template variables)
    """
    if not isinstance(text, str):
        return text

    def _replace(m: re.Match) -> str:
        key = m.group(1).strip()

        # env.VAR
        if key.startswith("env."):
            var = key[4:]
            return env.get(var, os.environ.get(var, m.group(0)))

        # built-in generators
        if key in ("uuid", "uuidv4"):
            return str(uuid.uuid4())
        if key == "timestamp":
            return str(int(_time.time()))
        if key == "timestamp_ms":
            return str(int(_time.time() * 1000))
        if key == "date":
            return datetime.datetime.now(datetime.timezone.utc).isoformat()

        # extra_vars lookup (template chaining)
        if extra_vars and key in extra_vars:
            return str(extra_vars[key])

        return m.group(0)

    return re.sub(r"\{\{(.+?)\}\}", _replace, text)


def resolve_in_obj(
    obj: Any,
    env: dict[str, str],
    extra_vars: dict[str, str] | None = None,
) -> Any:
    """Recursively resolve placeholders in dicts, lists, and strings."""
    if isinstance(obj, str):
        resolved = resolve_value(obj, env)
        if isinstance(resolved, str):
            resolved = resolve_placeholders(resolved, env, extra_vars)
        return resolved
    if isinstance(obj, dict):
        return {k: resolve_in_obj(v, env, extra_vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_in_obj(item, env, extra_vars) for item in obj]
    return obj


def set_at_path(obj: dict, path: str, value: Any) -> None:
    """Set a value at a dot-notation path in a nested dict.

    Supports: "data.message", "messages[0].content", "nested.array[1].field"
    """
    # Tokenize: split on dots, then handle array indices
    tokens: list[str | int] = []
    for part in path.split("."):
        # Check for array indices like "messages[0]"
        m = re.match(r"^([^\[]*)\[(\d+)\]$", part)
        if m:
            if m.group(1):
                tokens.append(m.group(1))
            tokens.append(int(m.group(2)))
        else:
            tokens.append(part)

    current: Any = obj
    for i, token in enumerate(tokens[:-1]):
        next_token = tokens[i + 1]
        if isinstance(token, int):
            while len(current) <= token:
                current.append({} if isinstance(next_token, str) else [])
            current = current[token]
        else:
            if token not in current:
                current[token] = [] if isinstance(next_token, int) else {}
            current = current[token]

    last = tokens[-1]
    if isinstance(last, int):
        while len(current) <= last:
            current.append(None)
        current[last] = value
    else:
        current[last] = value


def build_auth_headers(
    auth_config: dict | None,
    env: dict[str, str],
) -> dict[str, str]:
    """Build authentication headers from auth config.

    Supports:
    - bearer: Authorization: Bearer <token>
    - api-key: custom header with token
    - basic: Authorization: Basic <b64>
    """
    if not auth_config:
        return {}

    auth_type = auth_config.get("type", "").lower()

    if auth_type == "bearer":
        token = resolve_value(auth_config.get("token", ""), env) or ""
        return {"Authorization": f"Bearer {token}"}

    if auth_type == "api-key":
        token = resolve_value(auth_config.get("token", ""), env) or ""
        header = auth_config.get("header", "X-API-Key")
        return {header: token}

    if auth_type == "basic":
        username = resolve_value(auth_config.get("username", ""), env) or ""
        password = resolve_value(auth_config.get("password", ""), env) or ""
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}

    return {}


def _resource_candidates(
    resource_name: str,
    cli_override: str | None,
    config: dict,
) -> list[Path]:
    """Build the ordered candidate list for a named resource directory."""
    # CLI override — absolute or relative to CWD
    if cli_override:
        p = Path(cli_override)
        if not p.is_absolute():
            p = Path.cwd() / p
        return [p]  # hard override — no fallthrough

    candidates: list[Path] = []

    # Config value — relative to config file's directory
    defaults = config.get("defaults", {})
    config_value = defaults.get(f"{resource_name}_dir")
    config_dir = config.get("_config_dir")
    if config_value:
        p = Path(config_value)
        if not p.is_absolute() and config_dir:
            p = Path(config_dir) / p
        candidates.append(p)

    # CWD
    candidates.append(Path(resource_name))
    # Global
    candidates.append(GLOBAL_DIR / resource_name)

    return candidates


def resolve_resource_dir(
    resource_name: str,
    cli_override: str | None,
    config: dict,
    default: Path | None = None,
) -> Path | None:
    """Find a resource directory by name.

    Resolution order:
      1. cli_override (absolute or relative to CWD; hard — no fallthrough)
      2. {resource_name}_dir from config defaults (relative to config file)
      3. ./{resource_name}/ in CWD
      4. ~/.reqcap/{resource_name}/

    If none found, returns default (caller can create it).
    """
    candidates = _resource_candidates(resource_name, cli_override, config)
    return resolve_path(candidates, default=default)


def resolve_templates_dir(
    cli_templates_dir: str | None,
    config: dict,
) -> Path | None:
    """Find the templates directory to use.

    Resolution order:
      1. --templates-dir CLI flag
      2. templates_dir from config (resolved relative to config file)
      3. ./templates/ in CWD
      4. ~/.reqcap/templates/

    Returns the resolved Path if found, None otherwise.
    """
    return resolve_resource_dir("templates", cli_templates_dir, config)


def load_template(
    name_or_path: str,
    config: dict,
    templates_dir_override: str | None = None,
) -> dict | None:
    """Load a template from a YAML file.

    Resolution order:
      1. Exact/absolute file path
      2. Resolved templates directory + name.yaml
    """
    # 1. Direct/absolute path
    p = Path(name_or_path)
    if p.is_absolute() and p.exists() and p.is_file():
        return _read_template_file(p)
    if p.exists() and p.is_file():
        return _read_template_file(p)
    for ext in (".yaml", ".yml"):
        candidate = Path(name_or_path + ext)
        if candidate.exists():
            return _read_template_file(candidate)

    # 2. Look in the resolved templates directory
    tdir = resolve_templates_dir(templates_dir_override, config)
    if tdir:
        found = _find_in_dir(tdir, name_or_path)
        if found:
            return found

    return None


def resource_search_paths(
    resource_name: str,
    name: str,
    ext: str,
    config: dict,
    cli_override: str | None = None,
) -> list[str]:
    """Return human-readable list of paths checked for a named resource."""
    paths = [name, f"{name}{ext}"]
    candidates = _resource_candidates(resource_name, cli_override, config)
    for c in candidates:
        paths.append(str(c / f"{name}{ext}"))
    return paths


def template_search_paths(
    name: str,
    config: dict,
    templates_dir_override: str | None = None,
) -> list[str]:
    """Return human-readable list of paths that were checked for a template."""
    return resource_search_paths("templates", name, ".yaml", config, templates_dir_override)


def list_templates(
    config: dict,
    templates_dir_override: str | None = None,
) -> tuple[Path | None, list[dict]]:
    """List all template files from the resolved templates directory.

    Returns (resolved_dir, list_of_template_dicts).
    """
    tdir = resolve_templates_dir(templates_dir_override, config)
    if not tdir or not tdir.is_dir():
        return (tdir, [])

    templates: list[dict] = []
    for f in sorted(tdir.iterdir()):
        if f.suffix in (".yaml", ".yml") and f.is_file():
            tmpl = _read_template_file(f)
            if tmpl:
                templates.append(tmpl)
    return (tdir, templates)


def _find_in_dir(directory: Path, name: str) -> dict | None:
    """Look for name.yaml or name.yml in a directory."""
    if not directory.is_dir():
        return None
    for ext in (".yaml", ".yml"):
        candidate = directory / (name + ext)
        if candidate.exists():
            return _read_template_file(candidate)
    return None


def _read_template_file(path: Path) -> dict | None:
    """Read and validate a single template YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        # Default the name to the filename stem if not set
        if "name" not in data:
            data["name"] = path.stem
        return data
    except Exception:
        return None


def parse_curl(curl_command: str) -> dict:
    """Parse a curl command string into components.

    Returns: {"method": ..., "url": ..., "headers": {...}, "body": ..., "error": None}
    Handles: -X, -H, -d, --data, --data-raw, --json, quoted strings, escaped newlines.
    """
    result: dict[str, Any] = {
        "method": "GET",
        "url": "",
        "headers": {},
        "body": None,
        "error": None,
    }

    # Normalize line continuations
    cmd = curl_command.replace("\\\n", " ").replace("\\\r\n", " ").strip()

    try:
        tokens = shlex.split(cmd)
    except ValueError as e:
        result["error"] = f"Parse error: {e}"
        return result

    # Strip leading "curl" if present
    if tokens and tokens[0] == "curl":
        tokens = tokens[1:]

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request") and i + 1 < len(tokens):
            result["method"] = tokens[i + 1].upper()
            i += 2
        elif tok in ("-H", "--header") and i + 1 < len(tokens):
            header = tokens[i + 1]
            colon = header.find(":")
            if colon != -1:
                key = header[:colon].strip()
                val = header[colon + 1 :].strip()
                result["headers"][key] = val
            i += 2
        elif tok in ("-d", "--data", "--data-raw") and i + 1 < len(tokens):
            result["body"] = tokens[i + 1]
            if result["method"] == "GET":
                result["method"] = "POST"
            i += 2
        elif tok == "--json" and i + 1 < len(tokens):
            result["body"] = tokens[i + 1]
            result["headers"].setdefault("Content-Type", "application/json")
            result["headers"].setdefault("Accept", "application/json")
            if result["method"] == "GET":
                result["method"] = "POST"
            i += 2
        elif tok.startswith("-"):
            # Skip unknown flags; consume next token if it looks like a value
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 2
            else:
                i += 1
        else:
            # Positional argument = URL
            if not result["url"]:
                result["url"] = tok
            i += 1

    return result


def build_request_from_template(
    config: dict,
    template: dict,
    variables: dict[str, str],
    env: dict[str, str],
) -> dict:
    """Build a complete request dict from a loaded template.

    Returns: {
        "method": ..., "url": ..., "headers": {...},
        "body": ..., "filter": {...}, "exports": {...}, "stream": False,
    }
    """
    defaults = config.get("defaults", {})

    # Method
    method = template.get("method", "GET").upper()

    # URL: resolve base_url then append template url
    base_url = template.get("base_url") or defaults.get("base_url", "")
    base_url = resolve_value(base_url, env) or ""
    base_url = resolve_placeholders(base_url, env, variables)
    base_url = base_url.rstrip("/")

    path = template.get("url", "")
    path = resolve_placeholders(path, env, variables)
    if path and not path.startswith("/"):
        path = "/" + path

    url = base_url + path

    # Headers: defaults + template + auth
    headers = dict(defaults.get("headers") or {})
    headers.update(template.get("headers") or {})

    # Auth: template auth overrides default auth
    auth_config = template.get("auth") or defaults.get("auth")
    auth_headers = build_auth_headers(auth_config, env)
    # Resolve placeholders in auth headers (e.g. {{token}})
    auth_headers = {k: resolve_placeholders(v, env, variables) for k, v in auth_headers.items()}
    headers.update(auth_headers)

    # Resolve header values
    headers = {
        k: resolve_placeholders(resolve_value(v, env) or v, env, variables)
        for k, v in headers.items()
    }

    # Body: apply field values, then resolve
    body = None
    if template.get("body") is not None:
        import copy

        body_obj = copy.deepcopy(template["body"])

        # Apply fields from variables
        for field in template.get("fields", []):
            field_name = field.get("name", "")
            field_path = field.get("path", field_name)
            if field_name in variables:
                set_at_path(body_obj, field_path, variables[field_name])

        # Resolve placeholders in body
        body_obj = resolve_in_obj(body_obj, env, variables)
        body = json.dumps(body_obj)

    # Filter: template overrides default
    default_filter = defaults.get("filter", {})
    template_filter = template.get("filter")
    if template_filter is not None:
        filt = {**default_filter, **template_filter}
    else:
        filt = dict(default_filter) if default_filter else {}

    # Exports
    exports = template.get("exports") or {}

    # Stream
    stream = template.get("stream", False)

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "filter": filt,
        "exports": exports,
        "stream": stream,
    }


# ── Snapshots ────────────────────────────────────────────────────────────


def save_snapshot(name: str, result, snapshots_dir: Path) -> Path:
    """Save a response snapshot as JSON.

    Stores {status_code, headers, body, saved_at} to snapshots_dir/name.json.
    Creates the directory if it doesn't exist.
    """
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "status_code": result.status_code,
        "headers": dict(result.headers) if result.headers else {},
        "body": result.body,
        "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path = snapshots_dir / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def load_snapshot(
    name: str,
    config: dict,
    snapshots_dir_override: str | None = None,
) -> dict | None:
    """Load a named snapshot from the resolved snapshots directory."""
    sdir = resolve_resource_dir("snapshots", snapshots_dir_override, config)
    if not sdir:
        return None
    path = sdir / f"{name}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def diff_snapshot(snapshot: dict, result) -> list[str]:
    """Compare a saved snapshot against a current response.

    Returns a list of diff lines (empty list means identical).
    """
    diffs: list[str] = []

    # Status code
    snap_status = snapshot.get("status_code")
    if snap_status != result.status_code:
        diffs.append(f"status_code: {snap_status} → {result.status_code}")

    # Body
    snap_body = snapshot.get("body")
    curr_body = result.body

    if isinstance(snap_body, dict) and isinstance(curr_body, dict):
        _diff_dicts("body", snap_body, curr_body, diffs)
    elif snap_body != curr_body:
        diffs.append(f"body: {_summarize(snap_body)} → {_summarize(curr_body)}")

    return diffs


def _diff_dicts(prefix: str, old: dict, new: dict, diffs: list[str]) -> None:
    """Recursively diff two dicts, appending human-readable lines."""
    all_keys = sorted(set(list(old.keys()) + list(new.keys())))
    for key in all_keys:
        path = f"{prefix}.{key}"
        if key not in old:
            diffs.append(f"{path}: (absent) → {_summarize(new[key])}")
        elif key not in new:
            diffs.append(f"{path}: {_summarize(old[key])} → (absent)")
        elif isinstance(old[key], dict) and isinstance(new[key], dict):
            _diff_dicts(path, old[key], new[key], diffs)
        elif old[key] != new[key]:
            diffs.append(f"{path}: {_summarize(old[key])} → {_summarize(new[key])}")


def _summarize(value) -> str:
    """Short string representation of a value for diff output."""
    s = json.dumps(value) if isinstance(value, dict | list) else str(value)
    if len(s) > 80:
        return s[:77] + "..."
    return s


def list_snapshots(
    config: dict,
    snapshots_dir_override: str | None = None,
) -> tuple[Path | None, list[dict]]:
    """List all snapshot files in the resolved snapshots directory.

    Returns (resolved_dir, [{name, saved_at}]).
    """
    sdir = resolve_resource_dir("snapshots", snapshots_dir_override, config)
    if not sdir or not sdir.is_dir():
        return (sdir, [])

    snapshots: list[dict] = []
    for f in sorted(sdir.iterdir()):
        if f.suffix == ".json" and f.is_file():
            try:
                with open(f) as fh:
                    data = json.load(fh)
                snapshots.append(
                    {
                        "name": f.stem,
                        "saved_at": data.get("saved_at", ""),
                    },
                )
            except Exception:
                snapshots.append({"name": f.stem, "saved_at": "?"})
    return (sdir, snapshots)


# ── Form parsing ─────────────────────────────────────────────────────────


def parse_form_fields(form_specs: tuple[str, ...] | list[str]) -> dict:
    """Parse KEY=VALUE and KEY=@FILE form specs.

    Returns a dict with:
      - text fields: {key: str_value}
      - file fields: {key: (filename, file_handle, mime_type)}
    Text and file fields are separated into 'data' and 'files' keys.
    """
    import mimetypes

    data: dict[str, str] = {}
    files: dict[str, tuple[str, Any, str]] = {}

    for spec in form_specs:
        if "=" not in spec:
            continue
        key, value = spec.split("=", 1)
        key = key.strip()
        if value.startswith("@"):
            filepath = Path(value[1:])
            mime = mimetypes.guess_type(str(filepath))[0] or "application/octet-stream"
            files[key] = (filepath.name, open(filepath, "rb"), mime)  # noqa: SIM115
        else:
            data[key] = value

    return {"data": data, "files": files}
