# 架构测试

English version: [README.md](README.md)

架构检查由 `tools/guards/architecture_guard.py` 实现，通过以下命令运行：

```bash
make guard
```

Guard 强制项目级约束：

- Workspace metadata APIs 不应扩展 runtime lifecycle operations。
- Domain read APIs 不应绕过 Query Service。
- MModelAssistant 不属于当前开源 runtime/API surface。
- 业务模块不得导入 GraphStore provider implementation packages。
