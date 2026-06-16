# Object Graph Semantic Layer

中文：[对象图语义层](../../zh/concepts/object-graph-semantic-layer.md)

MModel is the object graph semantic layer inside a vendor-neutral semantic runtime for enterprise AI, data governance, and operational intelligence. It does not replace data platforms, telemetry collectors, metric stores, tracing systems, Kubernetes, Prometheus, OpenTelemetry, CMDB systems, or AI tools. It gives them a shared object vocabulary, relationship semantics, and graph-shaped context surface that people, services, and AI agents can query.


## Problem

Enterprise systems already produce and store a lot of data:

- Business systems describe customers, orders, tickets, assets, and processes.
- Data platforms describe tables, fields, metrics, ownership, and lineage.
- Observability systems describe metrics, logs, traces, events, profiles, and runbooks.
- CMDB, cloud APIs, and Kubernetes describe resources and workload state.
- AI applications need trustworthy context before they analyze, predict, or act.

The missing layer: semantic alignment. Raw data exists, but core enterprise questions stay fragmented:

- What business or operational object does this data describe?
- Which objects are related?
- Which fields, metrics, storage, query, and topology definitions explain that relationship?
- What safe context can an AI agent read before acting?

## MModel's Role

MModel models enterprise context as a workspace-scoped object graph:

- `EntitySet` defines a class of business or operational objects, such as services, instances, operations, databases, assets, and external dependencies.
- `DataSet` types define structured datasets and telemetry datasets, such as metrics, logs, traces, events, profiles, and runbooks.
- `Storage` types describe where data lives.
- `Link` types connect entities, datasets, and storage.
- Entity and relation records provide runtime graph data.
- Query Service exposes `.mmodel`, `.entity`, and `.topo` as one read surface.

## MModel Contribution

| Layer | Existing systems | MModel contribution |
|---|---|---|
| Enterprise data | Data warehouses, data catalogs, business APIs | Gives datasets, fields, metrics, ownership, and lineage shared semantic anchors. |
| Telemetry and operations | OpenTelemetry, agents, logs, metrics, traces | Maps operational signals to modeled objects and relations. |
| Runtime resources | Kubernetes, cloud APIs, CMDB | Provides stable entity and relation semantics. |
| Query and exploration | SLS, Prometheus, trace stores, graph stores | Offers one Query Service for model, entity, and topology reads. |
| Agent context | MCP clients and AI agents | Exposes safe resources, query templates, and read-only tools by default. |

## Design Principles

- Workspace first: every operation is scoped to a workspace.
- Spec first: schemas, OpenAPI, MCP schemas, and public model types are treated as contracts.
- Query first: reads go through Query Service instead of scattered domain endpoints.
- Provider neutral: storage is behind GraphStore providers.
- Agent safe: resources are metadata-oriented, and write tools require explicit enablement.

## Public Surfaces

- REST API: `api/openapi/openapi.yaml`
- CLI: `mmctl`
- MCP server: `mmodel-mcp`
- Web UI: `web/`
- SDKs: `sdk/go`, `sdk/python`, and `generated/java`

## Related References

- [Concepts Index](index.md)
- [Workspaces And Domains](workspaces-and-domains.md)
- [Model Elements](model-elements.md)
- [Quick Start](../getting-started/quickstart.md)
- [Query Service Guide](../guides/query-service.md)
- [GraphStore Providers](../graphstore-providers.md)
- [MCP Reference](../reference/mcp.md)
