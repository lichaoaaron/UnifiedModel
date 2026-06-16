# Multi-Domain Quickstart Example Pack

`examples/quickstart-multidomain` is the default `make quickstart` sample. It shows how one workspace can connect DevOps ownership, coarse Kubernetes runtime topology, and enterprise scenario domains from `Demo/mmodel-demo-2/mmodel`.

The Kubernetes domain is intentionally coarse-grained: it models the runtime objects that help explain service topology, not a full Kubernetes object model.

This pack is entity-topology only. It intentionally does not define `metric_set`, `log_set`, `trace_set`, `event_set`, `profile_set`, `runbook_set`, `data_link`, or `storage_link` objects in any domain.

## Contents

| Area | Path | Count | Purpose |
|---|---|---:|---|
| DevOps entity sets | `devops/entity_set/` | 10 | Teams, services, repositories, pipelines, environments, deployments, releases, changes, incidents, and SLOs. |
| Kubernetes entity sets | `k8s/entity_set/` | 7 | Coarse clusters, namespaces, workloads, pods, nodes, services, and ingresses. |
| Enterprise demo entity sets | `automaker/entity_set/`, `game/entity_set/`, `supplier/entity_set/` | 18 | Entity topology reused from `Demo/mmodel-demo-2/mmodel`. |
| Entity links | `*/link/entity_set_link/`, `cross-domain/link/entity_set_link/` | 42 | In-domain and cross-domain topology semantics. |
| Dataset definitions | not included | 0 | Quickstart stays focused on entity and topology modeling. |
| Runtime entities | `sample-data/entities.json` | 93 | CMS 2.0 compatible entity payloads. |
| Runtime relations | `sample-data/relations.json` | 125 | CMS 2.0 compatible topology payloads. |

## Import

Start the quickstart server:

```bash
make quickstart
```

Manual import into another workspace:

```bash
curl -X POST http://localhost:8080/api/v1/samples/demo/multi-domain-quickstart:import \
  -H 'Content-Type: application/json' \
  -d '{}'
```

## Query Examples

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20"

go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name,status,owner | limit 10"

go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getNeighborNodes('full', 2, [(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20"
```

## Maintenance Rules

- Keep model YAML, entity payloads, relation payloads, and docs aligned.
- Keep this pack free of dataset kinds such as `metric_set`, `log_set`, `trace_set`, `event_set`, `profile_set`, and `runbook_set`.
- Keep k8s coarse for quickstart readability.
- Reuse only `entity_set` and `entity_set_link` from `Demo/mmodel-demo-2/mmodel`; do not copy its metric, log, storage, or storage link definitions into quickstart.
- Run `make example-validate` and `go test ./internal/sampledata ./internal/bootstrap ./internal/query` after changing this pack.
