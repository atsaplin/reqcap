# Template reference

Templates are standalone YAML files that define reusable API requests. Each template is a single `.yaml` file.

## Template resolution

When you run `reqcap -t NAME`, the tool looks for the template in this order:

1. Exact file path (e.g. `reqcap -t path/to/my-template.yaml`)
2. `templates_dir` from config + `NAME.yaml` (if `templates_dir` is set)
3. `./templates/NAME.yaml`

## Template properties

| Property | Required | Description |
|---|---|---|
| `url` | Yes | Endpoint path. Appended to `base_url` if relative. |
| `method` | No | HTTP method (default: `GET`). |
| `description` | No | Shown in `--list-templates` output. |
| `name` | No | Identifier. Defaults to the filename (without extension). |
| `base_url` | No | Override the config `base_url` for this template only. |
| `headers` | No | Template-specific headers (merged with config defaults). |
| `auth` | No | Template-specific auth config (overrides default auth). |
| `body` | No | Request body as a YAML object. Serialized as JSON. |
| `fields` | No | Array of variable injection rules (see below). |
| `exports` | No | Map of `name: body.path` — auto-export response values. |
| `filter` | No | Response filter config with `body_fields` list. |
| `depends` | No | List of template names to run first (depth-first). |
| `snapshot` | No | Auto-save response: `{enabled: true, name: "..."}`. |

## Variable injection (fields)

The `fields` array maps `-v key=value` CLI args into specific paths in the request body.

```yaml
body:
  user:
    name: ""
    email: ""
    settings:
      theme: "light"

fields:
  - name: name
    path: user.name
  - name: email
    path: user.email
  - name: theme
    path: user.settings.theme
```

```bash
reqcap -t create-user -v name=Alice -v email=alice@test.com -v theme=dark
# body becomes: {"user": {"name": "Alice", "email": "alice@test.com", "settings": {"theme": "dark"}}}
```

The `path` uses dot notation. Array indices are supported: `messages[0].content`.

## Dependencies (depends)

Templates can declare dependencies that are executed depth-first before the main request. Exported variables from each dependency are available to downstream templates.

```yaml
# templates/get-users.yaml
depends:
  - login
method: GET
url: /api/users
headers:
  Authorization: "Bearer {{token}}"
```

```bash
reqcap -t get-users -v email=admin -v password=secret
# Runs: login (exports token) → get-users (uses {{token}})
```

Circular dependencies are detected and reported. A `-v` variable overrides any dep export of the same name.

## Auto-exports

The `exports` map extracts values from the response and prints them as shell `export` commands to stderr. When used with `depends:`, exported values are automatically passed to downstream templates as variables.

```yaml
exports:
  token: body.access_token
  user_id: body.user.id
```

On a successful response with `{"access_token": "abc", "user": {"id": 42}}`, stderr will contain:

```
export reqcap_token=abc
export reqcap_user_id=42
```

Capture with: `eval $(reqcap -t login -v ... 2>&1 1>/dev/null)`

## Auto-snapshot (snapshot)

Templates can automatically save the response as a snapshot after each run.

```yaml
snapshot:
  enabled: true
  name: health-baseline    # optional, defaults to template name
```

When `enabled: true`, the response is saved to the snapshots directory after execution. The `name` field overrides the snapshot filename (defaults to the template name). This works alongside `--snapshot` and `--diff` CLI flags.

## Template filter

```yaml
filter:
  body_fields: [id, name, email]
```

This is equivalent to passing `-f "id,name,email"` on the CLI. The CLI `-f` flag overrides the template filter.

Filter priority: CLI `--filter` > template `filter` > config default `filter`.

## Auth in templates

Templates can specify their own auth, overriding the config default:

```yaml
# Bearer token from a chained variable
auth:
  type: bearer
  token: "{{token}}"
```

```yaml
# API key
auth:
  type: api-key
  token: "{{env.API_KEY}}"
  header: X-API-Key
```

```yaml
# Basic auth
auth:
  type: basic
  username: "{{env.USER}}"
  password: "{{env.PASS}}"
```

## Placeholders in templates

All string values in a template support placeholders:

| Placeholder | Value |
|---|---|
| `{{env.VAR}}` | Environment variable |
| `{{uuid}}` | Random UUID v4 |
| `{{timestamp}}` | Unix epoch (seconds) |
| `{{timestamp_ms}}` | Unix epoch (milliseconds) |
| `{{date}}` | ISO 8601 datetime |
| `{{name}}` | Variable from `-v name=value` or dep export |

## Full example

```yaml
# templates/login.yaml
description: Authenticate and export token
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

```yaml
# templates/create-order.yaml
description: Create a new order (auto-login via depends)
depends:
  - login
url: /api/orders
method: POST
auth:
  type: bearer
  token: "{{token}}"
body:
  id: "{{uuid}}"
  items: []
  customer_email: ""
  placed_at: "{{date}}"
fields:
  - name: email
    path: customer_email
  - name: item
    path: items[0]
exports:
  order_id: body.id
snapshot:
  enabled: true
  name: last-order
filter:
  body_fields: [id, status, total]
```

```bash
# Single command — login runs automatically, token flows through
reqcap -t create-order -v email=a@b.com -v password=x -v item='{"sku":"A1","qty":2}'
```
