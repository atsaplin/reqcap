"""reqcap CLI - minimal HTTP client for AI agents."""

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path

import click

HISTORY_FILE = Path.home() / ".reqcap_history.json"
MAX_HISTORY = 50

TOOL_HELP = """\
reqcap — Minimal HTTP client for AI agents.

Executes HTTP requests and returns filtered, token-efficient output.
Designed as a tool for AI agents developing and testing APIs.

\b
MODES
─────
  Direct:     reqcap METHOD URL [options]
  Template:   reqcap -t TEMPLATE [options]
  Curl import: reqcap --import-curl "curl ..."

\b
DIRECT MODE
───────────
  reqcap GET http://localhost:3000/api/users
  reqcap POST http://localhost:3000/api/users -b '{"name":"test"}'
  reqcap DELETE http://localhost:3000/api/users/123

  If a .reqcap.yaml config exists with a base_url, relative paths work:
    reqcap GET /api/users

\b
TEMPLATE MODE
─────────────
  Execute pre-configured requests from standalone YAML template files.
  Templates are individual .yaml files, not embedded in the config.

  reqcap -t templates/login.yaml -v email=admin@test.com -v password=secret
  reqcap -t login -v email=admin@test.com       # looks in ./templates/login.yaml
  reqcap -t create-user -v name=John -v email=john@test.com

  Template resolution order:
    1. Exact file path or path with .yaml/.yml extension
    2. Resolved templates directory + name.yaml

  Templates directory resolution:
    1. --templates-dir CLI flag
    2. templates_dir from config (relative to config file)
    3. ./templates/ in CWD
    4. ~/.reqcap/templates/

  List available templates:
    reqcap --list-templates

\b
RESPONSE FILTERING (-f/--filter)
────────────────────────────────
  Filter the response body to return only the fields you need.
  This is the key feature for AI agents — minimizes token usage.

  Examples:
    reqcap GET /api/users -f "id,name,email"
    reqcap GET /api/users -f "data[].id,data[].name"
    reqcap GET /api/user/1 -f "profile.name,profile.role"

  See PATH SYNTAX below for full syntax. Use * to return everything.
  Filter priority: --filter flag > template filter > config default filter.

\b
VARIABLE SUBSTITUTION
─────────────────────
  Pass variables with -v key=value. Used in template field injection
  and placeholder resolution.

  reqcap -t create-user -v name=John -v email=john@test.com

\b
PLACEHOLDERS
────────────
  In templates (URLs, bodies, headers):
  \b
  {{env.VAR_NAME}}   Environment variable
  {{uuid}}           Random UUID v4
  {{timestamp}}      Unix timestamp (seconds)
  {{timestamp_ms}}   Unix timestamp (milliseconds)
  {{date}}           ISO 8601 datetime string
  {{my_var}}         Variable from -v flag or dep export

  In config files (.reqcap.yaml):
  \b
  ${VAR_NAME}        Environment variable (shell-style)

\b
VARIABLE PRECEDENCE
───────────────────
  When the same name appears in multiple sources:
  \b
  1. -v key=value      (CLI flag — highest priority)
  2. depends: exports   (from dependency template chain)
  3. {{env.VAR}}        (environment / .env file — lowest)

\b
PATH SYNTAX (used by -f, --export, fields[].path)
─────────────────────────────────────────────────
  All path expressions use the same syntax:
  \b
  field              Top-level key
  a.b                Nested key
  a[].b              Every array element
  a[0]               Specific index
  a[-1]              Last element
  a[2:5]             Slice
  headers[Key]       Bracket dict key

  Matching is case-insensitive. Combine with commas for -f:
    -f "id,name,data[].email"

\b
TEMPLATE DEPENDENCIES (depends)
───────────────────────────────
  Templates can declare dependencies that run first:

  \b
    # templates/get-users.yaml
    depends:
      - login
    method: GET
    url: /api/users
    headers:
      Authorization: "Bearer {{token}}"

  Dependencies are resolved depth-first. Exported variables
  from each dependency are available to downstream templates.

    reqcap -t get-users -v email=admin -v password=secret

  Circular dependencies are detected and reported.
  A -v variable overrides any dep export of the same name.

\b
REQUEST CHAINING (--export)
───────────────────────────
  For shell scripting, --export prints response values as env vars.
  Prefer `depends:` in templates for declarative chaining.

  \b
  reqcap GET /api/me --export token=body.access_token
  reqcap GET /api/me --export id          # shorthand for id=body.id

  Shell eval pattern:
    eval $(reqcap GET /api/auth --export token=body.token 2>&1 1>/dev/null)
    reqcap GET /api/users -H "Authorization: Bearer $reqcap_token"

  Templates can auto-export via the "exports" key.

\b
OUTPUT FORMAT
─────────────
  Default output (minimal, structured for AI parsing):
    STATUS: 200
    TIME: 45ms
    BODY:
    {"id": 1, "name": "test"}

  --verbose adds response headers.
  --raw outputs only the JSON body (for piping to jq, etc).

\b
CONFIG FILE FORMAT (.reqcap.yaml)
────────────────────────────────────
  Config resolution order:
    1. -c/--config flag (explicit path)
    2. .reqcap.yaml / .reqcap.yml / reqcap.yaml / reqcap.yml in CWD
    3. ~/.reqcap/config.yaml (global)

  The config sets defaults only. Templates are separate files.

  \b
  defaults:
    base_url: ${API_BASE_URL}       # env var resolved at runtime
    env_file: .env                  # load .env file
    timeout: 30                     # seconds
    templates_dir: templates        # where to find template files
    headers:
      Content-Type: application/json
    auth:
      type: bearer                  # bearer | api-key | basic
      token: ${API_TOKEN}
    filter:
      status: true
      headers: false
      body_fields: []               # empty = show full body

\b
TEMPLATE FILE FORMAT (templates/*.yaml)
───────────────────────────────────────
  Each template is a standalone YAML file with these top-level keys:

  \b
  # templates/login.yaml
  name: login                       # optional, defaults to filename
  description: Authenticate user
  url: /api/auth/login
  method: POST
  depends:                          # run these templates first
    - get-csrf-token
  body:
    email: ""
    password: ""
  fields:                           # maps -v values into the body
    - name: email
      path: email
    - name: password
      path: password
  exports:                          # auto-export on response
    token: body.access_token
  snapshot:                         # auto-save response snapshot
    enabled: true
    name: login-snapshot            # optional, defaults to template name
  filter:
    body_fields: [access_token, expires_in]

\b
AUTH TYPES (in config auth section)
───────────────────────────────────
  \b
  bearer:   {type: bearer, token: ${API_TOKEN}}
  api-key:  {type: api-key, token: ${KEY}, header: X-API-Key}
  basic:    {type: basic, username: ${USER}, password: ${PASS}}

\b
SNAPSHOTS
─────────
  Snapshot a response and diff against it later:
    reqcap GET /api/users --snapshot baseline
    reqcap GET /api/users --diff baseline

  Templates can auto-snapshot via the snapshot key:
    snapshot:
      enabled: true
      name: my-baseline           # optional, defaults to template name

  List snapshots:
    reqcap --list-snapshots

  Snapshots directory resolution follows the same pattern as templates.

\b
ASSERTIONS (--assert)
─────────────────────
  Binary pass/fail checks on responses. Exit code 1 on failure.
    reqcap GET /api/health --assert status=200
    reqcap GET /api/users --assert "body.count!=0"
    reqcap POST /api/login -b '...' --assert status=200 --assert "body.token!=null"

\b
FORM DATA (--form)
──────────────────
  Send multipart form-data / file uploads. Mutually exclusive with -b/--body.
    reqcap POST /api/upload --form name=test --form file=@photo.jpg
    reqcap POST /api/data --form key=value --form attachment=@report.pdf

\b
PROJECT INIT
────────────
  reqcap --init              Scaffold .reqcap.yaml + templates/ + snapshots/

\b
HISTORY
───────
  reqcap --history          Show recent requests
  reqcap --replay 0         Replay request at index 0
"""


