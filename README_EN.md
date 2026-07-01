# MModel

[![CI](https://github.com/alibaba/MModel/actions/workflows/ci.yml/badge.svg)](https://github.com/alibaba/MModel/actions/workflows/ci.yml)
![Go 1.22+](https://img.shields.io/badge/Go-1.22%2B-00ADD8)
![Node 22+](https://img.shields.io/badge/Node.js-22%2B-339933)
![License](https://img.shields.io/badge/License-Apache--2.0-blue)

中文版本：[README.md](README.md)

MModel (Mobile Model) is a vendor-neutral semantic runtime for enterprise AI, data governance, and operational intelligence. It turns fragmented schemas, entities, business objects, telemetry links, and topology relations into workspace-scoped graph context that humans, systems, and AI agents can understand and use through one local service.

With MModel, you can:

- Author and import model packs that define enterprise objects, operational objects, datasets, links, storage, and topology semantics.
- Write CMS 2.0 compatible runtime entities and relations.
- Query models, entities, and topology through one SPL surface: `.mmodel`, `.entity`, and `.topo`.
- Explore the workspace through a local Web UI.
- Connect agent clients through AgentGateway and MCP.
- Use public REST, CLI, and SDK contracts without depending on server internals.

## Why MModel

- Accelerate enterprise AI at scale. A unified semantic standard helps AI models understand data meaning across platforms, departments, tools, and domains, improving the path to intelligent operations, customer service, analytics, prediction, and agent workflows.
- Reduce data governance cost. A shared language for multi-source enterprise data frees data teams from repetitive metric alignment, field translation, and context reconstruction, so more effort goes into extracting value from data.
- Preserve vendor neutrality and choice. MModel is independent of any single platform, data tool, observability stack, or AI vendor, helping organizations avoid semantic lock-in while building digital infrastructure.
- Build an enterprise semantic operating system. MModel moves beyond a passive data dictionary toward a live, programmable semantic runtime that AI agents can query, reason over, and use as shared context for future multi-agent collaboration.

## Project Scope

This repository includes the local MModel service, `mmctl` CLI, MCP server, OpenAPI contract, React Web UI, generated SDK assets, example packs, Docker/Compose assets, and test suites.

The open-source core focuses on local operation, public contracts, semantic modeling, agent integration, and contributor-friendly extension points. Cloud-hosted control planes, multi-tenant authorization, Aliyun internal frontend packages, and domain-specific read APIs outside Query Service are outside the public core.

## Five-Minute Quick Start

Requirements:

- Go 1.22 or newer.
- Make.
- Node.js 22 or newer for the Web UI.
- pnpm 9 or newer is preferred; `corepack` or `npm exec` fallback is supported by the Makefile.

Check the local toolchain:

```bash
make check-env
```

Start the API and Web UI with a preloaded demo workspace:

```bash
make quickstart
```

`make quickstart` starts a local API, starts the Web UI, preloads the `demo` workspace with `GRAPHSTORE=memory`, and leaves no local demo data behind after the process stops.

Next steps:

- Open `http://localhost:5173`, select `demo`, and inspect the workspace through Explorer, Query, Data Store, and Agent views.
- Integrate an agent through AgentGateway or MCP. Start with `mmctl agent discover demo`, then connect an MCP client through `mmodel-mcp`.
- Query models, entities, and topology through CLI or REST using Query Service.

Detailed flows:

- [Quick Start](docs/en/getting-started/quickstart.md)
- [Web UI Guide](docs/en/guides/web-ui.md)
- [Query Service Guide](docs/en/guides/query-service.md)
- [MCP Reference](docs/en/reference/mcp.md)

Stop local services:

```bash
make stop-all
```

## OpenTelemetry Demo

MModel ships with an [OpenTelemetry Demo (Astronomy Shop)](https://github.com/open-telemetry/opentelemetry-demo) example pack under `examples/otel-demo/`. It models the OTel Demo's 16 microservices as entities, links their telemetry datasets (metrics, logs, traces), maps service-to-service call topology, and connects datasets to OpenSearch storage. This is a full end-to-end demonstration of MModel for observability and operations data.

The pack includes:

- **Model definitions**: EntitySet for `otel.service`, datasets for `metric_set` / `log_set` / `trace_set`, and OpenSearch storage definitions.
- **Runtime entities**: 16 OTel Demo microservice entity records with language, SDK version, and criticality metadata.
- **Runtime relations**: 16 service-to-service `calls` topology records.
- **Data and storage links**: `data_link` connecting services to their telemetry outputs, and `storage_link` connecting datasets to OpenSearch storage.

### Automatic Topology Discovery (`mmodel-topo-ingestor`)

Beyond the static model, MModel includes a live topology ingestor that discovers service-to-service call relationships directly from OpenTelemetry trace data stored in OpenSearch. It queries server spans in the configured index pattern, analyzes parent-child span relationships to identify call pairs, and writes discovered topology into MModel's EntityStore with proper F/L/K/D lifecycle timestamps.

```bash
# One-time scan
go run ./cmd/mmodel-topo-ingestor --once

# Continuous scanning (every 60s by default)
go run ./cmd/mmodel-topo-ingestor --interval 60s
```

Available flags:

| Flag | Default | Description |
|---|---|---|
| `--addr` | `http://localhost:8080` | MModel server address |
| `--workspace` | `otel-demo` | Target workspace ID |
| `--os-endpoint` | `http://localhost:13121` | OpenSearch endpoint |
| `--os-user` | `admin` | OpenSearch username |
| `--os-pass` | `MorenMima@123456` | OpenSearch password |
| `--interval` | `60s` | Scan interval for continuous mode |
| `--once` | `false` | Run once and exit |

### Quick Start (First-Time Team Setup)

```bash
# 1. Start the server
make quickstart

# 2. One-click create OTel Demo workspace (model + entities + relations)
bash ./scripts/reset-otel.sh

# 3. Open Web UI
# http://localhost:5173 → select otel-demo
```

### Query Examples

```bash
# List all services
go run ./cmd/umctl --addr http://localhost:8080 query run otel-demo ".entity with(domain='otel') | project __entity_id__,display_name | limit 10"

# Explore service call topology
go run ./cmd/umctl --addr http://localhost:8080 query run otel-demo ".topo | limit 10"

# Entity-centric trace lookup (requires OpenSearch)
go run ./cmd/umctl --addr http://localhost:8080 query run otel-demo ".entity with(domain='otel', name='otel.service', ids=('a0000000000000000000000000000002')) | evidence(kind='trace_set', from='2026-06-29T00:00:00Z', to='2026-06-30T23:59:59Z') | limit 5"

# Metric lookup
go run ./cmd/umctl --addr http://localhost:8080 query run otel-demo ".entity with(domain='otel', name='otel.service', ids=('a0000000000000000000000000000002')) | evidence(kind='metric_set', from='2026-06-29T00:00:00Z', to='2026-06-30T23:59:59Z') | limit 5"

# Log lookup (use frontend-proxy entity ID)
go run ./cmd/umctl --addr http://localhost:8080 query run otel-demo ".entity with(domain='otel', name='otel.service', ids=('a0000000000000000000000000000001')) | evidence(kind='log_set', from='2026-06-29T00:00:00Z', to='2026-06-30T23:59:59Z') | limit 5"
```

> **Note**: Evidence queries require OpenSearch access. Connect via SSH tunnel first:  
> `ssh -p 2222 -L localhost:13121:localhost:13121 sredev@10.2.115.188`

More details: [OpenTelemetry Demo Example Pack](examples/otel-demo/README.md)

## Architecture

![MModel architecture](images/architecture.png)

MModel runs as a local service around one workspace-scoped object graph:

- Model packs define the object vocabulary: EntitySets, datasets, links, storage, and relation semantics.
- EntityStore writes runtime entities and topology relations that instantiate the model.
- Query Service is the unified read surface for `.umodel`, `.entity`, and `.topo`.
- AgentGateway and MCP expose discovery, resources, query examples, and safe tools for agent clients.
- Web UI, CLI, REST, and SDK clients operate against the same public contracts.

Architecture details:

- [Architecture Overview](docs/en/architecture/overview.md)
- [Runtime Flow](docs/en/architecture/runtime-flow.md)
- [Query And Agent Architecture](docs/en/architecture/query-and-agent.md)

## Documentation

Start with the bilingual documentation index: [docs/README.md](docs/README.md).

| Area | Entry |
|---|---|
| Getting started | [Installation](docs/en/getting-started/installation.md), [Quick Start](docs/en/getting-started/quickstart.md) |
| Concepts | [Concepts Index](docs/en/concepts/index.md), [Object Graph Semantic Layer](docs/en/concepts/object-graph-semantic-layer.md) |
| Guides | [Model Authoring](docs/en/guides/model-authoring.md), [Entity And Relation Writes](docs/en/guides/entity-relation-writes.md), [Query Service](docs/en/guides/query-service.md), [Web UI](docs/en/guides/web-ui.md), [SDK And Client Guide](docs/en/guides/sdk-clients.md) |
| Architecture | [Architecture Overview](docs/en/architecture/overview.md), [Runtime Flow](docs/en/architecture/runtime-flow.md), [Query And Agent Architecture](docs/en/architecture/query-and-agent.md) |
| Reference | [CLI](docs/en/reference/cli.md), [MCP](docs/en/reference/mcp.md), [REST OpenAPI](api/openapi/openapi.yaml), [MCP Tool And Resource Schema](api/mcp/tools.schema.json) |
| Examples | [Multi-Domain Quickstart Example Pack](examples/quickstart-multidomain/README.md), [OpenTelemetry Demo](examples/otel-demo/README.md) |
| Deployment | [Docker And Compose](deployments/README.md) |

Chinese documentation: [docs/zh/README.md](docs/zh/README.md).

## Development

Install local dependencies:

```bash
make install-env
```

Build:

```bash
make build
```

Run focused checks:

```bash
make guard
make test-service
make verify
make example-validate
```

Run the local CI gate:

```bash
make ci
```

Generated Go and Python model SDKs live under `sdk/`. The Java SDK currently remains under `generated/java/`. The minimal Go service client lives under `sdk/go/service` and wraps public REST contracts.

## GraphStore Providers

Runtime GraphStore providers are selected with `--graphstore`.

| Provider | Typical use |
|---|---|
| `memory` | Ephemeral local tests and quickstart demos. Data is lost after process exit. |
| `file.memory` | JSON persistence under `--data`. Default for `make dev`, Docker, and Compose. |
| `local.ladybug` | Ladybug-backed environments. Requires `-tags ladybug` and a local Ladybug runtime. |

Provider details: [GraphStore Providers](docs/en/graphstore-providers.md).

## Governance And Support

- License: [Apache-2.0](LICENSE)
- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Support channels: [SUPPORT.md](SUPPORT.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
