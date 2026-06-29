# MModel SDK 说明

## 目标

SDK 为应用开发者、平台集成方和自动化工具提供稳定的编程入口，使其通过统一对象模型访问 MModel，而不是直接耦合底层 REST 细节。

## SDK 覆盖能力

- Entity 查询与详情读取
- Relation 与 Topology 读取
- Evidence 读取
- Investigation Timeline 读取
- Diagnosis Context 获取
- 平台集成辅助调用

## SDK 设计原则

- 建议与 REST API 保持能力一致。
- 建议优先面向对象模型，而不是原始 HTTP 封装。
- 建议为 Agent 和自动化任务提供低心智负担的调用路径。
- 建议对不同语言 SDK 保持一致命名和一致语义。

## 建议语言范围

- Go SDK
- Python SDK
- Java SDK

## 交付要求

- 提供统一命名约定。
- 提供典型查询与诊断调用示例。
- 提供版本兼容策略。
- 保证 SDK 行为与 REST / MCP 契约一致。