@click.command(
    cls=click.Command,
    help=TOOL_HELP,
    context_settings={"max_content_width": 88},
)
@click.argument("method", required=False)
@click.argument("url", required=False)
@click.option(
    "-t",
    "--template",
    "template_name",
    default=None,
    help="Template name or path. Use --list-templates to see available.",
)
@click.option(
    "-c",
    "--config",
    "config_file",
    default=None,
    help="Config file path. Default: .reqcap.yaml in CWD, then ~/.reqcap/config.yaml.",
)
@click.option(
    "--templates-dir",
    "templates_dir_override",
    default=None,
    help="Override templates directory. Default: resolved from config "
    "or ./templates/ or ~/.reqcap/templates/.",
)
@click.option(
    "-v",
    "--var",
    multiple=True,
    help="Variable as key=value. Injected into template fields and placeholders. Repeatable.",
)
@click.option("-b", "--body", default=None, help="Request body as JSON string.")
@click.option(
    "-H",
    "--header",
    multiple=True,
    help="HTTP header as 'Name: Value'. Repeatable.",
)
@click.option(
    "-f",
    "--filter",
    "filter_fields",
    default=None,
    help="Comma-separated body fields to extract. e.g. 'id,name' or 'data[].id,data[].name'.",
)
@click.option(
    "--timeout",
    type=int,
    default=None,
    help="Request timeout in seconds. Default: 30.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Include response headers in output.",
)
@click.option(
    "--raw",
    is_flag=True,
    default=False,
    help="Output raw JSON body only. Useful for piping.",
)
@click.option(
    "--export",
    multiple=True,
    help="Export response field as reqcap_<name> env var. "
    "Format: 'name' or 'name=body.path'. Repeatable.",
)
@click.option(
    "--import-curl",
    "import_curl",
    default=None,
    help="Parse and execute a curl command string.",
)
@click.option("--history", is_flag=True, default=False, help="Show request history.")
@click.option(
    "--replay",
    type=int,
    default=None,
    metavar="INDEX",
    help="Replay a request from history by index.",
)
@click.option(
    "--list-templates",
    "show_list_templates",
    is_flag=True,
    default=False,
    help="List all template files in the templates directory.",
)
@click.option(
    "--snapshots-dir",
    "snapshots_dir_override",
    default=None,
    help="Override snapshots directory.",
)
@click.option(
    "--snapshot",
    "snapshot_name",
    default=None,
    metavar="NAME",
    help="Snapshot the response under a given name.",
)
@click.option(
    "--diff",
    "diff_snapshot_name",
    default=None,
    metavar="NAME",
    help="Diff the response against a saved snapshot. Exit 1 if differences found.",
)
@click.option(
    "--list-snapshots",
    "show_list_snapshots",
    is_flag=True,
    default=False,
    help="List all saved snapshots.",
)
@click.option(
    "--assert",
    "assert_exprs",
    multiple=True,
    help="Assert expression like 'status=200' or 'body.field!=value'. "
    "Exit 1 on failure. Repeatable.",
)
@click.option(
    "--form",
    "form_fields",
    multiple=True,
    help="Form field as KEY=VALUE or KEY=@FILE for file upload. "
    "Sends multipart/form-data. Repeatable. "
    "Mutually exclusive with --body.",
)
@click.option(
    "--init",
    "do_init",
    is_flag=True,
    default=False,
    help="Scaffold .reqcap.yaml + templates/ + snapshots/ in CWD.",
)
@click.option(
    "--install-skill",
    "install_skill_agent",
    default=None,
    metavar="AGENT",
    help="Install reqcap skill to .<AGENT>/skills/reqcap-skill/ in CWD. e.g. --install-skill claude",
)
def main(
    method,
    url,
    template_name,
    config_file,
    templates_dir_override,
    var,
    body,
    header,
    filter_fields,
    timeout,
    verbose,
    raw,
    export,
    import_curl,
    history,
    replay,
    show_list_templates,
    install_skill_agent,
    snapshots_dir_override,
    snapshot_name,
    diff_snapshot_name,
    show_list_snapshots,
    assert_exprs,
    form_fields,
    do_init,
):
    """Execute HTTP requests with minimal, filtered output."""
    from reqcap.core import (
        build_auth_headers,
        build_request_from_template,
        diff_snapshot,
        list_snapshots,
        list_templates,
        load_config,
        load_env,
        load_snapshot,
        load_template,
        parse_curl,
        parse_form_fields,
        resolve_config_path,
        resolve_placeholders,
        resolve_resource_dir,
        resolve_value,
        save_snapshot,
        template_search_paths,
    )
    from reqcap.executor import execute_request
    from reqcap.filters import evaluate_assert, extract_value, format_output

    # --- Load config ---
    config_path = resolve_config_path(config_file)
    config = load_config(config_path)
    defaults = config.get("defaults", {})

    env_file = defaults.get("env_file")
    env = load_env(env_file)

    # Parse -v key=value pairs
    variables = {}
    for v_str in var:
        if "=" in v_str:
            k, val = v_str.split("=", 1)
            variables[k.strip()] = val.strip()

    # --- Validate mutually exclusive options ---
    if form_fields and body:
        click.echo("ERROR: --form and --body are mutually exclusive.", err=True)
        sys.exit(1)

    # --- Dispatch ---

    if do_init:
        _cmd_init()
        return

    if install_skill_agent:
        _cmd_install_skill(install_skill_agent)
        return

    if show_list_snapshots:
        _cmd_list_snapshots(
            config,
            snapshots_dir_override,
            list_snapshots_fn=list_snapshots,
        )
        return

    if show_list_templates:
        _cmd_list_templates(
            list_templates_fn=list_templates,
            config=config,
            templates_dir_override=templates_dir_override,
        )
        return

    if history:
        _cmd_history()
        return

    # Build snapshot/assert context for request modes
    snapshot_ctx = {
        "snapshot_name": snapshot_name,
        "diff_name": diff_snapshot_name,
        "snapshots_dir_override": snapshots_dir_override,
        "config": config,
        "snapshot_fn": save_snapshot,
        "load_fn": load_snapshot,
        "diff_fn": diff_snapshot,
        "resolve_dir_fn": resolve_resource_dir,
    }
    assert_ctx = {
        "exprs": assert_exprs,
        "evaluate_fn": evaluate_assert,
    }
    form_ctx = {
        "fields": form_fields,
        "parse_fn": parse_form_fields,
    }

    if replay is not None:
        _cmd_replay(
            replay,
            defaults,
            filter_fields,
            verbose,
            raw,
            execute_request,
            format_output,
            snapshot_ctx=snapshot_ctx,
            assert_ctx=assert_ctx,
        )
        return

    if import_curl:
        _cmd_import_curl(
            import_curl,
            header,
            timeout,
            defaults,
            filter_fields,
            verbose,
            raw,
            export,
            execute_request,
            format_output,
            extract_value,
            parse_curl,
            snapshot_ctx=snapshot_ctx,
            assert_ctx=assert_ctx,
            form_ctx=form_ctx,
        )
        return

    if template_name:
        template = load_template(template_name, config, templates_dir_override)
        if template is None:
            searched = template_search_paths(
                template_name,
                config,
                templates_dir_override,
            )
            click.echo(
                f"Template '{template_name}' not found. "
                f"Templates are user-created .yaml files, not built-in commands.\n"
                f"Searched:\n"
                + "\n".join(f"  - {p}" for p in searched)
                + "\nFor direct requests use: reqcap GET <url>",
                err=True,
            )
            sys.exit(1)
        _cmd_template(
            config,
            template,
            variables,
            env,
            header,
            body,
            timeout,
            defaults,
            filter_fields,
            verbose,
            raw,
            export,
            execute_request,
            format_output,
            extract_value,
            build_request_from_template,
            snapshot_ctx=snapshot_ctx,
            assert_ctx=assert_ctx,
            templates_dir_override=templates_dir_override,
        )
        return

    if method and url:
        _cmd_direct(
            method,
            url,
            body,
            header,
            timeout,
            defaults,
            env,
            variables,
            filter_fields,
            verbose,
            raw,
            export,
            resolve_value,
            resolve_placeholders,
            build_auth_headers,
            execute_request,
            format_output,
            extract_value,
            snapshot_ctx=snapshot_ctx,
            assert_ctx=assert_ctx,
            form_ctx=form_ctx,
        )
        return

    # Nothing matched — show help
    ctx = click.get_current_context()
    click.echo(ctx.get_help())
    ctx.exit(1)


