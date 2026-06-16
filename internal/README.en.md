# internal/

中文版本：[README.md](README.md)

Private application and infrastructure modules. These packages are not public API.

| Directory | Layer | Module category |
|---|---|---|
| `bootstrap/` | Bootstrap Layer | Server wiring, providers, adapters, routes, UI serving. |
| `workspace/` | Application Layer | Workspace control plane. |
| `mmodel/` | Application Layer | MModel data plane. |
| `entitystore/` | Application Layer | Entity and relation write plane. |
| `query/` | Application Layer | Query plane. |
| `agentgateway/` | Application + Adapter Layer | Agent and MCP-facing adapter. |
| `graphstore/` | Domain/Contract + Infrastructure Layer | Storage abstraction and providers. |

Architecture reference: [docs/en/architecture/overview.md](../docs/en/architecture/overview.md).
