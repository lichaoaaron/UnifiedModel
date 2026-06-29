# MModel 接口边界说明

## 目标

MModel API 负责向 Web、CLI、SDK、Agent 和宿主平台暴露统一能力，屏蔽底层数据来源和存储结构差异。

## 接口分层

### Query API

统一读接口，覆盖：

- Entity Query
- Relation Query
- Evidence Query
- Topology Query
- Historical Query

### Diagnosis API

面向诊断任务的上下文接口，覆盖：

- Entity Context
- Evidence Context
- Topology Context
- Investigation Context

### Integration API

面向宿主平台集成的辅助能力，覆盖：

- 对象详情 Deep Link
- 时间范围同步参数
- 上下文跳转参数
- 嵌入视图初始化参数

## 对外形态

- REST API
- SDK
- MCP Server

## 设计约束

- API 以对象语义为核心，而不是以底层存储结构为核心。
- 同一类能力在 REST、SDK、MCP 中保持一致命名与行为。
- 当前方案建议平台适配器优先消费 API，而不是旁路访问内部实现。
- 当前方案建议诊断相关接口优先输出结构化上下文，而不是直接透传底层原始数据。
