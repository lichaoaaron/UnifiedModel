# AGENTS.md

Repository guide for AI coding agents.

## Project In One Minute

MModel is an open-source object graph semantic layer for observability and operations data.

It turns model definitions, runtime entities, telemetry links, and topology relations into a workspace-scoped graph that humans and agents can inspect through one local service.

Think in five layers:

1. Model packs define the vocabulary: `EntitySet`, `DataSet`, `Link`, `Storage`, relation semantics.
2. EntityStore writes runtime entity and relation records.
3. GraphStore providers persist model graph and runtime graph data.
4. Query Service is the single read path through `.mmodel`, `.entity`, and `.topo`.
5. REST, CLI, Web UI, SDKs, AgentGateway, and MCP expose the same public contracts.

Do not describe MModel as an MVP, skeleton, prototype, toy, or internal demo.

## First Files To Read

Read in this order for orientation:

1. `README.md` - external positioning, quickstart, project scope.
2. `docs/en/README.md` - documentation map.
3. `docs/en/getting-started/quickstart.md` - expected first user flow.
4. `docs/en/concepts/object-graph-semantic-layer.md` - core product concept.
5. `docs/en/guides/query-service.md` - public read model.
6. `docs/en/reference/mcp.md` - agent-facing MCP surface.
7. `docs/en/architecture/overview.md` - system architecture.

For Chinese documentation work, read and update the matching `docs/zh/**` file.

## Directory Map

| Path | Purpose |
|---|---|
| `cmd/mmodel-server` | Local REST server and optional UI serving entrypoint. |
| `cmd/mmctl` | Public CLI for workspaces, model import, entity writes, topology writes, query, and agent metadata. |
| `cmd/mmodel-mcp` | stdio MCP server for agent clients. |
| `api/openapi` | REST OpenAPI contract. |
| `api/mcp` | MCP tool/resource schema. |
| `internal/bootstrap` | Wires services, providers, routes, sample loading, and UI serving. |
| `internal/workspace` | Workspace metadata service. |
| `internal/mmodel` | MModel validation, import, write, delete, export, and indexing. |
| `internal/entitystore` | Runtime entity and relation write/expire/delete behavior. |
| `internal/query` | Parser, planner, explain, and execution for `.mmodel`, `.entity`, `.topo`. |
| `internal/agentgateway` | Agent discovery, tools, resources, query examples, and MCP-facing semantics. |
| `internal/graphstore` | Provider-neutral persistence and graph access contracts. |
| `pkg/contract` | Public service interfaces. |
| `pkg/model` | Shared request, response, and domain model types. |
| `pkg/errors` | Stable error envelope and error codes. |
| `web` | React workspace UI. |
| `sdk/go`, `sdk/python`, `generated/java` | Public SDK assets. |
| `examples/quickstart-multidomain` | Default quickstart model and runtime sample. |
| `docs/en`, `docs/zh` | Separate English and Chinese docs. |

## Runtime Mental Model

Quickstart:

```bash
make quickstart
```

Default quickstart settings:

- `GRAPHSTORE=memory`
- `QUICKSTART_WORKSPACE=demo`
- `QUICKSTART_SAMPLE=multi-domain-quickstart`
- Web UI: `http://localhost:5173`
- API: `http://localhost:8080`

User journey after quickstart:

- Web UI: select `demo`, inspect Explorer, Query, Data Store, and Agent views.
- Query Service: run `.mmodel`, `.entity`, `.topo`.
- Agent integration: inspect AgentGateway, then connect through `mmodel-mcp`.
- SDK or REST: use public contracts, not server internals.

## Architecture Invariants

Preserve these boundaries:

- Workspace service owns workspace metadata only.
- MModel service owns model validation/import/write/delete/export/index behavior.
- EntityStore owns runtime entity and relation writes, expires, and deletes.
- Query Service is the only public read path for model, entity, relation, and topology data.
- Public query sources are `.mmodel`, `.entity`, and `.topo`.
- AgentGateway resources expose metadata, templates, and capabilities.
- AgentGateway tools return runtime rows through Query Service.
- GraphStore providers stay behind provider-neutral contracts.
- Public clients and SDKs use public REST, MCP, and model contracts.
- Web UI calls public REST APIs only.

Run `make guard` after touching routing, public APIs, service boundaries, query behavior, provider wiring, AgentGateway, MCP, or Web UI API usage.

## Worktree Rules

- Start with `git status --short`.
- Treat existing dirty files as user or other-agent work.
- Do not revert unrelated changes.
- Do not use destructive Git commands unless explicitly asked.
- Keep edits scoped to the current request.
- Use `rg` for search.
- Use `apply_patch` for manual edits.

## Documentation Rules

- Root README is for external users. It should explain what MModel does, how to start quickstart, and where to go next.
- Do not add internal module inventory tables to the root README.
- Put implementation details in `docs/en/architecture/**` and `docs/zh/architecture/**`.
- English and Chinese docs are separate files.
- Update `docs/en/**` and `docs/zh/**` pairs together.
- Keep `README_CN.md` and `README.zh-CN.md` identical.
- Keep commands, paths, API names, query strings, and code snippets aligned across languages.
- Keep quickstart docs aligned with `QUICKSTART_SAMPLE` in `Makefile`.
- Use direct project-owner language. Avoid sentences that describe the document itself, such as "this guide explains".

## Command Matrix

Environment:

```bash
make check-env
make install-env
```

Build:

```bash
make build
make build-service
make build-ui
```

Run:

```bash
make quickstart
make dev
make stop-all
```

Service and architecture checks:

```bash
make guard
make test-service
```

SDK and examples:

```bash
make expand
make verify
make example-validate
```

UI:

```bash
make test-ui
make build-ui
```

Full local gate:

```bash
make ci
```

## Task Routing

Documentation task:

- Read `README.md`, `docs/en/README.md`, and matching docs.
- Update English and Chinese pairs.
- Check `README_CN.md` and `README.zh-CN.md` equality when either changes.
- Run `git diff --check`.

Quickstart or sample task:

- Check `Makefile` quickstart variables.
- Check `internal/bootstrap/quickstart.go` and `internal/sampledata`.
- Keep README, quickstart docs, and sample README files aligned.
- Run `make example-validate`.
- Run `make test-service` when loading behavior changes.

Query task:

- Work under `internal/query`.
- Preserve `.mmodel`, `.entity`, `.topo` as the public read sources.
- Update Query Service docs and CLI examples when behavior changes.
- Run `make guard` and `make test-service`.

Agent or MCP task:

- Work under `internal/agentgateway`, `cmd/mmodel-mcp`, and `api/mcp`.
- Keep resources metadata-oriented.
- Keep runtime rows behind query tools.
- Update MCP reference when schema or behavior changes.
- Run `make guard` and `make test-service`.

Web UI task:

- Work under `web/src`.
- Use public REST APIs only.
- Build through Makefile so dependency fallback stays consistent.
- Run `make test-ui` or `make build-ui`.

Schema or SDK task:

- Work under `schemas`, generators, and SDK directories.
- Run `make expand`.
- Run `make verify`.
- Update SDK docs and examples for public behavior changes.

## Before Final Response

Minimum check:

```bash
git diff --check
```

Report:

- What changed.
- What verification ran.
- What was not run and why.
- Any unrelated dirty files left untouched.
