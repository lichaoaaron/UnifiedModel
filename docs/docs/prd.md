# MModel Product Requirements Document

## 1. 产品概述

### 1.1 产品名称

MModel，Model for IT Operations。

### 1.2 产品定位

MModel 是独立的运维语义层与故障调查平台。

MModel 的目标不是替代底层可观测数据系统，而是在日志、指标、Trace、事件和拓扑数据之上建立统一的运行时对象模型，并为 Web、CLI、Agent 和大模型提供统一的数据访问与调查接口。

### 1.3 产品目标

- 建立统一的运行时对象模型。
- 将日志、指标、Trace 等可观测数据组织为以 Entity 为中心的数据模型。
- 为 Web、CLI、Agent、大模型提供统一的数据访问接口。
- 降低运维人员理解复杂系统和定位故障的成本。

### 1.4 设计原则

- MModel 是独立产品，不依附于任何单一 Dashboard。
- 所有核心业务能力必须优先在 MModel Core 中实现。
- 平台只负责登录、导航、上下文同步和原始数据跳转。
- 用户先理解对象和关系，再消费证据和诊断结果。
- Agent 通过稳定的高层语义接口工作，而不是学习底层存储结构。

## 2. 产品核心能力

MModel Core 负责对象建模、运行时对象构建、关系管理、证据关联、历史回溯、统一查询和 AI 调查上下文输出。核心能力的设计目标不是提供孤立功能点，而是形成一条完整的调查链路：定义模型，构建运行时对象，理解关系，关联证据，还原历史状态，输出可被人和 Agent 共用的诊断上下文。

### 2.1 功能模块总览

| 功能模块 | 功能描述 | 用户最终获得的效果 |
|---|---|---|
| 模型定义 | 使用 YAML 定义 EntitySet、Relation、DataSet、Storage，以及实体与观测数据的映射关系。 | 用户能够快速描述一个 IT 系统的对象模型，而不是直接面向日志和指标开发。 |
| 运行时对象构建 | 持续从可观测数据中自动构建 Entity、Relation 和 Runtime Topology。 | 每一个服务、数据库、Pod、容器等对象，都拥有统一身份。 |
| 对象管理 | 提供 Entity 搜索、Entity 浏览、对象属性查看和对象生命周期管理。 | 用户可以快速定位任何一个运行对象。 |
| 对象关系 | 提供 Relation 浏览、上下游依赖、服务拓扑和影响关系分析。 | 用户能够理解对象之间的依赖关系。 |
| Evidence | 根据 Entity 自动关联 Metrics、Logs、Traces 和 Events。 | 用户不需要记住索引、字段、查询语法，就可以直接查看对象证据。 |
| 调查时间线 | 以对象为中心统一组织 Metrics、Logs、Traces、Events、Topology Changes 和 Diagnosis Steps 等时间序列事件。 | 用户能够从单一时间轴还原故障发生、扩散、定位和收敛过程。 |
| 历史回溯 | 支持 time_range 查询、历史拓扑和历史对象关系查看。 | 用户能够查看故障发生时刻真实存在的运行状态。 |
| Query API | 提供 Entity Query、Relation Query、Evidence Query、Topology Query，并支持统一查询语言。 | 所有查询能力统一，而不是分散在多个系统。 |
| Diagnosis API | 向 Agent 和大模型提供 Entity Context、Evidence Context、Topology Context。 | Agent 不需要学习底层数据结构，就能获取诊断上下文。 |
| SDK / REST / MCP | 提供 REST API、SDK 和 MCP Server。 | CLI、Agent、Web 共用同一套能力。 |
| Web UI | 提供对象地图、对象详情、拓扑浏览、Evidence 浏览和 Diagnosis 页面。 | 运维人员无需命令行即可完成日常排障。 |

### 2.2 核心模块详细要求

#### 2.2.1 模型定义

模型定义是 MModel 的起点。产品必须允许用户从对象视角定义运行环境，而不是直接从字段和索引视角组织数据。

要求包括：

- 使用 YAML 描述 EntitySet。
- 定义对象之间的 Relation 类型与语义。
- 定义 DataSet，并标明其数据类型与用途。
- 定义 Storage，并描述数据落点或访问入口。
- 定义实体标识、字段映射和观测数据映射关系。

