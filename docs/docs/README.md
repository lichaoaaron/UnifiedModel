# MModel 外协文档总览

本目录用于沉淀面向外协团队的产品需求、页面范围、接口边界、平台适配原则和协作约束。

这套文档回答的核心问题不是“代码如何实现”，而是：

- MModel 是什么产品
- 当前版本中，MModel 与宿主平台、Copilot 的建议边界是什么
- 第一阶段做什么，长期如何演进
- 外协团队应按什么范围、什么原则推进

## 阅读顺序

建议按以下顺序阅读：

1. [vision.md](vision.md)：产品定位、目标和边界
2. [prd.md](prd.md)：产品需求与阶段交付要求
3. [ui.md](ui.md)：页面结构与关键交互
4. [architecture.md](architecture.md)：核心分层与平台适配架构
5. [api.md](api.md)：对外接口边界
6. [sdk.md](sdk.md)：SDK 与 Agent 接入原则
7. [reference-screenshots.md](reference-screenshots.md)：参考截图说明
8. [roadmap.md](roadmap.md)：阶段目标与演进方向
9. [CONTRIBUTING.md](CONTRIBUTING.md)：外协协作约束

## 文档使用原则

- 当前文档默认将核心业务能力优先定义在 MModel Core 中，供方案讨论与外协评估时参考。
- 当前文档默认将宿主平台理解为登录、导航、上下文同步和原始数据跳转入口，这一边界后续仍可结合团队讨论调整。
- 参考截图只用于帮助理解能力结构和调查路径，不作为最终界面复刻要求。
- 若不同文档之间存在冲突，以 [prd.md](prd.md) 作为需求基准，以 [architecture.md](architecture.md) 作为边界基准。
