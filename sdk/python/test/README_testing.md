# MModel Python SDK 测试指南

本目录包含了用于测试和验证生成的MModel Python SDK的脚本。

## 📋 测试脚本列表

### 0. `run_python_tests.py` - 自动化测试脚本 ⭐

这是一个一键运行的自动化测试脚本，会自动完成整个测试流程：

- 🔍 检查Python版本和依赖
- 🛠️ 自动生成Python SDK
- 🧪 运行完整测试套件
- 🎯 运行演示程序
- 📊 生成详细的测试报告

#### 使用方法

```bash
# 一键运行所有测试（推荐）
python scripts/run_python_tests.py
```

这是最简单的使用方式，适合快速验证整个系统是否正常工作。

### 1. `test_python_sdk.py` - 完整测试程序

这是一个功能完整的测试程序，类似于Go版本的CLI工具，可以：

- 📁 自动扫描整个examples目录
- 🔍 解析MModel文件（JSON/YAML）
- ✅ 验证生成的类型系统
- 🔄 转换输出格式
- 📊 显示详细的测试结果和统计信息

#### 使用方法

```bash
# 测试整个examples目录
python scripts/test_python_sdk.py

# 测试单个文件
python scripts/test_python_sdk.py -i examples/dataset/metricset/sls_front_metric.yaml

# 转换文件格式（YAML到JSON）
python scripts/test_python_sdk.py -i examples/dataset/metricset/sls_front_metric.yaml -o output.json -of json

# 转换文件格式（JSON到YAML）
python scripts/test_python_sdk.py -i input.json -o output.yaml -of yaml

# 查看帮助
python scripts/test_python_sdk.py --help
```

#### 命令行参数

- `-i, --input`: 输入文件路径（可选，默认测试整个examples目录）
- `-o, --output`: 输出文件路径（可选，默认输出到控制台）
- `-if, --input-format`: 输入格式 json/yaml（可选，默认自动检测）
- `-of, --output-format`: 输出格式 json/yaml（默认: json）
- `-p, --pretty`: 美化输出（默认: true）
- `--no-pretty`: 禁用美化输出

### 2. `demo_python_sdk.py` - 演示程序

这是一个简单的演示脚本，展示MModel Python SDK的核心功能：

- 🔤 SemanticString使用演示
- 🔗 LinkEndpoint使用演示
- 📄 YAML解析演示
- 📋 JSON解析演示
- 🔍 类型检测演示
- 📁 文件解析演示

#### 使用方法

```bash
# 运行所有演示
python scripts/demo_python_sdk.py
```

## 🚀 快速开始

### 方式一：一键自动化测试（推荐）⭐

最简单的方式是使用自动化测试脚本：

```bash
python scripts/run_python_tests.py
```

这个脚本会自动完成所有步骤：生成SDK、运行测试、生成报告。

### 方式二：手动步骤

如果你想手动控制每个步骤：

#### 步骤1：生成Python SDK

```bash
python scripts/generators/schema_python_generator_v2.py
```

#### 步骤2：安装依赖（如果需要）

```bash
pip install PyYAML
```

#### 步骤3：运行测试

```bash
# 运行完整测试
python scripts/test_python_sdk.py

# 运行演示程序
python scripts/demo_python_sdk.py
```

## 📊 测试输出示例

### 自动化测试输出

```
🚀 MModel Python SDK 自动化测试
============================================================
开始时间: 2024-01-15 14:30:00

🔍 检查Python版本...
✅ Python版本: 3.9.7 (default, ...)
🔍 检查依赖...
✅ yaml: 已安装
✅ pathlib: 已安装

🔄 生成Python SDK...
   命令: python scripts/generators/schema_python_generator_v2.py
✅ 生成Python SDK成功

🔄 运行完整测试...
   命令: python scripts/test_python_sdk.py
✅ 运行完整测试成功

🔄 运行演示程序...
   命令: python scripts/demo_python_sdk.py
✅ 运行演示程序成功

📊 生成测试报告...
✅ 测试报告已保存到: test_report.json

⏱️ 总耗时: 15.32秒

============================================================
📋 测试总结
============================================================
测试时间: 2024-01-15T14:30:15.123456
Python版本: 3.9.7
🎉 总体结果: 全部通过

详细结果:
  完整测试: ✅ 通过
  演示程序: ✅ 通过

📝 建议:
  - MModel Python SDK工作正常
  - 可以开始使用生成的SDK
  - 查看generated/python/mmodel/README.md了解更多用法
============================================================

🎊 自动化测试完成！所有检查都通过了。
```

