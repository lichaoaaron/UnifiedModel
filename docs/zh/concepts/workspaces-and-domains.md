# Workspace 与 Domain

English: [Workspaces And Domains](../../en/concepts/workspaces-and-domains.md)

Workspace 和 domain 是 MModel 最重要的两个范围控制。


## Workspace

Workspace 是隔离上下文，包含：

- MModel 定义。
- Entity 和 Relation records。
- Query Service 执行上下文。
- AgentGateway discovery 和 tools。
- 本地 GraphStore 持久化数据。

公共 API 在路径中显式携带 workspace：

```http
POST /api/v1/mmodel/{workspace}/import
POST /api/v1/entitystore/{workspace}/entities:write
POST /api/v1/query/{workspace}/execute
GET  /api/v1/agent/{workspace}/discover
```

CLI 也使用同一模型：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
```

## Domain

Domain 是 workspace 内的语义命名空间，例如：

- `devops`：交付与服务责任对象。
- `k8s`：Kubernetes 对象。
- `automaker`、`game` 或 `supplier`：业务场景对象。

MModel metadata 中会声明 domain：

```yaml
metadata:
  name: "devops.service"
  domain: devops
```

Domain 过滤：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

## 边界规则

Workspace 边界：不同团队、不同演示、不同测试 fixture 或不同本地租户上下文的运行时隔离。

Domain 边界：DevOps 服务、Kubernetes workload、云资源或业务对象共享的一套语义词汇。

## 命名规则

| 项 | 形式 | 示例 |
|---|---|---|
| Workspace ID | 短、URL-safe、面向环境 | `demo`, `dev`, `quickstart-lab` |
| Domain | 小写语义命名空间 | `devops`, `k8s`, `automaker` |
| EntitySet name | `{domain}.{entity}` | `devops.service` |
| MetricSet name | `{domain}.metric.{scope}` | `devops.metric.devops.service` |
| Storage name | `{domain}.{kind}.{purpose}.storage` | `devops.metric_set.core.storage` |

## Persistence

使用 `file.memory` 时，workspace metadata 保存在 data root 下，graph collections 按 workspace 保存：

```text
data/
├── workspaces.json
└── graphstore/file-memory/workspaces/demo/
    ├── mmodels.json
    ├── entities.json
    └── relations.json
```

Provider 细节：[Storage 与 GraphStore](storage-and-graphstore.md)。
