# reqcap examples

All examples use [httpbin.org](https://httpbin.org) as the target API.

## Setup

From the repo root, install the project:

```bash
uv sync
```

Then `cd` into this directory so the `.reqcap.yaml` config is picked up
(it sets `base_url: https://httpbin.org`, enabling relative URLs like `/get`):

```bash
cd examples
```

All examples below use `uv run reqcap` to run without a global install.
If you've installed the package globally (`uv tool install .` or `pip install .`),
you can use `reqcap` directly instead.

## Direct mode

```bash
# Simple GET
uv run reqcap GET /get

# GET with response filtering
uv run reqcap GET /get -f "url,origin"

# POST with JSON body
uv run reqcap POST /post -b '{"name":"alice","role":"admin"}'

# POST with filtering - only show the echoed JSON and URL
uv run reqcap POST /post -b '{"name":"alice"}' -f "json,url"

# Custom headers
uv run reqcap GET /headers -H "X-Custom: hello" -H "X-Request-Id: {{uuid}}" -f "headers"

# Verbose output (includes response headers)
uv run reqcap GET /get --verbose

# Raw output (body only, no STATUS/TIME - good for piping)
uv run reqcap GET /ip --raw
```

## Template mode

```bash
# List available templates
uv run reqcap --list-templates

# Get your public IP
uv run reqcap -t get-ip

# Post data with variables
uv run reqcap -t post-data -v name=alice -v email=alice@test.com

# Request a specific status code
uv run reqcap -t status-check -v code=418
```

## Response filtering

```bash
# Single field
uv run reqcap GET /get -f "origin"

# Multiple fields
uv run reqcap GET /get -f "origin,url,headers"

# Nested fields
uv run reqcap GET /get -f "headers.Host,headers.User-Agent"

# Array iteration (jsonplaceholder as example)
uv run reqcap GET https://jsonplaceholder.typicode.com/users -f "data[].id,data[].name"

# First item only
uv run reqcap GET https://jsonplaceholder.typicode.com/posts -f "data[0].title"
```

## Assertions

```bash
# Assert status code
uv run reqcap GET /get --assert status=200

# Assert on response body
uv run reqcap GET /ip --assert "body.origin!="

# Multiple assertions - fails on first failure (exit code 1)
uv run reqcap GET /get --assert status=200 --assert "body.url!=null"

# Use in CI/scripts - exit code 1 on failure
uv run reqcap GET /status/500 --assert status=200 || echo "Health check failed"
```

## Snapshots

```bash
# Save a baseline response
uv run reqcap GET /get --snapshot baseline

# Compare current response to baseline (exit 0 = same, exit 1 = different)
uv run reqcap GET /get --diff baseline

# List saved snapshots
uv run reqcap --list-snapshots
```

Templates can also auto-snapshot via the `snapshot:` key — see `templates/status-check.yaml`
for an example.

## Template dependency chaining

Templates can declare `depends:` to run prerequisite templates first.
Exported variables from dependencies are available to downstream templates.

```bash
# get-with-origin depends on get-ip, which exports `origin`
uv run reqcap -t get-with-origin
```

See `templates/get-ip.yaml` and `templates/get-with-origin.yaml` for the
dependency chain example.

## Request chaining (--export)

For scripting or one-off chaining outside of templates:

```bash
# Export a value from the response
uv run reqcap GET /get --export origin=body.origin

# Chain requests using exported env vars
eval $(uv run reqcap GET /get --export origin=body.origin 2>&1 1>/dev/null)
echo $reqcap_origin

# Shorthand - export field with same name
uv run reqcap GET /ip --export origin
```

## Form data / file upload

```bash
# Text fields
uv run reqcap POST /post --form name=alice --form role=admin

# File upload
echo "hello world" > /tmp/test.txt
uv run reqcap POST /post --form file=@/tmp/test.txt --form description="test upload"
```

## Curl import

```bash
# Convert a curl command to reqcap
uv run reqcap --import-curl "curl -X POST https://httpbin.org/post -H 'Content-Type: application/json' -d '{\"name\":\"test\"}'"
```

## History and replay

```bash
# Show recent request history
uv run reqcap --history

# Replay the most recent request
uv run reqcap --replay 0
```

## Project scaffolding

```bash
# In a new project directory, scaffold config + directories
mkdir my-api-project && cd my-api-project
uv run reqcap --init
```
