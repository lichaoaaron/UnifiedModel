# MModel 配置文件验证器

这是一个通用的配置文件验证脚本，基于expanded_schemas中的schema定义来验证配置YAML文件的合法性。

## 🎯 功能特性

1. **自动schema选择**: 根据配置文件中的`kind`字段自动选择对应的schema
2. **完整结构验证**: 验证配置文件的结构和数据类型
3. **必填字段检查**: 检查schema中定义的必填字段
4. **约束条件验证**: 验证字段值的约束条件（枚举、正则、长度等）
5. **未定义字段检测**: 检测配置中使用但未在schema中定义的字段
6. **详细报告**: 生成包含错误和警告的详细验证报告

## 📁 文件说明

- `mmodel_validator.py`: 完整版验证器（需要PyYAML）

## 🚀 使用方法

### 方法1: 使用完整版验证器

```bash
# 安装依赖
pip install PyYAML

# 验证配置文件
python ./scripts/validators/mmodel_validator.py examples/dataset/metricset/sls.front.metric.yaml
```


## 📊 验证逻辑

### 1. 配置文件结构检查
- 验证根节点是否为对象类型
- 检查必填的`kind`字段是否存在

### 2. Schema匹配
- 根据`kind`字段值查找对应的schema定义
- 使用schema的第一个版本进行验证

### 3. 字段验证
- **类型验证**: 检查字段值是否符合预期的数据类型
- **约束验证**: 验证枚举值、正则表达式、长度限制等
- **必填字段**: 确保所有必填字段都存在
- **未定义字段**: 警告配置中存在但schema中未定义的字段

### 4. 特殊处理
- `kind`字段被自动排除，因为它是用于确定schema的元字段
- `constraint: null`情况的安全处理
- 支持`semantic_string`类型（字符串或多语言对象）
- 支持`enum`类型验证

## 📋 验证报告示例

### 成功案例
```
🎉 配置文件验证通过！
```

### 包含警告的案例
```
## ⚠️ 警告 (2 个)
1. 路径 'spec.metrics[0].extra_field': 字段未在schema中定义
2. 路径 'metadata.unknown_field': 字段未在schema中定义
```

### 包含错误的案例
```
## 🚨 错误 (1 个)
1. 路径 'spec.metrics[0].name': 缺少必填字段

## ⚠️ 警告 (1 个)
1. 路径 'spec.unknown_section': 字段未在schema中定义
```

## 🔧 支持的数据类型

- `string`: 字符串类型
- `number`: 数字类型（整数或浮点数）
- `integer`: 整数类型
- `boolean`/`bool`: 布尔类型
- `array`: 数组类型
- `object`: 对象类型
- `enum`: 枚举类型
- `semantic_string`: 语义字符串（支持多语言）
- `any`: 任意类型

## 🔍 约束条件支持

- **枚举约束**: `enum.values` - 限制字段值在指定范围内
- **正则约束**: `pattern` - 字符串匹配正则表达式
- **长度约束**: `min_len`/`max_len` - 字符串或数组长度限制
- **数值约束**: `min_value`/`max_value` - 数值范围限制
- **必填约束**: `required` - 标记必填字段
- **默认值**: `default_value` - 字段默认值


## 📈 扩展建议

1. **批量验证**: 支持验证整个目录下的所有配置文件
2. **自定义规则**: 允许添加业务特定的验证规则
3. **JSON输出**: 支持机器可读的JSON格式报告
4. **性能优化**: 对大型配置文件的验证性能优化
5. **增量验证**: 只验证发生变化的部分
