# Entities And Relations

中文：[Entity 与 Relation](../../zh/concepts/entities-and-relations.md)

Entities and relations are runtime data. They instantiate the model definitions described by EntitySets and EntitySetLinks.


## Model Layer Versus Runtime Layer

| Model definition | Runtime data |
|---|---|
| `entity_set` | Entity records |
| `entity_set_link` | Relation records |
| `data_link` | Query-time binding between entities and datasets |
| `storage_link` | Query-time routing between datasets and storage |

## Entity Writes

Entities are written through EntityStore:

```http
POST /api/v1/entitystore/{workspace}/entities:write
```

CLI:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity write demo examples/quickstart-multidomain/sample-data/entities.json
```

Read entities through Query Service:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 20"
```

## Relation Writes

Relations are written through EntityStore:

```http
POST /api/v1/entitystore/{workspace}/relations:write
```

CLI:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 topo write demo examples/quickstart-multidomain/sample-data/relations.json
```

Read topology through Query Service:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20"
```

## Visibility

EntityStore supports write, expire, and delete-style lifecycle operations. The local query path hides expired or deleted records by default, while provider implementations can keep history for time-aware reads.

## Identity

Runtime records need stable entity IDs. MModel uses validated entity identifiers in topology calls and provider storage. When authoring examples, keep IDs deterministic so tutorials and tests remain copy-pasteable.

## Design Rules

- Import model definitions before writing runtime records.
- Keep entity fields aligned with their EntitySet definitions.
- Keep relation type names aligned with EntitySetLink definitions.
- Find IDs with `.entity` before running `.topo`.
- Keep sample data small enough to inspect by hand but rich enough to show topology.
