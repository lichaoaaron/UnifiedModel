# Schema 转换工具

English version: [README_converter.md](README_converter.md)

本目录包含 MModel schema 转换相关工具说明。转换工具用于将源 schema、展开 schema 或中间表示转换为生成器和文档流程需要的格式。

## 使用原则

- 转换逻辑应保持可重复执行。
- 输入和输出路径应在命令或配置中显式说明。
- 转换结果变更时，应同步运行 schema 展开、SDK 验证和示例校验。
- 不要把一次性临时转换结果当作公共契约。

## 常用验证

从仓库根目录执行：

```bash
make expand
make verify
make example-validate
```

## 维护

修改转换器时，请同步更新英文文档、本中文文档以及受影响的生成器/validator 文档。