MModel 在这一层的价值，是把“服务、实例、数据库、Pod、容器、队列、外部依赖”等运行对象抽象成稳定语义模型，为后续自动构建 Entity Graph、证据关联和诊断上下文提供基础。

#### 2.2.2 运行时对象构建

MModel 必须持续从运行时数据中自动构建对象图，而不是要求用户手工维护对象清单。

要求包括：

- 从多类运行时数据中识别 Entity。
- 自动生成或更新 Relation。
- 形成可查询的 Runtime Topology。
- 支持对象状态变化、属性更新和关系变化。

最终交付不是一份静态 CMDB，而是一个可随运行时变化持续更新的对象图。

#### 2.2.3 对象管理

对象管理解决“我要找到哪个对象”的问题。

要求包括：

- 通过名称、类型、标签、属性、环境、状态等维度搜索 Entity。
- 提供列表与详情视图。
- 展示对象属性、状态、最近活动和关键标识。
- 展示对象生命周期，例如创建、活跃、异常、消失、过期。

用户应当能在几步之内定位任意运行对象，并理解它当前的身份和状态。

#### 2.2.4 对象关系

对象关系解决“这个对象与谁相关”的问题。

要求包括：

- 浏览对象之间的 Relation。
- 展示上下游依赖。
- 展示服务拓扑与跨层级关系。
- 识别影响关系与传播路径。

这一层必须支持从单个对象出发，快速看到依赖面和影响面。

#### 2.2.5 Evidence

Evidence 是 MModel 区别于单纯对象管理系统的关键能力。系统必须围绕对象自动聚合与该对象相关的多类证据。

要求包括：

- 自动关联 Metrics。
- 自动关联 Logs。
- 自动关联 Traces。
- 自动关联 Events。
- 支持以对象为中心聚合证据时间线。

用户不应被迫记忆底层索引名、日志字段、Trace 维度或查询语法，而应直接从对象进入证据。

#### 2.2.6 历史回溯

故障调查依赖时间语义。MModel 必须支持回到过去查看对象与关系的历史状态。

要求包括：

- 所有关键查询支持 `time_range`。
- 支持历史拓扑查看。
- 支持历史对象关系查看。
- 支持按故障发生时刻还原对象证据上下文。

最终效果是，用户看到的是“故障发生当时”的真实状态，而不是“现在”的状态误投影到过去。

#### 2.2.7 调查时间线

调查时间线是 MModel 的核心调查能力之一。系统必须以对象为中心，把与该对象相关的时间序列证据和调查过程统一组织到同一时间轴中，帮助用户和 Agent 还原故障是如何发生、扩散、定位与收敛的。

要求包括：

- 以对象为中心聚合时间序列事件。
- 支持统一展示 Metrics、Logs、Traces、Events、Topology Changes 和 Diagnosis Steps。
- 支持按时间范围、事件类型、关联对象和调查阶段筛选。
- 支持展示关键时间点，例如异常开始、峰值、根因确认、影响扩散和恢复。
- 支持从时间线事件联动到证据详情、拓扑快照和调查结论。

调查时间线的交付重点，不是简单罗列事件，而是帮助用户建立“对象 - 证据 - 时间 - 结论”的完整调查链路。

#### 2.2.8 Query API

Query API 是人和系统共享的统一读取入口。

要求包括：

- Entity Query
- Relation Query
- Evidence Query
- Topology Query
- 统一查询语言，例如 SPL 风格能力
- 支持分页、过滤、排序、聚合和时间范围约束

这一层必须抽象掉底层数据差异，让查询面保持统一。

#### 2.2.9 Diagnosis API

Diagnosis API 服务于 Agent 与大模型，不要求它们理解底层可观测平台的实现细节。

要求包括：

- 输出 Entity Context
- 输出 Evidence Context
- 输出 Topology Context
- 支持围绕单对象或多对象生成调查上下文
- 支持为 Root Cause Analysis 提供结构化输入

Diagnosis API 的交付重点不是原始数据透传，而是面向诊断任务的高层上下文封装。

#### 2.2.10 SDK / REST / MCP

MModel 必须将核心能力暴露为稳定的公共契约。

要求包括：

- REST API 作为通用服务接口
- SDK 作为开发者接入入口
- MCP Server 作为 Agent 接入入口
- CLI、Web、Agent 共用同一能力层

这样可以保证不同入口共享一致行为，而不是各自实现一套逻辑。