# ── Subcommand implementations ──────────────────────────────────────────


def _cmd_install_skill(agent_name):
    """Copy bundled skill data to .<agent>/skills/reqcap-skill/ in CWD."""
    import shutil

    skill_source = Path(__file__).parent / "skill_data"
    if not skill_source.exists():
        click.echo("ERROR: Skill data not found in package.", err=True)
        sys.exit(1)

    target = Path.cwd() / f".{agent_name}" / "skills" / "reqcap-skill"
    target.mkdir(parents=True, exist_ok=True)

    shutil.copytree(skill_source, target, dirs_exist_ok=True)
    click.echo(f"Installed reqcap skill to {target}")


def _cmd_list_templates(list_templates_fn, config, templates_dir_override=None):
    tdir, templates = list_templates_fn(config, templates_dir_override)
    if not templates:
        if tdir:
            click.echo(f"No templates found in: {tdir}")
        else:
            click.echo("No templates directory found.")
            click.echo("Searched: ./templates/, ~/.reqcap/templates/")
        click.echo("Templates are user-created .yaml files, not built-in.")
        return

    # Summary block — compact, LLM-scannable
    click.echo(f"Templates from: {tdir}")
    click.echo(f"{len(templates)} available:\n")
    for tpl in templates:
        name = tpl["name"]
        desc = tpl.get("description", "")
        method = tpl.get("method", "GET")
        url = tpl.get("url", "")
        label = f"  {name} — {desc}" if desc else f"  {name}"
        click.echo(label)
        detail_parts = [f"{method} {url}"]
        fields = tpl.get("fields", [])
        if fields:
            field_names = [f.get("name", "") for f in fields]
            detail_parts.append(f"vars: {', '.join(field_names)}")
        exports = tpl.get("exports", {})
        if exports:
            detail_parts.append(f"exports: {', '.join(exports.keys())}")
        depends = tpl.get("depends", [])
        if depends:
            if isinstance(depends, str):
                depends = [depends]
            detail_parts.append(f"depends: {', '.join(depends)}")
        snap_cfg = tpl.get("snapshot", {})
        if snap_cfg.get("enabled"):
            snap_name = snap_cfg.get("name") or name
            detail_parts.append(f"snapshot: {snap_name}")
        click.echo(f"    {' | '.join(detail_parts)}")
        body_fields = tpl.get("filter", {}).get("body_fields", [])
        if body_fields:
            click.echo(f"    filter: {', '.join(body_fields)}")
        click.echo()


