# MModel SDK

## 目标

SDK 为应用开发者、平台集成方和自动化工具提供稳定的编程入口，使其通过统一对象模型访问 MModel，而不是直接耦合底层 REST 细节。

## SDK 应覆盖的能力

- Entity 查询与详情读取
- Relation 与 Topology 读取
- Evidence 读取
- Diagnosis 上下文获取
- 历史时间范围查询
- 平台集成辅助调用

## SDK 设计原则

- 与 REST API 保持能力一致。
- 优先面向对象模型，而不是原始 HTTP 封装。
- 对 Agent 和自动化任务提供低心智负担调用路径。

## 后续补充

后续版本需要补充：

- Go / Python / Java SDK 范围定义
- 统一命名约定
- 典型调用示例
- 版本兼容策略
