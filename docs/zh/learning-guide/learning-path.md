# 实践学习路径

如果你想真正把 MModel 读懂，最有效的方式不是连续读很多文件，而是“读一点，跑一点，验证一点”。

## 第一阶段：先跑起来

目标：确认项目在你机器上的默认运行方式，并建立对 demo workspace 的直觉。

执行：

```bash
make quickstart
```

然后：

- 打开 `http://localhost:5173`
- 选择 `demo`
- 依次看看 Explorer、Query、Data Store、Agent

你在这一阶段要回答的问题：

- quickstart 默认导入了什么样例。
- API、Web UI 分别跑在哪个端口。
- `demo` workspace 里同时有哪些模型和运行时数据。

## 第二阶段：把三种读路径跑一遍

目标：把 `.mmodel`、`.entity`、`.topo` 三个公共查询源和真实结果对上。

执行：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".mmodel with(kind='entity_set') | sort name | limit 10"
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".entity with(domain='devops', name='devops.service', query='checkout') | limit 10"
go run ./cmd/mmctl --addr http://localhost:8080 query run demo ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 10"
```

你在这一阶段要回答的问题：

- 三种查询源各自读的是什么。
- 为什么 `.topo` 才允许 `graph-call`。
- 为什么 UI、CLI、REST 理论上应该得到同类结果。

## 第三阶段：读启动与组装代码

目标：建立服务 wiring 心智模型。

先看：

- `cmd/mmodel-server/main.go`
- `internal/bootstrap/app.go`
- `internal/bootstrap/quickstart.go`

你在这一阶段要回答的问题：

- 进程启动时做了哪些初始化。
- GraphStore provider 在哪里选择。
- quickstart 为什么默认改用 `memory`。

## 第四阶段：顺着写路径读

目标：看模型和运行时数据如何进入系统。

先看：

- `internal/mmodel/service.go`
- `internal/entitystore/service.go`
- `internal/sampledata/service.go`

建议同时对照：

- `examples/quickstart-multidomain/README.md`
- `examples/quickstart-multidomain/sample-data/entities.json`
- `examples/quickstart-multidomain/sample-data/relations.json`

你在这一阶段要回答的问题：

- 什么是模型写入，什么是运行时写入。
- `IdempotencyKey` 怎么工作。
- 样例导入时哪一步失败最可能影响 quickstart。

## 第五阶段：顺着读路径读

目标：把 Query Service 读透。

先看：

- `internal/query/service.go`
- `internal/query/planner.go`
- `internal/query/executor.go`
- `internal/query/*_test.go`

建议执行：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 query explain demo ".entity with(domain='devops', name='devops.service') | limit 5"
```

你在这一阶段要回答的问题：

- planner 和 executor 的边界是什么。
- provider capability 为什么要在 plan 阶段参与。
- explain 信息从哪里来。

## 第六阶段：再读 Agent 与 MCP

目标：理解 Agent 集成没有偏离主架构。

先看：

- `internal/agentgateway/service.go`
- `cmd/mmodel-mcp/main.go`
- `docs/zh/reference/mcp.md`

建议执行：

```bash
go run ./cmd/mmctl --addr http://localhost:8080 agent discover demo
go run ./cmd/mmctl --addr http://localhost:8080 agent tool demo query_spl_examples '{}'
```

你在这一阶段要回答的问题：

- AgentGateway 为什么不直接返回 runtime rows 资源。
- MCP 为什么仍然要复用 Query Service。
- 写工具为什么默认关闭。

## 第七阶段：用守卫和测试验证你的理解

目标：把“我大概懂了”变成“我知道边界在哪”。

执行：

```bash
make guard
make test-service
git diff --check
```

`make guard` 很关键，因为它把架构边界变成了可执行规则。

## 推荐的最终检查题

如果下面这些问题你都能自己回答，说明已经形成了比较稳的理解：

- 为什么 Query Service 是唯一公共读路径。
- MModel Service 和 EntityStore 的职责边界是什么。
- quickstart 为何默认使用 `memory` provider。
- AgentGateway 为什么只把资源做成元数据导向。
- Web UI 如何证明自己只调用公共 REST API。

## 配套参考

- [项目地图与阅读路线](README.md)
- [系统架构](architecture.md)
- [模型导入与运行时写入](model-and-write-flow.md)
- [查询执行链路](query-flow.md)
