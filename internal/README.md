# internal/

Application Layer + Infrastructure Layer — 私有模块，不对外暴露。

| 目录 | 层级 | 模块类别 | Spec |
|---|---|---|---|
| `bootstrap/` | Bootstrap Layer | — | spec 01 |
| `workspace/` | Application Layer | Control Plane | spec 02 |
| `mmodel/` | Application Layer | Data Plane | spec 04 |
| `entitystore/` | Application Layer | Data Plane | spec 05 |
| `query/` | Application Layer | Query Plane | spec 06 |
| `agentgateway/` | Application + Adapter Layer | Northbound Adapter | spec 07 |
| `graphstore/` | Domain/Contract + Infrastructure Layer | Storage Abstraction | spec 03 |
