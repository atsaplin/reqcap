---
name: reqcap-skill
description: >
  Minimal HTTP client CLI for AI agents. Usage: `reqcap METHOD URL [options]`.
  Example: `reqcap GET http://localhost:3000/health -f "status"`.
  Returns status code, timing, and filtered JSON body. Use `-f` to select
  specific response fields and minimize token output.
metadata:
  author: alekseyt
  version: "0.1.0"
compatibility: Requires Python 3.10+ and uv. Install with `uv tool install`.
allowed-tools: Bash(reqcap:*)
---

# reqcap — Minimal HTTP Client for AI Agents

Use `reqcap METHOD URL` instead of `curl` when testing APIs. It returns only the status code, timing, and the specific JSON fields you request.

**Basic syntax: `reqcap METHOD URL [options]`** — there are no built-in commands or subcommands.

## Common patterns

```bash
# Check if a server is running
reqcap GET http://localhost:3000/health

# Check server status and extract specific fields
reqcap GET http://localhost:8080/api/status -f "status,version"

# Create a resource
reqcap POST http://localhost:3000/api/users -b '{"name": "test"}' -f "id"

# Get a resource with filtered output
reqcap GET http://localhost:3000/api/users -f "data[].id,data[].name"

# Delete a resource
reqcap DELETE http://localhost:3000/api/users/123
```

## Output format

Default output (parse the `STATUS:` line first to check success):

```
STATUS: <code>
TIME: <ms>ms
BODY:
<json>
```

Use `--raw` for JSON body only (no status/time lines), useful for piping.

## Response filtering (-f)

Always use `-f` to minimize token output. Only request the fields you need.

```bash
reqcap GET /api/users -f "id,name,email"
reqcap GET /api/users -f "data[].id,data[].name"
reqcap GET /api/users -f "data[-1].name"
reqcap GET /api/users -f "data[0:3].id"
reqcap GET /api/user/1 -f "profile.name,profile.role"
```

### Path syntax

This syntax is shared by `-f` (response filtering), `--export`, and template `fields[].path` (body injection).

| Pattern | Meaning | Example |
|---|---|---|
| `field` | Top-level field | `id` |
| `a.b` | Nested field | `user.profile.name` |
| `a[].b` | Every array element | `data[].id` |
| `a[0]` | Specific index | `items[0].name` |
| `a[-1]` | Last element | `items[-1]` |
| `a[2:5]` | Slice | `items[2:5].id` |
| `a[2:]` | From index 2 onward | `items[2:]` |
| `a[:3]` | First 3 | `items[:3]` |
| `a[K]` | Bracket dict key | `headers[Content-Type]` |

Matching is case-insensitive. Combine with commas for `-f`: `-f "id,name,data[].email"`

## Headers and body

```bash
reqcap POST /api/data -b '{"key": "value"}' -H "Authorization: Bearer tok123"
```

## Template dependency chaining (preferred)

Templates can declare `depends:` to run prerequisites automatically. Exported variables flow through the chain.

```yaml
# templates/login.yaml
method: POST
url: /api/auth/login
exports:
  token: body.access_token

# templates/get-me.yaml
depends:
  - login
method: GET
url: /api/me
headers:
  Authorization: "Bearer {{token}}"
```

```bash
reqcap -t get-me -v email=a@b.com -v password=x -f "id,role"
# Runs login first, then get-me with the exported token
```

## Request chaining (--export, for scripting)

For one-off shell chaining outside templates:

```bash
eval $(reqcap POST /api/auth/login -b '{"email":"a@b.com","password":"x"}' --export token=body.access_token 2>&1 1>/dev/null)
reqcap GET /api/me -H "Authorization: Bearer $reqcap_token"
```

## Curl import

```bash
reqcap --import-curl "curl -X POST https://api.example.com -d '{\"n\":1}'" -f "id"
```

## Templates (advanced, project-specific)

Templates are user-created `.yaml` files that you place in a `templates/` directory in your project. There are NO built-in templates. You must create template files before using `-t`.

