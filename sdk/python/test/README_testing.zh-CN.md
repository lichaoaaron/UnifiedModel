# Python SDK 测试

English version: [README_testing.md](README_testing.md)

本目录包含 MModel Python SDK 的测试说明和测试入口。

## 运行

从仓库根目录执行：

```bash
python3 sdk/python/test/run_python_tests.py
```

或通过 Makefile：

```bash
make verify-python
```

## 维护规则

- schema 或生成器变化后运行 Python SDK 测试。
- 测试应覆盖生成类型的构造、序列化、反序列化和基本校验。
- 不要在测试中依赖服务端 internal packages。
