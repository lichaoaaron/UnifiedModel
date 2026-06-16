# EntitySet

English: [Entity Sets](../../en/concepts/entity-sets.md)

EntitySet 定义一类运维对象。服务、实例、操作、数据库、队列、Kubernetes workload 都可以是 EntitySet。


## 职责

EntitySet 回答：

- 这是什么类型的对象？
- 哪些字段能标识和描述它？
- 哪个 domain 拥有这套词汇？
- 哪些数据集或拓扑关系连接到它？

## 示例

```yaml
kind: entity_set
metadata:
  name: "devops.service"
  domain: devops
spec:
  fields:
    - name: id
      type: string
    - name: display_name
      type: string
    - name: owner
      type: string
```

多域 quickstart 样例包含：

- `devops.service`
- `devops.pipeline`
- `k8s.workload`
- `automaker.vehicle`
- `game.server`
- `supplier.production_batch`

见 [examples/quickstart-multidomain](../../../examples/quickstart-multidomain/README.zh-CN.md)。

## EntitySet 与 Entity Record

| 层次 | 示例 | 作用 |
|---|---|---|
| EntitySet | `devops.service` | 定义对象类型和字段。 |
| Entity record | 某个 checkout 服务 | 存储运行时对象实例。 |

Entity record 通过 EntityStore API 写入，通过 `.entity` 查询读取。EntitySet 作为 MModel element 导入，通过 `.mmodel` 查询读取。

## 设计规则

- 使用稳定身份字段，不要只依赖展示名。
- 字段面向运维人员和 Agent 保持清晰。
- 将 domain-specific semantics 放在 domain 中，不要放在 generic names 中。
- 通过 `data_link` 连接数据集，不要把存储查询细节塞进 EntitySet。
- 有拓扑语义时，通过 `entity_set_link` 连接实体类型。

## 查询示例

列出 EntitySet definitions：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | sort name | limit 20"
```

列出运行时 service entities：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service') | limit 20"
```
