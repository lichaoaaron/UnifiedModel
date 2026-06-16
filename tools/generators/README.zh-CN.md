# 生成器

English version: [README.md](README.md)

本目录包含 MModel schema 相关代码生成器。生成器会根据 schema 生成 SDK、类型定义或文档资产。

## 常见工作流

重新生成 schema 和 SDK 资产：

```bash
make expand
```

验证生成结果：

```bash
make verify
```

生成 schema HTML 文档：

```bash
make doc
```

## 维护原则

- 生成器改动必须可重复执行。
- schema、生成器、生成结果、测试和文档要在同一个 PR 中保持一致。
- 不要手工修改生成文件来绕过生成器问题。
- 公共 SDK API 变化时更新 docs 和 examples。
