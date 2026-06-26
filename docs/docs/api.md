# MModel API Overview

## 目标

MModel API 负责向 Web、CLI、SDK、Agent 和宿主平台暴露统一能力，屏蔽底层数据来源和存储结构差异。

## API 分层

### Query API

提供统一读取接口：

- Entity Query
- Relation Query
- Evidence Query
- Topology Query
- Historical Query

### Diagnosis API

提供面向诊断任务的上下文接口：

- Entity Context
- Evidence Context
- Topology Context
- Investigation Context

### Integration API

提供面向宿主平台集成的辅助能力：

- 对象详情深链
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
- 平台适配器只能消费 API，不能旁路访问内部实现。

## 后续补充

后续版本需要补充：

- API 资源模型
- 请求响应示例
- 错误码与权限模型
- 分页、过滤、排序与时间参数规范
