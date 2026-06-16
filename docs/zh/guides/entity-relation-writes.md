# 实体与关系写入指南

English: [Entity And Relation Write Guide](../../en/guides/entity-relation-writes.md)

模型导入后的运行时实体和关系写入流程。


## 先导入模型定义

```bash
make dev
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
go run ./cmd/mmctl --addr http://localhost:8080 mmodel import demo examples/quickstart-multidomain
```

## 写入 Entity

内置多域 quickstart 样例：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity write demo examples/quickstart-multidomain/sample-data/entities.json
```

REST endpoint：

```http
POST /api/v1/entitystore/{workspace}/entities:write
```

## 验证 Entity

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 20"
```

按关键字查询：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name | limit 20"
```

## 写入 Relation

```bash
go run ./cmd/mmctl --addr http://localhost:8080 topo write demo examples/quickstart-multidomain/sample-data/relations.json
```

REST endpoint：

```http
POST /api/v1/entitystore/{workspace}/relations:write
```

## 验证拓扑

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20"
```

## 过期记录

过期 entities：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 entity expire demo 10000000000000000000000000000101 "retired from sample"
```

过期 relations：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 topo expire demo <relation-id> "retired from sample"
```

## 规则

- 样例数据保持确定性。
- 文档、测试和截图使用稳定 ID。
- 模型定义先导入，运行时数据后写入。
- 运行时读取统一通过 Query Service。
- 优先使用小样例清楚展示 search、direct relation lookup 和 relation types。
