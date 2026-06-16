# Schema 工具说明

English version: [README_schema_tools.md](README_schema_tools.md)

本文档对应 MModel schema 工具链，包括 schema 展开、代码生成、文档生成和校验流程。

## 工具链职责

- 读取 `schemas/` 下的源 schema。
- 展开 `extends` 和共享 include。
- 生成 Go、Python、Java 等语言的 SDK 资产。
- 生成 HTML schema 参考文档。
- 为 example validation 和 SDK verification 提供一致输入。

## 推荐命令

```bash
make expand
make doc
make verify
make example-validate
```

## 维护规则

- 新增 schema kind 时更新 `schemas/manifest.yaml`。
- 变更共享 include 时检查所有引用方。
- 生成器输出变化时检查对应语言 SDK 测试。
- 文档应同时更新英文和中文版本。
