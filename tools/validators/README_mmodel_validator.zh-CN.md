# MModel Validator

English version: [README_mmodel_validator.md](README_mmodel_validator.md)

MModel Validator 用于校验 MModel YAML/JSON 配置是否符合 schema 规范。

## 典型用途

- 校验 `examples/` 下的模型包。
- 在提交前检查新增或修改的 MModel elements。
- 发现字段类型、必填字段、枚举值、引用关系等问题。

## 常用命令

从仓库根目录执行：

```bash
make example-validate
```

相关验证：

```bash
make expand
make verify
```

## 维护规则

- Validator 行为变化时更新示例、测试和文档。
- 错误信息应尽量包含文件、字段和原因。
- 不要把校验规则写死到单个 example；应回到 schema 或共享 validator 逻辑。
