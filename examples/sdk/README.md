# SDK Examples

中文：[SDK 示例](README.zh-CN.md)

Runnable examples for the public MModel SDK surfaces.

Coverage:

- inspect a MModel pack before importing it into a workspace;
- combine generated model SDKs with the REST service client;
- keep application code on public contracts instead of internal server packages.

## Examples

| Path | Surface | Purpose |
|---|---|---|
| [full-flow.md](full-flow.md) | End-to-end flow | SDK generation, service startup, and SDK execution. |
| [go/model-inspector](go/model-inspector) | Generated Go model SDK | Parse YAML/JSON MModel files, validate envelopes, list model metadata, and show link endpoints. |
| [go/service-quickstart](go/service-quickstart) | Go REST client | Create a workspace, import a model pack, query MModel elements, and inspect Agent discovery. |
| [python/inspect_model_pack.py](python/inspect_model_pack.py) | Generated Python model SDK | Scan a model pack and print kind/domain/name/link summaries. |

## Run The Go Examples

The generated Go SDK currently uses the repository-local module path `mmodel_go_cli`, so the runnable examples are kept in a small example module with a local `replace`.

```bash
cd examples/sdk/go
go mod tidy
go run ./model-inspector -path ../../quickstart-multidomain
```

For the REST client example, start the API first from the repository root:

```bash
make dev-api
```

Then, in another shell:

```bash
cd examples/sdk/go
go run ./service-quickstart -addr http://localhost:8080
```

## Run The Python Example

The Python example adds `sdk/python` to `sys.path` automatically from a repository checkout.

```bash
python3 examples/sdk/python/inspect_model_pack.py --path examples/quickstart-multidomain
```

## Contract Boundary

Generated model SDKs cover local model construction, parsing, and metadata inspection. Runtime reads and writes go through the public REST API, the Go REST client, `mmctl`, or MCP.
