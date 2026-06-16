# 多域 Quickstart 示例包

English: [Multi-Domain Quickstart Example Pack](README.md)

`examples/quickstart-multidomain` 是 `make quickstart` 默认导入的样例。它展示一个 workspace 如何把 DevOps 归属、粗粒度 Kubernetes 运行拓扑，以及 `Demo/mmodel-demo-2/mmodel` 中的企业场景域连接起来。

Kubernetes 域刻意保持粗粒度：只建模能解释服务拓扑的运行时对象，不照搬完整 Kubernetes 对象模型。

这个样例只覆盖实体和拓扑。所有域都不定义 `metric_set`、`log_set`、`trace_set`、`event_set`、`profile_set`、`runbook_set`、`data_link` 或 `storage_link`。

## 内容

| 区域 | 路径 | 数量 | 作用 |
|---|---|---:|---|
| DevOps EntitySet | `devops/entity_set/` | 10 | 团队、服务、仓库、流水线、环境、部署、发布、变更、故障、SLO。 |
| Kubernetes EntitySet | `k8s/entity_set/` | 7 | 粗粒度集群、命名空间、工作负载、Pod、节点、Service、Ingress。 |
| 企业 demo EntitySet | `automaker/entity_set/`, `game/entity_set/`, `supplier/entity_set/` | 18 | 直接复用 `Demo/mmodel-demo-2/mmodel` 的实体拓扑定义。 |
| EntitySetLink | `*/link/entity_set_link/`, `cross-domain/link/entity_set_link/` | 42 | 域内和跨域拓扑语义。 |
| DataSet 定义 | 不包含 | 0 | Quickstart 聚焦实体和拓扑建模。 |
| Runtime entities | `sample-data/entities.json` | 93 | CMS 2.0 兼容实体 payload。 |
| Runtime relations | `sample-data/relations.json` | 125 | CMS 2.0 兼容拓扑 payload。 |

## 导入

启动 quickstart：

```bash
make quickstart
```

手动导入到其他 workspace：

```bash
curl -X POST http://localhost:8080/api/v1/samples/demo/multi-domain-quickstart:import \
  -H 'Content-Type: application/json' \
  -d '{}'
```

## 查询示例

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20"

go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | project __entity_id__,display_name,status,owner | limit 10"

go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getNeighborNodes('full', 2, [(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20"
```

## 维护规则

- 保持模型 YAML、entity payload、relation payload 和文档一致。
- 保持这个样例不包含 `metric_set`、`log_set`、`trace_set`、`event_set`、`profile_set`、`runbook_set` 等 DataSet kind。
- quickstart 里的 k8s 保持粗粒度，避免变成完整 Kubernetes 规范。
- 只从 `Demo/mmodel-demo-2/mmodel` 复用 `entity_set` 和 `entity_set_link`，不要把其中的 metric、log、storage 或 storage link 定义复制进 quickstart。
- 修改后运行 `make example-validate` 和 `go test ./internal/sampledata ./internal/bootstrap ./internal/query`。
