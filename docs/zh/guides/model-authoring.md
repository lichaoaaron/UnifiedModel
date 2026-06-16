# 模型编写指南

English: [Model Authoring Guide](../../en/guides/model-authoring.md)

MModel 模型包编写和导入流程。


## 模型包结构

模型包是一个包含 YAML 或 JSON MModel elements 的目录。多域 quickstart 样例使用以下结构：

```text
examples/quickstart-multidomain/
├── devops/
│   └── entity_set/
├── automaker/
│   └── entity_set/
├── game/
│   └── entity_set/
├── supplier/
│   └── entity_set/
├── k8s/
│   └── entity_set/
├── cross-domain/
│   └── link/entity_set_link/
└── sample-data/
```

按类别拆分目录，保持 diff 易审阅。Quickstart 包刻意保持为实体拓扑样例，不包含 `metric_set`、`log_set`、`trace_set`、`event_set`、`profile_set`、`runbook_set` 等 DataSet kind，也不包含 `data_link` 或 `storage_link` 定义。

## 推荐编写顺序

1. 定义 EntitySet。
2. 有拓扑语义时，用 EntitySetLink 连接 EntitySet。
3. 添加小规模 sample entity/relation 数据。
4. 补充 README 和示例查询。

## 最小 EntitySet

```yaml
kind: entity_set
schema:
  url: "mmodel.aliyun.com"
  version: "v0.1.0"
metadata:
  name: "demo.service"
  domain: demo
spec:
  fields:
    - name: service_id
      type: string
    - name: service
      type: string
```

## 最小 EntitySetLink

```yaml
kind: entity_set_link
schema:
  url: "mmodel.aliyun.com"
  version: "v0.1.0"
metadata:
  name: "demo.service_calls_demo.service"
  domain: demo
spec:
  src:
    domain: demo
    kind: entity_set
    name: demo.service
  dest:
    domain: demo
    kind: entity_set
    name: demo.service
  entity_link_type: calls
```

## 校验示例

```bash
make example-validate
```

生成 schema 和 SDK 变化时：

```bash
make expand
make verify
```

## 导入到 Workspace

```bash
go run ./cmd/mmctl --addr http://localhost:8080 workspace create demo '{"name":"Demo"}'
go run ./cmd/mmctl --addr http://localhost:8080 mmodel import demo examples/quickstart-multidomain
```

## 检查模型

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | sort kind,name | limit 50"
```

## 审阅清单

- 名称稳定且带 domain。
- EntitySet 字段包含稳定身份字段。
- 拓扑关系名称明确。
- Quickstart 包保持不包含 DataSet、DataLink 和 StorageLink 定义。
- 尽可能包含 sample data。
- README 列出模型场景、资产和查询。