def _cmd_history():
    hist = _load_history()
    if not hist:
        click.echo("No request history.")
        return
    click.echo("Request history:\n")
    for i, entry in enumerate(hist):
        ts = entry.get("timestamp", "")
        m = entry.get("method", "?")
        u = entry.get("url", "?")
        tpl = entry.get("template")
        label = f"[{tpl}]" if tpl else u
        click.echo(f"  [{i}] {m:<6} {label}  ({ts})")


def _cmd_replay(
    index,
    defaults,
    filter_fields,
    verbose,
    raw,
    execute_request,
    format_output,
    snapshot_ctx=None,
    assert_ctx=None,
):
    hist = _load_history()
    if index < 0 or index >= len(hist):
        click.echo(f"Invalid index {index}. Use --history to list.", err=True)
        sys.exit(1)
    entry = hist[index]
    result = execute_request(
        method=entry["method"],
        url=entry["url"],
        headers=entry.get("headers"),
        body=entry.get("body"),
        timeout=_resolve_timeout(defaults.get("timeout")),
    )
    if result.error:
        click.echo(f"ERROR: {result.error}", err=True)
        sys.exit(1)
    fc = _build_filter_config(filter_fields, verbose, defaults)
    click.echo(format_output(result, filter_config=fc, verbose=verbose, raw=raw))
    _handle_asserts(assert_ctx, result)
    _handle_snapshot_ops(snapshot_ctx, result)


