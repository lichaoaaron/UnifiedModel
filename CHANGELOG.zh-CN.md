# 变更日志

English version: [CHANGELOG.md](CHANGELOG.md)

所有值得关注的 MModel Open Source 变更都应记录在这里。

在稳定版本发布前，项目使用简单的变更日志结构：

- `Added`：新增能力。
- `Changed`：行为变化。
- `Fixed`：缺陷修复。
- `Deprecated`：即将移除的行为。
- `Removed`：已移除的行为。
- `Security`：安全修复。

## 0.1.0 - Unreleased

### Added

- 本地单进程 MModel 服务。
- Workspace 元数据管理。
- MModel 导入、校验、写入、删除和索引路径。
- CMS 2.0 兼容的实体与关系写入/过期路径。
- 面向 `.mmodel`、`.entity`、`.topo` 的统一 Query Service。
- AgentGateway discovery、安全查询工具、resources 和 MCP stdio server。
- `mmctl` CLI，覆盖 workspace、MModel、EntityStore、topology、query 和 agent 工作流。
- `memory`、`file.memory` 和可选 `local.ladybug` GraphStore providers。
- React/Vite OpenMModel Web UI。
- REST OpenAPI 和 MCP tool/resource schemas。
- 生成的 Go、Python、Java model SDK 资产。
- APM common example pack 和 sample import endpoint。
- Architecture guard、contract tests、integration tests、e2e tests 和 golden tests。

### Changed

- 开源文档采用面向外部开发者的 README 和结构化 docs index。
- Docker 和 Compose 默认显式使用 `file.memory`。

### Security

- MCP 写工具默认关闭。
- 增加安全策略和私下报告指引。
