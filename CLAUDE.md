# CLAUDE.md

Claude Code quick context for MModel.

Read `AGENTS.md` first. It is the primary AI-agent guide for this repository.

## Project Snapshot

MModel is an open-source object graph semantic layer for observability and operations data.

Core idea:

- Model packs define object vocabulary and relation semantics.
- EntityStore writes runtime entities and topology relations.
- Query Service reads everything through `.mmodel`, `.entity`, and `.topo`.
- AgentGateway and MCP expose safe agent-facing discovery, resources, examples, and tools.
- Web UI, CLI, REST, and SDKs share public contracts.

Never call MModel an MVP, skeleton, prototype, toy, or internal demo.

## Fast Orientation

Read:

1. `README.md`
2. `docs/en/README.md`
3. `docs/en/getting-started/quickstart.md`
4. `docs/en/guides/query-service.md`
5. `docs/en/reference/mcp.md`
6. `docs/en/architecture/overview.md`

Important directories:

- `cmd/mmodel-server` - REST server.
- `cmd/mmctl` - public CLI.
- `cmd/mmodel-mcp` - MCP server.
- `internal/query` - public read path implementation.
- `internal/agentgateway` - agent-facing surface.
- `internal/sampledata` - bundled sample loading.
- `web` - React UI.
- `examples/quickstart-multidomain` - default quickstart sample.
- `docs/en` and `docs/zh` - paired documentation trees.

## Default Commands

```bash
git status --short
make check-env
make quickstart
make build
make guard
make test-service
make test-ui
make verify
make example-validate
make ci
```

Use focused commands for small changes. Use broader commands for public contracts, query behavior, samples, SDKs, Web UI, or docs that affect user workflows.

## Non-Negotiable Boundaries

- Runtime reads go through Query Service.
- Public query sources are `.mmodel`, `.entity`, and `.topo`.
- EntityStore writes runtime entities and relations.
- AgentGateway resources stay metadata-oriented.
- AgentGateway tools return runtime rows through Query Service.
- GraphStore providers stay behind contracts.
- Web UI and SDKs use public contracts only.

## Documentation Defaults

- Root README is user-facing. Keep it focused on value, quickstart, Web UI, Agent/MCP integration, Query Service, docs, and governance.
- Do not add internal module inventory tables to the root README.
- English and Chinese docs are separate files.
- Update paired `docs/en/**` and `docs/zh/**` files together.
- Keep `README_CN.md` and `README.zh-CN.md` identical.
- Keep quickstart docs aligned with `QUICKSTART_SAMPLE` in `Makefile`.

## Before Finishing

```bash
git diff --check
```

Final response should include changed files, verification run, and unrelated dirty files intentionally left untouched.
