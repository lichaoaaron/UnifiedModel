# OpenTelemetry Demo (Astronomy Shop) Example Pack

`examples/otel-demo` models the official [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) (Astronomy Shop) as an MModel pack. It defines the OTel demo microservices as entities, links their telemetry datasets (metrics, logs, traces), and maps the service-to-service call topology.

This pack covers the full picture: entity definitions, dataset definitions, storage definitions, data links, storage links, and entity topology links.

## Contents

| Area | Path | Count | Purpose |
|---|---:|---|
| Entity sets | `entity_set/` | 1 | OTel microservice entity definition. |
| Datasets | `dataset/` | 3 | metric_set, log_set, trace_set for OpenTelemetry signals. |
| Storage | `storage/` | 2 | OpenSearch live + local file snapshot storage. |
| Data links | `link/data_link/` | 3 | Service → produces → metric/log/trace. |
| Storage links | `link/storage_link/` | 3 | Dataset → stored_in → OpenSearch storage. |
| Entity links | `link/entity_set_link/` | 16 | Service-to-service call topology. |
| Runtime entities | `sample-data/entities.json` | 16 | 16 OTel Demo microservice entity records. |
| Runtime relations | `sample-data/relations.json` | 16 | Service call topology records. |

## Modeled Services (16)

| Service | Language | Role |
|---|---|---|
| frontend-proxy | Go | Envoy reverse proxy |
| frontend | Go | Web UI and session orchestration |
| frontend-web | JavaScript | Browser-side instrumentation |
| product-catalog | Go | Product listings and search |
| image-provider | Rust | Static asset serving |
| cart | .NET | Shopping cart (Redis-backed) |
| recommendation | Python | Product recommendations |
| currency | C++ | Currency conversion |
| product-reviews | Java | Product reviews |
| load-generator | Python (Locust) | Traffic simulation |
| quote | Rust | Shipping cost quotes |
| ad | Java | Contextual advertisements |
| shipping | Rust | Shipping cost estimation |
| checkout | Go | Checkout workflow orchestration |
| payment | JavaScript (Node.js) | Payment processing |
| fraud-detection | Kotlin | Fraud detection |

## Import

Create a new workspace and import:

```bash
# Create the workspace
curl -X POST http://localhost:8080/api/v1/workspaces \
  -H 'Content-Type: application/json' \
  -d '{"id": "otel-demo", "name": "OpenTelemetry Demo"}'

# Import the model pack
go run ./cmd/mmctl --addr http://localhost:8080 mmodel import otel-demo examples/otel-demo

# Import entity and relation records
go run ./cmd/mmctl --addr http://localhost:8080 entity write otel-demo examples/otel-demo/sample-data/entities.json
go run ./cmd/mmctl --addr http://localhost:8080 entity write otel-demo examples/otel-demo/sample-data/relations.json
```

## Query Examples

```bash
# List all entity sets
go run ./cmd/mmctl --addr http://localhost:8080 query run otel-demo ".mmodel with(kind='entity_set') | project domain,name | sort name"

# Find a service entity
go run ./cmd/mmctl --addr http://localhost:8080 query run otel-demo ".entity with(domain='otel', name='otel.service', query='frontend') | project __entity_id__,display_name,language | limit 10"

# Explore service topology (direct neighbors of checkout)
go run ./cmd/mmctl --addr http://localhost:8080 query run otel-demo ".topo | graph-call getDirectRelations([(:\"otel@otel.service\" {__entity_id__: 'a000000000000000000000000000000e'})]) | project src,relation,dest | limit 20"

# Evidence lookup: metrics for frontend-proxy
go run ./cmd/mmctl --addr http://localhost:8080 query run otel-demo ".entity with(domain='otel', name='otel.service', ids=('a0000000000000000000000000000001')) | evidence(kind='metric_set', from='2026-06-26T00:00:00Z', to='2026-06-26T12:00:00Z') | limit 5"
```

## Prerequisites

- OpenSearch running at `http://localhost:13121` (credentials in `storage/otel.opensearch_live.yaml`)
- OpenTelemetry Demo stack running and exporting to OpenSearch
- MModel server started

## Maintenance Rules

- Keep model YAML, entity payloads, relation payloads, and docs aligned.
- Update the service list when the OTel Demo adds or removes services.
- Adjust storage credentials and index patterns to match your environment.
