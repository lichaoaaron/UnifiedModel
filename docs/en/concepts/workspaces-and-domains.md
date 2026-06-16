# Workspaces And Domains

中文：[Workspace 与 Domain](../../zh/concepts/workspaces-and-domains.md)

Workspaces and domains are the two main scope controls in MModel.


## Workspace

A workspace is an isolated context for:

- MModel definitions.
- Entity and relation records.
- Query execution.
- AgentGateway discovery and tools.
- Local GraphStore persistence.

The public API makes the workspace explicit in path parameters:

```http
POST /api/v1/mmodel/{workspace}/import
POST /api/v1/entitystore/{workspace}/entities:write
POST /api/v1/query/{workspace}/execute
GET  /api/v1/agent/{workspace}/discover
```

CLI commands use the same model:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
```

## Domain

A domain is a semantic namespace inside a workspace. Examples include:

- `devops` for delivery and service ownership objects.
- `k8s` for Kubernetes objects.
- `automaker`, `game`, or `supplier` for business scenario objects.

Domain names appear in MModel metadata:

```yaml
metadata:
  name: "devops.service"
  domain: devops
```

They also appear in query filters:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

## Boundary Rules

Workspace boundary: operational isolation for separate teams, demos, test fixtures, or tenant-like local contexts.

Domain boundary: shared vocabulary and naming for DevOps services, Kubernetes workloads, cloud resources, or business-specific objects.

## Naming Rules

| Item | Shape | Example |
|---|---|---|
| Workspace ID | short, URL-safe, environment-oriented | `demo`, `dev`, `quickstart-lab` |
| Domain | lowercase semantic namespace | `devops`, `k8s`, `automaker` |
| EntitySet name | `{domain}.{entity}` | `devops.service` |
| MetricSet name | `{domain}.metric.{scope}` | `devops.metric.devops.service` |
| Storage name | `{domain}.{kind}.{purpose}.storage` | `devops.metric_set.core.storage` |

## Persistence

When using `file.memory`, workspace metadata is saved under the data root and graph collections are saved by workspace:

```text
data/
├── workspaces.json
└── graphstore/file-memory/workspaces/demo/
    ├── mmodels.json
    ├── entities.json
    └── relations.json
```

Provider details: [Storage And GraphStore Providers](storage-and-graphstore.md).
