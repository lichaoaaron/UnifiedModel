# 源码导航

这一篇不是讲概念，而是告诉你“下一步打开哪些文件最值”。

## 第一轮导航

如果你只打算花一小时建立整体认识，按这个顺序开文件：

1. `README.md`
2. `docs/zh/README.md`
3. `cmd/mmodel-server/main.go`
4. `internal/bootstrap/app.go`
5. `pkg/contract/contracts.go`
6. `internal/query/service.go`
7. `internal/agentgateway/service.go`
8. `examples/quickstart-multidomain/README.md`

## 目录地图

| 路径 | 作用 | 为什么值得先看 |
|---|---|---|
| `cmd/mmodel-server` | REST 服务入口 | 看进程如何启动、如何接 quickstart |
| `cmd/mmctl` | CLI 入口 | 看公共操作如何暴露给用户 |
| `cmd/mmodel-mcp` | MCP 入口 | 看 Agent 集成如何接入 |
| `internal/bootstrap` | 服务组装和路由 | 最快看到系统 wiring |
| `internal/workspace` | workspace 元数据 | 理解最外层隔离单元 |
| `internal/mmodel` | 模型校验与写入 | 理解模型定义如何进入系统 |
| `internal/entitystore` | 实体和关系写入 | 理解运行时图如何构建 |
| `internal/query` | 解析、规划、执行 | 理解统一读路径 |
| `internal/agentgateway` | Agent 适配层 | 理解资源、工具和发现 |
| `internal/graphstore` | 存储抽象和 provider | 理解 provider-neutral 设计 |
| `web/src/api` | 前端 API 调用层 | 验证 Web UI 是否只走公共 REST |

## 按问题找文件

### 我想知道服务是怎么装起来的

看：

- `internal/bootstrap/app.go`

搜索：

```bash
rg "NewService|NewProvider|HandleFunc" internal/bootstrap
```

### 我想知道查询为什么统一走 `.mmodel`、`.entity`、`.topo`

看：

- `internal/query/service.go`
- `internal/query/planner.go`
- `internal/query/executor.go`

搜索：

```bash
rg "Execute|Explain|graph-call|.entity|.topo|.mmodel" internal/query
```

### 我想知道模型写入和实体写入有什么区别

看：

- `internal/mmodel/service.go`
- `internal/entitystore/service.go`
- `internal/bootstrap/app.go`

搜索：

```bash
rg "PutElements|WriteEntities|WriteRelations|ExpireEntities|ExpireRelations" internal
```

### 我想知道 Web UI 是否遵守公共 API 边界

看：

- `web/src/api/client.ts`
- `web/src/features/settings/ApiMapPage.tsx`

搜索：

```bash
rg "/api/v1/query/|/api/v1/agent/|/api/v1/entitystore/" web/src
```

### 我想知道 AgentGateway 有没有偷偷实现第二套读模型

看：

- `internal/agentgateway/service.go`

重点确认：

- `ExecuteTool` 对查询工具最终调用了 `query.Execute` / `query.Explain`
- `ReadResource` 返回的是元数据，不是运行时实体行

## 推荐读测试的方式

很多实现细节从测试里更容易看出来。

优先看：

- `internal/query/parser_test.go`
- `internal/query/planner_test.go`
- `internal/query/service_test.go`
- `internal/agentgateway/service_test.go`
- `internal/bootstrap/quickstart_test.go`

你可以把测试当作“可执行设计说明”。

## 最有用的 `rg` 命令

```bash
rg "type Service struct" internal
rg "HandleFunc\\(" internal/bootstrap
rg "Query Service|AgentGateway|GraphStore" docs internal pkg
rg "query run demo|agent discover demo" docs examples
```

## 最后再看这些

当你已经理解主干后，再往外扩展：

- `api/openapi/openapi.yaml`
- `api/mcp/tools.schema.json`
- `sdk/go`
- `sdk/python`
- `generated/java`
- `tools/guards/architecture_guard.py`

这些文件更适合在“我已经知道系统主线是什么”的前提下看。

## 配套参考

- [系统架构](architecture.md)
- [查询执行链路](query-flow.md)
- [AgentGateway 与 MCP](agent-and-mcp.md)
