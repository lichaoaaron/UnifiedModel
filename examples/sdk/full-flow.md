# SDK End-To-End Flow

中文：[SDK 端到端示例流程](full-flow.zh-CN.md)

End-to-end SDK flow: generation, local service startup, generated-SDK inspection, REST client execution. Commands run from the repository root unless a command block explicitly changes directory.

## Goal

Result:

- regenerated and verified Go, Python, and Java model SDKs;
- a local MModel API service;
- a generated-SDK model-pack inspection flow;
- a Go REST client flow that creates a workspace, imports a model pack, and queries runtime state.

## 1. Prepare Dependencies

Fresh checkout setup:

```bash
make setup
```

`make setup` prepares Python dependencies and downloads Go or Java dependencies when the tools are available.

## 2. Generate SDKs

MModel model SDKs are generated from `schemas/`. Schema changes require:

```bash
make expand
```

Generated outputs:

- expands `schemas/` into `expanded_schemas/`;
- validates expanded schemas;
- regenerates `sdk/go/mmodel`;
- regenerates `sdk/python/mmodel`;
- regenerates `generated/java`.

Then verify generated SDK assets:

```bash
make verify
```

Focused Go REST client check:

```bash
cd sdk/go
go test ./service
```

## 3. Inspect A Model Pack With Generated SDKs

Generated model SDK responsibilities before runtime import: parse YAML/JSON, validate the envelope, read kind/domain/name, and inspect link src/dest endpoints.

### Go Model Inspector

```bash
cd examples/sdk/go
go run ./model-inspector -path ../../quickstart-multidomain -limit 5
```

Expected output includes the SDK version, kind counts, and model summaries:

```text
MModel Go SDK 2.0.0
Parsed 77 MModel files
- entity_set: 35
- entity_set_link: 42
...
```

### Python Model Inspector

Repository-root command:

```bash
python3 examples/sdk/python/inspect_model_pack.py --path examples/quickstart-multidomain --limit 5
```

The Python example adds the repository-local `sdk/python` path to `sys.path`.

## 4. Start The Local MModel API

REST client examples require a running API. New terminal:

```bash
DATA_ROOT=/tmp/mmodel-sdk-demo-data GRAPHSTORE=file.memory make dev-api
```

Keep that terminal running. Readiness check from another terminal:

```bash
curl -fsS http://localhost:8080/healthz
```

Alternative port:

```bash
API_ADDR=:18080 API_URL=http://localhost:18080 DATA_ROOT=/tmp/mmodel-sdk-demo-data GRAPHSTORE=file.memory make dev-api
```

Then pass the same base URL to the REST client with `-addr http://localhost:18080`.

## 5. Run The Go REST Client Example

In another terminal:

```bash
cd examples/sdk/go
go run ./service-quickstart -addr http://localhost:8080 -workspace sdk-demo
```

The example calls public REST contracts:

1. create or reuse the `sdk-demo` workspace;
2. import the `examples/quickstart-multidomain` model pack;
3. execute `.mmodel with(kind='entity_set') | limit 5`;
4. call Agent discovery and inspect tools, resources, and next actions.

Typical output:

```text
Workspace "sdk-demo" created.
Imported 77 MModel elements from /.../examples/quickstart-multidomain.
Query returned 5 rows with columns [...]
Agent discovery: 7 tools, 4 resources, 5 next actions.
```

Existing workspace behavior: reuse, then import and query.

## 6. Cross-Check With CLI

Cross-check the same workspace through `mmctl`:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run sdk-demo ".mmodel with(kind='entity_set') | limit 5"
```

Same workspace state through another public surface.

## Flow Boundary

| Stage | Entry | Notes |
|---|---|---|
| SDK generation | `make expand` | Generate Go/Python/Java model SDKs from schema. |
| Local validation | `model-inspector` / `inspect_model_pack.py` | Parse and inspect model packs without connecting to the service. |
| Service startup | `make dev-api` | Start the local MModel API. |
| Runtime integration | `service-quickstart` | Use public REST contracts for workspace import and query. |
| Cross-check | `mmctl` | Read the same workspace through CLI. |

Generated model SDKs do not own runtime reads and writes. Runtime entity, relation, query, and Agent discovery flows go through REST, `mmctl`, or MCP.

## Troubleshooting

### `make expand` misses Python dependencies

Run:

```bash
make setup
```

### `service-quickstart` cannot connect

Confirm the API is still running and that `-addr` matches the service port:

```bash
curl -fsS http://localhost:8080/healthz
```

### Go examples cannot resolve modules

Run Go SDK examples from `examples/sdk/go`, where `go.mod` uses a local `replace` to point at `sdk/go`:

```bash
cd examples/sdk/go
go run ./model-inspector -path ../../quickstart-multidomain
```

### Python cannot import `mmodel`

Repository checkout command:

```bash
python3 examples/sdk/python/inspect_model_pack.py --path examples/quickstart-multidomain
```
