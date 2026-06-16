# GraphStore Providers

English: [GraphStore Providers](../en/graphstore-providers.md)

MModel 通过 `GraphStore` 接口保存和查询 MModel elements、CMS 2.0 实体以及拓扑关系。运行时通过 `--graphstore` 选择 provider。


## Providers

| Provider | 持久化 | 典型用途 |
|---|---|---|
| `memory` | 进程内存 | 快速测试和一次性本地实验，进程退出后数据消失。 |
| `file.memory` | `--data` 下的 JSON 文件 | 本地开发和文档演示的默认选择，重启后数据保留。 |
| `local.ladybug` | Ladybug 数据库文件 | Ladybug-backed 环境，需要 `-tags ladybug` 和本地 Ladybug runtime。 |

启动示例：

```bash
go run ./cmd/mmodel-server --addr :8080 --data data --graphstore file.memory
```

当前 provider 位置：

- `GET /healthz` 的 `graphstore.provider`
- Query explain 的 `provider` 和 `storage_provider`

## `file.memory` 布局

`file.memory` 将数据保存在：

```text
<data-root>/graphstore/file-memory/
└── workspaces/
    └── demo/
        ├── mmodels.json
        ├── entities.json
        └── relations.json
```

Workspace 元数据单独保存在：

```text
<data-root>/workspaces.json
```

## 边界

- `file.memory` 面向单本地进程，不要让多个 writer 写同一个目录。
- JSON 文件服务于检查和演示，不是长期兼容性存储合约。
- 运行时读取仍通过 Query Service，不应绕过 `.mmodel`、`.entity`、`.topo`。

## 烟测

```bash
go run ./cmd/mmodel-server --addr :8080 --data /tmp/mmodel-demo --graphstore file.memory
go run ./cmd/mmctl --addr http://localhost:8080 mmodel put demo '{"id":"devops.service","kind":"entity_set","domain":"devops","name":"devops.service"}'
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel | limit 5"
find /tmp/mmodel-demo/graphstore/file-memory -maxdepth 4 -type f
```
