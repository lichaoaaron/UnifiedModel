# MModel 产品需求文档

## 1. 产品概述

### 1.1 产品名称

MModel，Model for IT Operations。

### 1.2 产品定位

在当前这版需求初稿中，MModel 被定义为一个偏独立的运维语义层与故障调查平台。

MModel 不替代底层可观测平台，而是在日志、指标、Trace、事件和拓扑数据之上建立统一的运行时对象模型，并向 Web、CLI、Agent 和大模型提供统一的数据访问与调查接口。

### 1.3 产品目标

- 建立统一的运行时对象模型。
- 将可观测数据组织为以 Entity 为中心的数据模型。
- 形成统一的对象、关系、证据、时间线和诊断上下文。
- 降低运维人员理解复杂系统和定位故障的成本。

### 1.4 设计原则

- 当前文档倾向于将 MModel 作为相对独立的产品能力进行设计，而不是直接按单一平台插件定义自身。
- 当前文档建议将核心业务能力优先沉淀在 MModel Core 中，便于后续扩展与平台适配。
- 结合第一阶段目标，平台侧当前主要承接登录、导航、上下文同步和原始数据跳转。
- Agent 在本稿设想中通过高层语义接口使用 MModel，而不是直接学习底层数据结构。

## 2. MModel Core

MModel Core 负责对象建模、运行时对象构建、关系管理、证据组织、历史回溯、统一查询和诊断上下文输出。

### 2.1 功能模块总览

| 功能模块 | 功能描述 | 用户最终获得的效果 |
|---|---|---|
| 模型定义 | 使用 YAML 定义 EntitySet、Relation、DataSet、Storage，以及实体与观测数据的映射关系。 | 用户能够快速描述一个 IT 系统的对象模型，而不是直接面向日志和指标开发。 |
| 运行时对象构建 | 持续从可观测数据中自动构建 Entity、Relation 和 Runtime Topology。 | 每一个服务、数据库、Pod、容器等对象，都拥有统一身份。 |
| 对象管理 | 提供 Entity 搜索、浏览、属性查看和生命周期管理。 | 用户可以快速定位任何一个运行对象。 |
| 对象关系 | 提供 Relation 浏览、上下游依赖、服务拓扑和影响关系分析。 | 用户能够理解对象之间的依赖关系。 |
| Evidence | 根据 Entity 自动关联 Metrics、Logs、Traces 和 Events。 | 用户不需要记住索引、字段、查询语法，就可以直接查看对象证据。 |
| 调查时间线 | 以对象为中心统一组织 Metrics、Logs、Traces、Events、Topology Changes 和 Diagnosis Steps 等时间序列事件。 | 用户能够从单一时间轴还原故障发生、扩散、定位和收敛过程。 |
| 历史回溯 | 支持 time_range 查询、历史拓扑和历史对象关系。 | 用户能够查看故障发生时刻真实存在的运行状态。 |
| Query API | 提供 Entity Query、Relation Query、Evidence Query、Topology Query，并支持统一查询语言。 | 所有查询能力统一，而不是分散在多个系统。 |
| Diagnosis API | 向 Agent、大模型提供 Entity Context、Evidence Context、Topology Context 和 Investigation Context。 | Agent 不需要学习底层数据结构，就可以获取诊断上下文。 |
| SDK / REST / MCP | 提供 REST API、SDK 和 MCP Server。 | CLI、Agent、Web 共用同一套能力。 |
| Web UI | 提供对象地图、实体探索、拓扑浏览、证据浏览、调查时间线、结构化诊断和调查报告页面。 | 运维人员无需命令行即可完成日常排障。 |

### 2.2 模块详细要求

#### 2.2.1 模型定义

模型定义是 MModel 的起点。产品必须允许用户从对象视角描述运行环境，而不是直接从字段、索引和查询语法视角组织数据。

要求包括：

- 使用 YAML 描述 EntitySet。
- 定义对象之间的 Relation 类型与语义。
- 定义 DataSet，并标明其用途和数据类别。
- 定义 Storage，并描述数据访问入口。
- 定义实体标识、字段映射和证据映射关系。

#### 2.2.2 运行时对象构建

MModel 必须持续从运行时数据中自动构建对象图，而不是要求用户手工维护对象清单。

要求包括：

- 从多类运行时数据中识别 Entity。
- 自动生成或更新 Relation。
- 形成可查询的 Runtime Topology。
- 支持对象状态变化、属性更新和关系变更。

#### 2.2.3 对象管理

对象管理解决“我要找到哪个对象”的问题。

要求包括：

- 通过名称、类型、标签、属性、环境和状态搜索 Entity。
- 提供列表与详情视图。
- 展示对象属性、状态、最近活动和关键标识。
- 展示对象生命周期，例如创建、活跃、异常、消失和过期。

