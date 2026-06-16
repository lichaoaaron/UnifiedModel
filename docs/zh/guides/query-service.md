# Query Service 指南

English: [Query Service Guide](../../en/guides/query-service.md)

Query Service 是 MModel 定义、实体、关系和拓扑的唯一公共读取路径。它接受以 `.mmodel`、`.entity` 或 `.topo` 开头的 SPL 字符串。


## 为什么读取统一走 Query Service

MModel 不暴露分散的公共读取 API，例如 entity lookup、relation lookup、graph traversal 或 model search endpoint。统一读取面让 CLI、Web UI、REST API、MCP tools 和 SDK 保持一致。

## 入口

REST：

```http
POST /api/v1/query/{workspace}/execute
POST /api/v1/query/{workspace}/explain
```

CLI：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
go run ./cmd/mmctl --addr http://localhost:8080 query explain demo ".mmodel | limit 5"
```

Agent tool：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 agent tool demo query_spl_execute '{"query":".mmodel | limit 5"}'
```

## `.mmodel`

读取 MModel 定义：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | sort name | limit 20"
```

常见读取：

- 列出 EntitySet。
- 查看 metric、log、trace、event、storage、link 定义。
- 支撑 Web UI Explorer 的图/表视图。

## `.entity`

读取运行时实体：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name | limit 20"
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
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | project src,relation,dest | limit 20"
```

`.topo` 支持 graph-call 风格的拓扑操作。`memory`、`file.memory` 和可选的 `local.ladybug` provider 都通过共享的 Go engine 支持受控只读 Cypher 兼容查询。`local.ladybug` 在使用 `-tags ladybug` 和本地 Ladybug runtime 构建时，仍然把图数据持久化到 Ladybug。

Cypher 可以在一次查询里返回完整实体属性和关系属性：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call cypher(`MATCH (src)-[r]->(dest) RETURN src, r AS relation, dest LIMIT 20`)"
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
go run ./cmd/mmctl --addr http://localhost:8080 query examples
```

## Explain

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
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
2. 执行器读取 MModel 快照，找到满足以下条件的 `data_link` 元素：
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

MModel 现已支持 `spec.type: opensearch`，仍然通过 `telemetry.Provider`
扩展点接入，查询语法保持不变：

```spl
.entity with(domain='platform', name='platform.service', ids=('ENTITY_ID'))
| evidence(kind='log_set', from='2026-06-03T01:00:00Z', to='2026-06-03T01:02:00Z')
| project serviceName,time,severityText
| limit 5
```

Provider 选择机制仍由 `storage.spec.type` 决定：

- `local_file` -> 本地 JSON 快照流式 provider。
- `opensearch` -> 在线 OpenSearch `_search` provider。

`skills/os-query` 只作为 DSL 与 OTEL 字段经验的设计参考，不是运行时依赖。

要让两种 provider 并存，在 `internal/bootstrap/app.go` 中同时注册：

```go
providers := []telemetry.Provider{
    localfile.New(config.DataRoot),
  opensearch.New(),
}
```

### OpenSearch Storage Properties

当 `spec.type: opensearch` 时，`spec.properties` 建议使用：

必填：

- `endpoint`
- `username`
- `password`
- `log_index`
- `metric_index`
- `trace_index`

可选（带默认值）：

- `time_field_log`（默认 `time`）
- `time_field_metric`（默认 `time`）
- `time_field_trace`（默认 `startTime`）
- `service_name_field_log`（默认 `serviceName`）
- `service_name_field_metric`（默认 `serviceName`）
- `service_name_field_trace`（默认 `serviceName`）
- `verify_tls`（默认 `true`）
- `request_timeout_ms`（默认 `10000`）
- `headers_json`（可选 JSON 对象字符串）

### 从 local_file 切换到 opensearch

可以在同一个模型包中并存两种 storage 示例，并通过 storage_link 目标进行切换：

- `platform.local_snapshot`（`type: local_file`）
- `platform.opensearch_live`（`type: opensearch`）

不需要改写 SPL 查询。

### OpenSearch 查询行为（最小实现）

对 `log_set`、`trace_set`、`metric_set`，provider 会调用 OpenSearch
`POST /{index}/_search`，最小行为包括：

- 按配置的 service 字段做等值过滤
- 按配置的时间字段做可选范围过滤
- `size = limit`
- 按时间字段升序，再按 `_doc` 稳定排序

### OpenSearch 错误与安全

- 凭据来自 storage properties 或外部配置注入，不在 Query Service / evidence 中硬编码。
- password 为空会返回明确错误。
- HTTP `401`、`403` 映射为 `PROVIDER_UNAVAILABLE`。
- HTTP `404` 映射为 `NOT_FOUND`。
- 超时映射为 `TIMEOUT`。
- explain 只返回 endpoint/index/字段等安全信息，不泄露凭据。

### OpenSearch Evidence Explain 字段

当 `storage_type` 为 `opensearch` 时，`evidence` explain 额外包含：

- `endpoint`
- `index_name`
- `service_field`
- `time_field`

这些字段用于描述实际请求形态，且不包含敏感信息。
