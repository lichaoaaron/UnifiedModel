# OpenTelemetry Demo（天文商店）示例包

`examples/otel-demo` 将官方 [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo)（天文商店）建模为 MModel 包。它将 OTel Demo 微服务定义为实体，关联其遥测数据集（指标、日志、链路），并映射服务间调用拓扑。

此包覆盖完整的建模要素：实体定义、数据集定义、存储定义、数据关联、存储关联以及实体拓扑关联。

## 内容

| 区域 | 路径 | 数量 | 说明 |
|---|---:|---|
| 实体集 | `entity_set/` | 1 | OTel 微服务实体定义。 |
| 数据集 | `dataset/` | 3 | OpenTelemetry 信号的 metric_set、log_set、trace_set。 |
| 存储 | `storage/` | 2 | OpenSearch 在线 + 本地文件快照存储。 |
| 数据关联 | `link/data_link/` | 3 | 服务 → produces → metric/log/trace。 |
| 存储关联 | `link/storage_link/` | 3 | 数据集 → stored_in → OpenSearch 存储。 |
| 实体关联 | `link/entity_set_link/` | 16 | 服务间调用拓扑。 |
| 运行时实体 | `sample-data/entities.json` | 16 | 16 个 OTel Demo 微服务实体记录。 |
| 运行时关系 | `sample-data/relations.json` | 16 | 服务调用拓扑记录。 |
