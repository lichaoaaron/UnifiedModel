# MModel Product Docs

本目录用于维护 MModel 的产品定位、需求、产品架构、接口边界、页面规划和阶段路线图。

这组文档面向产品、研发、设计、外协团队和集成团队，描述的是产品应该具备什么能力、如何分层、如何分阶段交付，不替代 `docs/zh/` 与 `docs/en/` 中面向学习、使用和实现细节的说明。

## 文档索引

- [vision.md](vision.md) - 为什么做 MModel，以及产品边界。
- [prd.md](prd.md) - 产品需求文档，定义核心能力、阶段交付、平台适配与用户旅程。
- [architecture.md](architecture.md) - 产品架构分层与平台适配架构。
- [api.md](api.md) - Query API、Diagnosis API、REST、SDK、MCP 的对外边界。
- [sdk.md](sdk.md) - SDK 的目标、对象模型与调用方式。
- [ui.md](ui.md) - Web UI 的页面结构与关键交互。
- [reference-screenshots.md](reference-screenshots.md) - 参考截屏附录，用于辅助外协理解目标能力与交互方向。
- [roadmap.md](roadmap.md) - 阶段目标与里程碑。
- [CONTRIBUTING.md](CONTRIBUTING.md) - 外协与跨团队协作约束。

## 文档使用原则

- 所有核心业务能力优先定义在 MModel Core 中。
- 任何 Dashboard、监控平台、运维平台都只作为集成入口，不承载 MModel 的核心业务逻辑。
- 平台集成只负责登录、导航、上下文同步和原始数据跳转。
- 产品文档更新时，优先维护 `prd.md`、`architecture.md` 和 `api.md` 的一致性。