def _cmd_import_curl(
    curl_str,
    header,
    timeout,
    defaults,
    filter_fields,
    verbose,
    raw,
    export,
    execute_request,
    format_output,
    extract_value,
    parse_curl,
    snapshot_ctx=None,
    assert_ctx=None,
    form_ctx=None,
):
    parsed = parse_curl(curl_str)
    if parsed.get("error"):
        click.echo(f"Error parsing curl: {parsed['error']}", err=True)
        sys.exit(1)

    headers = {**parsed.get("headers", {}), **_parse_headers(header)}
    form_data = _prepare_form_data(form_ctx)

    result = execute_request(
        method=parsed["method"],
        url=parsed["url"],
        headers=headers,
        body=parsed.get("body"),
        timeout=_resolve_timeout(timeout, defaults.get("timeout")),
        form_data=form_data,
    )
    if result.error:
        click.echo(f"ERROR: {result.error}", err=True)
        sys.exit(1)
    fc = _build_filter_config(filter_fields, verbose, defaults)
    click.echo(format_output(result, filter_config=fc, verbose=verbose, raw=raw))
    _save_to_history(parsed["method"], parsed["url"], parsed.get("body"), headers)
    _handle_asserts(assert_ctx, result)
    _handle_exports(export, result, extract_value)
    _handle_snapshot_ops(snapshot_ctx, result)


