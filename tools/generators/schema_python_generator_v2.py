#!/usr/bin/env python3
"""
MModel Schema Python SDK Generator V2

这个脚本基于原始的schemas目录，生成高复用的Python SDK代码。
利用Python的继承特性来实现继承关系，生成更优雅的代码结构。

主要改进：
1. 直接从schemas目录读取，保留原始的继承关系
2. 为共享类型生成独立的类定义
3. 使用Python的继承特性实现extends
4. 生成更简洁、高复用的代码
5. 使用dataclass和typing提供类型注解
6. 支持JSON/YAML序列化
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict, OrderedDict
import re


class PythonCodeGeneratorV2:
    def __init__(self, schemas_dir: str, output_dir: str):
        self.schemas_dir = Path(schemas_dir)
        self.output_dir = Path(output_dir)
        
        # 目录结构
        self.base_schema_path = self.schemas_dir / "base.yaml"
        self.core_dir = self.schemas_dir / "core"
        self.includes_dir = self.schemas_dir / "includes"
        
        # 存储所有的类型定义
        self.type_registry: Dict[str, Dict[str, Any]] = {}  # type_name:version -> definition
        self.schema_registry: Dict[str, Dict[str, Any]] = {}  # schema_name -> schema_content
        
        # 存储生成的Python类型名称映射
        self.python_type_mapping: Dict[str, str] = {}  # type_ref -> Python类型名
        
        # 记录依赖关系
        self.type_dependencies: Dict[str, Set[str]] = defaultdict(set)  # type -> dependencies
        
        # 存储内联类定义
        self.inline_classes: List[Tuple[str, List[str]]] = []
        
        # 基础类型映射
        self.primitive_types = {
            "string": "str",
            "number": "float",
            "integer": "int",
            "float": "float",
            "boolean": "bool",
            "bool": "bool",
            "object": "Dict[str, Any]",
            "array": "List[Any]",
            "map": "Dict[str, Any]",
            "any": "Any",
            "json": "Union[dict, list, str, int, float, bool, None]",
            "json_object": "Dict[str, Any]",
            "json_array": "List[Any]",
            "time": "datetime",
            "enum": "str",
        }
        
        # 加载base.yaml
        self.base_schema = self._load_base_schema()
        self.metadata_properties = self.base_schema.get("metadata_properties", {})
        self.additional_types = self.base_schema.get("additional_types", {})
        
    def _load_base_schema(self) -> Dict[str, Any]:
        """加载base.yaml文件"""
        try:
            with open(self.base_schema_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ 无法加载base.yaml: {e}")
            return {}
    
    def load_all_definitions(self):
        """加载所有的schema和类型定义"""
        print("🔍 正在加载schema定义...")
        
        # 1. 从base.yaml加载additional_types
        self._load_additional_types()
        
        # 2. 加载includes目录的共享类型
        self._load_include_types()
        
        # 3. 加载core目录的schema定义
        self._load_core_schemas()
        
        print(f"✅ 已加载 {len(self.type_registry)} 个类型定义")
        print(f"✅ 已加载 {len(self.schema_registry)} 个schema文件")
    
    def _load_additional_types(self):
        """从base.yaml加载additional_types"""
        if self.additional_types and 'types' in self.additional_types:
            types = self.additional_types.get('types', [])
            for type_def in types:
                if 'name' in type_def:
                    type_name = type_def['name']
                    # 对于base.yaml中的类型，默认版本为v1
                    self.type_registry[f"{type_name}:v1"] = {
                        'name': type_name,
                        'version': 'v1',
                        'spec': type_def,
                        'file': 'base'
                    }
                    print(f"📌 已加载base类型: {type_name}")
    
    def _load_include_types(self):
        """加载includes目录的共享类型"""
        if not self.includes_dir.exists():
            return
            
        for yaml_file in self.includes_dir.glob("*.schema.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                
                if content and 'name' in content:
                    type_name = content['name']
                    if 'versions' in content:
                        for version in content['versions']:
                            version_name = version.get('name', 'v1')
                            type_key = f"{type_name}:{version_name}"
                            self.type_registry[type_key] = {
                                'name': type_name,
                                'version': version_name,
                                'spec': version.get('spec', {}),
                                'file': 'includes'
                            }
                    print(f"📁 已加载include类型: {type_name}")
            except Exception as e:
                print(f"❌ 加载includes文件失败 {yaml_file}: {e}")
    
    def _load_core_schemas(self):
        """加载core目录的schema定义"""
        if not self.core_dir.exists():
            return
            
        for yaml_file in self.core_dir.rglob("*.schema.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                
                if content and 'name' in content:
                    schema_name = content['name']
                    self.schema_registry[schema_name] = content
                    
                    # 同时注册为类型
                    if 'versions' in content:
                        for version in content['versions']:
                            version_name = version.get('name', 'v1')
                            type_key = f"{schema_name}:{version_name}"
                            self.type_registry[type_key] = {
                                'name': schema_name,
                                'version': version_name,
                                'spec': version.get('spec', {}),
                                'file': 'core'
                            }
                    
                    print(f"📄 已加载schema: {schema_name}")
            except Exception as e:
                print(f"❌ 加载schema文件失败 {yaml_file}: {e}")
    
    def analyze_dependencies(self):
        """分析类型之间的依赖关系"""
        print("\n🔍 分析类型依赖关系...")
        
        for type_key, type_def in self.type_registry.items():
            if isinstance(type_def, dict) and 'spec' in type_def:
                self._analyze_spec_dependencies(type_key, type_def['spec'])
        
        # 打印依赖关系
        for type_key, deps in self.type_dependencies.items():
            if deps:
                print(f"📊 {type_key} 依赖: {', '.join(deps)}")
    
    def _analyze_spec_dependencies(self, type_key: str, spec: Dict[str, Any]):
        """分析spec中的依赖关系"""
        if not isinstance(spec, dict):
            return
            
        # 分析extends依赖
        if 'extends' in spec:
            extends_list = spec['extends']
            if isinstance(extends_list, list):
                for extend_ref in extends_list:
                    self.type_dependencies[type_key].add(extend_ref)
        
        # 分析type_ref依赖
        if 'type_ref' in spec:
            self.type_dependencies[type_key].add(spec['type_ref'])
        
        # 分析properties中的依赖
        if 'properties' in spec:
            for prop_name, prop_spec in spec['properties'].items():
                if isinstance(prop_spec, dict):
                    self._analyze_spec_dependencies(type_key, prop_spec)
    
    def generate_all(self):
        """生成所有的Python代码"""
        print("\n🚀 开始生成Python SDK代码 V2...")
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 加载所有定义
        self.load_all_definitions()
        
        # 2. 分析依赖关系
        self.analyze_dependencies()
        
        # 3. 生成基础类型文件
        self._generate_base_types()
        
        # 4. 生成共享类型文件
        self._generate_shared_types()
        
        # 5. 生成schema文件
        self._generate_schema_files()
        
        # 6. 生成主包文件
        self._generate_main_package()
        
        # 7. 生成__init__.py
        self._generate_init_file()
        
        # 8. 生成requirements.txt和README
        self._generate_requirements()
        self._generate_readme()
        
        print("\n✅ Python SDK V2代码生成完成！")
    
    def _get_python_type_name(self, type_key: str) -> str:
        """将类型键转换为Python类型名"""
        # 分解type_key
        parts = type_key.split(':')
        if len(parts) == 2:
            name, version = parts
        else:
            name = parts[0]
            version = 'v1'
        
        # 转换为驼峰命名
        name_parts = name.split('_')
        python_name = ''.join(word.capitalize() for word in name_parts)
        
        # 添加版本后缀
        version_suffix = version.replace('.', '').upper()
        return f"{python_name}{version_suffix}"
    
    def _to_python_field_name(self, field_name: str) -> str:
        """将字段名转换为Python字段名（snake_case）"""
        return field_name
    
    def _to_python_class_name(self, name: str) -> str:
        """将名称转换为Python类名（PascalCase）"""
        parts = name.split('_')
        return ''.join(word.capitalize() for word in parts)
    
    def _generate_base_types(self):
        """生成基础类型定义"""
        content = []
        content.append("# Code generated by schema_python_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append('"""')
        content.append("MModel Python SDK - 基础类型定义")
        content.append('"""')
        content.append("")
        content.append("from abc import ABC, abstractmethod")
        content.append("from dataclasses import dataclass, field")
        content.append("from datetime import datetime")
        content.append("from typing import Any, Dict, List, Optional, Union")
        content.append("import json")
        content.append("import yaml")
        content.append("")
        
        # 生成SemanticString类
        content.append("@dataclass")
        content.append("class SemanticString:")
        content.append('    """支持多语言的语义字符串"""')
        content.append("    zh_cn: Optional[str] = None")
        content.append("    en_us: Optional[str] = None")
        content.append("")
        content.append("    def __str__(self) -> str:")
        content.append('        """返回中文描述，如果没有则返回英文"""')
        content.append("        if self.zh_cn:")
        content.append("            return self.zh_cn")
        content.append("        return self.en_us or ''")
        content.append("")
        content.append("    def get(self, lang: str) -> str:")
        content.append('        """根据语言代码获取对应文本"""')
        content.append("        if lang == 'zh_cn' or lang == 'zh':")
        content.append("            return self.zh_cn or ''")
        content.append("        elif lang == 'en_us' or lang == 'en':")
        content.append("            return self.en_us or ''")
        content.append("        return ''")
        content.append("")
        content.append("    @classmethod")
        content.append("    def from_dict(cls, data: Union[str, Dict[str, str]]) -> 'SemanticString':")
        content.append('        """从字典或字符串创建SemanticString"""')
        content.append("        if isinstance(data, str):")
        content.append("            return cls(zh_cn=data, en_us=data)")
        content.append("        elif isinstance(data, dict):")
        content.append("            return cls(")
        content.append("                zh_cn=data.get('zh_cn'),")
        content.append("                en_us=data.get('en_us')")
        content.append("            )")
        content.append("        return cls()")
        content.append("")
        
        # 生成LinkEndpoint类
        content.append("@dataclass")
        content.append("class LinkEndpoint:")
        content.append('    """表示Link的端点信息"""')
        content.append("    domain: str")
        content.append("    kind: str")
        content.append("    name: str")
        content.append("    filter: Optional[str] = None")
        content.append("")
        
        # 生成基础接口
        content.append("class MModelObject(ABC):")
        content.append('    """所有MModel对象的基础接口"""')
        content.append("")
        content.append("    @abstractmethod")
        content.append("    def get_kind(self) -> str:")
        content.append('        """获取对象的类型标识"""')
        content.append("        pass")
        content.append("")
        content.append("    def validate(self) -> Optional[Exception]:")
        content.append('        """验证对象是否符合schema定义"""')
        content.append("        # TODO: 实现验证逻辑")
        content.append("        return None")
        content.append("")
        
        content.append("class MModelCoreObject(MModelObject):")
        content.append('    """所有core目录对象的接口"""')
        content.append("")
        content.append("    @abstractmethod")
        content.append("    def get_schema(self) -> Optional[Any]:")
        content.append('        """获取对象的Schema信息"""')
        content.append("        pass")
        content.append("")
        content.append("    @abstractmethod")
        content.append("    def get_metadata(self) -> Optional[Any]:")
        content.append('        """获取对象的Metadata信息"""')
        content.append("        pass")
        content.append("")
        
        content.append("class MModelLinkObject(MModelCoreObject):")
        content.append('    """所有link类型对象的接口"""')
        content.append("")
        content.append("    @abstractmethod")
        content.append("    def get_src(self) -> Optional[LinkEndpoint]:")
        content.append('        """获取源对象信息"""')
        content.append("        pass")
        content.append("")
        content.append("    @abstractmethod")
        content.append("    def get_dest(self) -> Optional[LinkEndpoint]:")
        content.append('        """获取目标对象信息"""')
        content.append("        pass")
        content.append("")
        
        # 写入文件
        output_file = self.output_dir / "base_types.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成基础类型文件: {output_file.name}")
    
    def _generate_shared_types(self):
        """生成共享类型定义"""
        content = []
        content.append("# Code generated by schema_python_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append('"""')
        content.append("MModel Python SDK - 共享类型定义")
        content.append('"""')
        content.append("")
        content.append("from __future__ import annotations")
        content.append("from dataclasses import dataclass, field")
        content.append("from datetime import datetime")
        content.append("from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING")
        content.append("")
        content.append("if TYPE_CHECKING:")
        content.append("    from .base_types import MModelObject, SemanticString")
        content.append("else:")
        content.append("    from .base_types import MModelObject, SemanticString")
        content.append("")
        
        # 初始化内联类列表
        self.inline_classes = []
        
        # 先生成所有内联类
        inline_content = []
        
        # 按照依赖顺序生成类型
        generated = set()
        
        # 先生成没有依赖的类型
        for type_key in self.type_registry:
            if type_key not in self.type_dependencies or not self.type_dependencies[type_key]:
                if type_key not in generated:
                    self._generate_type_class(content, type_key, generated)
        
        # 再生成有依赖的类型
        max_iterations = len(self.type_registry) * 2
        iteration = 0
        while len(generated) < len(self.type_registry) and iteration < max_iterations:
            iteration += 1
            for type_key in self.type_registry:
                if type_key not in generated:
                    # 检查所有依赖是否已生成
                    deps = self.type_dependencies.get(type_key, set())
                    if all(dep in generated or self._resolve_type_ref(dep) is None for dep in deps):
                        self._generate_type_class(content, type_key, generated)
        
        # 先生成所有内联类，然后再生成主类
        all_inline_classes = []
        all_main_classes = []
        
        # 收集内联类
        for inline_class_name, inline_class_content in self.inline_classes:
            all_inline_classes.extend(inline_class_content)
        
        # 重新整理内容：先内联类，后主类
        final_content = content[:10]  # 保留头部导入
        final_content.extend(all_inline_classes)  # 添加内联类
        final_content.extend(content[10:])  # 添加主类
        
        # 写入文件
        output_file = self.output_dir / "shared_types.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_content))
        
        print(f"✅ 生成共享类型文件: {output_file.name}")
    
    def _generate_type_class(self, content: List[str], type_key: str, generated: Set[str]):
        """生成单个类型的class定义"""
        type_def = self.type_registry.get(type_key)
        if not type_def or not isinstance(type_def, dict):
            return
            
        # 跳过schema类型，它们会在单独的文件中生成
        if type_def.get('file') == 'core':
            return
            
        # 生成Python类型名
        python_type_name = self._get_python_type_name(type_key)
        self.python_type_mapping[type_key] = python_type_name
        
        # 添加到已生成集合
        generated.add(type_key)
        
        # 获取spec
        spec = type_def.get('spec', type_def)
        
        # 生成继承关系
        base_classes = []
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_type = self._get_python_type_for_ref(extend_ref)
                if parent_type and parent_type != "object":
                    base_classes.append(parent_type)
        
        if not base_classes:
            base_classes = ["MModelObject"]
        
        # 生成类定义
        content.append("@dataclass")
        content.append(f"class {python_type_name}({', '.join(base_classes)}):")
        
        # 添加文档字符串
        desc = self._get_description(spec.get('description', ''))
        if desc:
            content.append(f'    """{desc}"""')
        else:
            content.append(f'    """{type_def.get("name", type_key)} class"""')
        
        # 处理properties
        has_fields = False
        if 'properties' in spec and isinstance(spec['properties'], dict):
            # 收集已经从父类继承的属性
            inherited_props = self._get_inherited_properties(spec)
            
            for prop_name, prop_spec in spec['properties'].items():
                # 跳过已经从父类继承的属性
                if prop_name not in inherited_props:
                    self._generate_class_field(content, prop_name, prop_spec, python_type_name)
                    has_fields = True
        
        if not has_fields:
            content.append("    pass")
        
        content.append("")
        
        # 生成get_kind方法
        content.append(f"    def get_kind(self) -> str:")
        content.append(f"        return '{type_def.get('name', type_key.split(':')[0])}'")
        content.append("")
    
    def _generate_schema_files(self):
        """为每个schema生成独立的文件"""
        for schema_name, schema_content in self.schema_registry.items():
            self._generate_single_schema_file(schema_name, schema_content)
    
    def _generate_single_schema_file(self, schema_name: str, schema_content: Dict[str, Any]):
        """生成单个schema文件"""
        content = []
        content.append("# Code generated by schema_python_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append('"""')
        content.append(f"MModel Python SDK - {schema_name} Schema")
        content.append('"""')
        content.append("")
        content.append("from __future__ import annotations")
        content.append("from dataclasses import dataclass, field")
        content.append("from datetime import datetime")
        content.append("from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING")
        content.append("")
        content.append("if TYPE_CHECKING:")
        content.append("    from .base_types import MModelCoreObject, MModelLinkObject, SemanticString, LinkEndpoint")
        content.append("else:")
        content.append("    from .base_types import MModelCoreObject, MModelLinkObject, SemanticString, LinkEndpoint")
        content.append("")
        content.append("# 延迟导入共享类型以避免循环依赖")
        content.append("try:")
        content.append("    from .shared_types import *")
        content.append("except ImportError:")
        content.append("    pass")
        content.append("")
        
        # 初始化内联类列表
        self.inline_classes = []
        
        # 生成每个版本的class
        if 'versions' in schema_content:
            for version in schema_content['versions']:
                version_name = version.get('name', 'v1')
                spec = version.get('spec', {})
                
                # 生成class名称
                type_key = f"{schema_name}:{version_name}"
                python_type_name = self._get_python_type_name(type_key)
                self.python_type_mapping[type_key] = python_type_name
                
                # 生成class定义
                self._generate_schema_class(content, python_type_name, spec, schema_name)
        
        # 生成所有内联类
        for inline_class_name, inline_class_content in self.inline_classes:
            content.extend(inline_class_content)
        
        # 写入文件
        output_file = self.output_dir / f"{schema_name}.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成schema文件: {output_file.name}")
    
    def _generate_main_package(self):
        """生成主包文件"""
        content = []
        content.append("# Code generated by schema_python_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append('"""')
        content.append("MModel Python SDK - 主包文件")
        content.append('"""')
        content.append("")
        content.append("from __future__ import annotations")
        content.append("import json")
        content.append("import yaml")
        content.append("from typing import Any, Dict, Type, Union, Optional, Tuple, TYPE_CHECKING, get_type_hints, get_origin, get_args")
        content.append("from dataclasses import is_dataclass, fields as dataclass_fields")
        content.append("")
        content.append("if TYPE_CHECKING:")
        content.append("    from .base_types import MModelCoreObject, MModelObject, LinkEndpoint, SemanticString")
        content.append("else:")
        content.append("    from .base_types import MModelCoreObject, MModelObject, LinkEndpoint, SemanticString")
        content.append("")
        content.append('VERSION = "2.0.0"')
        content.append("")
        
        # 生成类型注册表
        content.append("# 类型注册表")
        content.append("TYPE_REGISTRY: Dict[str, Type] = {}")
        content.append("")
        content.append("# 注册类型的函数")
        content.append("def _register_types():")
        content.append('    """注册所有类型到类型注册表"""')
        content.append("    global TYPE_REGISTRY")
        content.append("")
        
        # 按schema分组注册类型
        schema_types = {}
        for type_key, python_type_name in sorted(self.python_type_mapping.items()):
            if self.type_registry.get(type_key, {}).get('file') != 'core':
                continue
            schema_name = type_key.split(':')[0]
            if schema_name not in schema_types:
                schema_types[schema_name] = []
            schema_types[schema_name].append((type_key, python_type_name))
        
        for schema_name, types in schema_types.items():
            content.append(f'    # 注册 {schema_name} 相关类型')
            content.append(f'    try:')
            content.append(f'        from . import {schema_name}')
            for type_key, python_type_name in types:
                content.append(f'        TYPE_REGISTRY["{type_key}"] = getattr({schema_name}, "{python_type_name}", None)')
            content.append(f'    except (ImportError, AttributeError) as e:')
            content.append(f'        pass  # 模块 {schema_name} 导入失败: {{e}}')
            content.append("")
        
        content.append("")
        content.append("# 延迟注册所有类型，避免循环导入")
        content.append("def register_all_types():")
        content.append('    """手动注册所有类型（用于解决循环导入问题）"""')
        content.append("    _register_types()")
        content.append("")
        content.append("# 尝试自动注册")
        content.append("try:")
        content.append("    _register_types()")
        content.append("except Exception:")
        content.append("    pass  # 如果自动注册失败，可以手动调用register_all_types()")
        content.append("")
        
        # 生成解析函数
        self._generate_parser_functions(content)
        
        # 生成工具函数
        self._generate_utility_functions(content)
        
        # 写入文件
        output_file = self.output_dir / "mmodel.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成主包文件: {output_file.name}")
    
    def _generate_init_file(self):
        """生成__init__.py文件"""
        content = []
        content.append("# Code generated by schema_python_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append('"""')
        content.append("MModel Python SDK")
        content.append('"""')
        content.append("")
        content.append("from .base_types import *")
        content.append("from .shared_types import *")
        content.append("from .mmodel import *")
        content.append("")
        
        # 导入所有schema模块
        for schema_name in self.schema_registry.keys():
            content.append(f"from .{schema_name} import *")
        
        content.append("")
        content.append('__version__ = "2.0.0"')
        content.append("")
        
        # 写入文件
        output_file = self.output_dir / "__init__.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成__init__.py文件: {output_file.name}")
    
    def _get_inherited_properties(self, spec: Dict[str, Any]) -> Set[str]:
        """获取从父类继承的属性名集合"""
        inherited = set()
        
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_def = self._resolve_type_ref(extend_ref)
                if parent_def and 'spec' in parent_def:
                    parent_spec = parent_def['spec']
                    if 'properties' in parent_spec:
                        inherited.update(parent_spec['properties'].keys())
                    # 递归获取父类的父类属性
                    inherited.update(self._get_inherited_properties(parent_spec))
        
        return inherited
    
    def _resolve_type_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        """解析类型引用"""
        # 如果没有版本号，添加默认版本
        if ':' not in ref:
            ref = f"{ref}:v1"
        
        return self.type_registry.get(ref)
    
    def _get_python_type_for_ref(self, ref: str) -> str:
        """获取引用类型对应的Python类型"""
        # 如果没有版本号，添加默认版本
        if ':' not in ref:
            ref = f"{ref}:v1"
        
        # 如果已经在映射中，使用映射的名称
        if ref in self.python_type_mapping:
            return self.python_type_mapping[ref]
        elif ref in self.type_registry:
            python_type_name = self._get_python_type_name(ref)
            self.python_type_mapping[ref] = python_type_name
            return python_type_name
        else:
            return "object"
    
    def _generate_class_field(self, content: List[str], field_name: str, field_spec: Dict[str, Any], parent_class_name: str):
        """生成类字段"""
        if field_spec is None:
            return
            
        # 获取字段描述
        desc = ""
        if isinstance(field_spec, dict) and 'description' in field_spec:
            desc = self._get_description(field_spec['description'])
        
        # 获取Python类型
        python_type = self._get_python_type(field_spec, field_name, parent_class_name)
        
        # 检查是否必填
        is_required = self._is_required_field(field_spec)
        
        # 生成字段
        python_field_name = self._to_python_field_name(field_name)
        
        if desc:
            content.append(f"    # {desc}")
        
        # 简化类型处理，统一使用Optional并设置默认值
        if python_type.startswith("Optional["):
            content.append(f"    {python_field_name}: {python_type} = None")
        else:
            content.append(f"    {python_field_name}: Optional[{python_type}] = None")
    
    def _get_python_type(self, spec: Dict[str, Any], field_name: str = "", parent_class_name: str = "") -> str:
        """获取字段的Python类型"""
        if not isinstance(spec, dict):
            return "Any"
        
        # 处理type_ref
        if 'type_ref' in spec:
            ref_type = self._get_python_type_for_ref(spec['type_ref'])
            # 使用字符串形式避免前向引用问题
            return f"Optional['{ref_type}']" if ref_type != "object" else "Optional[Any]"
        
        # 处理constraint中的类型
        if 'constraint' in spec and isinstance(spec['constraint'], dict):
            constraint = spec['constraint']
            
            # 处理array约束
            if 'array' in constraint and 'item' in constraint['array']:
                item_spec = constraint['array']['item']
                item_type = self._get_python_type(item_spec, f"{field_name}_item", parent_class_name)
                return f"List[{item_type}]"
            
            # 处理map约束
            if 'map' in constraint:
                value_spec = constraint['map'].get('value', {'type': 'string'})
                value_type = self._get_python_type(value_spec, f"{field_name}_value", parent_class_name)
                return f"Dict[str, {value_type}]"
            
            # 处理enum约束
            if 'enum' in constraint:
                enum_values = constraint.get('enum', [])
                if enum_values and field_name and parent_class_name:
                    # 对于enum，使用str类型而不是生成专门的enum类
                    return "Optional[str]"
        
        # 处理基本类型
        if 'type' in spec:
            base_type = spec['type']
            
            # 检查是否是自定义类型
            if base_type not in self.primitive_types:
                # 尝试查找类型定义
                type_ref = f"{base_type}:v1"
                if type_ref in self.type_registry:
                    type_name = self._get_python_type_name(type_ref)
                    return f"Optional['{type_name}']"
                
                # 特殊处理semantic_string
                if base_type == 'semantic_string':
                    return "Optional[SemanticString]"
            
            # 处理object类型
            if base_type == 'object' and 'properties' in spec:
                # 检查是否是semantic_string的展开形式
                props = spec['properties']
                if isinstance(props, dict) and set(props.keys()) <= {"zh_cn", "en_us"}:
                    return "Optional[SemanticString]"
                
                # 生成内联class
                if field_name and parent_class_name:
                    inline_class_name = f"{parent_class_name}{self._to_python_class_name(field_name)}"
                    self._generate_inline_class_with_properties(inline_class_name, spec)
                    return f"Optional['{inline_class_name}']"
                else:
                    return "Dict[str, Any]"
            
            return self.primitive_types.get(base_type, "Any")
        
        # 如果没有type字段，但有properties，也处理为object
        if 'properties' in spec and isinstance(spec['properties'], dict):
            # 生成内联class
            if field_name and parent_class_name:
                inline_class_name = f"{parent_class_name}{self._to_python_class_name(field_name)}"
                self._generate_inline_class_with_properties(inline_class_name, spec)
                return f"Optional['{inline_class_name}']"
            else:
                return "Dict[str, Any]"
        
        return "Any"
    
    def _is_required_field(self, field_spec: Dict[str, Any]) -> bool:
        """判断字段是否必填"""
        if not isinstance(field_spec, dict):
            return False
            
        if 'constraint' in field_spec:
            constraint = field_spec['constraint']
            if isinstance(constraint, dict):
                return constraint.get('required', False)
        
        return False
    
    def _get_description(self, desc: Any) -> str:
        """获取描述文本，处理换行和限制长度"""
        text = ""
        if isinstance(desc, str):
            text = desc
        elif isinstance(desc, dict):
            # 优先返回中文描述
            if 'zh_cn' in desc:
                text = desc['zh_cn']
            elif 'en_us' in desc:
                text = desc['en_us']
        
        if not text:
            return ""
        
        # 处理换行符，将多行文本合并为单行
        text = text.replace('\n', ' ').replace('\r', ' ')
        
        # 替换连续的空格为单个空格
        text = ' '.join(text.split())
        
        # 限制长度为128字符
        if len(text) > 128:
            # 截断到125个字符，为 "..." 留出空间
            text = text[:125] + "..."
        
        return text
    
    def _generate_inline_class_with_properties(self, class_name: str, spec: Dict[str, Any]):
        """生成带有properties的内联类（用于object类型）"""
        content = []
        
        # 生成类注释
        desc = self._get_description(spec.get('description', ''))
        content.append("@dataclass")
        content.append(f"class {class_name}:")
        if desc:
            content.append(f'    """{desc}"""')
        else:
            content.append(f'    """{class_name} inline class"""')
        
        # 处理properties
        has_fields = False
        if 'properties' in spec and isinstance(spec['properties'], dict):
            for prop_name, prop_spec in spec['properties'].items():
                self._generate_class_field(content, prop_name, prop_spec, class_name)
                has_fields = True
        
        if not has_fields:
            content.append("    pass")
        
        content.append("")
        
        # 将内联类添加到待生成列表
        self.inline_classes.append((class_name, content))
    
    def _generate_schema_class(self, content: List[str], class_name: str, spec: Dict[str, Any], schema_name: str):
        """生成schema的class定义"""
        # 确定基类
        base_classes = []
        
        # 检查是否是link类型
        if schema_name.endswith('_link'):
            base_classes.append("MModelLinkObject")
        else:
            base_classes.append("MModelCoreObject")
        
        # 处理extends
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_type = self._get_python_type_for_ref(extend_ref)
                if parent_type and parent_type != "object":
                    if parent_type not in base_classes:
                        base_classes.append(parent_type)
        
        # 生成类定义
        content.append("@dataclass")
        content.append(f"class {class_name}({', '.join(base_classes)}):")
        
        # 添加文档字符串
        desc = self._get_description(spec.get('description', ''))
        if desc:
            content.append(f'    """{desc}"""')
        else:
            content.append(f'    """{schema_name} class"""')
        
        # 处理type_ref（使用继承）
        if 'type_ref' in spec:
            ref_type = self._get_python_type_for_ref(spec['type_ref'])
            if ref_type and ref_type != "object":
                # 在Python中，我们通过字段嵌入实现类似功能
                content.append(f"    # 引用 {spec['type_ref']}")
        
        # 处理properties
        has_fields = False
        if 'properties' in spec and isinstance(spec['properties'], dict):
            # 收集已经从父类继承的属性
            inherited_props = self._get_inherited_properties(spec)
            
            for prop_name, prop_spec in spec['properties'].items():
                if prop_name not in inherited_props:
                    self._generate_class_field(content, prop_name, prop_spec, class_name)
                    has_fields = True
        
        if not has_fields:
            content.append("    pass")
        
        content.append("")
        
        # 生成get_kind方法
        content.append(f"    def get_kind(self) -> str:")
        content.append(f"        return '{schema_name}'")
        content.append("")
        
        # 生成MModelCoreObject接口方法
        if "MModelCoreObject" in base_classes or "MModelLinkObject" in base_classes:
            content.append(f"    def get_schema(self) -> Optional[Any]:")
            content.append("        return getattr(self, 'schema', None)")
            content.append("")
            
            content.append(f"    def get_metadata(self) -> Optional[Any]:")
            content.append("        return getattr(self, 'metadata', None)")
            content.append("")
        
        # 如果是link类型，生成MModelLinkObject接口方法
        if "MModelLinkObject" in base_classes:
            content.append(f"    def get_src(self) -> Optional[LinkEndpoint]:")
            content.append("        spec = getattr(self, 'spec', None)")
            content.append("        if spec and hasattr(spec, 'src'):")
            content.append("            src = spec.src")
            content.append("            if src:")
            content.append("                return LinkEndpoint(")
            content.append("                    domain=getattr(src, 'domain', ''),")
            content.append("                    kind=getattr(src, 'kind', ''),")
            content.append("                    name=getattr(src, 'name', ''),")
            content.append("                    filter=getattr(src, 'filter', None)")
            content.append("                )")
            content.append("        return None")
            content.append("")
            
            content.append(f"    def get_dest(self) -> Optional[LinkEndpoint]:")
            content.append("        spec = getattr(self, 'spec', None)")
            content.append("        if spec and hasattr(spec, 'dest'):")
            content.append("            dest = spec.dest")
            content.append("            if dest:")
            content.append("                return LinkEndpoint(")
            content.append("                    domain=getattr(dest, 'domain', ''),")
            content.append("                    kind=getattr(dest, 'kind', ''),")
            content.append("                    name=getattr(dest, 'name', '')")
            content.append("                )")
            content.append("        return None")
            content.append("")
    
    def _generate_parser_functions(self, content: List[str]):
        """生成解析函数"""
        content.append("# 解析函数")
        content.append("def parse_json(data: bytes, target_type: Type) -> Any:")
        content.append('    """从JSON数据解析对象"""')
        content.append("    json_data = json.loads(data)")
        content.append("    try:")
        content.append("        return target_type(**json_data)")
        content.append("    except TypeError as e:")
        content.append("        # 如果直接实例化失败，尝试简单赋值")
        content.append("        instance = target_type()")
        content.append("        for key, value in json_data.items():")
        content.append("            if hasattr(instance, key):")
        content.append("                setattr(instance, key, value)")
        content.append("        return instance")
        content.append("")
        
        content.append("def parse_yaml(data: bytes, target_type: Type) -> Any:")
        content.append('    """从YAML数据解析对象"""')
        content.append("    yaml_data = yaml.safe_load(data)")
        content.append("    try:")
        content.append("        return target_type(**yaml_data)")
        content.append("    except TypeError as e:")
        content.append("        # 如果直接实例化失败，尝试简单赋值")
        content.append("        instance = target_type()")
        content.append("        for key, value in yaml_data.items():")
        content.append("            if hasattr(instance, key):")
        content.append("                setattr(instance, key, value)")
        content.append("        return instance")
        content.append("")
        
        content.append("def _convert_value_to_type(value: Any, target_type: Type) -> Any:")
        content.append('    """递归地将值转换为目标类型')
        content.append("    ")
        content.append("    Args:")
        content.append("        value: 要转换的值（通常是从 YAML/JSON 解析的 dict/list）")
        content.append("        target_type: 目标类型（可能是 dataclass、Optional、List 等）")
        content.append("    ")
        content.append("    Returns:")
        content.append("        转换后的值")
        content.append('    """')
        content.append("    # 如果值是 None，直接返回")
        content.append("    if value is None:")
        content.append("        return None")
        content.append("    ")
        content.append("    # 获取类型的 origin（如 List, Optional）和 args（如 List[str] 中的 str）")
        content.append("    origin = get_origin(target_type)")
        content.append("    args = get_args(target_type)")
        content.append("    ")
        content.append("    # 处理 Optional[X] 类型（实际上是 Union[X, None]）")
        content.append("    if origin is Union:")
        content.append("        # 找到非 None 的类型")
        content.append("        non_none_types = [arg for arg in args if arg is not type(None)]")
        content.append("        if non_none_types:")
        content.append("            # 递归处理第一个非 None 类型")
        content.append("            return _convert_value_to_type(value, non_none_types[0])")
        content.append("        return value")
        content.append("    ")
        content.append("    # 处理 List 类型")
        content.append("    if origin is list:")
        content.append("        if not isinstance(value, list):")
        content.append("            return value")
        content.append("        if args:")
        content.append("            # 递归转换列表中的每个元素")
        content.append("            element_type = args[0]")
        content.append("            return [_convert_value_to_type(item, element_type) for item in value]")
        content.append("        return value")
        content.append("    ")
        content.append("    # 处理 Dict 类型")
        content.append("    if origin is dict:")
        content.append("        return value")
        content.append("    ")
        content.append("    # 处理 dataclass 类型")
        content.append("    if is_dataclass(target_type) and isinstance(value, dict):")
        content.append("        # 递归转换嵌套的 dataclass")
        content.append("        return _dict_to_dataclass(target_type, value)")
        content.append("    ")
        content.append("    # 其他情况直接返回")
        content.append("    return value")
        content.append("")
        content.append("")
        content.append("def _dict_to_dataclass(dataclass_type: Type, data: Dict[str, Any]) -> Any:")
        content.append('    """将字典递归转换为 dataclass 实例')
        content.append("    ")
        content.append("    Args:")
        content.append("        dataclass_type: 目标 dataclass 类型")
        content.append("        data: 字典数据")
        content.append("    ")
        content.append("    Returns:")
        content.append("        dataclass 实例")
        content.append('    """')
        content.append("    if not is_dataclass(dataclass_type):")
        content.append("        return data")
        content.append("    ")
        content.append("    try:")
        content.append("        # 获取 dataclass 的类型提示")
        content.append("        type_hints = get_type_hints(dataclass_type)")
        content.append("    except Exception:")
        content.append("        # 如果获取类型提示失败，使用字段定义")
        content.append("        type_hints = {}")
        content.append("        for field in dataclass_fields(dataclass_type):")
        content.append("            type_hints[field.name] = field.type")
        content.append("    ")
        content.append("    # 转换每个字段的值")
        content.append("    converted_data = {}")
        content.append("    for key, value in data.items():")
        content.append("        if key in type_hints:")
        content.append("            # 递归转换嵌套的类型")
        content.append("            converted_data[key] = _convert_value_to_type(value, type_hints[key])")
        content.append("        else:")
        content.append("            # 没有类型提示的字段保持原样")
        content.append("            converted_data[key] = value")
        content.append("    ")
        content.append("    # 创建 dataclass 实例")
        content.append("    try:")
        content.append("        return dataclass_type(**converted_data)")
        content.append("    except Exception:")
        content.append("        # 如果构造失败，尝试无参构造后赋值")
        content.append("        instance = dataclass_type()")
        content.append("        for key, value in converted_data.items():")
        content.append("            if hasattr(instance, key):")
        content.append("                setattr(instance, key, value)")
        content.append("        return instance")
        content.append("")
        content.append("")
        content.append("def _create_instance_from_data(target_type: Type, data: Dict[str, Any]) -> Any:")
        content.append('    """从数据创建类型实例的辅助函数"""')
        content.append("    # 首先尝试使用递归转换")
        content.append("    if is_dataclass(target_type):")
        content.append("        try:")
        content.append("            return _dict_to_dataclass(target_type, data)")
        content.append("        except Exception as e:")
        content.append("            # 如果递归转换失败，继续尝试旧的方法")
        content.append("            pass")
        content.append("    ")
        content.append("    try:")
        content.append("        # 尝试直接使用构造函数")
        content.append("        return target_type(**data)")
        content.append("    except Exception:")
        content.append("        try:")
        content.append("            # 尝试无参构造后赋值")
        content.append("            instance = target_type()")
        content.append("            for key, value in data.items():")
        content.append("                if hasattr(instance, key):")
        content.append("                    # 处理特殊类型")
        content.append("                    if key == 'metadata' and isinstance(value, dict):")
        content.append("                        # 尝试转换为SemanticString")
        content.append("                        if 'description' in value and isinstance(value['description'], dict):")
        content.append("                            value['description'] = SemanticString.from_dict(value['description'])")
        content.append("                    setattr(instance, key, value)")
        content.append("            return instance")
        content.append("        except Exception as e:")
        content.append("            # 如果都失败了，返回一个简单的对象")
        content.append("            class SimpleObject:")
        content.append("                def __init__(self):")
        content.append("                    for key, value in data.items():")
        content.append("                        setattr(self, key, value)")
        content.append("                def get_kind(self):")
        content.append("                    return data.get('kind', 'unknown')")
        content.append("                def validate(self):")
        content.append("                    return None")
        content.append("                def get_schema(self):")
        content.append("                    return getattr(self, 'schema', None)")
        content.append("                def get_metadata(self):")
        content.append("                    return getattr(self, 'metadata', None)")
        content.append("            return SimpleObject()")
        content.append("")
        
        content.append("def parse_mmodel_json(data: bytes) -> MModelCoreObject:")
        content.append('    """自动检测类型并解析JSON"""')
        content.append("    # 先解析header获取kind和version")
        content.append("    json_data = json.loads(data)")
        content.append("    ")
        content.append("    kind = json_data.get('kind')")
        content.append("    if not kind:")
        content.append("        raise ValueError('missing required field: kind')")
        content.append("    ")
        content.append("    metadata = json_data.get('metadata')")
        content.append("    if not metadata:")
        content.append("        raise ValueError('missing required field: metadata')")
        content.append("    ")
        content.append("    domain = metadata.get('domain') if isinstance(metadata, dict) else None")
        content.append("    if not domain:")
        content.append("        raise ValueError('missing required field: metadata.domain')")
        content.append("    ")
        content.append("    name = metadata.get('name') if isinstance(metadata, dict) else None")
        content.append("    if not name:")
        content.append("        raise ValueError('missing required field: metadata.name')")
        content.append("    ")
        content.append("    schema_info = json_data.get('schema', {})")
        content.append("    version = schema_info.get('version')")
        content.append("    if not version:")
        content.append("        raise ValueError('missing required field: schema.version')")
        content.append("    ")
        content.append("    spec = json_data.get('spec')")
        content.append("    if spec is None:")
        content.append("        raise ValueError('missing required field: spec')")
        content.append("    ")
        content.append("    if isinstance(spec, dict) and len(spec) == 0:")
        content.append("        raise ValueError('spec field cannot be empty')")
        content.append("    ")
        content.append("    # 构建类型键")
        content.append("    type_key = f'{kind}:{version}'")
        content.append("    ")
        content.append("    # 查找类型")
        content.append("    target_type = TYPE_REGISTRY.get(type_key)")
        content.append("    if not target_type:")
        content.append("        # 尝试兼容版本")
        content.append("        if version.startswith('v0.'):")
        content.append("            alt_type_key = f'{kind}:v1.0.0'")
        content.append("            target_type = TYPE_REGISTRY.get(alt_type_key)")
        content.append("        if not target_type:")
        content.append("            raise ValueError(f'unknown type: {type_key}')")
        content.append("    ")
        content.append("    # 创建实例")
        content.append("    return _create_instance_from_data(target_type, json_data)")
        content.append("")
        
        content.append("def parse_mmodel_yaml(data: bytes) -> MModelCoreObject:")
        content.append('    """自动检测类型并解析YAML"""')
        content.append("    # 先解析header获取kind和version")
        content.append("    yaml_data = yaml.safe_load(data)")
        content.append("    ")
        content.append("    kind = yaml_data.get('kind')")
        content.append("    if not kind:")
        content.append("        raise ValueError('missing required field: kind')")
        content.append("    ")
        content.append("    metadata = yaml_data.get('metadata')")
        content.append("    if not metadata:")
        content.append("        raise ValueError('missing required field: metadata')")
        content.append("    ")
        content.append("    domain = metadata.get('domain') if isinstance(metadata, dict) else None")
        content.append("    if not domain:")
        content.append("        raise ValueError('missing required field: metadata.domain')")
        content.append("    ")
        content.append("    name = metadata.get('name') if isinstance(metadata, dict) else None")
        content.append("    if not name:")
        content.append("        raise ValueError('missing required field: metadata.name')")
        content.append("    ")
        content.append("    schema_info = yaml_data.get('schema', {})")
        content.append("    version = schema_info.get('version')")
        content.append("    if not version:")
        content.append("        raise ValueError('missing required field: schema.version')")
        content.append("    ")
        content.append("    spec = yaml_data.get('spec')")
        content.append("    if spec is None:")
        content.append("        raise ValueError('missing required field: spec')")
        content.append("    ")
        content.append("    if isinstance(spec, dict) and len(spec) == 0:")
        content.append("        raise ValueError('spec field cannot be empty')")
        content.append("    ")
        content.append("    # 构建类型键")
        content.append("    type_key = f'{kind}:{version}'")
        content.append("    ")
        content.append("    # 查找类型")
        content.append("    target_type = TYPE_REGISTRY.get(type_key)")
        content.append("    if not target_type:")
        content.append("        # 尝试兼容版本")
        content.append("        if version.startswith('v0.'):")
        content.append("            alt_type_key = f'{kind}:v1.0.0'")
        content.append("            target_type = TYPE_REGISTRY.get(alt_type_key)")
        content.append("        if not target_type:")
        content.append("            raise ValueError(f'unknown type: {type_key}')")
        content.append("    ")
        content.append("    # 创建实例")
        content.append("    return _create_instance_from_data(target_type, yaml_data)")
        content.append("")
    
    def _generate_utility_functions(self, content: List[str]):
        """生成工具函数"""
        content.append("# 导入MModelLinkObject用于类型检查")
        content.append("try:")
        content.append("    from .base_types import MModelLinkObject")
        content.append("except ImportError:")
        content.append("    MModelLinkObject = None")
        content.append("")
        
        content.append("# 工具函数")
        content.append("def is_core_object(obj: Any) -> bool:")
        content.append('    """判断对象是否实现了MModelCoreObject接口"""')
        content.append("    return isinstance(obj, MModelCoreObject)")
        content.append("")
        
        content.append("def is_link_object(obj: Any) -> bool:")
        content.append('    """判断对象是否实现了MModelLinkObject接口"""')
        content.append("    if MModelLinkObject is None:")
        content.append("        return False")
        content.append("    return isinstance(obj, MModelLinkObject)")
        content.append("")
        
        content.append("def get_object_metadata(obj: Any) -> Optional[Any]:")
        content.append('    """获取任意MModel对象的Metadata（如果支持）"""')
        content.append("    if is_core_object(obj):")
        content.append("        return obj.get_metadata()")
        content.append("    return None")
        content.append("")
        
        content.append("def get_object_schema(obj: Any) -> Optional[Any]:")
        content.append('    """获取任意MModel对象的Schema（如果支持）"""')
        content.append("    if is_core_object(obj):")
        content.append("        return obj.get_schema()")
        content.append("    return None")
        content.append("")
        
        content.append("def get_link_endpoints(obj: Any) -> Tuple[Optional[LinkEndpoint], Optional[LinkEndpoint]]:")
        content.append('    """获取Link对象的源和目标端点（如果支持）"""')
        content.append("    if is_link_object(obj):")
        content.append("        return obj.get_src(), obj.get_dest()")
        content.append("    return None, None")
        content.append("")
    
    def _generate_requirements(self):
        """生成requirements.txt文件"""
        content = []
        content.append("# MModel Python SDK Dependencies")
        content.append("# Generated by schema_python_generator_v2.py")
        content.append("")
        content.append("PyYAML>=6.0")
        content.append("dataclasses-json>=0.5.7")
        content.append("typing-extensions>=4.0.0")
        content.append("")
        content.append("# Optional dependencies for advanced features")
        content.append("# pydantic>=1.10.0  # Alternative to dataclasses")
        content.append("# marshmallow>=3.17.0  # Schema validation")
        content.append("# jsonschema>=4.0.0  # JSON schema validation")
        
        # 写入文件
        output_file = self.output_dir / "requirements.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成requirements.txt文件: {output_file.name}")
    
    def _generate_readme(self):
        """生成README.md文件"""
        content = []
        content.append("# MModel Python SDK V2")
        content.append("")
        content.append("这是由 `schema_python_generator_v2.py` 自动生成的 MModel Python SDK。")
        content.append("")
        content.append("## 特性")
        content.append("")
        content.append("- ✅ 使用 Python 的继承特性实现继承关系")
        content.append("- ✅ 生成简洁、高复用的代码")
        content.append("- ✅ 保留原始 schema 的结构关系")
        content.append("- ✅ 支持动态类型创建和解析")
        content.append("- ✅ 提供通用接口 `MModelCoreObject` 和 `MModelLinkObject`")
        content.append("- ✅ 支持 JSON/YAML 自动解析")
        content.append("- ✅ 类型安全的 Python 类型注解")
        content.append("")
        content.append("## 安装")
        content.append("")
        content.append("```bash")
        content.append("pip install -r requirements.txt")
        content.append("```")
        content.append("")
        content.append("## 使用示例")
        content.append("")
        content.append("### 基础用法")
        content.append("")
        content.append("```python")
        content.append("from mmodel import *")
        content.append("")
        content.append("# 判断对象类型")
        content.append("if is_core_object(obj):")
        content.append("    metadata = get_object_metadata(obj)")
        content.append("    schema = get_object_schema(obj)")
        content.append("    kind = obj.get_kind()  # 获取对象类型")
        content.append("")
        content.append("# 处理Link对象")
        content.append("if is_link_object(obj):")
        content.append("    src, dest = get_link_endpoints(obj)")
        content.append("    print(f'Link from {src.name} to {dest.name}')")
        content.append("```")
        content.append("")
        content.append("### 自动解析")
        content.append("")
        content.append("```python")
        content.append("import yaml")
        content.append("from mmodel import parse_mmodel_yaml, parse_mmodel_json")
        content.append("")
        content.append("# 自动解析YAML文件")
        content.append("with open('sls_front_metric.yaml', 'rb') as f:")
        content.append("    data = f.read()")
        content.append("    obj = parse_mmodel_yaml(data)")
        content.append("    print(f'Parsed object kind: {obj.get_kind()}')")
        content.append("    metadata = obj.get_metadata()")
        content.append("    print(f'Object name: {metadata.name}')")
        content.append("")
        content.append("# 自动解析JSON数据")
        content.append("json_data = b'{\"kind\":\"metric_set\",\"schema\":{\"version\":\"v1.0.0\"}}'")
        content.append("obj = parse_mmodel_json(json_data)")
        content.append("# obj 自动被解析为对应的类型")
        content.append("print(f'Object type: {type(obj).__name__}')")
        content.append("```")
        content.append("")
        content.append("### 手动解析")
        content.append("")
        content.append("```python")
        content.append("from mmodel import parse_json, parse_yaml")
        content.append("from mmodel import MetricSetV100  # 假设有这个类型")
        content.append("")
        content.append("# 解析为特定类型")
        content.append("with open('metric.json', 'rb') as f:")
        content.append("    data = f.read()")
        content.append("    metric_set = parse_json(data, MetricSetV100)")
        content.append("    print(f'Metric set name: {metric_set.metadata.name}')")
        content.append("```")
        content.append("")
        content.append("### 创建对象")
        content.append("")
        content.append("```python")
        content.append("from mmodel import SemanticString, LinkEndpoint")
        content.append("")
        content.append("# 创建语义字符串")
        content.append("desc = SemanticString(")
        content.append("    zh_cn='这是一个测试',")
        content.append("    en_us='This is a test'")
        content.append(")")
        content.append("print(str(desc))  # 输出: 这是一个测试")
        content.append("")
        content.append("# 从字典创建")
        content.append("desc2 = SemanticString.from_dict('通用描述')")
        content.append("desc3 = SemanticString.from_dict({")
        content.append("    'zh_cn': '中文描述',")
        content.append("    'en_us': 'English description'")
        content.append("})")
        content.append("")
        content.append("# 创建链接端点")
        content.append("endpoint = LinkEndpoint(")
        content.append("    domain='infrastructure',")
        content.append("    kind='service',")
        content.append("    name='user-service'")
        content.append(")")
        content.append("```")
        content.append("")
        content.append("## 接口说明")
        content.append("")
        content.append("### 基础接口")
        content.append("")
        content.append("- `MModelObject`: 所有 MModel 对象的基础接口")
        content.append("  - `get_kind() -> str`: 获取对象的类型标识")
        content.append("  - `validate() -> Optional[Exception]`: 验证对象是否符合 schema 定义")
        content.append("")
        content.append("- `MModelCoreObject`: 继承自 `MModelObject`，core 目录下所有对象的接口")
        content.append("  - `get_schema() -> Optional[Schema]`: 获取对象的 Schema 信息")
        content.append("  - `get_metadata() -> Optional[Metadata]`: 获取对象的 Metadata 信息")
        content.append("")
        content.append("- `MModelLinkObject`: 继承自 `MModelCoreObject`，所有 link 类型对象的接口")
        content.append("  - `get_src() -> Optional[LinkEndpoint]`: 获取源端点信息")
        content.append("  - `get_dest() -> Optional[LinkEndpoint]`: 获取目标端点信息")
        content.append("")
        content.append("### 工具函数")
        content.append("")
        content.append("- `is_core_object(obj: Any) -> bool`: 判断对象是否实现了 `MModelCoreObject` 接口")
        content.append("- `is_link_object(obj: Any) -> bool`: 判断对象是否实现了 `MModelLinkObject` 接口")
        content.append("- `get_object_metadata(obj: Any) -> Optional[Metadata]`: 获取任意 MModel 对象的 Metadata")
        content.append("- `get_object_schema(obj: Any) -> Optional[Schema]`: 获取任意 MModel 对象的 Schema")
        content.append("- `get_link_endpoints(obj: Any) -> tuple[Optional[LinkEndpoint], Optional[LinkEndpoint]]`: 获取 Link 对象的源和目标端点")
        content.append("")
        content.append("### 解析函数")
        content.append("")
        content.append("- `parse_json(data: bytes, target_type: Type) -> Any`: 从 JSON 数据解析为指定类型")
        content.append("- `parse_yaml(data: bytes, target_type: Type) -> Any`: 从 YAML 数据解析为指定类型")
        content.append("- `parse_mmodel_json(data: bytes) -> MModelCoreObject`: 自动检测类型并解析 JSON")
        content.append("- `parse_mmodel_yaml(data: bytes) -> MModelCoreObject`: 自动检测类型并解析 YAML")
        content.append("")
        content.append("## 版本兼容性")
        content.append("")
        content.append("- 支持 v0.x.x 版本自动映射到 v1.0.0")
        content.append("- v1 主版本内向后兼容")
        content.append("- 遵循语义化版本规范")
        content.append("")
        content.append("## 开发")
        content.append("")
        content.append("此 SDK 由 `schema_python_generator_v2.py` 自动生成，请勿手动修改生成的代码。")
        content.append("")
        content.append("如需修改，请更新 schemas 目录中的 YAML 文件，然后重新运行生成器：")
        content.append("")
        content.append("```bash")
        content.append("python scripts/generators/schema_python_generator_v2.py")
        content.append("```")
        
        # 写入文件
        output_file = self.output_dir / "README.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成README.md文件: {output_file.name}")


