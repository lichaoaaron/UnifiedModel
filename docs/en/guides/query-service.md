# Query Service Guide

中文：[Query Service 指南](../../zh/guides/query-service.md)

Query Service is the only public read path for UModel definitions, entities, relations, and topology. It accepts SPL strings that start with `.umodel`, `.entity`, or `.topo`.

## Why Reads Go Through Query Service

UModel intentionally avoids separate public domain read APIs such as entity lookup, relation lookup, graph traversal, or model search endpoints. One read surface keeps the CLI, Web UI, REST API, MCP tools, and SDK clients aligned.

## Entry Points

REST:

```http
POST /api/v1/query/{workspace}/execute
POST /api/v1/query/{workspace}/explain
```

CLI:

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".umodel | limit 5"
go run ./cmd/umctl --addr http://localhost:8080 query explain demo ".umodel | limit 5"
```

Agent tool:

```bash
go run ./cmd/umctl --addr http://localhost:8080 agent tool demo query_spl_execute '{"query":".umodel | limit 5"}'
```

## `.umodel`

`.umodel` reads UModel definitions.

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".umodel with(kind='entity_set') | sort name | limit 20"
```

Common reads:

- List entity sets.
- Inspect metric, log, trace, event, storage, and link definitions.
- Power the Web UI Explorer graph/table view.

## `.entity`

`.entity` reads runtime entity records.

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name | limit 20"
```

Common reads:

- Search entities in a domain and entity type.
- Inspect object properties.
- Feed object IDs into topology queries.

Agent and REST callers can bind named parameters into `with(...)` filters and `where` predicates:

```json
{
  "query": ".entity with(domain='devops', name='devops.service', query=$query) | limit 20",
  "parameters": {
    "query": "checkout"
  }
}
```

## `.topo`

`.topo` reads runtime topology relations.

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | project src,relation,dest | limit 20"
```

`.topo` supports graph-call style topology operations. The `memory`, `file.memory`, and optional `local.ladybug` providers support controlled read-only Cypher-compatible graph calls through the shared Go engine. `local.ladybug` still persists graph data in Ladybug when built with `-tags ladybug` and a local Ladybug runtime.

Cypher can return full entity and relation property maps in one query:

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".topo | graph-call cypher(`MATCH (src)-[r]->(dest) RETURN src, r AS relation, dest LIMIT 20`)"
```

Use `properties(src)`, `properties(r)`, and `properties(dest)` when callers want to make the property-map shape explicit.

## Common Pipe Operations

The local query layer supports the operations used by tests, examples, and the Web UI:

- `with(...)` for source-specific filters.
- `project` to select output fields.
- `sort` to order rows.
- `limit` to bound output.
- `graph-call` for topology functions.

Run the built-in examples:

```bash
go run ./cmd/umctl --addr http://localhost:8080 query examples
```

## Explain Output

Run `query explain` before wiring queries into UI or agent workflows:

```bash
go run ./cmd/umctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

Explain output reports:

- Query source: `.umodel`, `.entity`, or `.topo`.
- Active provider.
- Storage provider.
- Planned filters and limits.

## Boundary Rules

- Do not add public entity, relation, or topology read endpoints outside Query Service.
- Keep CLI domain reads behind `umctl query run` and `umctl query explain`.
- Keep AgentGateway resources metadata-only. Runtime rows should be returned by tools, not resources.

## evidence(...) — Entity Telemetry Lookback

The `evidence(...)` pipeline operator attaches telemetry data (metrics, logs, or traces) to a single entity selected by a `.entity` query. It resolves the following chain at runtime:

```
Entity → DataLink → DataSet → StorageLink → Storage → TelemetryProvider → local files
```

### Syntax

```
.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='log_set')
| limit 20

.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='metric_set')
| limit 20

.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='trace_set', from='2026-06-03T01:00:00Z', to='2026-06-03T01:02:00Z')
| limit 20
```

