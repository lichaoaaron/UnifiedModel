# MModel Java SDK 测试指南

## 概述

这份文档说明了如何运行 MModel Java SDK 的测试用例，以验证生成的 Java 代码的功能正确性。

## 测试结构

测试代码位于 `src/test/java/com/mmodel/` 目录下，包含以下测试类：

### 1. 基础测试类

- **BaseTypesTest**: 测试基础类型（SemanticString、LinkEndpoint）的功能
- **MModelTest**: 测试主包 MModel 类的功能，包括 JSON 解析和工具函数
- **SchemaTest**: 测试所有 schema 类的基本功能和接口实现
- **SharedTypesTest**: 测试 shared 包中的共享类型

### 2. 集成测试

- **JsonParsingIntegrationTest**: 测试完整的 JSON 解析流程和复杂场景

### 3. 性能测试

- **PerformanceTest**: 测试大量数据解析和类型转换的性能

### 4. 测试套件

- **AllTestSuite**: 组织所有测试类的测试套件

## 运行测试

### 前提条件

确保已安装：
- Java 8 或更高版本
- Maven 3.6 或更高版本

### 运行所有测试

```bash
# 在项目根目录下执行
cd generated/java
mvn test
```

### 运行特定测试类

```bash
# 运行基础类型测试
mvn test -Dtest=BaseTypesTest

# 运行 JSON 解析集成测试
mvn test -Dtest=JsonParsingIntegrationTest

# 运行性能测试
mvn test -Dtest=PerformanceTest
```

### 运行测试套件

```bash
mvn test -Dtest=AllTestSuite
```

## 测试内容说明

### 基础功能测试

1. **类型创建和字段设置**
   - 验证所有生成的类可以正常创建实例
   - 验证 getter/setter 方法正常工作
   - 验证接口实现正确

2. **接口继承关系**
   - 验证 MModelObject、MModelCoreObject、MModelLinkObject 接口实现
   - 验证 getKind() 方法返回正确的类型标识
   - 验证 Link 类型对象实现了 MModelLinkObject 接口

3. **JSON 解析功能**
   - 验证从 JSON 字符串解析为具体类型
   - 验证自动类型检测和解析
   - 验证版本兼容性（v0.x.x 自动映射到 v1.0.0）
   - 验证错误处理（缺少必需字段、未知类型等）

### 高级功能测试

4. **复杂 JSON 结构解析**
   - 验证嵌套对象解析
   - 验证数组字段解析
   - 验证多语言 SemanticString 解析
   - 验证 Map 类型字段解析

5. **工具函数**
   - 验证 MModel.isCoreObject() 和 MModel.isLinkObject()
   - 验证 MModel.getObjectMetadata() 和 MModel.getObjectSchema()
   - 验证 MModel.getLinkEndpoints() 函数

### 性能测试

6. **大量数据处理**
   - 测试解析 1000+ JSON 对象的性能
   - 测试类型检查的性能
   - 测试对象创建的性能
   - 测试内存使用情况

## 测试数据

测试使用的示例数据位于 `src/test/resources/test-data/` 目录：

- `sample-metric-set.json`: 完整的 MetricSet JSON 示例
- `sample-data-link.json`: 完整的 DataLink JSON 示例

这些文件包含了复杂的嵌套结构，用于验证 JSON 解析的完整性。

## 预期测试结果

运行测试后，应该看到类似以下的输出：

```
[INFO] Tests run: 45, Failures: 0, Errors: 0, Skipped: 0
```

### 性能基准

性能测试的预期基准：
- JSON 解析：平均每个对象 < 10ms
- 类型检查：平均每次检查 < 0.1ms
- 对象创建：平均每个对象 < 0.2ms
- 内存使用：10000 个对象 < 100MB

## 故障排除

### 常见问题

1. **编译错误**
   ```
   解决方案：确保 Java 8+ 和 Maven 正确安装，运行 mvn clean compile
   ```

2. **依赖缺失**
   ```
   解决方案：运行 mvn dependency:resolve 下载依赖
   ```

3. **测试失败**
   ```
   解决方案：检查具体的失败信息，可能是：
   - JSON 解析库版本不兼容
   - 生成的代码有问题
   - 测试环境配置问题
   ```

### 调试测试

如果需要调试特定测试，可以：

1. 在测试类中添加 `System.out.println()` 输出调试信息
2. 使用 IDE 的调试器单步执行测试
3. 查看详细的测试报告：`target/surefire-reports/`

## 验证清单

运行测试后，验证以下功能正常：

- [ ] 所有 schema 类可以正常创建和使用
- [ ] JSON 自动解析功能正常
- [ ] 类型判断函数正常工作
- [ ] 继承关系正确实现
- [ ] SemanticString 多语言支持正常
- [ ] LinkEndpoint 类功能正常
- [ ] 工具函数返回正确结果
- [ ] 性能满足预期基准
- [ ] 内存使用在合理范围内

## 扩展测试

如果需要添加更多测试：

1. 在对应的测试类中添加新的 `@Test` 方法
2. 创建新的测试数据文件
3. 验证新功能的正确性
4. 更新这份文档

通过这些测试，可以确保 MModel Java SDK V2 生成的代码完全符合预期，所有特性都能正常工作。