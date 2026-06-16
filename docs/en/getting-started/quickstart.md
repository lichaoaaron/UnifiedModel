# Quick Start

中文：[快速开始](../../zh/getting-started/quickstart.md)

Start MModel with the bundled multi-domain demo loaded, then run model, entity, topology, and AgentGateway checks.


## 1. Start With Demo Data

```bash
make quickstart
```

The API runs at `http://localhost:8080` and the Web UI runs at `http://localhost:5173`.

Quickstart preloads the `demo` workspace in `GRAPHSTORE=memory`. Process stop resets the demo state.

Choose a path:

- Web UI: open `http://localhost:5173`, select `demo`, and inspect the sample through Explorer, Query, Data Store, and Agent views. Docs: [Web UI Guide](../guides/web-ui.md).
- Agent integration: inspect AgentGateway with `mmctl agent discover demo`, then connect an MCP client through `mmodel-mcp`. Docs: [MCP Reference](../reference/mcp.md) and [Query And Agent Architecture](../architecture/query-and-agent.md).
- CLI or REST queries: run `.mmodel`, `.entity`, and `.topo` through Query Service. Docs: [Query Service Guide](../guides/query-service.md).

Sample assets: [examples/quickstart-multidomain](../../../examples/quickstart-multidomain/README.md).

API-only startup:

```bash
go run ./cmd/mmodel-server --quickstart
```

## 2. Query Model Definitions

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | sort name | limit 10"
```

## 3. Query Runtime Entities

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | limit 10"
```

## 4. Query Topology

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 10"
```

## 5. Explain A Query

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

Explain output shows the query source, active provider, storage provider, planned operators, and limits.

## 6. Inspect Agent Metadata

```bash
go run ./cmd/mmctl --addr http://localhost:8080 agent discover demo
go run ./cmd/mmctl --addr http://localhost:8080 agent tool demo query_spl_examples '{}'
```

## 7. Open The Web UI

Open `http://localhost:5173` and select `demo`.

- Explorer: MModel definitions.
- Query: `.mmodel`, `.entity`, and `.topo`.
- Imports & Writes: model import, entity writes, and relation writes.
- Agent: discovery, tools, resources, and next actions.

## 8. Stop

```bash
make stop-all
```

## Related References

- [Concepts](../concepts/index.md)
- [Multi-Domain Quickstart Example Pack](../../../examples/quickstart-multidomain/README.md)
- [Query Service Guide](../guides/query-service.md)
- [Architecture Overview](../architecture/overview.md)