#### 2.2.11 Web UI

Web UI 是面向运维人员的主要可视化入口。

要求包括：

- 对象地图
- 对象详情
- 拓扑浏览
- Evidence 浏览
- 调查时间线
- Diagnosis 页面
- 历史时间范围切换

用户应当在不依赖命令行的情况下完成日常故障调查闭环。

## 3. MModel vs Copilot 职责边界

### 3.1 设计原则

MModel 与 Copilot 的关系应当是“结构化调查能力提供方”与“通用对话助手调用方”的关系，而不是由 Copilot 承载 MModel 的核心业务逻辑。

职责划分原则如下：

- MModel 负责对象语义、拓扑语义、证据组织、调查时间线和结构化诊断结果。
- Copilot 负责自然语言交互、任务编排、追问、解释和结果表达。
- Copilot 通过 Skill、MCP、REST API 或 SDK 调用 MModel 能力，而不是绕过 MModel 直接拼装调查逻辑。
- 任何对象、关系、证据、影响面和报告模型的定义，都优先沉淀在 MModel 中。

### 3.2 MModel 负责的能力

MModel 应负责以下能力：

- Model Definition
- Runtime Entity Graph
- Entity Management
- Topology
- Evidence Association
- Historical Runtime
- Investigation Timeline
- Query API
- Diagnosis API
- Root Cause 候选结构
- Impact Analysis 结构
- Report 数据模型
- Skill / MCP / SDK / REST 对外能力
- 结构化调查页面与结果视图

其中，拓扑随调查推进而变化、对象相关证据随时间轴聚合、根因候选与影响面收敛等能力，都属于 MModel 的调查语义层，不属于 Copilot 的对话层。

### 3.3 Copilot 负责的能力

Copilot 应负责以下能力：

- 通用对话界面
- 多轮会话管理
- 自然语言理解与追问
- 基于 MModel Skill / MCP 的工具调用编排
- 对结构化调查结果做自然语言解释
- 对时间线、根因、影响面和报告进行摘要与重述
- 辅助生成报告措辞、结论描述和后续建议

Copilot 可以帮助用户理解与追问，但不应单独定义对象模型、证据模型、拓扑逻辑或调查主流程。

### 3.4 协作方式

推荐协作方式如下：

- MModel 提供对象、证据、拓扑、调查时间线、影响面和报告的结构化能力。
- Copilot 消费这些能力，并通过通用对话助手界面完成用户交互。
- MModel 自身仍保留实体探索与结构化调查结果视图，确保其作为独立产品成立。
- Copilot 可以嵌入 MModel，也可以作为独立助手调用 MModel，但两者的职责边界保持稳定。

## 4. 第一阶段交付

### 4.1 阶段目标

第一阶段为了快速交付，允许将 MModel 集成到 Grafana 中作为宿主入口，但这只是一种交付策略，不改变 MModel 的产品定位。

在这一阶段，MModel Core 仍然负责对象、关系、证据、诊断和拓扑相关能力；Grafana 负责承载登录、导航、时间上下文和原始数据跳转体验。

### 4.2 集成能力

| 集成能力 | 用户最终体验 |
|---|---|
| Grafana 左侧菜单新增 MModel | 用户可以从现有运维入口直接进入 MModel，不需要单独记忆系统地址。 |
| Grafana 内打开对象地图 | 用户在现有工作台内直接查看 MModel 的对象视图。 |
| Grafana 内查看对象详情与拓扑 | 用户不离开当前平台即可进入对象调查流程。 |
| Grafana 内发起故障诊断 | 用户可以在同一工作空间触发 AI 调查与诊断。 |
| 与 Grafana 时间范围同步 | 用户切换时间范围后，MModel 自动查看对应时刻的对象、关系和证据。 |
| 跳转到 Grafana Explore | 用户在 MModel 中发现问题后，可一键跳到原始数据视图继续深挖。 |
| 复用 Grafana 登录 | 用户无需重复登录即可访问 MModel。 |
| 上下文跳转到指定对象 | 用户可从告警、面板或链接直接进入某个对象的详情页。 |

### 4.3 能力归属

#### 属于 MModel Core 的能力

- 模型定义
- Runtime Entity Graph
- Entity Management
- Topology
- Evidence 关联
- Historical Runtime
- Query API
- Diagnosis API
- REST / SDK / MCP
- MModel 自身的对象、诊断与调查页面

