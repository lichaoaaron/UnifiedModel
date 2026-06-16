# MModel Python SDK

English version: [README.md](README.md)

本目录包含 MModel schemas 的生成 Python SDK。它用于在 Python 中构造、解析和校验 MModel schema model 对象。

## 使用场景

- 在 Python 工具中构造 MModel elements。
- 读取或生成 YAML/JSON model definitions。
- 与 schema-generated 类型保持一致。

## 常用工作流

从仓库根目录重新生成 SDK：

```bash
make expand
```

验证 Python SDK：

```bash
make verify-python
```

运行 Python SDK 测试：

```bash
python3 sdk/python/test/run_python_tests.py
```

## 维护规则

- SDK 由 schema 生成，不要手工修改生成文件。
- schema 变化时同步更新生成 SDK、测试和文档。
- 公共 SDK 类型不应依赖服务端 internal packages。
