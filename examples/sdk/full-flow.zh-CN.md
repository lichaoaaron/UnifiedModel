# SDK 端到端示例流程

English: [SDK End-To-End Flow](full-flow.md)

端到端 SDK 流程：生成 SDK、启动本地服务、用生成 SDK 检查模型包、运行 REST client。所有命令默认从仓库根目录执行，除非命令块里显式 `cd` 到其他目录。

## 目标

结果：

- 重新生成并验证过的 Go、Python、Java 模型 SDK；
- 一个运行中的本地 MModel API 服务；
- 一个用生成 SDK 扫描模型包的本地校验流程；
- 一个用 Go REST client 连接服务、创建 workspace、导入模型包并查询的运行时流程。

## 1. 准备依赖

首次 checkout：

```bash
make setup
```

`make setup` 准备 Python 依赖，并在可用时下载 Go 和 Java SDK 相关依赖。

## 2. 生成 SDK

MModel 的模型 SDK 来自 `schemas/`。Schema 变更后执行：

```bash
make expand
```

生成输出：

- 展开 `schemas/` 到 `expanded_schemas/`；
- 校验展开后的 schema；
- 重新生成 `sdk/go/mmodel`；
- 重新生成 `sdk/python/mmodel`；
- 重新生成 `generated/java`。

生成后运行完整 SDK 校验：

```bash
make verify
```

Go REST client 定向检查：

```bash
cd sdk/go
go test ./service
```

## 3. 用生成 SDK 检查模型包

生成模型 SDK 在运行时导入前负责：解析 YAML/JSON、校验 envelope、读取 kind/domain/name、识别 link 的 src/dest。

### Go 模型检查

```bash
cd examples/sdk/go
go run ./model-inspector -path ../../quickstart-multidomain -limit 5
```

输出会包含 SDK 版本、各 kind 数量，以及前几条模型摘要，例如：

```text
MModel Go SDK 2.0.0
Parsed 77 MModel files
- entity_set: 35
- entity_set_link: 42
...
```

### Python 模型检查

回到仓库根目录后运行：

```bash
python3 examples/sdk/python/inspect_model_pack.py --path examples/quickstart-multidomain --limit 5
```

Python 示例自动把仓库内 `sdk/python` 加入 `sys.path`，不需要额外设置 `PYTHONPATH`。

## 4. 启动本地 MModel API 服务

REST client 示例需要正在运行的 API。新终端：

```bash
DATA_ROOT=/tmp/mmodel-sdk-demo-data GRAPHSTORE=file.memory make dev-api
```

保持这个终端运行。另一个终端执行 readiness check：

```bash
curl -fsS http://localhost:8080/healthz
```

备用端口：

```bash
API_ADDR=:18080 API_URL=http://localhost:18080 DATA_ROOT=/tmp/mmodel-sdk-demo-data GRAPHSTORE=file.memory make dev-api
```

后续 REST client 的 `-addr` 也要同步改为 `http://localhost:18080`。

## 5. 运行 Go REST client 示例

在另一个终端中运行：

```bash
cd examples/sdk/go
go run ./service-quickstart -addr http://localhost:8080 -workspace sdk-demo
```

示例调用公开 REST contract：

1. 创建或复用 `sdk-demo` workspace；
2. 导入 `examples/quickstart-multidomain` 模型包；
3. 执行 `.mmodel with(kind='entity_set') | limit 5` 查询；
4. 调用 Agent discovery，确认工具、资源和 next action 可被发现。

典型输出：

```text
Workspace "sdk-demo" created.
Imported 77 MModel elements from /.../examples/quickstart-multidomain.
Query returned 5 rows with columns [...]
Agent discovery: 7 tools, 4 resources, 5 next actions.
```

已存在 workspace 时，示例复用该 workspace 并继续导入和查询。

## 6. 用 CLI 交叉验证

通过 `mmctl` 交叉验证同一个 workspace：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run sdk-demo ".mmodel with(kind='entity_set') | limit 5"
```

REST client 写入的 workspace 可通过其他公开入口读取。

## 流程边界

| 阶段 | 入口 | 备注 |
|---|---|---|
| SDK 生成 | `make expand` | 从 schema 生成 Go/Python/Java 模型 SDK。 |
| 本地校验 | `model-inspector` / `inspect_model_pack.py` | 不连接服务，只解析和检查模型包。 |
| 服务启动 | `make dev-api` | 启动本地 MModel API。 |
| 运行时集成 | `service-quickstart` | 通过公开 REST contract 操作 workspace、导入和查询。 |
| 交叉验证 | `mmctl` | 用 CLI 读取同一个 workspace 的状态。 |

生成模型 SDK 不直接承担运行时读写；运行时实体、关系、查询和 Agent discovery 应通过 REST、`mmctl` 或 MCP 进入服务。

## 常见问题

### `make expand` 缺 Python 依赖

先运行：

```bash
make setup
```

### `service-quickstart` 连接失败

确认 API 服务仍在运行，并检查 `-addr` 是否和 `make dev-api` 的端口一致：

```bash
curl -fsS http://localhost:8080/healthz
```

### Go 示例找不到模块

Go SDK 示例需要在 `examples/sdk/go` 目录运行，因为这个目录的 `go.mod` 通过本地 `replace` 指向 `sdk/go`：

```bash
cd examples/sdk/go
go run ./model-inspector -path ../../quickstart-multidomain
```

### Python 示例找不到 `mmodel`

仓库 checkout 命令：

```bash
python3 examples/sdk/python/inspect_model_pack.py --path examples/quickstart-multidomain
```
