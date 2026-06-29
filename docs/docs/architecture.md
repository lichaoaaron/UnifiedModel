# MModel 产品架构说明

## 架构目标

产品架构的当前目标，是尽量将 MModel Core 与平台集成层分离，让对象语义、证据组织、调查时间线和诊断能力优先沉淀在 MModel 内部，同时将宿主平台差异尽量控制在薄适配层中。

## 架构分层

### 1. MModel Core

MModel Core 承载所有核心业务能力：

- Model Definition
- Runtime Entity Graph
- Entity Management
- Topology
- Evidence Association
- Historical Runtime
- Investigation Timeline
- Query API
- Diagnosis API
- MModel Web UI

### 2. Access Layer

统一对外访问层，负责以一致契约暴露能力：

- REST API
- SDK
- CLI
- MCP Server

该层保证不同入口共享同一能力模型，而不是分别实现一套逻辑。

### 3. Platform Adapter Layer

平台适配层承接不同宿主平台的集成差异，负责：

- SSO
- Deep Link
- URL 参数映射
- 时间范围同步
- 上下文同步
- Embedded View
- 原始数据页面跳转

### 4. Host Platform Layer

宿主平台负责：

- 登录
- 门户导航
- 告警入口
- 原始数据承接页面

## 关键边界

- 当前方案建议平台适配器尽量不要实现 MModel 的核心对象逻辑。
- 当前方案建议对象、关系、证据、历史回溯、时间线和诊断逻辑优先通过 MModel Core 暴露。
- 若后续支持多平台切换，建议尽量避免影响 MModel 的核心 API、对象模型和调查链路。

## 适配原则

- 所有平台都对接同一套 MModel Core API。
- Adapter 只做协议转换、上下文同步和入口承接。
- Adapter 中不重复实现对象建模、证据关联和诊断逻辑。
- 宿主平台退出或替换时，MModel 核心能力无需重写。
