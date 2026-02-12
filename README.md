# reqcap

Minimal HTTP client that returns only what you need — status, timing, and the specific JSON fields you ask for. Run templates, save snapshots, test your features e2e quickly. 

> [!NOTE]
> **Built for AI agents too.** Filtered output saves tokens, `--list-templates` lets agents discover existing test scenarios, `--diff` catches regressions, and `--install-skill` teaches Claude Code to use reqcap automatically.

## Why reqcap?

A typical `curl -s https://httpbin.org/json` dumps 42 lines. reqcap gives you just the fields you asked for:

```bash
reqcap GET https://httpbin.org/json -f "slideshow.title,slideshow.author"
```

```text
STATUS: 200
TIME: 45ms
BODY:
{
  "slideshow": {
    "title": "Sample Slide Show",
    "author": "Yours Truly"
  }
}
```

Save requests as reusable templates, snapshot known-good responses, diff them later to catch regressions — all from the CLI.

```bash
reqcap -t list-users
reqcap -t list-users --snapshot baseline
reqcap -t list-users --diff baseline
reqcap --list-templates
```

## Features

- [Templates](#templates) — reusable YAML request scenarios with variables, auth, and chaining
- [Snapshots](#snapshots) — save responses and diff to detect regressions
- [Response filtering](#response-filtering) — extract nested fields, array slices, specific indices
- [Assertions](#assertions) — `--assert status=200` exits 1 on failure
- [Request chaining](#request-chaining) — export response values and feed them into the next request
- [Template dependencies](#template-dependencies) — declarative `depends:` for multi-step flows
- [Config file](#config-file) — base URLs, default headers, env var substitution
- [Placeholders](#placeholders) — `{{uuid}}`, `{{date}}`, `{{env.VAR}}` auto-expand in templates
- [Auth types](#auth-types) — bearer, API key, basic auth in config or per-template
- [Form data](#form-data) — `--form` for multipart uploads
- [Curl import](#curl-import) — paste a curl command and run it through reqcap
- [History](#history) — replay recent requests
- [Project init](#project-init) — scaffold config and directories

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv tool install reqcap
```

## Quick start

Scaffold config and directories:

```bash
reqcap --init
```

This creates `.reqcap.yaml`, `templates/`, and `snapshots/`.

Test an endpoint with filtered output:

```bash
reqcap GET https://httpbin.org/json -f "slideshow.title,slideshow.author"
```

POST with a JSON body:

```bash
reqcap POST https://httpbin.org/post -b '{"name": "test", "email": "test@example.com"}'
```

Run a saved template:

```bash
reqcap -t login -v email=admin@test.com -v password=secret
```

Snapshot a response, then diff later:

```bash
reqcap GET /api/health --snapshot baseline
reqcap GET /api/health --diff baseline
```

See what templates are available:

```bash
reqcap --list-templates
```

## Templates

Templates are standalone YAML files — each template is its own file, not embedded in the config. This keeps templates portable, version-controllable, and easy to share.

> [!TIP]
> **For AI agents:** An agent can run `reqcap --list-templates` at the start of a task to discover what test scenarios already exist, then re-run them as it makes changes — like lightweight e2e tests it didn't have to write.

### Creating a template

Create a YAML file in your `templates/` directory:

```yaml
# templates/login.yaml
description: Authenticate user
url: /api/auth/login
method: POST
body:
  email: ""
  password: ""
fields:
  - name: email
    path: email
  - name: password
    path: password
exports:
  token: body.access_token
filter:
  body_fields: [access_token, expires_in]
```

### Using templates

Run by name (resolves to `templates/login.yaml`):

```bash
reqcap -t login -v email=admin@test.com -v password=secret
```

Run by file path:

```bash
reqcap -t templates/login.yaml -v email=admin@test.com -v password=secret
```

List all available templates:

```bash
reqcap --list-templates
```

### Template file location

Templates are resolved in this order:

1. Exact file path (e.g. `reqcap -t path/to/my-template.yaml`)
2. `templates_dir` from config + name (e.g. `custom-templates/login.yaml`)
3. `./templates/` + name (e.g. `templates/login.yaml`)

### Template properties

| Property | Description |
|---|---|
| `name` | Optional identifier (defaults to filename) |
| `description` | Shown in `--list-templates` |
| `url` | Endpoint path (appended to base_url) |
| `method` | HTTP method: GET, POST, PUT, PATCH, DELETE |
| `base_url` | Override the default base_url for this template |
| `headers` | Template-specific headers (merged with defaults) |
| `auth` | Template-specific auth (overrides default) |
| `body` | Request body template (JSON object) |
| `fields` | Variables injected into body via `-v` |
| `exports` | Auto-export response values (see [Request chaining](#request-chaining)) |
| `filter` | Template-specific response filter |
| `depends` | List of template names to run first (see [Template dependencies](#template-dependencies)) |
| `snapshot` | Auto-save response: `{enabled: true, name: "..."}` |

### Template fields

The `fields` array defines variables that get injected into the request body at the specified JSON path.

```yaml
# templates/chat.yaml
url: /api/chat
method: POST
body:
  messages:
    - role: "user"
      content: ""

fields:
  - name: prompt
    path: messages[0].content
```

```bash
reqcap -t chat -v prompt="Hello, world"
```

The body becomes `{"messages": [{"role": "user", "content": "Hello, world"}]}`.

### Template with per-request auth

```yaml
# templates/create-user.yaml
url: /api/users
method: POST
auth:
  type: bearer
  token: "{{token}}"
body:
  id: "{{uuid}}"
  name: ""
  email: ""
  created_at: "{{date}}"
fields:
  - name: name
    path: name
  - name: email
    path: email
filter:
  body_fields: [id, name, email]
```

```bash
reqcap -t create-user -v token=sk-abc123 -v name=Alice -v email=alice@test.com
```

## Snapshots

Save responses and diff against them to detect regressions.

```bash
reqcap GET /api/health --snapshot baseline
reqcap GET /api/health --diff baseline
reqcap --list-snapshots
```

Templates can auto-save snapshots with `snapshot: {enabled: true}`.

> [!TIP]
> **For AI agents:** Snapshot a response before making changes, then `--diff` after to verify nothing broke. Agents get a clear pass/fail signal without eyeballing JSON.

## Response filtering

The `-f`/`--filter` flag extracts only the fields you specify from the response body.

> [!TIP]
> **For AI agents:** Filtered output keeps responses small and token-efficient. An agent checking a 500-field response only sees the 3 fields it asked for.

### Syntax

| Pattern | Meaning |
|---|---|
| `field` | Top-level field |
| `nested.field` | Nested object field |
| `data[].id` | Field from every array element |
| `data[0].id` | Field from a specific array index |
| `data[-1]` | Last element of an array |
| `data[2:5]` | Slice of array elements |
| `headers[Content-Type]` | Bracket notation for dict keys |
| `*` | No filtering (return everything) |

### Examples

```bash
reqcap GET /api/users -f "total,page"
reqcap GET /api/user/1 -f "profile.name,profile.role"
reqcap GET /api/users -f "data[].id,data[].name"
reqcap GET /api/users -f "data[-1].name"
reqcap GET /api/users -f "data[0:3].id"
reqcap GET /api/users -f "total,data[].id,data[].email"
```

Given this response:

```json
{
  "total": 150,
  "page": 1,
  "data": [
    {"id": 1, "name": "Alice", "email": "alice@co.com", "metadata": {"large": "..."}},
    {"id": 2, "name": "Bob", "email": "bob@co.com", "metadata": {"large": "..."}}
  ]
}
```

`reqcap GET /api/users -f "total,data[].id,data[].name"` returns:

```json
{
  "total": 150,
  "data": [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"}
  ]
}
```

### Output modes

Default output includes status, timing, and filtered body. `--verbose` adds response headers. `--raw` outputs JSON body only, with no status/time lines — useful for piping:

```bash
reqcap GET /api/users --raw | jq '.data[0]'
```

## Assertions

Assert response values and exit with code 1 on failure:

```bash
reqcap GET /api/health --assert status=200
reqcap GET /api/user/1 --assert "body.role=admin"
reqcap POST /api/items --assert "status!=500" --assert "body.id!=null"
```

> [!TIP]
> **For AI agents:** Assertions give a clear exit code agents can branch on — no output parsing needed.

## Request chaining

Chain requests together by exporting values from one response and using them in the next.

### Template auto-exports

Define `exports` in a template to automatically extract and export values from the response:

```yaml
# templates/login.yaml
url: /api/auth/login
method: POST
body: { email: "", password: "" }
fields:
  - { name: email, path: email }
  - { name: password, path: password }
exports:
  token: body.access_token
  user_id: body.user.id
```

Export statements are printed to stderr as shell `export` commands. Capture them with `eval`:

```bash
eval $(reqcap -t login -v email=a@b.com -v password=x 2>&1 1>/dev/null)
reqcap -t get-users -v token=$reqcap_token
```

### CLI --export flag

Export arbitrary fields from any response:

```bash
reqcap GET /api/me --export token=body.access_token
reqcap GET /api/me --export id
```

The shorthand `--export id` is equivalent to `--export id=body.id`.

### How chaining works

1. `--export` prints `export reqcap_<name>=<value>` to stderr
2. Wrap with `eval $(... 2>&1 1>/dev/null)` to set env vars in your shell
3. Pass them to the next request with `-v` or `-H`

For declarative chaining, use `depends:` in templates instead (see [Template dependencies](#template-dependencies)).

## Template dependencies

Templates can declare `depends:` to run prerequisite templates automatically. Exported variables flow through the chain.

```yaml
# templates/login.yaml
method: POST
url: /api/auth/login
body: { email: "", password: "" }
fields:
  - { name: email, path: email }
  - { name: password, path: password }
exports:
  token: body.access_token
```

```yaml
# templates/get-users.yaml
depends:
  - login
method: GET
url: /api/users
headers:
  Authorization: "Bearer {{token}}"
```

Running `reqcap -t get-users -v email=admin -v password=secret` executes login first (exporting `token`), then get-users with the token injected.

Dependencies execute depth-first. Circular dependencies are detected and reported.

> [!TIP]
> **For AI agents:** A single `reqcap -t get-users` can handle login + auth + the actual request. Agents don't need to manage multi-step auth flows manually.

## Config file

Create a `.reqcap.yaml` in your project root (or pass `-c path/to/config.yaml`). The config sets defaults — templates are separate files (see [Templates](#templates)).

reqcap auto-discovers config files in this order: `.reqcap.yaml`, `.reqcap.yml`, `reqcap.yaml`, `reqcap.yml`.

### Minimal config

```yaml
defaults:
  base_url: http://localhost:3000
  headers:
    Content-Type: application/json
```

With this config, `reqcap GET /api/users` resolves to `http://localhost:3000/api/users`.

### Full config structure

```yaml
defaults:
  base_url: ${API_BASE_URL}
  env_file: .env
  timeout: 30
  templates_dir: templates
  headers:
    Content-Type: application/json
  auth:
    type: bearer
    token: ${API_TOKEN}
  filter:
    status: true
    headers: false
    body_fields: []
```

### Environment variables

Config values can reference environment variables with `${VAR_NAME}`. These are resolved from:

1. A `.env` file (specified by `defaults.env_file`)
2. The shell environment

```yaml
defaults:
  base_url: ${API_BASE_URL}
  auth:
    token: ${API_TOKEN}
```

```text
# .env
API_BASE_URL=http://localhost:3000
API_TOKEN=sk-abc123
```

## Placeholders

In templates (URLs, bodies, headers):

| Placeholder | Value |
|---|---|
| `{{env.VAR_NAME}}` | Environment variable |
| `{{uuid}}` | Random UUID v4 |
| `{{timestamp}}` | Unix timestamp (seconds) |
| `{{timestamp_ms}}` | Unix timestamp (milliseconds) |
| `{{date}}` | ISO 8601 datetime |
| `{{my_var}}` | Variable from `-v` flag or dep export |

In config files (`.reqcap.yaml`): use `${VAR_NAME}` for environment variable substitution.

### Example

```yaml
# templates/create-item.yaml
url: /api/items
method: POST
body:
  id: "{{uuid}}"
  created_at: "{{date}}"
  owner: "{{env.USER_ID}}"
  name: ""
fields:
  - name: name
    path: name
```

## Auth types

Configure authentication in `defaults.auth` or per-template `auth`:

### Bearer token

```yaml
auth:
  type: bearer
  token: ${API_TOKEN}
```

### API key (custom header)

```yaml
auth:
  type: api-key
  token: ${API_KEY}
  header: X-API-Key
```

### Basic auth

```yaml
auth:
  type: basic
  username: ${USER}
  password: ${PASS}
```

## Form data

Submit form data and file uploads with `--form`:

```bash
reqcap POST /api/upload --form name=test --form file=@photo.jpg
```

## Curl import

Parse and execute a curl command directly:

```bash
reqcap --import-curl "curl -X POST https://api.example.com/users \
  -H 'Content-Type: application/json' \
  -d '{\"name\": \"test\"}'"
```

Supports `-X`, `-H`, `-d`, `--data`, `--data-raw`, `--json`, and quoted strings.

## History

reqcap saves the last 50 requests (auth headers excluded).

```bash
reqcap --history
reqcap --replay 0
reqcap --replay 0 -f "id,name"
```

## Project init

Scaffold a new project with config and directories:

```bash
reqcap --init
```

This creates `.reqcap.yaml`, `templates/`, and `snapshots/`.

> [!TIP]
> **For AI agents:** Run `reqcap --install-skill claude` to install an [agent skill](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/skills) that teaches Claude Code how to use reqcap — no docs reading needed.

## CLI flags reference

| Flag | Short | Description |
|---|---|---|
| `METHOD URL` | | Direct request (positional args) |
| `--template` | `-t` | Run a template file (name or path) |
| `--config` | `-c` | Config file path |
| `--templates-dir` | | Override templates directory |
| `--var` | `-v` | Variable as `key=value` (repeatable) |
| `--body` | `-b` | Request body (JSON string) |
| `--header` | `-H` | HTTP header as `Name: Value` (repeatable) |
| `--filter` | `-f` | Comma-separated body fields to extract |
| `--timeout` | | Request timeout in seconds |
| `--verbose` | | Include response headers |
| `--raw` | | JSON body only (for piping) |
| `--export` | | Export response field as env var (repeatable) |
| `--assert` | | Assert `status=200` or `body.field!=val` (exit 1 on fail) |
| `--snapshot` | | Save response as named snapshot |
| `--diff` | | Diff response against saved snapshot |
| `--list-snapshots` | | List saved snapshots |
| `--snapshots-dir` | | Override snapshots directory |
| `--form` | | Form field `KEY=VALUE` or `KEY=@FILE` (repeatable) |
| `--import-curl` | | Parse and run a curl command |
| `--history` | | Show request history |
| `--replay` | | Replay history entry by index |
| `--list-templates` | | List template files in templates dir |
| `--init` | | Scaffold project (config + directories) |
| `--install-skill` | | Install skill data to agent directory |
| `--help` | | Full help with all syntax docs |

## License

MIT
