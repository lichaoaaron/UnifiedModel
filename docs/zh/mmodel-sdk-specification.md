# MModel SDK 规范

English: [MModel SDK Specification](../en/mmodel-sdk-specification.md)

生成式和手写 MModel SDK 的预期行为，覆盖 Go、Python、Java 以及未来语言绑定。

## 版本

- 规范版本：`1.0.0`
- 范围：模型对象类型、解析、校验、类型注册、序列化和兼容性行为
- 事实来源：`schemas/` 下的 schema 文件、`pkg/model` 下的公共模型契约，以及 `pkg/contract` 下的公共服务契约

## 核心概念

### Schema Envelope

每个 MModel 对象都遵循通用 envelope：

- `kind` 标识模型对象类型。
- `schema` 携带 schema 版本元数据。
- `metadata` 携带 identity、domain、name、labels 和 display fields。
- `spec` 携带类型专属配置。

即使目标语言使用不同命名习惯，SDK 也应一致暴露这套 envelope。

### 继承与组合

Schema 通过 `extends` 共享通用结构。SDK 应将继承映射到目标语言的惯用机制：

- Go：embedding 或生成的组合 helper。
- Python：适用时使用 classes、dataclasses 或 Pydantic-style composition。
- Java：interfaces、abstract base classes 或生成继承。

生成 API 应保持 schema 关系清晰，同时不要求调用者理解 generator 内部实现。

### 版本化

SDK 应在解析后的对象中保留 schema version，并支持 version-aware parsing：

- Version key 应稳定且确定，例如 `{kind}:{version}`。
- 预稳定 schema version 在结构兼容时映射到第一个稳定 SDK type。
- 新 SDK version 应继续读取较旧的兼容对象。

## 类型映射

| Schema type | Go | Python | Java |
|---|---|---|---|
| `string` | `string` | `str` | `String` |
| `number` | `float64` | `float` | `Double` |
| `integer` | `int64` | `int` | `Long` |
| `boolean` | `bool` | `bool` | `Boolean` |
| `object` | `map[string]any` 或 struct | `dict` 或 model class | `Map<String, Object>` 或 class |
| `array` | `[]T` | `list[T]` | `List<T>` |
| timestamp | `time.Time` 或 string wrapper | `datetime` 或 string wrapper | `Instant` 或 string wrapper |
| raw JSON | `json.RawMessage` | `dict` / `Any` | `JsonNode` 或等价类型 |

语言实现可选择更严格的目标类型，但必须保留 JSON/YAML round-trip 行为。

## 共享接口

### MModelObject

所有 MModel 对象都应暴露：

- `kind()` 或等价的 kind 访问方法。
- `validate()` 或等价校验入口。
- JSON 和 YAML 序列化。
- 当对象携带 `metadata` 与 `schema` 时，应提供对应访问能力。

### MModelCoreObject

核心模型对象应暴露：

- `schema` 元数据。
- `metadata` 元数据。
- 稳定 identity fields。
- 基于对象 schema 的校验。

### MModelLinkObject

Link 对象应暴露：

- source endpoint 访问能力。
- target endpoint 访问能力。
- 可选 filter 或 field mapping 访问能力。
- 校验 source 与 target endpoint metadata 在结构上完整。

## 解析与序列化

SDK 应提供：

- 将 JSON 解析为已知目标类型。
- 将 YAML 解析为已知目标类型。
- 检测 `kind` 与 `schema.version`，并实例化匹配的生成类型。
- 将对象序列化回 JSON 和 YAML，同时不丢失允许的 unknown fields。
- 解析错误应包含 path、可用时的 line/column，以及稳定的 error category。

自动 parser 应遵循以下流程：

1. 先解码足够内容以读取 `kind` 与 `schema.version`。
2. 构造 type key。
3. 查询 type registry。
4. 实例化目标类型。
5. 解码完整文档。
6. 校验对象。

## 类型注册表

每个 SDK 都应为生成类型和自定义类型提供 registry：

- 按 kind 和 version 注册 type factory。
- 通过 type key 创建实例。
- 列出已知类型以支持诊断。
- 检查某个 type key 是否受支持。

Registry 应可扩展，使下游用户无需 fork generator 就能添加领域专属 schema types。

## Helpers

SDK 应包含常见 runtime checks 的 helper functions：

- 判断某个值是否实现 core object interface。
- 判断某个值是否实现 link object interface。
- 从任意兼容 MModel object 中提取 metadata。
- 从任意兼容 MModel object 中提取 schema metadata。
- 从 link objects 中提取 source 与 target endpoints。

## 错误处理

SDK 应暴露带稳定类别的结构化错误：

| Error category | 含义 |
|---|---|
| validation error | 对象不满足 schema 或语义规则。 |
| parse error | JSON/YAML 解码失败。 |
| unknown type | 没有已注册类型匹配 kind/version pair。 |
| unsupported version | kind 已知，但 version 不受支持。 |
| missing field | 缺少必填字段。 |

错误应包含可获得的最佳 field path 和人类可读 message。

## 命名规则

- 生成类型名称应稳定，例如 `MetricSetV100`。
- Schema fields 使用 `snake_case`。
- SDK fields 与 methods 应遵循目标语言习惯。
- Serialization tags 必须保持 JSON/YAML field names 与 schema 兼容。
- Optional fields 应使用目标语言惯用的 optional 或 pointer 语义。
- Embedded 或 inline fields 应保留 schema shape。

## 实现要求

每个 SDK 实现必须支持：

1. 支持 schema kinds 的生成模型类型。
2. JSON 和 YAML 解析。
3. JSON 和 YAML 序列化。
4. 自动 kind/version detection。
5. Type registry lookup。
6. Core object validation。
7. Link endpoint validation。

推荐能力：

- 面向大文件的 streaming parse。
- 独立 schema validator。
- Type conversion helpers。
- 检查生成对象的 debug helpers。
- 在合适时使用 zero-copy 或 low-allocation parsing。

## 测试要求

每个 SDK 都应包含：

- 覆盖生成类型与继承/组合行为的 unit tests。
- 覆盖 JSON 和 YAML 输入的 parser tests。
- 覆盖 kind/version routing 的 auto-detection tests。
- 覆盖成功与失败场景的 validation tests。
- 覆盖较旧受支持 schema version 的 compatibility tests。
- 断言稳定类别和有效 path 的 error tests。
- 面向仓库 `examples/` 树的 example-file tests。

大型 schema bundles 和批量 example parsing 需要 performance tests。

## 文档要求

每个 SDK package 都应提供：

- 安装指南。
- 基础 parse/serialize 示例。
- Type registry 示例。
- Validation 示例。
- Error handling 示例。
- 兼容性与升级指南。

Go、Python 和 Java 文档应与本规范以及生成代码行为保持一致。

## 兼容性规则

- 新 SDK 应读取兼容的旧对象。
- 删除 public generated type 属于 breaking change。
- 重命名 public methods 属于 breaking change，除非保留 compatibility aliases。
- 增加 optional fields 是兼容变更。
- 增加 required fields 需要 schema version change。
- Public contract changes 必须在同一个 pull request 中更新 OpenAPI、CLI、SDK docs、tests 和 examples。

## Tooling 集成

SDK tooling 范围：

- Schema validation commands。
- Code generation commands。
- Type checking commands。
- IDE metadata，例如 schema completion 或 diagnostics。
- 面向生成代码校验的 build tasks。

仓库校验入口：

```bash
make verify
make verify-go
make verify-python
make verify-java
```
