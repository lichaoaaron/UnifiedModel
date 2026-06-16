# Changelog

All notable changes to MModel Open Source should be documented in this file.

The project follows a simple changelog structure until stable releases are published:

- `Added` for new features.
- `Changed` for behavior changes.
- `Fixed` for bug fixes.
- `Deprecated` for soon-to-be removed behavior.
- `Removed` for removed behavior.
- `Security` for vulnerability fixes.

## 0.1.0 - Unreleased

### Added

- Local single-process MModel service.
- Workspace metadata management.
- MModel import, validate, write, delete, and index paths.
- CMS 2.0 compatible entity and relation write/expire paths.
- Unified Query Service for `.mmodel`, `.entity`, and `.topo`.
- AgentGateway discovery, safe query tools, resources, and MCP stdio server.
- `mmctl` CLI for workspace, MModel, EntityStore, topology, query, and agent workflows.
- `memory`, `file.memory`, and optional `local.ladybug` GraphStore providers.
- React/Vite OpenMModel Web UI.
- REST OpenAPI and MCP tool/resource schemas.
- Generated Go, Python, and Java model SDK assets.
- APM common example pack and sample import endpoint.
- Architecture guard, contract tests, integration tests, e2e tests, and golden tests.

### Changed

- Open-source documentation now uses an external-developer-first README and structured docs index.
- Docker and Compose defaults now explicitly use `file.memory`.

### Security

- MCP write tools are disabled by default.
- Security policy and private-reporting guidance added.
