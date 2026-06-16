# 对象图语义层

English: [Object Graph Semantic Layer](../../en/concepts/object-graph-semantic-layer.md)

MModel 是厂商中立企业语义运行时中的对象图语义层，面向企业 AI、数据治理和智能运维。它不替代数据平台、OpenTelemetry、Prometheus、Kubernetes、链路追踪系统、CMDB 或 AI 工具，而是为这些系统提供统一对象词汇、关系语义和可查询的图上下文，让人、服务和 AI Agent 都能读取并使用。


## 问题

企业系统已经产生并保存了大量数据：

- 业务系统描述客户、订单、工单、资产和流程。
- 数据平台描述表、字段、指标、Owner 和血缘。
- 可观测系统描述指标、日志、链路、事件、Profile 和 Runbook。
- CMDB、云 API 和 Kubernetes 描述资源与运行时工作负载。
- AI 应用在分析、预测或行动前需要可信上下文。

缺失层：语义对齐。原始数据已经存在，但核心企业问题仍然分散：

- 这些数据描述的是哪个业务对象或运维对象？
- 哪些对象之间有关联？
- 哪些字段、指标、存储、查询和拓扑定义支撑这种关系？
- AI Agent 行动前的安全上下文是什么？

## MModel 的角色

MModel 将企业上下文建模成 workspace-scoped 的对象图：

- `EntitySet` 定义业务对象或运维对象类型，例如服务、实例、操作、数据库、资产和外部依赖。
- `DataSet` 定义结构化数据集和遥测数据集，例如指标、日志、链路、事件、Profile 和 Runbook。
- `Storage` 描述数据所在位置。
- `Link` 连接实体、数据集和存储。
- Entity 和 Relation records 提供运行时对象图。
- Query Service 用 `.mmodel`、`.entity`、`.topo` 提供统一读取入口。

## MModel 贡献

| 层次 | 既有系统 | MModel 的贡献 |
|---|---|---|
| 企业数据 | 数据仓库、数据目录、业务 API | 让数据集、字段、指标、Owner 和血缘拥有共享语义锚点。 |
| 遥测与运维 | OpenTelemetry、日志、指标、链路 | 将运维信号映射到有语义的对象和关系。 |
| 运行时资源 | Kubernetes、云 API、CMDB | 提供稳定的实体和关系语义。 |
| 查询探索 | SLS、Prometheus、Trace store、Graph store | 提供统一 Query Service。 |
| Agent 上下文 | MCP client、AI Agent | 暴露安全资源、查询模板和默认只读工具。 |

## 设计原则

- Workspace first：所有操作都属于某个 workspace。
- Spec first：Schema、OpenAPI、MCP schema 和公共模型类型都是契约。
- Query first：读取通过 Query Service，而不是散落的领域读取 API。
- Provider neutral：存储通过 GraphStore provider 隔离。
- Agent safe：Resources 以元数据为主，写工具需要显式启用。

## 公共入口

- REST API：`api/openapi/openapi.yaml`
- CLI：`mmctl`
- MCP server：`mmodel-mcp`
- Web UI：`web/`
- SDKs：`sdk/go`、`sdk/python` 和 `generated/java`

## 相关参考

- [概念索引](index.md)
- [Workspace 与 Domain](workspaces-and-domains.md)
- [Model Elements](model-elements.md)
- [快速开始](../getting-started/quickstart.md)
- [Query Service 指南](../guides/query-service.md)
- [GraphStore Providers](../graphstore-providers.md)
- [MCP 参考](../reference/mcp.md)
