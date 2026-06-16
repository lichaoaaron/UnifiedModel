# MModel Python SDK V2

这是由 `schema_python_generator_v2.py` 自动生成的 MModel Python SDK。

## 特性

- ✅ 使用 Python 的继承特性实现继承关系
- ✅ 生成简洁、高复用的代码
- ✅ 保留原始 schema 的结构关系
- ✅ 支持动态类型创建和解析
- ✅ 提供通用接口 `MModelCoreObject` 和 `MModelLinkObject`
- ✅ 支持 JSON/YAML 自动解析
- ✅ 类型安全的 Python 类型注解

## 安装

```bash
pip install -r requirements.txt
```

## 使用示例

### 基础用法

```python
from mmodel import *

# 判断对象类型
if is_core_object(obj):
    metadata = get_object_metadata(obj)
    schema = get_object_schema(obj)
    kind = obj.get_kind()  # 获取对象类型

# 处理Link对象
if is_link_object(obj):
    src, dest = get_link_endpoints(obj)
    print(f'Link from {src.name} to {dest.name}')
```

### 自动解析

```python
import yaml
from mmodel import parse_mmodel_yaml, parse_mmodel_json

# 自动解析YAML文件
with open('sls_front_metric.yaml', 'rb') as f:
    data = f.read()
    obj = parse_mmodel_yaml(data)
    print(f'Parsed object kind: {obj.get_kind()}')
    metadata = obj.get_metadata()
    print(f'Object name: {metadata.name}')

# 自动解析JSON数据
json_data = b'{"kind":"metric_set","schema":{"version":"v1.0.0"}}'
obj = parse_mmodel_json(json_data)
# obj 自动被解析为对应的类型
print(f'Object type: {type(obj).__name__}')
```

### 手动解析

```python
from mmodel import parse_json, parse_yaml
from mmodel import MetricSetV100  # 假设有这个类型

# 解析为特定类型
with open('metric.json', 'rb') as f:
    data = f.read()
    metric_set = parse_json(data, MetricSetV100)
    print(f'Metric set name: {metric_set.metadata.name}')
```

### 创建对象

```python
from mmodel import SemanticString, LinkEndpoint

# 创建语义字符串
desc = SemanticString(
    zh_cn='这是一个测试',
    en_us='This is a test'
)
print(str(desc))  # 输出: 这是一个测试

# 从字典创建
desc2 = SemanticString.from_dict('通用描述')
desc3 = SemanticString.from_dict({
    'zh_cn': '中文描述',
    'en_us': 'English description'
})

# 创建链接端点
endpoint = LinkEndpoint(
    domain='infrastructure',
    kind='service',
    name='user-service'
)
```

## 接口说明

### 基础接口

- `MModelObject`: 所有 MModel 对象的基础接口
  - `get_kind() -> str`: 获取对象的类型标识
  - `validate() -> Optional[Exception]`: 验证对象是否符合 schema 定义

- `MModelCoreObject`: 继承自 `MModelObject`，core 目录下所有对象的接口
  - `get_schema() -> Optional[Schema]`: 获取对象的 Schema 信息
  - `get_metadata() -> Optional[Metadata]`: 获取对象的 Metadata 信息

- `MModelLinkObject`: 继承自 `MModelCoreObject`，所有 link 类型对象的接口
  - `get_src() -> Optional[LinkEndpoint]`: 获取源端点信息
  - `get_dest() -> Optional[LinkEndpoint]`: 获取目标端点信息

### 工具函数

- `is_core_object(obj: Any) -> bool`: 判断对象是否实现了 `MModelCoreObject` 接口
- `is_link_object(obj: Any) -> bool`: 判断对象是否实现了 `MModelLinkObject` 接口
- `get_object_metadata(obj: Any) -> Optional[Metadata]`: 获取任意 MModel 对象的 Metadata
- `get_object_schema(obj: Any) -> Optional[Schema]`: 获取任意 MModel 对象的 Schema
- `get_link_endpoints(obj: Any) -> tuple[Optional[LinkEndpoint], Optional[LinkEndpoint]]`: 获取 Link 对象的源和目标端点

### 解析函数

- `parse_json(data: bytes, target_type: Type) -> Any`: 从 JSON 数据解析为指定类型
- `parse_yaml(data: bytes, target_type: Type) -> Any`: 从 YAML 数据解析为指定类型
- `parse_mmodel_json(data: bytes) -> MModelCoreObject`: 自动检测类型并解析 JSON
- `parse_mmodel_yaml(data: bytes) -> MModelCoreObject`: 自动检测类型并解析 YAML

## 版本兼容性

- 支持 v0.x.x 版本自动映射到 v1.0.0
- v1 主版本内向后兼容
- 遵循语义化版本规范

## 开发

此 SDK 由 `schema_python_generator_v2.py` 自动生成，请勿手动修改生成的代码。

如需修改，请更新 schemas 目录中的 YAML 文件，然后重新运行生成器：

```bash
python scripts/generators/schema_python_generator_v2.py
```