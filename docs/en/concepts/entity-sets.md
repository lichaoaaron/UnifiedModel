# Entity Sets

中文：[EntitySet](../../zh/concepts/entity-sets.md)

An EntitySet defines a class of operational objects. Services, instances, operations, databases, queues, and Kubernetes workloads are all typical EntitySet candidates.


## Responsibilities

An EntitySet answers:

- What type of object is this?
- Which fields identify and describe it?
- Which domain owns the vocabulary?
- Which datasets or topology links can attach to it?

## Example

```yaml
kind: entity_set
metadata:
  name: "devops.service"
  domain: devops
spec:
  fields:
    - name: id
      type: string
    - name: display_name
      type: string
    - name: owner
      type: string
```

The multi-domain quickstart sample contains EntitySets such as:

- `devops.service`
- `devops.pipeline`
- `k8s.workload`
- `automaker.vehicle`
- `game.server`
- `supplier.production_batch`

See [examples/quickstart-multidomain](../../../examples/quickstart-multidomain/README.md).

## EntitySet Versus Entity Record

| Layer | Example | Purpose |
|---|---|---|
| EntitySet | `devops.service` | Defines the object type and fields. |
| Entity record | a specific checkout service | Stores one runtime object instance. |

Entity records are written through EntityStore APIs and read through `.entity` queries. EntitySet definitions are imported as MModel elements and read through `.mmodel`.

## Design Rules

- Use stable identity fields, not only display names.
- Keep fields understandable to operators and agents.
- Put domain-specific semantics in the domain, not in generic names.
- Link to datasets with `data_link` instead of embedding storage-specific query details in the EntitySet.
- Link to other entities with `entity_set_link` when topology matters.

## Query Examples

List EntitySet definitions:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | sort name | limit 20"
```

List runtime service entities:

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 20"
```