Parameters:

| Parameter | Required | Description |
|---|---|---|
| `kind` | Yes | Dataset kind. Must be `metric_set`, `log_set`, or `trace_set`. |
| `from` | No | ISO-8601 start of time range (inclusive). |
| `to` | No | ISO-8601 end of time range (inclusive). |

The `.entity` portion must resolve to **exactly one entity**. Zero or multiple entities produce an `INVALID_ARGUMENT` error.

### Execution Chain

1. The entity query runs as normal and must return exactly one row.
2. The executor reads the UModel snapshot to find a `data_link` element where:
   - `spec.src.domain` and `spec.src.name` match the entity type.
   - `spec.dest.kind` matches the requested `kind`.
3. The `fields_mapping` in the `data_link` spec provides the entity-to-dataset field mapping. The executor reads the mapped entity field value (e.g. `display_name`) to obtain the service name filter.
4. The executor finds a `storage_link` element where `spec.src.name` matches the DataSet name.
5. The executor finds the `storage` element named in the StorageLink's `spec.dest.name`.
6. The storage element's `spec.type` selects the TelemetryProvider (e.g. `local_file`).
7. The provider streams files, filters by service name and time range, and returns up to `limit` rows.

### Model Requirements

To use `evidence(...)` on an entity type, define:

1. One or more `metric_set`, `log_set`, or `trace_set` elements in the model pack.
2. A `data_link` for each dataset kind connecting the entity type to the dataset, with `fields_mapping` mapping the entity field to `serviceName`.
3. An `external_storage` (or other storage) element with `spec.type` matching a registered TelemetryProvider.
4. A `storage_link` connecting each dataset to the storage.

Example `data_link` mapping:

```yaml
spec:
  src:
    domain: platform
    kind: entity_set
    name: platform.service
  dest:
    domain: platform
    kind: log_set
    name: platform.service_logs
  data_link_type: produce
  fields_mapping:
    display_name: serviceName
```

### Local Snapshot Directory Configuration

The `local_file` TelemetryProvider resolves data paths from the Storage element's `spec.properties`:

```yaml
spec:
  type: local_file
  properties:
    metric_dir: data/metric
    log_dir: data/log
    trace_dir: data/trace
    time_field_metric: time
    time_field_log: time
    time_field_trace: startTime
```

Paths are resolved relative to the server's `data_root` directory (set by the `--data` flag or default). The local snapshot directory is **not** configured in the query request; it comes from the model.

### Streaming and Large Files

The local file provider reads JSON arrays incrementally using `encoding/json.Decoder`. It never loads an entire file into memory. Scanning stops as soon as the requested `limit` rows have been collected. Files are scanned in lexicographic name order.

### Explain Output

`evidence(...)` queries include an `evidence` section in the explain output:

```json
{
  "evidence": {
    "entity_id": "...",
    "entity_type": "platform.service",
    "entity_field_value": "iam-manage",
    "data_link_name": "platform.service_produces_platform.service_logs",
    "dataset_kind": "log_set",
    "dataset_name": "platform.service_logs",
    "storage_link_name": "platform.service_logs_stored_in_platform.local_snapshot",
    "storage_name": "platform.local_snapshot",
    "storage_type": "local_file",
    "provider": "local_file",
    "fields_mapping": {"display_name": "serviceName"},
    "time_from": "",
    "time_to": "",
    "scanned_files": ["data/log/opensearch_export_logs_0000.json"],
    "returned_rows": 20
  }
}
```

### Extending to OpenSearch

To add an OpenSearch provider, implement the `telemetry.Provider` interface in a new package and register it in `internal/bootstrap/app.go`:

```go
providers := []telemetry.Provider{
    localfile.New(config.DataRoot),
    opensearch.New(opensearchConfig),
}
```

The Query Service core and evidence executor require no changes. The storage type string in the model's Storage element selects the correct provider at runtime.
