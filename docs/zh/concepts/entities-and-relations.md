# Entity 与 Relation

English: [Entities And Relations](../../en/concepts/entities-and-relations.md)

Entity 和 Relation 是运行时数据。它们实例化 EntitySet 和 EntitySetLink 定义的对象图。


## 模型层与运行时层

| 模型定义 | 运行时数据 |
|---|---|
| `entity_set` | Entity records |
| `entity_set_link` | Relation records |
| `data_link` | 查询时实体与数据集的绑定 |
| `storage_link` | 查询时数据集与存储的路由 |

## 写入 Entity

REST：

```http
POST /api/v1/entitystore/{workspace}/entities:write
```

CLI：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity write demo examples/quickstart-multidomain/sample-data/entities.json
```

读取：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 20"
```

## 写入 Relation

REST：

```http
POST /api/v1/entitystore/{workspace}/relations:write
```

CLI：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 topo write demo examples/quickstart-multidomain/sample-data/relations.json
```

读取拓扑：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20"
```

## Visibility

EntityStore 支持 write、expire 和 delete-style 操作。本地查询默认隐藏 expired/deleted records，provider 保留历史后支持 time-aware 查询。

## Identity

运行时记录需要稳定 entity IDs。MModel 在 topology calls 和 provider storage 中使用经过校验的 entity identifiers。示例 ID 保持确定，教程和测试即可直接复制运行。

## 设计规则

- 先导入模型定义，再写运行时数据。
- Entity 字段要和 EntitySet 定义一致。
- Relation 类型要和 EntitySetLink 语义一致。
- 使用 `.entity` 找到 ID，再使用 `.topo` 做拓扑查询。
- 样例数据应足够小，便于人工检查，同时也要足够丰富，能展示拓扑。
