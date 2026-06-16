# Entity And Relation Write Guide

中文：[实体与关系写入指南](../../zh/guides/entity-relation-writes.md)

Runtime entity and relation write workflow after model import.


## Start With Model Definitions

Import a model pack before writing runtime data:

```bash
make dev
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
go run ./cmd/mmctl --addr http://localhost:8080 mmodel import demo examples/quickstart-multidomain
```

## Write Entities

Bundled multi-domain quickstart sample:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity write demo examples/quickstart-multidomain/sample-data/entities.json
```

Equivalent REST endpoint:

```http
POST /api/v1/entitystore/{workspace}/entities:write
```

## Verify Entities

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 20"
```

Keyword search:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name | limit 20"
```

## Write Relations

```bash
go run ./cmd/mmctl --addr http://localhost:8080 topo write demo examples/quickstart-multidomain/sample-data/relations.json
```

Equivalent REST endpoint:

```http
POST /api/v1/entitystore/{workspace}/relations:write
```

## Verify Topology

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20"
```

## Expire Records

Expire entities:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity expire demo 10000000000000000000000000000101 "retired from sample"
```

Expire relations:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 topo expire demo <relation-id> "retired from sample"
```

## Rules

- Keep sample data deterministic.
- Use IDs that are stable across docs, tests, and screenshots.
- Write model definitions first, runtime data second.
- Read runtime data only through Query Service.
- Prefer small examples that show search, direct relation lookup, and relation types clearly.
