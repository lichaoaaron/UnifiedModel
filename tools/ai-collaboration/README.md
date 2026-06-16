# AI Collaboration Toolchain

This directory stores development-time prompts, checklists, and skill contracts. Runtime code must not depend on these files.

Suggested skill ownership:

| Skill | Scope |
|---|---|
| `mmodel-architecture-guard` | Review module boundaries and forbidden APIs |
| `graphstore-provider-dev` | Implement GraphStore providers behind the storage port |
| `cms2-entity-relation-compat` | Keep EntityStore payloads compatible with CMS 2.0 |
| `spl-query-dev` | Maintain unified SPL parsing, planning, execution, and explain |
| `mcp-agentgateway-dev` | Maintain MCP resources/tools without leaking data-plane internals |
| `openapi-sdk-sync` | Keep OpenAPI, CLI, SDK, and server routes aligned |
| `release-readiness-check` | Validate quickstart, docs, images, licenses, and notices |

AI-generated changes should always name the target module, public contracts touched, forbidden dependencies checked, and tests run.