def main():
    """主函数"""
    print("🚀 MModel Schema Python SDK Generator V2 启动")
    print("=" * 50)
    
    # 配置路径
    schemas_dir = "schemas"
    output_dir = "sdk/python/mmodel"
    
    # 检查必要的目录
    if not os.path.exists(schemas_dir):
        print(f"❌ schemas目录不存在: {schemas_dir}")
        return
    
    # 创建生成器
    generator = PythonCodeGeneratorV2(schemas_dir, output_dir)
    
    try:
        # 生成所有代码
        generator.generate_all()
        
        print(f"\n✅ Python SDK V2代码已生成到: {output_dir}")
        print("\n📝 使用说明:")
        print("1. 将生成的代码复制到您的Python项目中")
        print("2. 安装依赖: pip install -r requirements.txt")
        print("3. 导入包: from mmodel import *")
        print("\n🎯 V2版本特性:")
        print("- 使用Python的继承特性实现继承关系")
        print("- 生成简洁、高复用的代码")
        print("- 保留原始schema的结构关系")
        print("- 支持动态类型创建和解析")
        print("- 提供通用接口MModelCoreObject和MModelLinkObject")
        print("- 类型安全的Python类型注解")
        print("\n📚 接口使用示例:")
        print("# 判断对象类型")
        print("if is_core_object(obj):")
        print("    metadata = get_object_metadata(obj)")
        print("    schema = get_object_schema(obj)")
        print("    kind = obj.get_kind()  # 获取对象类型")
        print("")
        print("# 处理Link对象")
        print("if is_link_object(obj):")
        print("    src, dest = get_link_endpoints(obj)")
        print("    print(f'Link from {src.name} to {dest.name}')")
        print("")
        print("# 自动解析YAML文件")
        print("with open('sls_front_metric.yaml', 'rb') as f:")
        print("    data = f.read()")
        print("    obj = parse_mmodel_yaml(data)")
        print("    print(f'Parsed object kind: {obj.get_kind()}')")
        print("    metadata = obj.get_metadata()")
        print("    print(f'Object name: {metadata.name}')")
        print("")
        print("# 自动解析JSON数据")
        print("json_data = b'{\"kind\":\"metric_set\",\"schema\":{\"version\":\"v1.0.0\"}}'")
        print("obj = parse_mmodel_json(json_data)")
        print("# obj 自动被解析为对应的类型")
        print("print(f'Object type: {type(obj).__name__}')")
        print("")
        print("# 创建语义字符串")
        print("desc = SemanticString(zh_cn='这是一个测试', en_us='This is a test')")
        print("print(str(desc))  # 输出: 这是一个测试")
        
    except Exception as e:
        print(f"\n❌ 生成过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 
