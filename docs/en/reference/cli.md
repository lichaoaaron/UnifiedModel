# CLI Reference

中文：[CLI 参考](../../zh/reference/cli.md)

`mmctl` is the public CLI for the local MModel REST API.

Repository-root command:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 help
```

Build a local binary:

```bash
go build -o mmctl ./cmd/mmctl
./mmctl --addr http://localhost:8080 help
```

## Global Options

| Option | Default | Description |
|---|---|---|
| `--addr` | `http://localhost:8080` | Base URL for `mmodel-server`. |

## Server Quickstart Flags

`mmodel-server` preloads the bundled demo before it starts serving requests:

```bash
go run ./cmd/mmodel-server --quickstart
```

| Flag | Default | Description |
|---|---|---|
| `--quickstart` | `false` | Create the quickstart workspace and import bundled sample data before listening. Uses `memory` unless `--graphstore` is explicitly set. |
| `--quickstart-workspace` | `demo` | Workspace id used by `--quickstart`. |
| `--quickstart-sample` | `multi-domain-quickstart` | Sample package imported by `--quickstart`. |

## Command Groups

| Group | Commands | Purpose |
|---|---|---|
| `workspace` | `create`, `get`, `list`, `update`, `delete` | Manage workspace metadata. |
| `mmodel` | `put`, `delete`, `import`, `export`, `validate` | Write, validate, import, and export MModel definitions. |
| `entity` | `write`, `delete`, `expire` | Write or expire entity records. |
| `topo` | `write`, `delete`, `expire` | Write or expire relation records. |
| `query` | `run`, `explain`, `examples` | Read model, entity, and topology data through Query Service. |
| `agent` | `discover`, `tool`, `mcp` | Inspect agent metadata and execute safe tools. |

Entity and topology read commands are intentionally absent. Use `query run` or `query explain` for all reads.

## Workspace

```bash
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
go run ./cmd/mmctl --addr http://localhost:8080 workspace get demo
go run ./cmd/mmctl --addr http://localhost:8080 workspace list
go run ./cmd/mmctl --addr http://localhost:8080 workspace update demo '{"description":"Updated"}'
go run ./cmd/mmctl --addr http://localhost:8080 workspace delete demo
```

## MModel

```bash
go run ./cmd/mmctl --addr http://localhost:8080 mmodel validate demo examples/quickstart-multidomain/devops/entity_set/devops.service.yaml
go run ./cmd/mmctl --addr http://localhost:8080 mmodel put demo '{"kind":"entity_set","domain":"devops","name":"devops.service"}'
go run ./cmd/mmctl --addr http://localhost:8080 mmodel import demo examples/quickstart-multidomain
go run ./cmd/mmctl --addr http://localhost:8080 mmodel export demo 100
```

`mmodel put` and `mmodel validate` accept a JSON object, a JSON array, or a JSON payload with an `elements` field.

## EntityStore

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity write demo /tmp/entity.json
go run ./cmd/mmctl --addr http://localhost:8080 entity expire demo devops/devops.service/10000000000000000000000000000101
go run ./cmd/mmctl --addr http://localhost:8080 topo write demo /tmp/relation.json
go run ./cmd/mmctl --addr http://localhost:8080 topo delete demo devops/devops.service/10000000000000000000000000000101/runs/k8s/k8s.workload/20000000000000000000000000000201
```

Write commands accept JSON objects, arrays, or payloads with `entities` or `relations`.

## Query

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query examples
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
go run ./cmd/mmctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

Reference: [Query Service Guide](../guides/query-service.md).

## Agent

```bash
go run ./cmd/mmctl --addr http://localhost:8080 agent discover demo
go run ./cmd/mmctl --addr http://localhost:8080 agent tool demo query_spl_examples '{}'
go run ./cmd/mmctl --addr http://localhost:8080 agent tool demo query_spl_explain '{"query":".mmodel | limit 5"}'
```

`agent mcp` prints a reminder to use the `mmodel-mcp` binary for stdio MCP workflows.
