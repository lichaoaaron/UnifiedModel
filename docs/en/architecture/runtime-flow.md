# Runtime Flow

中文：[运行时流程](../../zh/architecture/runtime-flow.md)

Runtime paths for startup, model import, entity/relation writes, Query Service, AgentGateway, and MCP.


## Startup

```mermaid
sequenceDiagram
  participant Main as mmodel-server
  participant Bootstrap as internal/bootstrap
  participant Workspace as Workspace Store
  participant Graph as GraphStore Provider
  participant HTTP as REST Router

  Main->>Bootstrap: parse flags and build app
  Bootstrap->>Graph: select provider
  Bootstrap->>Workspace: initialize workspace persistence
  Bootstrap->>HTTP: register routes and UI handler
  HTTP-->>Main: listen on address
```

Runtime flags:

| Flag | Meaning |
|---|---|
| `--addr` | API listen address, for example `:8080`. |
| `--data` | Local data root. |
| `--graphstore` | Provider name: `memory`, `file.memory`, or `local.ladybug`. |

## Model Import

```mermaid
sequenceDiagram
  participant Client
  participant API as REST API
  participant MModel as MModel Service
  participant Validator as Schema Validator
  participant Graph as GraphStore

  Client->>API: POST /api/v1/mmodel/{workspace}/import
  API->>MModel: import path or pack
  MModel->>Validator: validate elements
  Validator-->>MModel: validation result
  MModel->>Graph: put MModel elements
  Graph-->>MModel: write result
  MModel-->>Client: import result
```

The bundled multi-domain quickstart sample uses the same path, wrapped by:

```http
POST /api/v1/samples/{workspace}/multi-domain-quickstart:import
```

## Entity And Relation Writes

```mermaid
sequenceDiagram
  participant Client
  participant API
  participant Store as EntityStore
  participant Graph as GraphStore

  Client->>API: entities:write or relations:write
  API->>Store: validate workspace and payload
  Store->>Graph: write records
  Graph-->>Store: write result
  Store-->>Client: accepted / failed items
```

EntityStore is write-oriented. Runtime reads go through Query Service.

## Query Execution

```mermaid
sequenceDiagram
  participant Client
  participant API
  participant Query as Query Service
  participant Planner as Parser and planner
  participant Graph as GraphStore

  Client->>API: POST /api/v1/query/{workspace}/execute
  API->>Query: query request
  Query->>Planner: parse SPL
  Planner-->>Query: source and operators
  Query->>Graph: read model/entity/topology data
  Graph-->>Query: rows
  Query-->>Client: rows and explain metadata
```

## AgentGateway And MCP

AgentGateway exposes a safe agent-facing layer:

- Discovery lists tools, resources, and next actions.
- Query tools execute or explain SPL.
- Resources expose metadata and templates.
- Write tools stay disabled unless explicitly enabled.

`mmodel-mcp` connects MCP clients to the same AgentGateway semantics used by REST.

## Local Persistence

With `file.memory`, GraphStore data is saved under:

```text
data/graphstore/file-memory/workspaces/<workspace>/
├── mmodels.json
├── entities.json
└── relations.json
```

Workspace metadata is saved separately at:

```text
data/workspaces.json
```

Storage details: [Storage And GraphStore Providers](../concepts/storage-and-graphstore.md).
