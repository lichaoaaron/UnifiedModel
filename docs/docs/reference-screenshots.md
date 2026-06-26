# MModel Reference Screenshots

## 使用说明

本文件用于收集参考截屏，帮助外协团队理解 MModel 目标页面应承载的能力、信息结构和调查流程。

这些截屏可以来自阿里云 UModel、AWS DevOps Agent 或其他已有内部产品，但只作为能力参考，不作为 MModel 最终产品定义。

必须明确以下边界：

- 截屏只用于辅助理解，不代表 MModel 的最终 UI 设计稿。
- 截屏只表达能力和交互方向，不表达品牌、命名或平台归属。
- 任何平台特有字段、菜单结构或耦合逻辑都不应直接继承为 MModel 产品要求。
- 核心判断标准始终以 [prd.md](prd.md) 和 [ui.md](ui.md) 为准。

## 建议目录

建议将图片文件放在：

`docs/docs/assets/`

建议文件命名：

- `01-object-map.png`
- `02-entity-detail.png`
- `03-topology.png`
- `04a-trace-evidence.png`
- `04b-log-evidence.png`
- `04c-metric-evidence.png`
- `05-diagnosis.png`
- `06-impact-analysis.png`
- `07-investigation-report.png`
- `08-investigation-timeline.png`

## 推荐最小集合

如果希望人工工作量最小，优先准备以下 8 到 10 张图：

- 对象地图
- 实体探索概览
- 拓扑浏览
- 调用链证据视图
- 日志证据视图
- 指标证据视图
- 结构化诊断结果页
- 影响面分析页
- 调查报告页
- 调查时间线页

## 标注模板

每张图建议使用统一模板，避免外协把参考图误当成最终需求。

```md
## X. 页面名称参考

![页面名称参考](assets/example.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解该页面应该承载的核心任务
对应 MModel 能力：Entity Management / Topology / Evidence / Diagnosis / Report
建议保留：信息分组、关键入口、调查主路径
不建议照搬：品牌元素、平台绑定逻辑、阿里云特有字段、非通用交互
备注：如果 MModel 后续要支持多平台嵌入，该页面需要保持独立产品边界
```

## 1. 对象地图参考

![对象地图参考](assets/01-object-map.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解对象地图如何作为调查入口组织对象类型、对象分组和问题聚焦路径
对应 MModel 能力：Web UI / Entity Management / Topology
建议保留：对象入口层级、对象分类方式、从概览进入调查的路径
不建议照搬：品牌样式、平台导航、与特定平台耦合的菜单结构
备注：MModel 中该页面需要同时支持独立访问和平台嵌入

## 2. 实体探索概览参考

![实体探索概览参考](assets/02-entity-detail.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解实体探索概览页如何组织对象身份、状态、属性和核心调查入口
对应 MModel 能力：Entity Management / Health / Evidence
建议保留：对象摘要区、标签属性区、健康摘要区、进入拓扑与证据的入口
不建议照搬：阿里云特有字段命名、平台特有状态枚举
备注：MModel 中该页面更适合作为“实体探索-概览”主视图，而不是承载所有子页面的超级详情页

## 3. 拓扑浏览参考

![拓扑浏览参考](assets/03-topology.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解如何从一个对象出发查看上下游依赖和影响路径
对应 MModel 能力：Topology / Relation / Historical Runtime
建议保留：中心对象视角、上下游方向表达、节点关系浏览方式
不建议照搬：平台专用拓扑语义、宿主系统特有交互控件
备注：MModel 需要支持当前态与历史态拓扑切换

## 4. 证据页子视图参考

MModel 的证据能力建议设计为“一个统一证据页入口 + 多个证据子视图”。

在截图参考上，不强制要求提供一张完整的证据聚合页面，而是允许分别提供调用链、日志和指标三个子视图截图。

### 4a. 调用链证据视图参考

![调用链证据视图参考](assets/04a-trace-evidence.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解对象证据页中的调用链分析子视图如何组织 Trace、Span、接口维度和链路异常线索
对应 MModel 能力：Evidence / Trace / Query API
建议保留：对象上下文保持、时间范围联动、链路异常切入方式
不建议照搬：底层平台特有的查询语法、供应商专用术语、与宿主平台强耦合的操作入口
备注：该截图代表统一证据页中的“调用链”子视图，而不是独立一级页面

### 4b. 日志证据视图参考

![日志证据视图参考](assets/04b-log-evidence.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解对象证据页中的日志探索子视图如何展示与对象相关的日志片段、异常日志和筛选条件
对应 MModel 能力：Evidence / Logs / Query API
建议保留：对象相关日志聚合方式、时间范围联动、异常日志定位入口
不建议照搬：底层索引名、平台专有字段名、与日志平台绑定过深的操作方式
备注：该截图代表统一证据页中的“日志”子视图，而不是独立一级页面

### 4c. 指标证据视图参考

![指标证据视图参考](assets/04c-metric-evidence.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解对象证据页中的指标探索子视图如何展示对象核心指标、异常波动和时间趋势
对应 MModel 能力：Evidence / Metrics / Query API
建议保留：对象指标摘要、时间趋势呈现、异常波动识别方式
不建议照搬：平台特定图表组件、指标体系命名和与底层监控系统绑定的查询操作
备注：该截图代表统一证据页中的“指标”子视图，而不是独立一级页面

## 5. 结构化诊断结果参考

![结构化诊断结果参考](assets/05-diagnosis.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解结构化诊断页如何呈现上下文摘要、可疑根因、证据摘要和建议动作
对应 MModel 能力：Diagnosis API / Web UI
建议保留：诊断结论结构、证据引用方式、调查建议输出格式
不建议照搬：模型品牌、供应商表述、特定产品能力命名
备注：MModel 侧重点应是结构化调查结果页，而不是强聊天感的 Copilot 主界面

## 6. 影响面分析参考

![影响面分析参考](assets/06-impact-analysis.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解如何展示故障传播影响面与关联对象范围
对应 MModel 能力：Topology / Relation / Diagnosis
建议保留：影响对象列表、传播路径摘要、优先级呈现
不建议照搬：特定业务域术语、宿主平台专用操作入口
备注：该页面用于支撑故障研判与处置优先级判断

## 7. 调查报告参考

![调查报告参考](assets/07-investigation-report.png)

来源：阿里云 UModel 截屏
参考目的：帮助理解调查结果如何沉淀为结构化报告
对应 MModel 能力：Diagnosis / Report
建议保留：事件摘要、根因结论、证据清单、影响范围、后续建议
不建议照搬：组织内固定审批流、特定平台输出样式
备注：MModel 报告应支持人工补充与 Agent 自动生成

## 8. 调查时间线参考

![调查时间线参考](assets/08-investigation-timeline.png)

来源：AWS DevOps Agent 或阿里云 UModel 截屏
参考目的：帮助理解如何以对象为中心统一展示相关 Metrics、Logs、Traces、Events、Topology Changes 和 Diagnosis Steps
对应 MModel 能力：Investigation Timeline / Evidence / Topology / Diagnosis
建议保留：时间轴组织方式、关键时刻高亮、事件与拓扑或证据的联动关系
不建议照搬：特定产品的品牌样式、供应商术语、与某一助手强绑定的页面框架
备注：该页面是新规划中的核心能力，建议优先补图
