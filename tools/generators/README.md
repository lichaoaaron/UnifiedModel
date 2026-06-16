# MModel Schema Go SDK Generator

这个生成器基于 `base.yaml` 中定义的元数据规范，解析展开后的 schema 文件，生成相应的 Go SDK 代码。

## 功能特性

1. **基于元数据自动生成**：不依赖硬编码，直接基于 `base.yaml` 定义的元数据来解析 schema
2. **支持复杂数据结构**：
   - 自动生成内联结构体定义
   - 正确处理数组和 map 类型
   - 支持语义字符串（SemanticString）类型
3. **多格式支持**：生成的代码支持从 JSON 和 YAML 解析数据结构
4. **未识别字段处理**：类似 protobuf，将未识别的字段保存在 Extension 结构中
5. **健壮的代码生成**：
   - 自动处理未使用的 import
   - 注释中的中文标点符号自动转换
   - 注释长度限制在 128 字节以内

## 使用方法

### 1. 准备工作

首先需要运行 schema 展开器生成展开后的 schema 文件：

```bash
python scripts/generators/schema_expander.py
```

### 2. 运行生成器

```bash
python scripts/generators/schema_go_generator.py
```

生成的代码将保存在 `generated/go/mmodel` 目录中。

### 3. 使用生成的 SDK

```go
import (
    "encoding/json"
    "your-module/mmodel"
)

// 解析 JSON
var metricSet mmodel.MetricSetV100
err := json.Unmarshal(jsonData, &metricSet)

// 访问数据
fmt.Println(metricSet.Metadata.Name)

// 访问未识别的字段
for key, value := range metricSet.Extension.Fields {
    fmt.Printf("未识别字段 %s: %v\n", key, value)
}
```

## 生成的代码结构

- `common_types.go` - 通用类型定义（SemanticString, Extension）
- `mmodel.go` - 主包文件和辅助函数
- `{schema_name}.go` - 每个 schema 对应的结构体和解析方法

## 类型映射

| Schema 类型 | Go 类型 |
|------------|---------|
| string | string |
| number | float64 |
| integer | int64 |
| boolean | bool |
| object | 内联结构体或 map[string]interface{} |
| array | []T |
| map | map[string]T |
| semantic_string | *SemanticString |
| any | interface{} |
| time | time.Time |

## 注意事项

1. 生成的代码需要依赖 `gopkg.in/yaml.v3`，使用前请安装：
   ```bash
   go get gopkg.in/yaml.v3
   ```

2. 未识别的字段会被保存在 `Extension.Fields` 中，这允许向前兼容新增的字段

3. 所有可选字段都带有 `omitempty` 标签，在序列化时会忽略零值

4. 注释会自动处理：
   - 中文标点符号转换为英文标点
   - 多行注释合并为单行
   - 注释长度限制在 128 字节

## 示例

完整的使用示例请参考 `generated/go/example.go`

## 后续优化计划

- [ ] 支持字段值范围校验（min/max, pattern 等）
- [ ] 支持 oneOf 约束的更好处理
- [ ] 支持生成字段验证方法
- [ ] 支持自定义类型映射配置
- [ ] 支持嵌套对象的未识别字段处理 