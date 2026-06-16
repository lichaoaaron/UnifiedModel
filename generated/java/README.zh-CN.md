# MModel Java SDK

English version: [README.md](README.md)

本目录包含由 MModel schema 生成的 Java SDK 资产。

## 用途

- 在 Java 项目中构造和处理 MModel schema model 对象。
- 验证 schema 生成器对 Java 类型映射的输出。
- 作为多语言 SDK 兼容性检查的一部分。

## 生成与验证

从仓库根目录执行：

```bash
make expand
make verify-java
```

## 维护规则

- 本目录内容由 schema/generator 生成，不应手工修改生成文件。
- schema 或生成器变化时，同步更新测试和文档。
- Java SDK 当前仍保留在 `generated/java/`，Go 和 Python SDK 位于 `sdk/` 下。
