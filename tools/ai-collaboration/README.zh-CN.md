# AI 协作工具链

English version: [README.md](README.md)

本目录保存开发期 prompts、checklists 和 skill contracts。运行时代码不得依赖这些文件。

建议 skill ownership：

| Skill | 范围 |
|---|---|
| `mmodel-architecture-guard` | Review module boundaries and forbidden APIs |
| `graphstore-provider-dev` | Implement GraphStore providers behind the storage port |
| `cms2-entity-relation-compat` | Keep EntityStore payloads compatible with CMS 2.0 |
| `spl-query-dev` | Maintain unified SPL parsing, planning, execution, and explain |
| `mcp-agentgateway-dev` | Maintain MCP resources/tools without leaking data-plane internals |
| `openapi-sdk-sync` | Keep OpenAPI, CLI, SDK, and server routes aligned |
| `release-readiness-check` | Validate quickstart, docs, images, licenses, and notices |

AI 生成的变更应始终说明目标模块、触碰的公共契约、检查过的禁用依赖和运行过的测试。
