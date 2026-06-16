# 快速开始

English: [Quick Start](../../en/getting-started/quickstart.md)

启动已加载内置多域 demo 的 MModel，然后查询模型、实体、拓扑和 AgentGateway 元数据。


## 1. 启动并加载 Demo 数据

```bash
make quickstart
```

API 地址是 `http://localhost:8080`，Web UI 地址是 `http://localhost:5173`。

Quickstart 使用 `GRAPHSTORE=memory` 预加载 `demo` workspace。进程停止后 demo 状态重置。

选择路径：

- Web UI：打开 `http://localhost:5173`，选择 `demo`，通过 Explorer、Query、Data Store 和 Agent 视图查看样例。文档：[Web UI 指南](../guides/web-ui.md)。
- Agent 集成：用 `mmctl agent discover demo` 查看 AgentGateway 能力，再通过 `mmodel-mcp` 连接 MCP client。文档：[MCP 参考](../reference/mcp.md)、[Query 与 Agent 架构](../architecture/query-and-agent.md)。
- CLI 或 REST 查询：通过 Query Service 运行 `.mmodel`、`.entity` 和 `.topo`。文档：[Query Service 指南](../guides/query-service.md)。

样例资产：[examples/quickstart-multidomain](../../../examples/quickstart-multidomain/README.zh-CN.md)。

仅启动 API：

```bash
go run ./cmd/mmodel-server --quickstart
```

## 2. 查询模型定义

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | sort name | limit 10"
```

## 3. 查询运行时实体

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | limit 10"
```

## 4. 查询拓扑

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 10"
```

## 5. Explain 查询计划

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

Explain 输出查询入口、provider、计划算子和 limit 信息。

## 6. 查看 Agent 元数据

```bash
go run ./cmd/mmctl --addr http://localhost:8080 agent discover demo
go run ./cmd/mmctl --addr http://localhost:8080 agent tool demo query_spl_examples '{}'
```

## 7. 打开 Web UI

打开 `http://localhost:5173`，选择 `demo` workspace。

- Explorer：查看 MModel 定义。
- Query：运行 `.mmodel`、`.entity`、`.topo`。
- Imports & Writes：导入模型、写入实体和关系。
- Agent：查看 discovery、tools、resources 和 next actions。

## 8. 停止

```bash
make stop-all
```

## 相关参考

- [概念索引](../concepts/index.md)
- [多域 Quickstart 示例包](../../../examples/quickstart-multidomain/README.zh-CN.md)
- [Query Service 指南](../guides/query-service.md)
- [架构总览](../architecture/overview.md)