```bash
# Only works if templates/login.yaml exists in the project
reqcap -t login -v email=admin@test.com -v password=secret
reqcap --list-templates   # shows templates available in the current project
```

## CLI flags

| Flag | Short | Purpose |
|---|---|---|
| `METHOD URL` | | Direct request |
| `--template` | `-t` | Run a template file (name or path) |
| `--config` | `-c` | Config file path |
| `--templates-dir` | | Override templates directory |
| `--var` | `-v` | Variable `key=value` (repeatable) |
| `--body` | `-b` | JSON request body |
| `--header` | `-H` | Header `Name: Value` (repeatable) |
| `--filter` | `-f` | Comma-separated fields to extract |
| `--timeout` | | Timeout in seconds |
| `--verbose` | | Include response headers |
| `--raw` | | JSON body only |
| `--export` | | Export field as shell env var |
| `--assert` | | Assert `status=200` or `body.field!=val` (exit 1 on fail) |
| `--snapshot` | | Save response as named snapshot |
| `--diff` | | Diff response against saved snapshot |
| `--list-snapshots` | | List saved snapshots |
| `--form` | | Form field `KEY=VALUE` or `KEY=@FILE` (repeatable) |
| `--import-curl` | | Run a curl command string |
| `--history` | | Show recent requests |
| `--replay` | | Replay history entry by index |
| `--list-templates` | | List template files with descriptions |

## Config resolution

Config is found automatically (first match wins):
1. `-c /path/to/config` (explicit)
2. `.reqcap.yaml` in current directory
3. `~/.reqcap/config.yaml` (global)

Place `~/.reqcap/config.yaml` for global defaults that apply everywhere.

```yaml
defaults:
  base_url: http://localhost:3000
  env_file: .env
  timeout: 30
  templates_dir: templates    # resolved relative to this config file
  headers:
    Content-Type: application/json
  auth:
    type: bearer          # bearer | api-key | basic
    token: ${API_TOKEN}
```

## Templates (advanced, user-created)

Templates directory is found automatically (first match wins):
1. `--templates-dir /path` (explicit)
2. `templates_dir` from config (relative to config file's directory)
3. `./templates/` in current directory
4. `~/.reqcap/templates/` (global)

Create `.yaml` files in whichever templates directory you use:

```yaml
# templates/create-user.yaml
description: Create a new user
url: /api/users
method: POST
body:
  name: ""
  email: ""
fields:
  - name: name
    path: name
  - name: email
    path: email
exports:
  user_id: body.id
filter:
  body_fields: [id, name, email]
```

Properties: `url`, `method`, `body`, `headers`, `auth`, `fields`, `exports`, `filter`, `description`, `base_url`, `depends`, `snapshot`.

## Placeholders

In templates (URLs, bodies, headers):

| Placeholder | Value |
|---|---|
| `{{env.VAR}}` | Environment variable |
| `{{uuid}}` | Random UUID v4 |
| `{{timestamp}}` | Unix epoch seconds |
| `{{timestamp_ms}}` | Unix epoch milliseconds |
| `{{date}}` | ISO 8601 datetime |
| `{{my_var}}` | From `-v` flag or dep export |

In config files: `${VAR}` (shell-style env var substitution).

## Variable precedence

1. `-v key=value` (CLI flag — highest)
2. `depends:` exports (from dependency chain)
3. `{{env.VAR}}` / `os.environ` (lowest)

## Best practices

1. **Always use `-f`** — never dump full responses, specify exactly the fields you need.
2. **Check status first** — parse the `STATUS:` line before reading the body.
3. **Use `--raw` for piping** — when chaining with other tools or parsing JSON programmatically.
4. **Create templates** for repeated requests — less error-prone than rebuilding CLI args.
5. **Use relative URLs** with a config that sets `base_url` to keep commands short.
6. **Filter arrays with `[]`** — use `data[].id` instead of fetching entire arrays.
7. **Use `depends:` for chaining** — declare dependencies in templates instead of manual `eval` piping.
8. **Use `snapshot:` for baselines** — auto-save responses in templates, then `--diff` to detect regressions.