def _resolve_and_execute_deps(
    template,
    config,
    variables,
    env,
    defaults,
    templates_dir_override,
    execute_request,
    extract_value,
    build_request_from_template,
    visited=None,
    chain=None,
    cli_var_keys=None,
):
    """Depth-first execute template dependencies, accumulating exports into variables.

    Returns updated variables dict.
    Raises click.ClickException on cycle or load failure.
    """
    from reqcap.core import load_template

    depends = template.get("depends", [])
    if not depends:
        return variables

    if isinstance(depends, str):
        depends = [depends]

    if visited is None:
        visited = set()
    if chain is None:
        chain = []

    template_name = template.get("name", "unknown")
    visited.add(template_name)
    chain.append(template_name)

    variables = dict(variables)  # shallow copy to accumulate into

    for dep_name in depends:
        if dep_name in visited:
            cycle_path = " → ".join(chain + [dep_name])
            click.echo(
                f"ERROR: Circular dependency detected: {cycle_path}",
                err=True,
            )
            sys.exit(1)

        dep_template = load_template(dep_name, config, templates_dir_override)
        if dep_template is None:
            click.echo(
                f"ERROR: Dependency template '{dep_name}' not found.",
                err=True,
            )
            sys.exit(1)

        # Recurse into this dep's own dependencies (depth-first)
        variables = _resolve_and_execute_deps(
            dep_template,
            config,
            variables,
            env,
            defaults,
            templates_dir_override,
            execute_request,
            extract_value,
            build_request_from_template,
            visited=set(visited),
            chain=list(chain),
            cli_var_keys=cli_var_keys,
        )

        # Build and execute the dependency request
        req = build_request_from_template(config, dep_template, variables, env)
        result = execute_request(
            method=req["method"],
            url=req["url"],
            headers=req.get("headers"),
            body=req.get("body"),
            timeout=_resolve_timeout(req.get("timeout"), defaults.get("timeout")),
        )

        if result.error:
            click.echo(
                f"ERROR: Dependency '{dep_name}' failed: {result.error}",
                err=True,
            )
            sys.exit(1)

        # Print compact status line for dep
        elapsed = int(result.elapsed_ms)
        click.echo(f"[dep: {dep_name}] STATUS: {result.status_code} ({elapsed}ms)")

        # Extract exports from dep response, merge into variables
        # CLI -v variables take precedence over dep exports
        exports = req.get("exports", {})
        if exports and result.body:
            for ename, epath in exports.items():
                if cli_var_keys and ename in cli_var_keys:
                    continue  # CLI -v takes precedence
                value = extract_value(result.body, epath)
                if value is not None:
                    variables[ename] = str(value)

    visited.discard(template_name)
    chain.pop()
    return variables


def _cmd_template(
    config,
    template,
    variables,
    env,
    header,
    body,
    timeout,
    defaults,
    filter_fields,
    verbose,
    raw,
    export,
    execute_request,
    format_output,
    extract_value,
    build_request_from_template,
    snapshot_ctx=None,
    assert_ctx=None,
    templates_dir_override=None,
):
    template_name = template.get("name", "unknown")

    # Resolve and execute dependencies first
    variables = _resolve_and_execute_deps(
        template,
        config,
        variables,
        env,
        defaults,
        templates_dir_override,
        execute_request,
        extract_value,
        build_request_from_template,
        cli_var_keys=set(variables.keys()),
    )

    req = build_request_from_template(config, template, variables, env)

    req["headers"].update(_parse_headers(header))

    if body:
        req["body"] = body

    result = execute_request(
        method=req["method"],
        url=req["url"],
        headers=req.get("headers"),
        body=req.get("body"),
        timeout=_resolve_timeout(timeout, req.get("timeout"), defaults.get("timeout")),
    )
    if result.error:
        click.echo(f"ERROR: {result.error}", err=True)
        sys.exit(1)

    fc = _build_filter_config(filter_fields, verbose, defaults, req.get("filter"))
    click.echo(format_output(result, filter_config=fc, verbose=verbose, raw=raw))
    _save_to_history(
        req["method"],
        req["url"],
        req.get("body"),
        req.get("headers"),
        template_name,
    )

    _handle_asserts(assert_ctx, result)

    # Template auto-exports
    exports = req.get("exports", {})
    if exports and result.body:
        for ename, epath in exports.items():
            value = extract_value(result.body, epath)
            if value is not None:
                click.echo(
                    f"export reqcap_{ename}={_shell_quote(str(value))}",
                    err=True,
                )

    _handle_exports(export, result, extract_value)
    _handle_snapshot_ops(snapshot_ctx, result)

    # Template auto-snapshot — reuse _handle_snapshot_ops with injected name
    snap_cfg = template.get("snapshot", {})
    if snap_cfg.get("enabled") and snapshot_ctx:
        auto_name = snap_cfg.get("name") or template_name
        _handle_snapshot_ops(
            {**snapshot_ctx, "snapshot_name": auto_name, "diff_name": None},
            result,
        )