#### 2.2.4 对象关系

对象关系解决“这个对象与谁相关”的问题。

要求包括：

- 浏览对象之间的 Relation。
- 展示上下游依赖。
- 展示服务拓扑与跨层级关系。
- 识别影响关系与传播路径。

#### 2.2.5 Evidence

Evidence 是 MModel 区别于单纯对象管理系统的关键能力。系统必须围绕对象自动聚合多类证据。

要求包括：

- 自动关联 Metrics。
- 自动关联 Logs。
- 自动关联 Traces。
- 自动关联 Events。
- 支持在统一入口下查看不同证据子视图。

#### 2.2.6 调查时间线

调查时间线是 MModel 的核心调查能力之一。系统必须以对象为中心，把与该对象相关的时间序列证据和调查过程统一组织到同一时间轴中。

要求包括：

- 以对象为中心聚合时间序列事件。
- 统一展示 Metrics、Logs、Traces、Events、Topology Changes 和 Diagnosis Steps。
- 支持按时间范围、事件类型、关联对象和调查阶段筛选。
- 支持高亮关键时刻，例如异常开始、峰值、根因确认、影响扩散和恢复。
- 支持从时间线事件联动到证据详情、拓扑快照和调查结论。

#### 2.2.7 历史回溯

故障调查依赖时间语义。MModel 必须支持回到过去查看对象与关系的历史状态。

要求包括：

- 关键查询支持 `time_range`。
- 支持历史拓扑查看。
- 支持历史对象关系查看。
- 支持按故障发生时刻还原对象证据上下文。

#### 2.2.8 Query API

Query API 是人和系统共享的统一读取入口。

要求包括：

- Entity Query
- Relation Query
- Evidence Query
- Topology Query
- 统一查询语言
- 支持分页、过滤、排序、聚合和时间范围约束

#### 2.2.9 Diagnosis API

Diagnosis API 面向 Agent 与大模型，不要求它们理解底层可观测平台的实现细节。

要求包括：

- 输出 Entity Context。
- 输出 Evidence Context。
- 输出 Topology Context。
- 输出 Investigation Context。
- 支持围绕单对象或多对象生成 Root Cause Analysis 所需上下文。

#### 2.2.10 SDK / REST / MCP

MModel 必须将核心能力暴露为稳定的公共契约。

要求包括：

- REST API 作为通用服务接口。
- SDK 作为开发者接入入口。
- MCP Server 作为 Agent 接入入口。
- CLI、Web、Agent 共用同一能力模型。

#### 2.2.11 Web UI

Web UI 是面向运维人员的主要可视化入口。

要求包括：

- 对象地图
- 实体探索
- 拓扑浏览
- 证据浏览
- 调查时间线
- 结构化诊断结果
- 影响面分析
- 调查报告

## 3. MModel vs Copilot 职责边界（当前方案设想）

### 3.1 边界原则

结合当前分工设想，MModel 与 Copilot 更适合被理解为“结构化调查能力提供方”与“通用对话助手调用方”的关系。本节用于描述当前版本的建议边界，便于外协理解，并不代表团队最终已经完全定稿。

### 3.2 当前建议由 MModel 负责

- 对象模型与关系模型
- 运行时拓扑
- 证据组织与聚合
- 调查时间线
- 结构化诊断结果
- 影响面分析结果
- 调查报告数据模型
- Skill / MCP / REST / SDK 能力输出
- 结构化调查页面与结果视图

### 3.3 当前建议由 Copilot 负责

- 通用对话界面
- 多轮会话管理
- 自然语言理解与追问
- 基于 MModel Skill / MCP 的工具编排
- 对结构化调查结果做自然语言解释、摘要和重述
- 辅助生成报告措辞、结论描述和后续建议

### 3.4 协作方式

- 当前建议由 MModel 提供对象、证据、拓扑、时间线、影响面和报告的结构化能力。
- 当前建议由 Copilot 消费这些能力，并通过通用对话助手界面完成自然语言交互。
- 结合目前分工，MModel 侧建议保留实体探索与结构化调查结果视图。
- 当前已明确的是，第一阶段 Copilot 不放在 MModel 项目中；更长期的集成形态可后续再讨论。

## 4. 第一阶段交付

### 4.1 阶段目标

目前可以明确的是，第一阶段以集成到 Grafana 为交付目标。其余关于长期产品边界、平台角色和能力归属的描述，均作为当前版本的方案设想与讨论基础。

### 4.2 集成能力

