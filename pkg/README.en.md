# pkg/

中文版本：[README.md](README.md)

Public domain and contract layer.

| Directory | Description |
|---|---|
| `model/` | Domain model types for workspace, MModel, entities, relations, and query. |
| `contract/` | Service interface contracts such as GraphStore and workspace management. |
| `errors/` | Shared error envelope and stable error codes. |

These packages are safe for public-facing service contracts. Server internals should remain under `internal/`.
