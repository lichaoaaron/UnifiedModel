# MModel Schema 工具集

这个工具集包含两个Python脚本，用于处理MModel Schema定义文件：

1. **schema_expander.py** - Schema展开器
2. **schema_validator.py** - Schema验证器

## 🎯 功能概述

### Schema展开器 (schema_expander.py)
- 递归扫描`schemas/core`目录中的所有`.schema.yaml`文件
- 解析`schemas/includes`目录中的共享类型定义
- 展开`extends`继承关系
- 解析`type_ref`引用
- 生成完整的、自包含的schema定义
- 支持循环依赖检测

### Schema验证器 (schema_validator.py)
- 验证展开后的schema文件结构完整性
- 检查是否还存在未解析的引用
- 验证必填字段
- 检查异常深的嵌套结构
- 生成详细的验证报告

## 🚀 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install PyYAML
```

### 2. 运行Schema展开器

```bash
# 展开所有schema文件
python schema_expander.py
```

**输出：**
- `expanded_schemas/` 目录包含所有展开后的schema文件
- `expanded_schemas/expansion_report.md` 展开过程报告

### 3. 运行Schema验证器

```bash
# 验证展开后的schema文件
python schema_validator.py
```

**输出：**
- `expanded_schemas/validation_report.md` 验证结果报告

## 📁 目录结构

```
mmodel/
├── schemas/                    # 原始schema定义
│   ├── core/                  # 核心schema文件
│   │   ├── dataset/          # 数据集相关schema
│   │   ├── link/             # 链接相关schema
│   │   └── storage/          # 存储相关schema
│   ├── includes/             # 共享类型定义
│   ├── base.yaml            # Schema元数据定义规范
│   └── manifest.yaml        # 版本清单
├── expanded_schemas/          # 展开后的schema文件
│   ├── *.expanded.yaml       # 展开后的schema文件
│   ├── expansion_report.md   # 展开报告
│   └── validation_report.md  # 验证报告
├── schema_expander.py        # Schema展开器
├── schema_validator.py       # Schema验证器
└── venv/                     # Python虚拟环境
```

## 🔧 工作原理

### Schema展开过程

1. **加载阶段**
   - 扫描`schemas/includes/`目录，加载共享类型定义
   - 扫描`schemas/core/`目录，加载所有schema文件

2. **展开阶段**
   - 处理`extends`继承关系，合并父类型定义
   - 解析`type_ref`引用，用完整定义替换引用
   - 递归处理嵌套结构
   - 检测并处理循环依赖

3. **输出阶段**
   - 生成完整的、自包含的schema文件
   - 创建展开过程报告

### 引用解析示例

**原始定义：**
```yaml
metrics:
  type: array
  constraint:
    array:
      item:
        type_ref: "metric:v1"
```

**展开后：**
```yaml
metrics:
  type: array
  constraint:
    array:
      item:
        type: object
        properties:
          name:
            type: string
            # ... 完整的metric定义
```

## 📊 验证检查项

### 基本结构检查
- ✅ 顶级字段完整性（name, versions）
- ✅ 版本结构正确性（name, spec）

### 引用解析检查
- ✅ 无未解析的`type_ref`引用
- ✅ 无未解析的`extends`引用

### 结构完整性检查
- ✅ 必填字段验证
- ✅ 异常深度嵌套检测

## 🎯 使用场景

### 1. Schema开发验证
在开发新的schema定义时，使用这些工具验证：
- 所有引用都能正确解析
- 继承关系正确
- 没有循环依赖

### 2. 独立验证
展开后的schema文件可以独立验证，无需依赖其他文件：
- 便于单元测试
- 便于文档生成
- 便于第三方工具集成

### 3. 持续集成
在CI/CD流程中使用：
```bash
# 在CI中运行
python schema_expander.py
python schema_validator.py

# 检查退出码
if [ $? -eq 0 ]; then
    echo "Schema验证通过"
else
    echo "Schema验证失败"
    exit 1
fi
```

## 🔍 故障排除

### 常见问题

1. **找不到类型定义**
   ```
   ⚠️  未找到类型定义: field_spec:v1
   ```
   - 检查`schemas/includes/`目录中是否存在对应的schema文件
   - 确认版本号是否正确

2. **循环依赖**
   ```
   ⚠️  检测到循环依赖: metadata:v1
   ```
   - 检查类型定义之间的引用关系
   - 重新设计类型层次结构

3. **文件解析失败**
   ```
   ❌ 加载schema文件失败: invalid yaml syntax
   ```
   - 检查YAML文件语法
   - 确认文件编码为UTF-8

## 📈 扩展功能

### 自定义验证规则
可以扩展`schema_validator.py`添加自定义验证规则：

```python
def _check_custom_rules(self, content: Dict[str, Any], result: Dict[str, Any]):
    """自定义验证规则"""
    # 添加您的验证逻辑
    pass
```

### 输出格式支持
可以扩展输出格式支持（JSON、XML等）：

```python
def save_as_json(self, expanded_schemas: Dict[str, Dict[str, Any]], output_dir: str):
    """保存为JSON格式"""
    # 实现JSON输出
    pass
```

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这些工具！

## 📄 许可证

本工具集遵循项目的许可证协议。 