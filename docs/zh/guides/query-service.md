# Query Service 指南

English: [Query Service Guide](../../en/guides/query-service.md)

Query Service 是 UModel 定义、实体、关系和拓扑的唯一公共读取路径。它接受以 `.umodel`、`.entity` 或 `.topo` 开头的 SPL 字符串。


## 为什么读取统一走 Query Service

UModel 不暴露分散的公共读取 API，例如 entity lookup、relation lookup、graph traversal 或 model search endpoint。统一读取面让 CLI、Web UI、REST API、MCP tools 和 SDK 保持一致。

## 入口

REST：

```http
POST /api/v1/query/{workspace}/execute
POST /api/v1/query/{workspace}/explain
```

CLI：

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".umodel | limit 5"
go run ./cmd/umctl --addr http://localhost:8080 query explain demo ".umodel | limit 5"
```

Agent tool：

```bash
go run ./cmd/umctl --addr http://localhost:8080 agent tool demo query_spl_execute '{"query":".umodel | limit 5"}'
```

## `.umodel`

读取 UModel 定义：

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".umodel with(kind='entity_set') | sort name | limit 20"
```

常见读取：

- 列出 EntitySet。
- 查看 metric、log、trace、event、storage、link 定义。
- 支撑 Web UI Explorer 的图/表视图。

## `.entity`

读取运行时实体：

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name | limit 20"
```

Agent 和 REST 调用方可以把命名参数绑定到 `with(...)` filters 和 `where` predicates：

```json
{
  "query": ".entity with(domain='devops', name='devops.service', query=$query) | limit 20",
  "parameters": {
    "query": "checkout"
  }
}
```

## `.topo`

读取运行时拓扑关系：

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | project src,relation,dest | limit 20"
```

`.topo` 支持 graph-call 风格的拓扑操作。`memory`、`file.memory` 和可选的 `local.ladybug` provider 都通过共享的 Go engine 支持受控只读 Cypher 兼容查询。`local.ladybug` 在使用 `-tags ladybug` 和本地 Ladybug runtime 构建时，仍然把图数据持久化到 Ladybug。

Cypher 可以在一次查询里返回完整实体属性和关系属性：

```bash
go run ./cmd/umctl --addr http://localhost:8080 query run demo ".topo | graph-call cypher(`MATCH (src)-[r]->(dest) RETURN src, r AS relation, dest LIMIT 20`)"
```

调用方如果希望显式表达属性 map 返回形态，可以使用 `properties(src)`、`properties(r)` 和 `properties(dest)`。

## 常用管道操作

- `with(...)`：source-specific 过滤。
- `project`：选择字段。
- `sort`：排序。
- `limit`：限制输出。
- `graph-call`：拓扑函数。

查看内置示例：

```bash
go run ./cmd/umctl --addr http://localhost:8080 query examples
```

## Explain

```bash
go run ./cmd/umctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

Explain 输出包含 source、provider、storage provider、filters 和 limits。

## 边界规则

- 不新增 Query Service 之外的公共 entity/relation/topology 读取 endpoint。
- CLI 领域读取保持在 `query run` 和 `query explain` 后面。
- AgentGateway resources 保持 metadata-only，运行时 rows 通过 tools 返回。

## evidence(...) — Entity 回查 Telemetry

`evidence(...)` 管道算子将遥测数据（指标、日志或链路）附加到 `.entity` 查询选中的单个实体上。它在运行时解析以下链路：

```
Entity → DataLink → DataSet → StorageLink → Storage → TelemetryProvider → 本地文件
```

### 语法

```
.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='log_set')
| limit 20

.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='metric_set')
| limit 20

