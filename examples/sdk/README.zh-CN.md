# SDK 示例

English: [SDK Examples](README.md)

公开 MModel SDK surface 的可运行示例。

覆盖范围：

- 在导入 workspace 之前检查 MModel 模型包；
- 把生成模型 SDK 与 REST service client 组合起来；
- 让应用代码依赖公开契约，而不是 server internal package。

## 示例列表

| 路径 | 入口 | 用途 |
|---|---|---|
| [full-flow.zh-CN.md](full-flow.zh-CN.md) | 端到端流程 | SDK 生成、服务启动和 SDK 示例运行。 |
| [go/model-inspector](go/model-inspector) | 生成的 Go 模型 SDK | 解析 YAML/JSON MModel 文件，校验 envelope，列出模型元数据，并展示 link endpoint。 |
| [go/service-quickstart](go/service-quickstart) | Go REST client | 创建 workspace、导入模型包、查询 MModel 元素，并查看 Agent discovery。 |
| [python/inspect_model_pack.py](python/inspect_model_pack.py) | 生成的 Python 模型 SDK | 扫描模型包并输出 kind/domain/name/link 摘要。 |

## 运行 Go 示例

生成的 Go SDK 当前使用仓库内模块路径 `mmodel_go_cli`，所以示例放在一个小的 example module 中，并通过本地 `replace` 指向 `sdk/go`。

```bash
cd examples/sdk/go
go mod tidy
go run ./model-inspector -path ../../quickstart-multidomain
```

REST client 示例需要先从仓库根目录启动 API：

```bash
make dev-api
```

然后在另一个 shell 中运行：

```bash
cd examples/sdk/go
go run ./service-quickstart -addr http://localhost:8080
```

## 运行 Python 示例

Python 示例从仓库 checkout 运行时自动把 `sdk/python` 加入 `sys.path`。

```bash
python3 examples/sdk/python/inspect_model_pack.py --path examples/quickstart-multidomain
```

## 契约边界

生成模型 SDK 覆盖本地模型构造、解析和元数据检查。运行时读写通过公开 REST API、Go REST client、`mmctl` 或 MCP。
