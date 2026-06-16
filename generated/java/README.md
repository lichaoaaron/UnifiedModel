# MModel Java SDK V2

这是由 `schema_java_generator_v2.py` 自动生成的 MModel Java SDK。

## 特性

- ✅ 使用 Java 的继承特性实现继承关系
- ✅ 生成简洁、高复用的代码
- ✅ 保留原始 schema 的结构关系
- ✅ 支持动态类型创建和解析
- ✅ 提供通用接口 `MModelCoreObject` 和 `MModelLinkObject`
- ✅ 支持 JSON 自动解析（使用 FastJSON）
- ✅ 类型安全的 Java 类型定义

## 构建

```bash
mvn clean compile
```

## 使用示例

### 基础用法

```java
import com.mmodel.*;

// 判断对象类型
if (MModel.isCoreObject(obj)) {
    Object metadata = MModel.getObjectMetadata(obj);
    Object schema = MModel.getObjectSchema(obj);
    String kind = ((MModelObject) obj).getKind(); // 获取对象类型
}

// 处理Link对象
if (MModel.isLinkObject(obj)) {
    LinkEndpoint[] endpoints = MModel.getLinkEndpoints(obj);
    LinkEndpoint src = endpoints[0];
    LinkEndpoint dest = endpoints[1];
    System.out.printf("Link from %s to %s%n", src.getName(), dest.getName());
}
```

### 自动解析

```java
import com.mmodel.MModel;

// 自动解析JSON数据
String jsonData = "{\"kind\":\"metric_set\",\"schema\":{\"version\":\"v1.0.0\"}}";
MModelCoreObject obj = MModel.parseMModelJson(jsonData);
System.out.printf("Parsed object kind: %s%n", obj.getKind());
```

### 手动解析

```java
import com.mmodel.MModel;
import com.mmodel.schema.MetricSetV100; // 假设有这个类型

// 解析为特定类型
String json = "...";
MetricSetV100 metricSet = MModel.parseJson(json, MetricSetV100.class);
System.out.printf("Metric set name: %s%n", metricSet.getMetadata());
```

## 接口说明

### 基础接口

- `MModelObject`: 所有 MModel 对象的基础接口
  - `getKind() -> String`: 获取对象的类型标识
  - `validate() -> Exception`: 验证对象是否符合 schema 定义

- `MModelCoreObject`: 继承自 `MModelObject`，core 目录下所有对象的接口
  - `getSchema() -> Object`: 获取对象的 Schema 信息
  - `getMetadata() -> Object`: 获取对象的 Metadata 信息

- `MModelLinkObject`: 继承自 `MModelCoreObject`，所有 link 类型对象的接口
  - `getSrc() -> LinkEndpoint`: 获取源端点信息
  - `getDest() -> LinkEndpoint`: 获取目标端点信息

### 工具函数

- `MModel.isCoreObject(Object obj) -> boolean`: 判断对象是否实现了 `MModelCoreObject` 接口
- `MModel.isLinkObject(Object obj) -> boolean`: 判断对象是否实现了 `MModelLinkObject` 接口
- `MModel.getObjectMetadata(Object obj) -> Object`: 获取任意 MModel 对象的 Metadata
- `MModel.getObjectSchema(Object obj) -> Object`: 获取任意 MModel 对象的 Schema
- `MModel.getLinkEndpoints(Object obj) -> LinkEndpoint[]`: 获取 Link 对象的源和目标端点

### 解析函数

- `MModel.parseJson(String jsonStr, Class<T> clazz) -> T`: 从 JSON 字符串解析为指定类型
- `MModel.parseMModelJson(String jsonStr) -> MModelCoreObject`: 自动检测类型并解析 JSON

## 版本兼容性

- 支持 v0.x.x 版本自动映射到 v1.0.0
- v1 主版本内向后兼容
- 遵循语义化版本规范

## 开发

此 SDK 由 `schema_java_generator_v2.py` 自动生成，请勿手动修改生成的代码。

如需修改，请更新 schemas 目录中的 YAML 文件，然后重新运行生成器：

```bash
python scripts/generators/schema_java_generator_v2.py
```
