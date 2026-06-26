# MModel Product Architecture

## 目标

产品架构的目标是把 MModel Core 与平台集成层彻底分离，让对象语义、证据关联和诊断能力稳定沉淀在 MModel 内部，而把宿主平台差异控制在薄适配层中。

## 架构分层

### MModel Core

MModel Core 承载所有核心业务能力：

- Model Definition
- Runtime Entity Graph
- Entity Management
- Topology
- Evidence Association
- Historical Runtime
- Query API
- Diagnosis API
- Web UI

### Access Layer

统一对外访问层，承接：

- REST API
- SDK
- CLI
- MCP Server

这一层保证不同入口共享同一能力，而不是各自实现分叉逻辑。

### Platform Adapter Layer

平台适配层承接不同宿主平台的集成差异：

- SSO
- Deep Link
- URL 参数映射
- 时间范围同步
- 上下文同步
- Embedded View
- 原始数据页跳转

### Host Platform Layer

宿主平台负责：

- 登录
- 门户导航
- 告警入口
- 原始数据承接页面

## 关键约束

- 平台适配器不得实现 MModel 的核心对象逻辑。
- 所有对象、关系、证据、历史回溯和诊断逻辑都通过 MModel Core 暴露。
- 平台切换不应影响 MModel 的核心 API 和对象模型。

## 后续补充

后续版本需要补充：

- 平台适配层组件图
- 上下文同步协议
- Deep Link 规范
- Embedded View 生命周期
- 多平台认证与授权边界