### 完整测试输出

```
🚀 开始MModel Python SDK测试
============================================================
✅ 成功导入MModel Python SDK
📁 扫描examples目录: /path/to/examples
📊 找到 1 个文件，开始测试...

📄 测试文件: examples/dataset/metricset/sls_front_metric.yaml
  ✅ 解析成功
     格式: yaml
     类型: MetricSetV010
     Kind: metric_set
     🔹 MModelCoreObject: ✅
     🔹 Metadata: ✅ (name: sls_front.metricset)
     🔹 Schema: ✅ (version: v0.1.0)
     🔹 Validation: ✅

📊 测试总结
============================================================
总文件数:     1
成功解析:     1
解析失败:     0
JSON文件:     0
YAML文件:     1
成功率:       100.0%

🔍 发现的类型:
  - MetricSetV010

============================================================
🎉 所有测试通过！MModel Python SDK工作正常。
```

### 演示程序输出

```
🚀 MModel Python SDK 演示程序
============================================================
✅ 成功导入MModel Python SDK
SDK 版本: 2.0.0

🔤 SemanticString 演示
----------------------------------------
创建语义字符串: 这是一个测试
中文: 这是一个测试
英文: This is a test
从字符串创建: 通用描述
从字典创建: 中文描述

🔗 LinkEndpoint 演示
----------------------------------------
链接端点: infrastructure.service.user-service
过滤条件: status=active

📄 YAML 解析演示
----------------------------------------
✅ 解析成功
类型: MetricSetV100
Kind: metric_set
✅ 实现了MModelCoreObject接口
元数据名称: demo_metric
Schema版本: v1.0.0
✅ 对象验证通过

...

============================================================
🎉 演示完成！
```

## 🛠️ 故障排除

### 常见问题

1. **自动化测试失败**：
   ```
   ❌ 生成Python SDK失败
   ```
   **解决方案**：检查schemas目录是否存在，确保在项目根目录运行
   ```bash
   cd /path/to/mmodel
   python scripts/run_python_tests.py
   ```

2. **导入错误**：
   ```
   ❌ 无法导入MModel Python SDK: No module named 'mmodel'
   ```
   **解决方案**：先运行生成器
   ```bash
   python scripts/generators/schema_python_generator_v2.py
   ```

3. **找不到examples目录**：
   ```
   ❌ examples目录不存在: /path/to/examples
   ```
   **解决方案**：确保在项目根目录运行脚本

4. **解析失败**：
   ```
   ❌ 解析失败: YAML解析错误: ...
   ```
   **解决方案**：检查YAML/JSON文件格式是否正确

5. **依赖缺失**：
   ```
   ❌ yaml: 未安装
   ```
   **解决方案**：安装PyYAML
   ```bash
   pip install PyYAML
   ```

### 调试技巧

1. **详细错误信息**：测试脚本会显示详细的错误堆栈信息
2. **单个文件测试**：使用`-i`参数测试单个有问题的文件
3. **格式转换**：使用测试脚本进行格式转换以验证数据结构

## 🔧 自定义测试

### 添加新的测试用例

你可以基于`test_python_sdk.py`添加新的测试功能：

```python
def _test_custom_feature(self, obj):
    """测试自定义功能"""
    try:
        # 你的测试逻辑
        custom_result = obj.custom_method()
        print(f"     🔹 自定义功能: ✅ ({custom_result})")
    except Exception as e:
        print(f"     🔹 自定义功能: ❌ ({e})")
```

### 添加新的演示

你可以基于`demo_python_sdk.py`添加新的演示：

```python
def demo_custom_feature():
    """演示自定义功能"""
    print("\n🎯 自定义功能演示")
    print("-" * 40)

    # 你的演示代码
    pass

# 在main函数中调用
demo_custom_feature()
```

## 📝 注意事项

1. **SDK生成优先**：确保在运行测试前先生成SDK
2. **Python版本**：建议使用Python 3.7+
3. **依赖管理**：脚本会自动处理路径问题
4. **错误处理**：脚本包含完善的错误处理和用户友好的错误信息

## 🤝 贡献

如果你发现测试脚本的问题或有改进建议，请：

1. 检查是否有现有的issue
2. 创建详细的bug报告或功能请求
3. 提交pull request

---

💡 **提示**：这些测试脚本不仅用于验证SDK的正确性，也是学习如何使用MModel Python SDK的好例子！