def _cmd_direct(
    method,
    url,
    body,
    header,
    timeout,
    defaults,
    env,
    variables,
    filter_fields,
    verbose,
    raw,
    export,
    resolve_value,
    resolve_placeholders,
    build_auth_headers,
    execute_request,
    format_output,
    extract_value,
    snapshot_ctx=None,
    assert_ctx=None,
    form_ctx=None,
):
    method = method.upper()

    base_url = resolve_value(defaults.get("base_url"), env) or ""
    if not url.startswith(("http://", "https://")):
        url = base_url + url

    headers = {}
    for k, v in defaults.get("headers", {}).items():
        headers[k] = resolve_placeholders(v, env, variables)

    auth_config = defaults.get("auth")
    if auth_config:
        headers.update(build_auth_headers(auth_config, env))

    headers.update(_parse_headers(header))

    if body:
        body = resolve_placeholders(body, env, variables)

    form_data = _prepare_form_data(form_ctx)

    result = execute_request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        timeout=_resolve_timeout(timeout, defaults.get("timeout")),
        form_data=form_data,
    )
    if result.error:
        click.echo(f"ERROR: {result.error}", err=True)
        sys.exit(1)

    fc = _build_filter_config(filter_fields, verbose, defaults)
    click.echo(format_output(result, filter_config=fc, verbose=verbose, raw=raw))
    _save_to_history(method, url, body, headers)
    _handle_asserts(assert_ctx, result)
    _handle_exports(export, result, extract_value)
    _handle_snapshot_ops(snapshot_ctx, result)


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_headers(header_tuples):
    """Parse -H 'Name: Value' tuples into a dict."""
    headers = {}
    for h in header_tuples:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


def _prepare_form_data(form_ctx):
    """Parse form context into form_data dict, or None."""
    if form_ctx and form_ctx.get("fields"):
        return form_ctx["parse_fn"](form_ctx["fields"])
    return None


def _resolve_timeout(*sources, default=30):
    """Return the first truthy timeout from sources, or default."""
    for t in sources:
        if t:
            return t
    return default


def _build_filter_config(filter_fields, verbose, defaults, template_filter=None):
    """Build filter config with priority: CLI > template > defaults."""
    if filter_fields:
        fields = [f.strip() for f in filter_fields.split(",")]
        return {"status": True, "headers": verbose, "body_fields": fields}
    if template_filter:
        return template_filter
    default_filter = defaults.get("filter")
    if default_filter:
        return default_filter
    return None


def _handle_exports(export_specs, result, extract_value_fn):
    if not export_specs or not result.body:
        return
    for spec in export_specs:
        if "=" in spec:
            name, path = spec.split("=", 1)
        else:
            name = spec
            path = f"body.{spec}"
        value = extract_value_fn(result.body, path)
        if value is not None:
            click.echo(
                f"export reqcap_{name}={_shell_quote(str(value))}",
                err=True,
            )


def _handle_asserts(assert_ctx, result):
    """Evaluate all --assert expressions. Exit 1 on first failure."""
    if not assert_ctx or not assert_ctx.get("exprs"):
        return
    evaluate_fn = assert_ctx["evaluate_fn"]
    for expr in assert_ctx["exprs"]:
        passed, message = evaluate_fn(expr, result)
        if not passed:
            click.echo(message, err=True)
            sys.exit(1)