#### 属于 Grafana Integration 的能力

- 菜单入口接入
- 单点登录与会话复用
- 时间范围同步
- Deep Link 与 URL 参数映射
- 从 Grafana 跳转进入 MModel
- 从 MModel 跳回 Grafana 原始数据视图
- 宿主平台内嵌展示或容器化展示

## 5. 长期目标

### 5.1 长期目标说明

长期目标是让 MModel 保持独立产品，同时具备面向多个宿主平台的可适配能力。任何平台都不应承载 MModel 的核心业务逻辑，平台仅作为访问入口、身份承接与上下文同步层。

### 5.2 平台适配矩阵

| 平台 | 集成方式 | 是否需要开发 Adapter | 改造成本 |
|---|---|---|---|
| Grafana | 菜单入口、嵌入视图、时间同步、深链跳转、单点登录 | 是 | 中 |
| OpenSearch Dashboard | 应用入口、URL 跳转、时间同步、登录复用 | 是 | 中 |
| SkyWalking | 页面入口、上下文跳转、链路对象联动 | 是 | 中 |
| BOMC | 门户入口、统一身份、工单与对象调查联动 | 是 | 中到高 |
| 自研监控平台 | REST / SDK / Embedded View / SSO / Context Sync | 是 | 视平台成熟度而定 |

### 5.3 MModel Platform Adapter Layer

为避免业务逻辑绑定到单个平台，MModel 需要设计统一的平台适配层。

适配层能力包括：

- Deep Link
- URL 参数映射
- REST API 集成
- SDK 集成
- Embedded View
- SSO
- Context Sync

### 5.4 适配层职责边界

平台负责：

- 登录
- 跳转
- 上下文同步
- 原始数据页承接

MModel 负责：

- Entity
- Relation
- Evidence
- Diagnosis
- Topology
- 历史回溯
- 统一查询接口

### 5.5 适配层设计原则

- 所有平台都对接同一套 MModel Core API。
- 适配器只做协议转换、上下文同步与入口承接。
- 适配器中不重复实现对象建模、证据关联和诊断逻辑。
- 平台退出或切换时，MModel 核心能力不需要重写。

## 6. 最终产品效果

### 6.1 运维人员用户旅程

运维人员通常从告警、异常表现或业务反馈中发现故障。

在目标形态下，用户旅程如下：

1. 发现故障。
2. 进入 MModel。
3. 搜索相关对象，定位到出问题的服务、Pod、数据库或依赖组件。
4. 查看该对象的上下游拓扑，理解依赖关系。
5. 查看与该对象自动关联的 Metrics、Logs、Traces、Events。
6. 发起 AI 自动诊断，获取初步 Root Cause Analysis。
7. 查看影响面，识别受影响对象、服务链路和业务范围。
8. 生成调查报告，用于复盘、协同和后续处置。

这一旅程的核心价值，是让运维人员从“找数据”转为“围绕对象调查问题”。

### 6.2 Agent 用户旅程

Agent 的工作流应围绕稳定语义接口，而不是围绕底层数据存储实现。

目标工作流如下：

1. 调用 Entity API，识别目标对象。
2. 调用 Evidence API，获取相关证据。
3. 获取 Entity Context、Evidence Context、Topology Context。
4. 基于结构化上下文完成 Root Cause Analysis。
5. 输出诊断结果，包括可疑根因、证据摘要、影响范围和建议动作。

这一旅程的核心价值，是让 Agent 直接使用高层语义能力，而不是学习具体平台的底层数据结构。

## 7. 交付要求

### 7.1 面向外协团队的交付要求

- 所有开发以 MModel Core 优先为原则。
- 平台集成不得承载核心业务逻辑。
- 任何页面、接口、SDK 或 Adapter 的设计，都必须能映射回本 PRD 中定义的核心能力。
- 第一阶段允许以 Grafana 作为交付入口，但文档、接口和代码结构必须为多平台适配预留边界。

### 7.2 成功标准

- 用户能够用模型描述 IT 系统对象，而不是直接面向原始可观测数据。
- 用户能够围绕对象完成搜索、关系分析、证据查看和历史回溯。
- Agent 能够通过统一接口完成上下文获取与诊断。
- 第一阶段能够在 Grafana 中快速落地入口与调查体验。
- 长期演进不被任何单一平台绑定。
