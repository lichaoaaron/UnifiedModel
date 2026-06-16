# cmd/

中文版本：[README.md](README.md)

Entry Layer: process entry points.

| Directory | Description |
|---|---|
| `mmodel-server/` | MModel HTTP service. |
| `mmctl/` | CLI tool for the public REST API. |
| `mmodel-mcp/` | stdio MCP server. |

## GraphStore Provider Flag

`mmodel-server` and `mmodel-mcp` both support `--graphstore`:

| Provider | Description |
|---|---|
| `memory` | In-memory provider for fast local verification; data is lost on process exit. |
| `file.memory` | In-memory querying plus JSON file persistence under `<--data>/graphstore/file-memory/`. |
| `local.ladybug` | Ladybug-backed provider; requires `-tags ladybug` and a local Ladybug runtime. |

Examples:

```bash
go run ./cmd/mmodel-server --addr :8080 --data data --graphstore file.memory
go run ./cmd/mmodel-mcp --data data --graphstore file.memory
```

See [GraphStore Providers](../docs/en/graphstore-providers.md).