| 集成能力 | 用户最终体验 |
|---|---|
| Grafana 左侧菜单新增 MModel | 用户可以从现有运维入口直接进入 MModel。 |
| Grafana 内打开对象地图 | 用户可在当前工作台中直接查看 MModel 的对象入口。 |
| Grafana 内查看实体探索与拓扑 | 用户不离开当前平台即可进入对象调查流程。 |
| Grafana 内发起结构化诊断 | 用户可以在同一工作空间触发 AI 调查与诊断。 |
| 与 Grafana 时间范围同步 | 用户切换时间范围后，MModel 自动查看对应时刻的对象、关系和证据。 |
| 跳转到 Grafana Explore | 用户在 MModel 中发现问题后，可一键跳转到原始数据视图继续深挖。 |
| 复用 Grafana 登录 | 用户无需重复登录即可访问 MModel。 |
| 上下文跳转到指定对象 | 用户可从告警、面板或链接直接进入某个对象的调查入口。 |

### 4.3 能力归属

当前建议优先放入 MModel Core 的能力：

- 模型定义
- Runtime Entity Graph
- Entity Management
- Topology
- Evidence
- Investigation Timeline
- Historical Runtime
- Query API
- Diagnosis API
- REST / SDK / MCP
- MModel 自身页面与调查流程

当前建议放在 Grafana Integration 侧的能力：

- 菜单接入
- 登录复用
- 时间同步
- 上下文映射
- Deep Link 跳转
- 嵌入式承载
- 原始数据视图回跳

## 5. 长期平台适配能力

### 5.1 长期目标

长期方向上，当前文档倾向于让 MModel 保持较强的独立能力，同时具备面对多个宿主平台的可适配能力。该方向主要用于指导当前架构预留，并不表示团队已经对最终产品形态完全定稿。

### 5.2 平台适配矩阵

| 平台 | 集成方式 | 是否需要开发 Adapter | 改造成本 |
|---|---|---|---|
| Grafana | 菜单入口、嵌入视图、时间同步、Deep Link、SSO | 是 | 中 |
| OpenSearch Dashboard | 应用入口、URL 跳转、时间同步、登录复用 | 是 | 中 |
| SkyWalking | 页面入口、对象上下文跳转、链路联动 | 是 | 中 |
| BOMC | 门户入口、统一身份、工单与调查联动 | 是 | 中到高 |
| 自研监控平台 | REST / SDK / Embedded View / SSO / Context Sync | 是 | 视平台成熟度而定 |

### 5.3 MModel Platform Adapter Layer

为了避免过早把业务逻辑绑定到单一平台，当前方案建议预留统一的平台适配层。适配层能力包括：

- Deep Link
- URL 参数映射
- REST API 集成
- SDK 集成
- Embedded View
- SSO
- Context Sync

### 5.4 职责边界

当前建议平台侧主要负责：

- 登录
- 跳转
- 上下文同步
- 原始数据视图承接

当前建议 MModel 侧主要负责：

- Entity
- Relation
- Evidence
- Diagnosis
- Topology
- Historical Runtime
- Investigation Timeline
- 统一查询接口

## 6. 最终产品效果

### 6.1 运维人员用户旅程

1. 发现故障。
2. 进入 MModel。
3. 搜索相关对象，定位到问题服务、Pod、数据库或依赖组件。
4. 查看对象拓扑，理解上下游依赖和影响路径。
5. 查看自动聚合的 Metrics、Logs、Traces 和 Events。
6. 查看调查时间线，还原故障发生与扩散过程。
7. 发起 AI 自动诊断，获取初步 Root Cause Analysis。
8. 查看影响面，识别受影响对象、服务链路和业务范围。
9. 生成调查报告，用于协同、复盘和后续处置。

### 6.2 Agent 用户旅程

1. 调用 Entity API，识别目标对象。
2. 调用 Evidence API，获取相关证据。
3. 调用 Topology 与 Investigation Context，获取结构化上下文。
4. 执行 Root Cause Analysis。
5. 输出诊断结果，包括疑似根因、证据摘要、影响范围和建议动作。

## 7. 外协交付要求

### 7.1 交付原则

- 当前版本建议以 MModel Core 优先为原则推进设计与实现。
- 当前版本建议避免把核心业务逻辑直接沉淀到平台集成层。
- 任何页面、接口、SDK 或 Adapter 的设计，都必须能映射回本 PRD 中定义的核心能力。
- 第一阶段以 Grafana 作为交付入口；同时建议文档、接口和代码结构尽量为后续多平台适配预留边界。

### 7.2 成功标准

- 用户能够用模型描述 IT 系统对象，而不是直接面向原始可观测数据。
- 用户能够围绕对象完成搜索、关系分析、证据查看、时间线调查和历史回溯。
- Agent 能够通过统一接口完成上下文获取与诊断。
- 第一阶段能够在 Grafana 中快速落地入口与调查体验。
- 长期演进不被任何单一平台绑定。