.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='trace_set', from='2026-06-03T01:00:00Z', to='2026-06-03T01:02:00Z')
| limit 20
```

参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `kind` | 是 | 数据集类型，必须为 `metric_set`、`log_set` 或 `trace_set`。 |
| `from` | 否 | 时间范围下限，ISO-8601 格式（含边界）。 |
| `to` | 否 | 时间范围上限，ISO-8601 格式（含边界）。 |

`.entity` 部分必须恰好返回 **一个实体**。零个或多个实体会返回 `INVALID_ARGUMENT` 错误。

### 执行链路

1. 实体查询正常运行，必须返回恰好一行。
2. 执行器读取 UModel 快照，找到满足以下条件的 `data_link` 元素：
   - `spec.src.domain` 和 `spec.src.name` 与实体类型匹配。
   - `spec.dest.kind` 与请求的 `kind` 匹配。
3. `data_link` spec 中的 `fields_mapping` 提供实体字段到数据集字段的映射。执行器从实体读取映射的字段值（例如 `display_name`），得到 serviceName 过滤条件。
4. 执行器找到满足 `spec.src.name` 与 DataSet 名称匹配的 `storage_link` 元素。
5. 执行器找到 StorageLink 的 `spec.dest.name` 指向的 `storage` 元素。
6. Storage 元素的 `spec.type` 用于选择 TelemetryProvider（例如 `local_file`）。
7. Provider 流式扫描文件，按 serviceName 和时间范围过滤，返回最多 `limit` 行数据。

### 模型要求

要在实体类型上使用 `evidence(...)`，需要定义：

1. 模型包中的一个或多个 `metric_set`、`log_set` 或 `trace_set` 元素。
2. 每个数据集类型对应一个 `data_link`，连接实体类型和数据集，`fields_mapping` 将实体字段映射到 `serviceName`。
3. 一个 `external_storage`（或其他 storage）元素，`spec.type` 与注册的 TelemetryProvider 匹配。
4. 每个数据集到 storage 之间的 `storage_link`。

`data_link` 映射示例：

```yaml
spec:
  src:
    domain: platform
    kind: entity_set
    name: platform.service
  dest:
    domain: platform
    kind: log_set
    name: platform.service_logs
  data_link_type: produce
  fields_mapping:
    display_name: serviceName
```

### 本地快照目录配置

`local_file` TelemetryProvider 从 Storage 元素的 `spec.properties` 中解析数据路径：

```yaml
spec:
  type: local_file
  properties:
    metric_dir: data/metric
    log_dir: data/log
    trace_dir: data/trace
    time_field_metric: time
    time_field_log: time
    time_field_trace: startTime
```

路径相对于服务的 `data_root` 目录（通过 `--data` 参数或默认值配置）。快照目录**不在查询请求中配置**，来源于模型定义。

### 流式扫描大文件

本地文件 Provider 使用 `encoding/json.Decoder` 增量读取 JSON 数组，不会将整个文件加载到内存。一旦收集到请求的 `limit` 行数据就停止扫描。文件按文件名字典序依次扫描。

### Explain 输出

`evidence(...)` 查询的 explain 输出包含 `evidence` 节：

```json
{
  "evidence": {
    "entity_id": "...",
    "entity_type": "platform.service",
    "entity_field_value": "iam-manage",
    "data_link_name": "platform.service_produces_platform.service_logs",
    "dataset_kind": "log_set",
    "dataset_name": "platform.service_logs",
    "storage_link_name": "platform.service_logs_stored_in_platform.local_snapshot",
    "storage_name": "platform.local_snapshot",
    "storage_type": "local_file",
    "provider": "local_file",
    "fields_mapping": {"display_name": "serviceName"},
    "time_from": "",
    "time_to": "",
    "scanned_files": ["data/log/opensearch_export_logs_0000.json"],
    "returned_rows": 20
  }
}
```

### 扩展 OpenSearch Provider

要新增 OpenSearch Provider，在新包中实现 `telemetry.Provider` 接口，然后在 `internal/bootstrap/app.go` 中注册：

```go
providers := []telemetry.Provider{
    localfile.New(config.DataRoot),
    opensearch.New(opensearchConfig),
}
```

Query Service 核心和 evidence 执行器无需修改。Storage 元素中的 storage type 字符串在运行时选择对应 Provider。