def _handle_snapshot_ops(snapshot_ctx, result):
    """Handle --snapshot and --diff snapshot operations."""
    if not snapshot_ctx:
        return

    snap_name = snapshot_ctx.get("snapshot_name")
    diff_name = snapshot_ctx.get("diff_name")
    config = snapshot_ctx.get("config", {})
    snapshots_dir_override = snapshot_ctx.get("snapshots_dir_override")
    snapshot_fn = snapshot_ctx.get("snapshot_fn")
    load_fn = snapshot_ctx.get("load_fn")
    diff_fn = snapshot_ctx.get("diff_fn")
    resolve_dir_fn = snapshot_ctx.get("resolve_dir_fn")

    if snap_name:
        sdir = resolve_dir_fn(
            "snapshots",
            snapshots_dir_override,
            config,
            default=Path("snapshots"),
        )
        path = snapshot_fn(snap_name, result, sdir)
        click.echo(f"Snapshot saved: {path}", err=True)

    if diff_name:
        snapshot = load_fn(diff_name, config, snapshots_dir_override)
        if snapshot is None:
            click.echo(f"Snapshot '{diff_name}' not found.", err=True)
            sys.exit(1)
        diffs = diff_fn(snapshot, result)
        if diffs:
            click.echo("Differences found:", err=True)
            for line in diffs:
                click.echo(f"  {line}", err=True)
            sys.exit(1)
        else:
            click.echo("No differences.", err=True)


def _cmd_list_snapshots(config, snapshots_dir_override, list_snapshots_fn):
    """List all saved snapshots."""
    sdir, snapshots = list_snapshots_fn(config, snapshots_dir_override)
    if not snapshots:
        if sdir:
            click.echo(f"No snapshots found in: {sdir}")
        else:
            click.echo("No snapshots directory found.")
            click.echo("Searched: ./snapshots/, ~/.reqcap/snapshots/")
        return
    click.echo(f"Snapshots from: {sdir}\n")
    for snap in snapshots:
        name = snap["name"]
        saved_at = snap.get("saved_at", "")
        click.echo(f"  {name}  ({saved_at})")


def _cmd_init():
    """Scaffold .reqcap.yaml + templates/ + snapshots/ in CWD."""
    config_file = Path(".reqcap.yaml")
    templates_dir = Path("templates")
    snapshots_dir = Path("snapshots")

    if config_file.exists():
        click.echo(f"  {config_file} (skipped, already exists)")
    else:
        base_url = _detect_base_url()
        config_content = _generate_config(base_url)
        config_file.write_text(config_content)
        click.echo(f"  {config_file} (created)")

    for d in (templates_dir, snapshots_dir):
        if d.exists():
            click.echo(f"  {d}/ (skipped, already exists)")
        else:
            d.mkdir(parents=True)
            click.echo(f"  {d}/ (created)")

    click.echo("\nProject initialized. Run 'reqcap --help' to get started.")


def _detect_base_url() -> str:
    """Sniff CWD for framework files, return likely localhost URL."""
    if Path("package.json").exists():
        return "http://localhost:3000"
    if Path("pyproject.toml").exists() or Path("requirements.txt").exists():
        return "http://localhost:8000"
    if Path("go.mod").exists():
        return "http://localhost:8080"
    if Path("Gemfile").exists():
        return "http://localhost:3000"
    if Path("Cargo.toml").exists():
        return "http://localhost:8080"
    return "http://localhost:3000"


def _generate_config(base_url: str) -> str:
    """Return .reqcap.yaml content string."""
    return f"""\
# reqcap configuration
# See: reqcap --help

defaults:
  base_url: {base_url}
  # env_file: .env
  timeout: 30
  templates_dir: templates
  snapshots_dir: snapshots
  headers:
    Content-Type: application/json
  # auth:
  #   type: bearer
  #   token: ${{API_TOKEN}}
"""


def _shell_quote(s):
    if not s:
        return "''"
    if all(c.isalnum() or c in "-_=./:@" for c in s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


def _load_history():
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text())
    except Exception:
        pass
    return []


def _save_to_history(method, url, body=None, headers=None, template=None):
    hist = _load_history()
    entry = {"method": method, "url": url, "timestamp": datetime.now().isoformat()}
    if body:
        entry["body"] = body
    if headers:
        safe = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        if safe:
            entry["headers"] = safe
    if template:
        entry["template"] = template
    hist.insert(0, entry)
    with contextlib.suppress(Exception):
        HISTORY_FILE.write_text(json.dumps(hist[:MAX_HISTORY], indent=2))
