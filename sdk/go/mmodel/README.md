# MModel Go SDK V2

这是 MModel Schema 的 Go SDK V2 版本，相比 V1 版本有重大改进。

## 主要特性

### 1. 高复用的代码结构

V2 版本直接基于原始的 schema 定义生成代码，保留了 schema 之间的继承关系：

- **类型复用**：共享类型（如 `MetadataV1`、`SchemaV1`）只定义一次，被多个 schema 引用
- **Go 嵌入特性**：使用 Go 的结构体嵌入来实现继承关系
- **减少代码冗余**：相比 V1 版本，代码量大幅减少

### 2. 继承关系示例

#### 简单继承
```go
// metric_set 的 metadata 字段直接使用 MetadataV1 类型
type MetricSetV100 struct {
    Schema   *SchemaV1   `json:"schema" yaml:"schema"`
    Metadata *MetadataV1 `json:"metadata" yaml:"metadata"`
    Spec     map[string]interface{} `json:"spec" yaml:"spec"`
}
```

#### 嵌入继承
```go
// TraceSetV100Spec 嵌入了 TelemetryDataV1，同时添加了自己的字段
type TraceSetV100Spec struct {
    TelemetryDataV1 // 嵌入父类型
    // TraceSet 特有的字段
    TraceIdField      string `json:"trace_id_field" yaml:"trace_id_field"`
    SpanIdField       string `json:"span_id_field" yaml:"span_id_field"`
    ParentSpanIdField string `json:"parent_span_id_field,omitempty" yaml:"parent_span_id_field,omitempty"`
    Protocol          string `json:"protocol,omitempty" yaml:"protocol,omitempty"`
}
```

### 3. 使用示例

```go
// 创建 TraceSet 实例
traceSet := &mmodel.TraceSetV100{
    Schema: &mmodel.SchemaV1{
        Url:     "mmodel.aliyun.com",
        Version: "v1.0.0",
    },
    Metadata: &mmodel.MetadataV1{
        Name:        "app_traces",
        DisplayName: &mmodel.SemanticString{
            ZhCN: "应用追踪",
            EnUS: "Application Traces",
        },
        Domain: "apm",
    },
    Spec: &mmodel.TraceSetV100Spec{
        // 继承的字段可以直接使用
        TelemetryDataV1: mmodel.TelemetryDataV1{
            TimeField:    "timestamp",
            DisplayField: "span_name",
        },
        // TraceSet 特有的字段
        TraceIdField: "trace_id",
        SpanIdField:  "span_id",
        Protocol:     "opentelemetry",
    },
}
```

### 4. 文件结构

- `base_types.go` - 基础类型定义（如 SemanticString）
- `shared_types.go` - 共享的类型定义（如 MetadataV1、SchemaV1、LinkV1 等）
- `{schema_name}.go` - 每个 schema 的具体实现
- `mmodel.go` - 主包文件，包含解析函数和类型注册表

### 5. 动态类型创建

V2 版本支持通过类型名称动态创建实例：

```go
// 根据类型名称动态创建实例
obj, err := mmodel.ParseType("metric_set:v1.0.0", jsonData, "json")
```

## 相比 V1 的改进

1. **代码量减少 60%+**：通过复用共享类型，避免了大量重复代码
2. **更好的类型安全**：使用具体的类型而不是 `map[string]interface{}`
3. **保留原始继承关系**：代码结构与 schema 定义完全一致
4. **更易于维护**：修改共享类型只需要在一个地方修改
5. **支持 Go 的特性**：充分利用 Go 的嵌入特性实现优雅的继承

## 使用方法

1. 将生成的代码复制到您的 Go 项目中
2. 安装依赖：`go get gopkg.in/yaml.v3`
3. 导入包：`import "your-module/mmodel"`
4. 参考 `example_test.go` 中的示例代码 