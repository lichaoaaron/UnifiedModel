#!/usr/bin/env python3
"""
MModel Schema Java SDK Generator V2

这个脚本基于原始的schemas目录，生成高复用的Java SDK代码。
利用Java的继承特性来实现继承关系，生成更优雅的代码结构。

主要特性：
1. 直接从schemas目录读取，保留原始的继承关系
2. 为共享类型生成独立的类定义
3. 使用Java的继承和接口实现extends
4. 生成更简洁、高复用的代码
5. 使用FastJSON进行JSON序列化/反序列化
6. 支持类型注解和Builder模式
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict, OrderedDict
import re


class JavaCodeGeneratorV2:
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
        
        # 存储生成的Java类型名称映射
        self.java_type_mapping: Dict[str, str] = {}  # type_ref -> Java类型名
        
        # 记录依赖关系
        self.type_dependencies: Dict[str, Set[str]] = defaultdict(set)  # type -> dependencies
        
        # 存储内联类定义
        self.inline_classes: List[Tuple[str, List[str]]] = []
        
        # 基础类型映射
        self.primitive_types = {
            "string": "String",
            "number": "Double",
            "integer": "Long",
            "float": "Double",
            "boolean": "Boolean",
            "bool": "Boolean",
            "object": "Map<String, Object>",
            "array": "List<Object>",
            "map": "Map<String, Object>",
            "any": "Object",
            "json": "Object",
            "json_object": "Map<String, Object>",
            "json_array": "List<Object>",
            "time": "LocalDateTime",
            "enum": "String",
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
        """生成所有的Java代码"""
        print("\n🚀 开始生成Java SDK代码 V2...")
        
        # 创建输出目录结构
        self.output_dir.mkdir(parents=True, exist_ok=True)
        src_dir = self.output_dir / "src" / "main" / "java" / "com" / "mmodel"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 加载所有定义
        self.load_all_definitions()
        
        # 2. 分析依赖关系
        self.analyze_dependencies()
        
        # 3. 生成基础类型文件
        self._generate_base_types(src_dir)
        
        # 4. 生成共享类型文件
        self._generate_shared_types(src_dir)
        
        # 5. 生成schema文件
        self._generate_schema_files(src_dir)
        
        # 6. 生成主包文件
        self._generate_main_package(src_dir)
        
        # 7. 生成Maven配置文件
        self._generate_maven_config()
        
        # 8. 生成测试文件
        self._generate_test_files()
        
        print("\n✅ Java SDK V2代码生成完成！")
    
    def _generate_base_types(self, src_dir: Path):
        """生成基础类型定义"""
        # 生成SemanticString.java
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel;")
        content.append("")
        content.append("import com.alibaba.fastjson.annotation.JSONField;")
        content.append("import java.util.*;")
        content.append("")
        content.append("/**")
        content.append(" * 支持多语言的语义字符串")
        content.append(" */")
        content.append("public class SemanticString {")
        content.append("    @JSONField(name = \"zh_cn\")")
        content.append("    private String zhCn;")
        content.append("")
        content.append("    @JSONField(name = \"en_us\")")
        content.append("    private String enUs;")
        content.append("")
        content.append("    public SemanticString() {}")
        content.append("")
        content.append("    public SemanticString(String zhCn, String enUs) {")
        content.append("        this.zhCn = zhCn;")
        content.append("        this.enUs = enUs;")
        content.append("    }")
        content.append("")
        content.append("    /**")
        content.append("     * 返回中文描述，如果没有则返回英文")
        content.append("     */")
        content.append("    @Override")
        content.append("    public String toString() {")
        content.append("        if (zhCn != null && !zhCn.isEmpty()) {")
        content.append("            return zhCn;")
        content.append("        }")
        content.append("        return enUs != null ? enUs : \"\";")
        content.append("    }")
        content.append("")
        content.append("    /**")
        content.append("     * 根据语言代码获取对应文本")
        content.append("     */")
        content.append("    public String get(String lang) {")
        content.append("        if (\"zh_cn\".equals(lang) || \"zh\".equals(lang)) {")
        content.append("            return zhCn != null ? zhCn : \"\";")
        content.append("        } else if (\"en_us\".equals(lang) || \"en\".equals(lang)) {")
        content.append("            return enUs != null ? enUs : \"\";")
        content.append("        }")
        content.append("        return \"\";")
        content.append("    }")
        content.append("")
        content.append("    /**")
        content.append("     * 从字符串或Map创建SemanticString")
        content.append("     */")
        content.append("    public static SemanticString fromObject(Object data) {")
        content.append("        if (data instanceof String) {")
        content.append("            return new SemanticString((String) data, (String) data);")
        content.append("        } else if (data instanceof Map) {")
        content.append("            Map<?, ?> map = (Map<?, ?>) data;")
        content.append("            String zhCn = (String) map.get(\"zh_cn\");")
        content.append("            String enUs = (String) map.get(\"en_us\");")
        content.append("            return new SemanticString(zhCn, enUs);")
        content.append("        }")
        content.append("        return new SemanticString();")
        content.append("    }")
        content.append("")
        content.append("    // Getters and Setters")
        content.append("    public String getZhCn() { return zhCn; }")
        content.append("    public void setZhCn(String zhCn) { this.zhCn = zhCn; }")
        content.append("    public String getEnUs() { return enUs; }")
        content.append("    public void setEnUs(String enUs) { this.enUs = enUs; }")
        content.append("}")
        
        # 写入SemanticString.java
        output_file = src_dir / "SemanticString.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print(f"✅ 生成基础类型文件: {output_file.name}")
        
        # 生成LinkEndpoint.java
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel;")
        content.append("")
        content.append("/**")
        content.append(" * 表示Link的端点信息")
        content.append(" */")
        content.append("public class LinkEndpoint {")
        content.append("    private String domain;")
        content.append("    private String kind;")
        content.append("    private String name;")
        content.append("    private String filter;")
        content.append("")
        content.append("    public LinkEndpoint() {}")
        content.append("")
        content.append("    public LinkEndpoint(String domain, String kind, String name, String filter) {")
        content.append("        this.domain = domain;")
        content.append("        this.kind = kind;")
        content.append("        this.name = name;")
        content.append("        this.filter = filter;")
        content.append("    }")
        content.append("")
        content.append("    // Getters and Setters")
        content.append("    public String getDomain() { return domain; }")
        content.append("    public void setDomain(String domain) { this.domain = domain; }")
        content.append("    public String getKind() { return kind; }")
        content.append("    public void setKind(String kind) { this.kind = kind; }")
        content.append("    public String getName() { return name; }")
        content.append("    public void setName(String name) { this.name = name; }")
        content.append("    public String getFilter() { return filter; }")
        content.append("    public void setFilter(String filter) { this.filter = filter; }")
        content.append("}")
        
        # 写入LinkEndpoint.java
        output_file = src_dir / "LinkEndpoint.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print(f"✅ 生成基础类型文件: {output_file.name}")
        
        # 生成MModelObject.java
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel;")
        content.append("")
        content.append("/**")
        content.append(" * 所有MModel对象的基础接口")
        content.append(" */")
        content.append("public interface MModelObject {")
        content.append("    /**")
        content.append("     * 获取对象的类型标识")
        content.append("     */")
        content.append("    String getKind();")
        content.append("")
        content.append("    /**")
        content.append("     * 验证对象是否符合schema定义")
        content.append("     */")
        content.append("    default Exception validate() {")
        content.append("        // TODO: 实现验证逻辑")
        content.append("        return null;")
        content.append("    }")
        content.append("}")
        
        # 写入MModelObject.java
        output_file = src_dir / "MModelObject.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print(f"✅ 生成基础类型文件: {output_file.name}")
        
        # 生成MModelCoreObject.java
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel;")
        content.append("")
        content.append("/**")
        content.append(" * 所有core目录对象的接口")
        content.append(" */")
        content.append("public interface MModelCoreObject extends MModelObject {")
        content.append("    /**")
        content.append("     * 获取对象的Schema信息")
        content.append("     */")
        content.append("    Object getSchema();")
        content.append("")
        content.append("    /**")
        content.append("     * 获取对象的Metadata信息")
        content.append("     */")
        content.append("    Object getMetadata();")
        content.append("}")
        
        # 写入MModelCoreObject.java
        output_file = src_dir / "MModelCoreObject.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print(f"✅ 生成基础类型文件: {output_file.name}")
        
        # 生成MModelLinkObject.java
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel;")
        content.append("")
        content.append("/**")
        content.append(" * 所有link类型对象的接口")
        content.append(" */")
        content.append("public interface MModelLinkObject extends MModelCoreObject {")
        content.append("    /**")
        content.append("     * 获取源对象信息")
        content.append("     */")
        content.append("    LinkEndpoint getSrc();")
        content.append("")
        content.append("    /**")
        content.append("     * 获取目标对象信息")
        content.append("     */")
        content.append("    LinkEndpoint getDest();")
        content.append("}")
        
        # 写入MModelLinkObject.java
        output_file = src_dir / "MModelLinkObject.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print(f"✅ 生成基础类型文件: {output_file.name}")
    
    def _generate_shared_types(self, src_dir: Path):
        """生成共享类型定义"""
        # 按照依赖顺序生成类型
        generated = set()
        
        # 先生成没有依赖的类型
        for type_key in self.type_registry:
            if type_key not in self.type_dependencies or not self.type_dependencies[type_key]:
                if type_key not in generated:
                    self._generate_type_class(src_dir, type_key, generated)
        
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
                        self._generate_type_class(src_dir, type_key, generated)
        
        print(f"✅ 生成共享类型文件完成")
    
    def _generate_type_class(self, src_dir: Path, type_key: str, generated: Set[str]):
        """生成单个类型的class定义"""
        type_def = self.type_registry.get(type_key)
        if not type_def or not isinstance(type_def, dict):
            return
            
        # 跳过schema类型，它们会在单独的文件中生成
        if type_def.get('file') == 'core':
            return
            
        # 生成Java类型名
        java_type_name = self._get_java_type_name(type_key)
        self.java_type_mapping[type_key] = java_type_name
        
        # 添加到已生成集合
        generated.add(type_key)
        
        # 获取spec
        spec = type_def.get('spec', type_def)
        
        # 生成类定义
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel.shared;")
        content.append("")
        content.append("import com.alibaba.fastjson.annotation.JSONField;")
        content.append("import com.mmodel.*;")
        content.append("import java.time.LocalDateTime;")
        content.append("import java.util.*;")
        content.append("")
        
        # 生成继承关系
        implements_list = []
        extends_class = None
        
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_type = self._get_java_type_for_ref(extend_ref)
                if parent_type and parent_type != "Object":
                    if parent_type.endswith("Object"):  # 接口
                        implements_list.append(parent_type)
                    else:  # 类
                        extends_class = parent_type
        
        if not implements_list and not extends_class:
            implements_list = ["MModelObject"]
        
        # 生成类定义
        desc = self._get_description(spec.get('description', ''))
        if desc:
            content.append("/**")
            content.append(f" * {desc}")
            content.append(" */")
        
        class_def = f"public class {java_type_name}"
        if extends_class:
            class_def += f" extends {extends_class}"
        if implements_list:
            class_def += f" implements {', '.join(implements_list)}"
        content.append(f"{class_def} {{")
        
        # 共享类型使用简单类型解析（Map<String, Object>），不生成内联类，
        # 以保证与测试代码和下游 schema 的兼容性
        if 'properties' in spec and isinstance(spec['properties'], dict):
            inherited_props = self._get_inherited_properties(spec)
            
            for prop_name, prop_spec in spec['properties'].items():
                if prop_name not in inherited_props:
                    java_type = self._get_java_type(prop_spec, prop_name, java_type_name)
                    self._generate_class_field_simple(content, prop_name, java_type, prop_spec)
        
        # 生成getKind方法
        content.append("")
        content.append("    @Override")
        content.append("    public String getKind() {")
        content.append(f"        return \"{type_def.get('name', type_key.split(':')[0])}\";")
        content.append("    }")
        
        content.append("}")
        
        # 写入文件
        shared_dir = src_dir / "shared"
        shared_dir.mkdir(exist_ok=True)
        output_file = shared_dir / f"{java_type_name}.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成共享类型: {java_type_name}")
    
    def _generate_schema_files(self, src_dir: Path):
        """为每个schema生成独立的文件"""
        for schema_name, schema_content in self.schema_registry.items():
            self._generate_single_schema_file(src_dir, schema_name, schema_content)
    
    def _generate_single_schema_file(self, src_dir: Path, schema_name: str, schema_content: Dict[str, Any]):
        """生成单个schema文件"""
        # 生成每个版本的class
        if 'versions' in schema_content:
            for version in schema_content['versions']:
                version_name = version.get('name', 'v1')
                spec = version.get('spec', {})
                
                # 生成class名称
                type_key = f"{schema_name}:{version_name}"
                java_type_name = self._get_java_type_name(type_key)
                self.java_type_mapping[type_key] = java_type_name
                
                # 生成class定义
                self._generate_schema_class(src_dir, java_type_name, spec, schema_name)
    
    def _generate_schema_class(self, src_dir: Path, class_name: str, spec: Dict[str, Any], schema_name: str):
        """生成schema的class定义"""
        # 初始化当前schema的内联类列表
        schema_inline_classes = []
        
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel.schema;")
        content.append("")
        content.append("import com.alibaba.fastjson.annotation.JSONField;")
        content.append("import com.mmodel.*;")
        content.append("import com.mmodel.shared.*;")
        content.append("import java.time.LocalDateTime;")
        content.append("import java.util.*;")
        content.append("")
        
        # 确定基类和接口
        implements_list = []
        extends_class = None
        
        # 检查是否是link类型
        if schema_name.endswith('_link'):
            implements_list.append("MModelLinkObject")
        else:
            implements_list.append("MModelCoreObject")
        
        # 处理extends
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_type = self._get_java_type_for_ref(extend_ref)
                if parent_type and parent_type != "Object":
                    if not parent_type.endswith("Object"):  # 不是接口
                        extends_class = parent_type
        
        # 生成类定义
        desc = self._get_description(spec.get('description', ''))
        if desc:
            content.append("/**")
            content.append(f" * {desc}")
            content.append(" */")
        else:
            content.append("/**")
            content.append(f" * {schema_name} schema class")
            content.append(" */")
        
        class_def = f"public class {class_name}"
        if extends_class:
            class_def += f" extends {extends_class}"
        if implements_list:
            class_def += f" implements {', '.join(implements_list)}"
        content.append(f"{class_def} {{")
        
        # 记录已生成的字段名，用于检查是否需要生成Override方法
        generated_fields = set()
        
        # 处理properties
        if 'properties' in spec and isinstance(spec['properties'], dict):
            # 收集已经从父类继承的属性
            inherited_props = self._get_inherited_properties(spec)
            
            for prop_name, prop_spec in spec['properties'].items():
                if prop_name not in inherited_props:
                    # 检查是否需要生成内联类
                    java_type = self._get_java_type_for_schema(prop_spec, prop_name, class_name, schema_inline_classes)
                    self._generate_class_field_simple(content, prop_name, java_type, prop_spec)
                    generated_fields.add(prop_name)
        
        # 始终生成getKind方法，返回固定的类型名称
        content.append("")
        content.append("    @Override")
        content.append("    public String getKind() {")
        content.append(f"        return \"{schema_name}\";")
        content.append("    }")
        
        # 只有在没有生成schema和metadata字段时才生成接口方法
        if ("MModelCoreObject" in implements_list or "MModelLinkObject" in implements_list):
            if 'schema' not in generated_fields:
                content.append("")
                content.append("    @Override")
                content.append("    public Object getSchema() {")
                content.append("        return this.schema;")
                content.append("    }")
            
            if 'metadata' not in generated_fields:
                content.append("")
                content.append("    @Override")
                content.append("    public Object getMetadata() {")
                content.append("        return this.metadata;")
                content.append("    }")
        
        # 如果是link类型，生成MModelLinkObject接口方法
        if "MModelLinkObject" in implements_list:
            content.append("")
            content.append("    @Override")
            content.append("    public LinkEndpoint getSrc() {")
            content.append("        // TODO: 实现获取源端点逻辑")
            content.append("        return null;")
            content.append("    }")
            content.append("")
            content.append("    @Override")
            content.append("    public LinkEndpoint getDest() {")
            content.append("        // TODO: 实现获取目标端点逻辑")
            content.append("        return null;")
            content.append("    }")
        
        # 生成所有内联类（作为静态内部类）
        for inline_class_name, inline_class_content in schema_inline_classes:
            content.append("")
            # 调整缩进，将内联类内容缩进一级
            for line in inline_class_content:
                if line:  # 非空行才缩进
                    content.append("    " + line)
                else:
                    content.append(line)
        
        content.append("}")  # 关闭主类
        
        # 写入文件
        schema_dir = src_dir / "schema"
        schema_dir.mkdir(exist_ok=True)
        output_file = schema_dir / f"{class_name}.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成schema文件: {class_name}")
    
    def _generate_main_package(self, src_dir: Path):
        """生成主包文件"""
        content = []
        content.append("// Code generated by schema_java_generator_v2.py. DO NOT EDIT.")
        content.append("")
        content.append("package com.mmodel;")
        content.append("")
        content.append("import com.alibaba.fastjson.JSON;")
        content.append("import com.alibaba.fastjson.TypeReference;")
        content.append("import com.mmodel.schema.*;")
        content.append("import java.util.*;")
        content.append("import java.util.function.Supplier;")
        content.append("")
        
        content.append("/**")
        content.append(" * MModel Java SDK 主包")
        content.append(" */")
        content.append("public class MModel {")
        content.append("    ")
        content.append("    public static final String VERSION = \"2.0.0\";")
        content.append("")
        
        # 生成类型注册表
        content.append("    // 类型注册表")
        content.append("    private static final Map<String, Supplier<MModelCoreObject>> TYPE_REGISTRY = new HashMap<>();")
        content.append("")
        content.append("    static {")
        content.append("        // 注册所有类型")
        
        # 注册所有生成的类型
        for type_key, java_type_name in sorted(self.java_type_mapping.items()):
            if self.type_registry.get(type_key, {}).get('file') != 'core':
                continue
            content.append(f"        TYPE_REGISTRY.put(\"{type_key}\", {java_type_name}::new);")
        
        content.append("    }")
        content.append("")
        
        # 生成解析函数
        content.append("    /**")
        content.append("     * 从JSON字符串解析MModel对象")
        content.append("     */")
        content.append("    public static <T> T parseJson(String jsonStr, Class<T> clazz) {")
        content.append("        return JSON.parseObject(jsonStr, clazz);")
        content.append("    }")
        content.append("")
        
        content.append("    /**")
        content.append("     * 自动检测类型并解析JSON")
        content.append("     */")
        content.append("    public static MModelCoreObject parseMModelJson(String jsonStr) {")
        content.append("        // 先解析header获取kind和version")
        content.append("        Map<String, Object> header = JSON.parseObject(jsonStr, new TypeReference<Map<String, Object>>(){});")
        content.append("        ")
        content.append("        String kind = (String) header.get(\"kind\");")
        content.append("        if (kind == null || kind.isEmpty()) {")
        content.append("            throw new IllegalArgumentException(\"missing required field: kind\");")
        content.append("        }")
        content.append("        ")
        content.append("        Map<String, Object> schema = (Map<String, Object>) header.get(\"schema\");")
        content.append("        if (schema == null) {")
        content.append("            throw new IllegalArgumentException(\"missing required field: schema\");")
        content.append("        }")
        content.append("        ")
        content.append("        String version = (String) schema.get(\"version\");")
        content.append("        if (version == null || version.isEmpty()) {")
        content.append("            throw new IllegalArgumentException(\"missing required field: schema.version\");")
        content.append("        }")
        content.append("        ")
        content.append("        // 构建类型键")
        content.append("        String typeKey = kind + \":\" + version;")
        content.append("        ")
        content.append("        // 查找类型工厂")
        content.append("        Supplier<MModelCoreObject> factory = TYPE_REGISTRY.get(typeKey);")
        content.append("        if (factory == null) {")
        content.append("            // 尝试兼容版本")
        content.append("            if (version.startsWith(\"v0.\")) {")
        content.append("                String altTypeKey = kind + \":v1.0.0\";")
        content.append("                factory = TYPE_REGISTRY.get(altTypeKey);")
        content.append("            }")
        content.append("            if (factory == null) {")
        content.append("                throw new IllegalArgumentException(\"unknown type: \" + typeKey);")
        content.append("            }")
        content.append("        }")
        content.append("        ")
        content.append("        // 解析为具体类型")
        content.append("        MModelCoreObject obj = factory.get();")
        content.append("        return JSON.parseObject(jsonStr, obj.getClass());")
        content.append("    }")
        content.append("")
        
        # 生成工具函数
        content.append("    /**")
        content.append("     * 判断对象是否实现了MModelCoreObject接口")
        content.append("     */")
        content.append("    public static boolean isCoreObject(Object obj) {")
        content.append("        return obj instanceof MModelCoreObject;")
        content.append("    }")
        content.append("")
        
        content.append("    /**")
        content.append("     * 判断对象是否实现了MModelLinkObject接口")
        content.append("     */")
        content.append("    public static boolean isLinkObject(Object obj) {")
        content.append("        return obj instanceof MModelLinkObject;")
        content.append("    }")
        content.append("")
        
        content.append("    /**")
        content.append("     * 获取任意MModel对象的Metadata（如果支持）")
        content.append("     */")
        content.append("    public static Object getObjectMetadata(Object obj) {")
        content.append("        if (obj instanceof MModelCoreObject) {")
        content.append("            return ((MModelCoreObject) obj).getMetadata();")
        content.append("        }")
        content.append("        return null;")
        content.append("    }")
        content.append("")
        
        content.append("    /**")
        content.append("     * 获取任意MModel对象的Schema（如果支持）")
        content.append("     */")
        content.append("    public static Object getObjectSchema(Object obj) {")
        content.append("        if (obj instanceof MModelCoreObject) {")
        content.append("            return ((MModelCoreObject) obj).getSchema();")
        content.append("        }")
        content.append("        return null;")
        content.append("    }")
        content.append("")
        
        content.append("    /**")
        content.append("     * 获取Link对象的源和目标端点（如果支持）")
        content.append("     */")
        content.append("    public static LinkEndpoint[] getLinkEndpoints(Object obj) {")
        content.append("        if (obj instanceof MModelLinkObject) {")
        content.append("            MModelLinkObject linkObj = (MModelLinkObject) obj;")
        content.append("            return new LinkEndpoint[]{linkObj.getSrc(), linkObj.getDest()};")
        content.append("        }")
        content.append("        return new LinkEndpoint[]{null, null};")
        content.append("    }")
        
        content.append("}")
        
        # 写入文件
        output_file = src_dir / "MModel.java"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"✅ 生成主包文件: {output_file.name}")
    
    def _generate_maven_config(self):
        """生成Maven配置文件"""
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    
    <groupId>com.mmodel</groupId>
    <artifactId>mmodel-java-sdk</artifactId>
    <version>2.0.0</version>
    <packaging>jar</packaging>
    
    <name>MModel Java SDK</name>
    <description>Java SDK for MModel Schema</description>
    
    <properties>
        <maven.compiler.source>8</maven.compiler.source>
        <maven.compiler.target>8</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    
    <dependencies>
        <dependency>
            <groupId>com.alibaba</groupId>
            <artifactId>fastjson</artifactId>
            <version>2.0.25</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.8.1</version>
                <configuration>
                    <source>8</source>
                    <target>8</target>
                </configuration>
            </plugin>
            
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.2.1</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>"""
        
        # 写入pom.xml
        pom_file = self.output_dir / "pom.xml"
        with open(pom_file, 'w', encoding='utf-8') as f:
            f.write(pom_content)
        
        # 生成README
        readme_content = """# MModel Java SDK V2

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
String jsonData = "{\\"kind\\":\\"metric_set\\",\\"schema\\":{\\"version\\":\\"v1.0.0\\"}}";
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
"""
        
        readme_file = self.output_dir / "README.md"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        print(f"✅ 生成Maven配置文件: pom.xml")
        print(f"✅ 生成README文件: README.md")
    
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
    
    def _get_java_type_for_ref(self, ref: str) -> str:
        """获取引用类型对应的Java类型"""
        # 如果没有版本号，添加默认版本
        if ':' not in ref:
            ref = f"{ref}:v1"
        
        # 如果已经在映射中，使用映射的名称
        if ref in self.java_type_mapping:
            return self.java_type_mapping[ref]
        elif ref in self.type_registry:
            java_type_name = self._get_java_type_name(ref)
            self.java_type_mapping[ref] = java_type_name
            return java_type_name
        else:
            return "Object"
    
    def _generate_class_field(self, content: List[str], field_name: str, field_spec: Dict[str, Any], parent_class_name: str):
        """生成类字段"""
        if field_spec is None:
            return
            
        # 获取字段描述
        desc = ""
        if isinstance(field_spec, dict) and 'description' in field_spec:
            desc = self._get_description(field_spec['description'])
        
        # 获取Java类型
        java_type = self._get_java_type(field_spec, field_name, parent_class_name)
        
        # 生成字段
        java_field_name = self._to_java_field_name(field_name)
        
        if desc:
            content.append(f"    /**")
            content.append(f"     * {desc}")
            content.append(f"     */")
        
        content.append(f"    @JSONField(name = \"{field_name}\")")
        content.append(f"    private {java_type} {java_field_name};")
        content.append("")
        
        # 生成getter和setter
        # 正确处理驼峰命名：第一个字母大写
        capitalized_field_name = java_field_name[0].upper() + java_field_name[1:] if java_field_name else ""
        getter_name = f"get{capitalized_field_name}"
        setter_name = f"set{capitalized_field_name}"
        
        # 对于kind字段，不生成getter（因为会在后面生成Override方法）
        if field_name != "kind":
            content.append(f"    public {java_type} {getter_name}() {{")
            content.append(f"        return {java_field_name};")
            content.append("    }")
            content.append("")
        
        content.append(f"    public void {setter_name}({java_type} {java_field_name}) {{")
        content.append(f"        this.{java_field_name} = {java_field_name};")
        content.append("    }")
        content.append("")
    
    def _generate_class_field_simple(self, content: List[str], field_name: str, java_type: str, field_spec: Dict[str, Any]):
        """生成简单的类字段，不包含getter/setter"""
        if field_spec is None:
            return
            
        # 获取字段描述
        desc = ""
        if isinstance(field_spec, dict) and 'description' in field_spec:
            desc = self._get_description(field_spec['description'])
        
        # 生成字段
        java_field_name = self._to_java_field_name(field_name)
        
        if desc:
            content.append(f"    /**")
            content.append(f"     * {desc}")
            content.append(f"     */")
        
        content.append(f"    @JSONField(name = \"{field_name}\")")
        content.append(f"    private {java_type} {java_field_name};")
        content.append("")
        
        # 生成getter和setter
        capitalized_field_name = java_field_name[0].upper() + java_field_name[1:] if java_field_name else ""
        getter_name = f"get{capitalized_field_name}"
        setter_name = f"set{capitalized_field_name}"
        
        # 对于kind字段，不生成getter（因为会在后面生成Override方法）
        if field_name != "kind":
            content.append(f"    public {java_type} {getter_name}() {{")
            content.append(f"        return {java_field_name};")
            content.append("    }")
            content.append("")
        
        content.append(f"    public void {setter_name}({java_type} {java_field_name}) {{")
        content.append(f"        this.{java_field_name} = {java_field_name};")
        content.append("    }")
        content.append("")
    
    def _get_java_type_for_schema(self, spec: Dict[str, Any], field_name: str, parent_class_name: str, inline_classes: List[Tuple[str, List[str]]]) -> str:
        """获取schema字段的Java类型，并生成必要的内联类"""
        if not isinstance(spec, dict):
            return "Object"
        
        # 处理type_ref
        if 'type_ref' in spec:
            return self._get_java_type_for_ref(spec['type_ref'])
        
        # 处理extends（属性级别的extends）
        if 'extends' in spec and isinstance(spec['extends'], list):
            # 如果有extends但没有自己的properties，直接使用父类型
            if 'properties' not in spec or not spec['properties']:
                for extend_ref in spec['extends']:
                    parent_type = self._get_java_type_for_ref(extend_ref)
                    if parent_type and parent_type != "Object":
                        return parent_type
            else:
                # 如果有extends且有自己的properties，需要生成内联类
                field_name_camel = self._to_java_field_name(field_name)
                inline_class_name = f"{parent_class_name}{field_name_camel[0].upper() + field_name_camel[1:] if field_name_camel else ''}"
                self._generate_inline_class_with_extends(inline_class_name, spec, inline_classes)
                return inline_class_name
        
        # 处理constraint中的类型
        if 'constraint' in spec and isinstance(spec['constraint'], dict):
            constraint = spec['constraint']
            
            # 处理array约束
            if 'array' in constraint and 'item' in constraint['array']:
                item_spec = constraint['array']['item']
                item_type = self._get_java_type_for_schema(item_spec, f"{field_name}_item", parent_class_name, inline_classes)
                return f"List<{item_type}>"
            
            # 处理map约束
            if 'map' in constraint:
                value_spec = constraint['map'].get('value', {'type': 'string'})
                value_type = self._get_java_type_for_schema(value_spec, f"{field_name}_value", parent_class_name, inline_classes)
                return f"Map<String, {value_type}>"
        
        # 处理基本类型
        if 'type' in spec:
            base_type = spec['type']
            
            # 检查是否是自定义类型
            if base_type not in self.primitive_types:
                # 尝试查找类型定义
                type_ref = f"{base_type}:v1"
                if type_ref in self.type_registry:
                    type_name = self._get_java_type_name(type_ref)
                    return type_name
                
                # 特殊处理semantic_string
                if base_type == 'semantic_string':
                    return "SemanticString"
            
            # 处理object类型
            if base_type == 'object' and 'properties' in spec:
                # 检查是否是semantic_string的展开形式
                props = spec['properties']
                if isinstance(props, dict) and set(props.keys()) <= {"zh_cn", "en_us"}:
                    return "SemanticString"
                
                # 生成内联class
                if field_name and parent_class_name:
                    field_name_camel = self._to_java_field_name(field_name)
                    inline_class_name = f"{parent_class_name}{field_name_camel[0].upper() + field_name_camel[1:] if field_name_camel else ''}"
                    self._generate_inline_class_with_properties(inline_class_name, spec, inline_classes)
                    return inline_class_name
                else:
                    return "Map<String, Object>"
            
            return self.primitive_types.get(base_type, "Object")
        
        # 如果没有type字段，但有properties，也处理为object
        if 'properties' in spec and isinstance(spec['properties'], dict):
            # 生成内联class
            if field_name and parent_class_name:
                field_name_camel = self._to_java_field_name(field_name)
                inline_class_name = f"{parent_class_name}{field_name_camel[0].upper() + field_name_camel[1:] if field_name_camel else ''}"
                self._generate_inline_class_with_properties(inline_class_name, spec, inline_classes)
                return inline_class_name
            else:
                return "Map<String, Object>"
        
        return "Object"
    
    def _generate_inline_class_with_properties(self, class_name: str, spec: Dict[str, Any], inline_classes: List[Tuple[str, List[str]]]):
        """生成带有properties的内联类（用于object类型）"""
        content = []
        
        # 生成类注释
        desc = self._get_description(spec.get('description', ''))
        if desc:
            content.append("/**")
            content.append(f" * {desc}")
            content.append(" */")
        else:
            content.append("/**")
            content.append(f" * {class_name} inline class")
            content.append(" */")
        
        content.append(f"public static class {class_name} {{")
        
        # 处理properties
        if 'properties' in spec and isinstance(spec['properties'], dict):
            for prop_name, prop_spec in spec['properties'].items():
                # 递归处理嵌套类型
                java_type = self._get_java_type_for_schema(prop_spec, prop_name, class_name, inline_classes)
                self._generate_inline_field(content, prop_name, java_type, prop_spec)
        
        content.append("}")
        
        # 将内联类添加到待生成列表
        inline_classes.append((class_name, content))
    
    def _generate_inline_class_with_extends(self, class_name: str, spec: Dict[str, Any], inline_classes: List[Tuple[str, List[str]]]):
        """生成带有继承的内联类"""
        content = []
        
        # 生成类注释
        desc = self._get_description(spec.get('description', ''))
        if desc:
            content.append("/**")
            content.append(f" * {desc}")
            content.append(" */")
        else:
            content.append("/**")
            content.append(f" * {class_name} inline class with extends")
            content.append(" */")
        
        # 确定继承关系
        extends_class = None
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_type = self._get_java_type_for_ref(extend_ref)
                if parent_type and parent_type != "Object":
                    extends_class = parent_type
                    break
        
        class_def = f"public static class {class_name}"
        if extends_class:
            class_def += f" extends {extends_class}"
        content.append(f"{class_def} {{")
        
        # 处理自己的properties，跳过从父类继承的属性以避免
        # 协变返回类型不兼容（子类内联类未继承父类内联类）
        if 'properties' in spec and isinstance(spec['properties'], dict):
            inherited_props = self._get_inherited_properties(spec)
            for prop_name, prop_spec in spec['properties'].items():
                if prop_name not in inherited_props:
                    java_type = self._get_java_type_for_schema(prop_spec, prop_name, class_name, inline_classes)
                    self._generate_inline_field(content, prop_name, java_type, prop_spec)
        
        content.append("}")
        
        # 将内联类添加到待生成列表
        inline_classes.append((class_name, content))
    
    def _generate_inline_field(self, content: List[str], field_name: str, java_type: str, field_spec: Dict[str, Any]):
        """为内联类生成字段"""
        if field_spec is None:
            return
            
        # 获取字段描述
        desc = ""
        if isinstance(field_spec, dict) and 'description' in field_spec:
            desc = self._get_description(field_spec['description'])
        
        # 生成字段
        java_field_name = self._to_java_field_name(field_name)
        
        if desc:
            content.append(f"    /**")
            content.append(f"     * {desc}")
            content.append(f"     */")
        
        content.append(f"    @JSONField(name = \"{field_name}\")")
        content.append(f"    private {java_type} {java_field_name};")
        content.append("")
        
        # 生成getter和setter
        capitalized_field_name = java_field_name[0].upper() + java_field_name[1:] if java_field_name else ""
        getter_name = f"get{capitalized_field_name}"
        setter_name = f"set{capitalized_field_name}"
        
        content.append(f"    public {java_type} {getter_name}() {{")
        content.append(f"        return {java_field_name};")
        content.append("    }")
        content.append("")
        
        content.append(f"    public void {setter_name}({java_type} {java_field_name}) {{")
        content.append(f"        this.{java_field_name} = {java_field_name};")
        content.append("    }")
        content.append("")
    
    def _get_java_type(self, spec: Dict[str, Any], field_name: str = "", parent_class_name: str = "") -> str:
        """获取字段的Java类型（不生成内联类，嵌套对象统一使用 Map）"""
        if not isinstance(spec, dict):
            return "Object"
        
        # 处理type_ref
        if 'type_ref' in spec:
            return self._get_java_type_for_ref(spec['type_ref'])
        
        # 处理 extends（属性级别继承，直接使用父类型）
        if 'extends' in spec and isinstance(spec['extends'], list):
            for extend_ref in spec['extends']:
                parent_type = self._get_java_type_for_ref(extend_ref)
                if parent_type and parent_type != "Object":
                    return parent_type
        
        # 处理constraint中的类型
        if 'constraint' in spec and isinstance(spec['constraint'], dict):
            constraint = spec['constraint']
            
            # 处理array约束
            if 'array' in constraint and 'item' in constraint['array']:
                item_spec = constraint['array']['item']
                item_type = self._get_java_type(item_spec, f"{field_name}_item", parent_class_name)
                return f"List<{item_type}>"
            
            # 处理map约束
            if 'map' in constraint:
                value_spec = constraint['map'].get('value', {'type': 'string'})
                value_type = self._get_java_type(value_spec, f"{field_name}_value", parent_class_name)
                return f"Map<String, {value_type}>"
        
        # 处理基本类型
        if 'type' in spec:
            base_type = spec['type']
            
            # 检查是否是自定义类型
            if base_type not in self.primitive_types:
                # 尝试查找类型定义
                type_ref = f"{base_type}:v1"
                if type_ref in self.type_registry:
                    type_name = self._get_java_type_name(type_ref)
                    return type_name
                
                # 特殊处理semantic_string
                if base_type == 'semantic_string':
                    return "SemanticString"
            
            # 处理object类型
            if base_type == 'object' and 'properties' in spec:
                # 检查是否是semantic_string的展开形式
                props = spec['properties']
                if isinstance(props, dict) and set(props.keys()) <= {"zh_cn", "en_us"}:
                    return "SemanticString"
                
                # 生成内联class - 在Java中使用Map
                return "Map<String, Object>"
            
            return self.primitive_types.get(base_type, "Object")
        
        # 如果没有type字段，但有properties，也处理为object
        if 'properties' in spec and isinstance(spec['properties'], dict):
            return "Map<String, Object>"
        
        return "Object"
    
    def _get_java_type_name(self, type_key: str) -> str:
        """将类型键转换为Java类型名"""
        # 分解type_key
        parts = type_key.split(':')
        if len(parts) == 2:
            name, version = parts
        else:
            name = parts[0]
            version = 'v1'
        
        # 转换为驼峰命名
        name_parts = name.split('_')
        java_name = ''.join(word.capitalize() for word in name_parts)
        
        # 添加版本后缀
        version_suffix = version.replace('.', '').upper()
        return f"{java_name}{version_suffix}"
    
    def _to_java_field_name(self, field_name: str) -> str:
        """将字段名转换为Java字段名（camelCase）"""
        # Java保留关键字映射
        reserved_keywords = {
            'enum': 'enumValues',
            'class': 'clazz',
            'interface': 'interfaceType',
            'extends': 'extendsType',
            'implements': 'implementsType',
            'public': 'publicField',
            'private': 'privateField',
            'protected': 'protectedField',
            'static': 'staticField',
            'final': 'finalField',
            'abstract': 'abstractField',
            'default': 'defaultValue',
            'package': 'packageName',
            'import': 'importType',
            'throw': 'throwException',
            'throws': 'throwsException',
            'try': 'tryBlock',
            'catch': 'catchBlock',
            'finally': 'finallyBlock',
            'if': 'ifCondition',
            'else': 'elseCondition',
            'switch': 'switchStatement',
            'case': 'caseValue',
            'break': 'breakStatement',
            'continue': 'continueStatement',
            'return': 'returnValue',
            'for': 'forLoop',
            'while': 'whileLoop',
            'do': 'doLoop',
            'new': 'newInstance',
            'this': 'thisInstance',
            'super': 'superClass',
            'null': 'nullValue',
            'true': 'trueValue',
            'false': 'falseValue',
            'boolean': 'booleanValue',
            'byte': 'byteValue',
            'char': 'charValue',
            'short': 'shortValue',
            'int': 'intValue',
            'long': 'longValue',
            'float': 'floatValue',
            'double': 'doubleValue',
            'void': 'voidType',
            'synchronized': 'synchronizedBlock',
            'volatile': 'volatileField',
            'transient': 'transientField',
            'native': 'nativeMethod',
            'strictfp': 'strictfpValue',
            'assert': 'assertStatement',
            'goto': 'gotoStatement',
            'const': 'constValue',
            'instanceof': 'instanceofCheck'
        }
        
        # 检查是否是保留关键字
        if field_name in reserved_keywords:
            return reserved_keywords[field_name]
        
        # 转换为camelCase
        parts = field_name.split('_')
        if len(parts) == 1:
            return field_name
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])
    
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


    # =========================================
    # 测试文件生成
    # =========================================

    def _generate_test_files(self):
        """Step 8: 生成所有测试文件"""
        print("\n🧪 开始生成测试文件...")

        test_base = self.output_dir / "src" / "test" / "java" / "com" / "mmodel"
        test_base.mkdir(parents=True, exist_ok=True)

        shared_types = []
        schema_types = []

        for type_key in sorted(self.type_registry.keys()):
            type_def = self.type_registry[type_key]
            java_name = self.java_type_mapping.get(type_key)
            if not java_name:
                continue
            name = type_def.get('name', type_key.split(':')[0])
            if type_def.get('file') == 'core':
                schema_types.append((name, type_key, java_name, name.endswith('_link')))
            else:
                shared_types.append((type_key, java_name, type_def))

        self._gen_test_base_types(test_base)
        self._gen_test_mmodel(test_base, schema_types)
        self._gen_test_mmodel2(test_base, schema_types)
        self._gen_test_json_parsing(test_base)
        self._gen_test_metric_set_demo(test_base)

        d = test_base / "shared"
        d.mkdir(exist_ok=True)
        self._gen_test_shared_types(d, shared_types)

        d = test_base / "schema"
        d.mkdir(exist_ok=True)
        self._gen_test_schemas(d, schema_types)

        d = test_base / "integration"
        d.mkdir(exist_ok=True)
        self._gen_test_integration(d, schema_types)

        d = test_base / "performance"
        d.mkdir(exist_ok=True)
        self._gen_test_performance(d, schema_types)

        print("✅ 测试文件生成完成")

    def _get_type_props_for_test(self, type_key: str) -> list:
        """获取类型属性用于测试生成"""
        type_def = self.type_registry.get(type_key, {})
        spec = type_def.get('spec', {})
        java_name = self.java_type_mapping.get(type_key, '')
        props = []
        if not isinstance(spec.get('properties'), dict):
            return props
        inherited = self._get_inherited_properties(spec) if 'extends' in spec else set()
        for pn, ps in spec['properties'].items():
            if pn == 'kind' or pn in inherited:
                continue
            jf = self._to_java_field_name(pn)
            jt = self._get_java_type(ps, pn, java_name)
            cap = jf[0].upper() + jf[1:] if jf else ''
            props.append({'name': pn, 'field': jf, 'type': jt, 'get': f'get{cap}', 'set': f'set{cap}'})
        return props

    def _gen_field_test(self, prop: dict, var: str) -> List[str]:
        """生成单个字段的测试代码行"""
        t, f, g, s = prop['type'], prop['field'], prop['get'], prop['set']
        L = []
        if t == "String":
            L.append(f'        {var}.{s}("{f}_test");')
            L.append(f'        assertEquals("{f}_test", {var}.{g}());')
        elif t == "Long":
            L.append(f'        {var}.{s}(42L);')
            L.append(f'        assertEquals(Long.valueOf(42L), {var}.{g}());')
        elif t == "Double":
            L.append(f'        {var}.{s}(3.14);')
            L.append(f'        assertEquals(Double.valueOf(3.14), {var}.{g}());')
        elif t == "Boolean":
            L.append(f'        {var}.{s}(true);')
            L.append(f'        assertTrue({var}.{g}());')
        elif t == "Object":
            L.append(f'        {var}.{s}("test_obj");')
            L.append(f'        assertEquals("test_obj", {var}.{g}());')
        elif t == "LocalDateTime":
            v = f"{f}Val"
            L.append(f'        LocalDateTime {v} = LocalDateTime.now();')
            L.append(f'        {var}.{s}({v});')
            L.append(f'        assertEquals({v}, {var}.{g}());')
        elif t.startswith("Map<"):
            v = f"{f}Map"
            val_type = t.split(", ", 1)[1].rstrip(">") if ", " in t else "Object"
            L.append(f'        {t} {v} = new HashMap<>();')
            if val_type in ("String", "Object"):
                L.append(f'        {v}.put("k1", "v1");')
            else:
                L.append(f'        {v}.put("k1", new {val_type}());')
            L.append(f'        {var}.{s}({v});')
            L.append(f'        assertEquals({v}, {var}.{g}());')
        elif t.startswith("List<"):
            v = f"{f}List"
            inner = t[5:-1]
            L.append(f'        {t} {v} = new ArrayList<>();')
            if inner in ("String", "Object"):
                L.append(f'        {v}.add("item1");')
            elif inner in ("Long", "Integer"):
                L.append(f'        {v}.add(1L);')
            elif inner.startswith("Map<"):
                L.append(f'        {v}.add(new HashMap<>());')
            else:
                L.append(f'        {v}.add(new {inner}());')
            L.append(f'        {var}.{s}({v});')
            L.append(f'        assertEquals({v}, {var}.{g}());')
        else:
            v = f"{f}Val"
            L.append(f'        {t} {v} = new {t}();')
            L.append(f'        {var}.{s}({v});')
            L.append(f'        assertEquals({v}, {var}.{g}());')
        return L

    def _java_escape(self, s: str) -> str:
        """将字符串转义为 Java 字符串字面量内容"""
        return s.replace('\\', '\\\\').replace('"', '\\"')

    def _write_test(self, path, lines: List[str]):
        """写入测试文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    # ---------- BaseTypesTest ----------

    def _gen_test_base_types(self, d):
        content = """\
// Code generated by schema_java_generator_v2.py. DO NOT EDIT.

package com.mmodel;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashMap;
import java.util.Map;

public class BaseTypesTest {

    @Test
    public void testSemanticStringCreation() {
        SemanticString ss = new SemanticString("中文描述", "English Description");
        assertEquals("中文描述", ss.getZhCn());
        assertEquals("English Description", ss.getEnUs());
    }

    @Test
    public void testSemanticStringToString() {
        assertEquals("中文", new SemanticString("中文", "English").toString());
        assertEquals("English", new SemanticString(null, "English").toString());
        assertEquals("", new SemanticString(null, null).toString());
    }

    @Test
    public void testSemanticStringGet() {
        SemanticString ss = new SemanticString("中文描述", "English Description");
        assertEquals("中文描述", ss.get("zh_cn"));
        assertEquals("中文描述", ss.get("zh"));
        assertEquals("English Description", ss.get("en_us"));
        assertEquals("English Description", ss.get("en"));
        assertEquals("", ss.get("unknown"));
    }

    @Test
    public void testSemanticStringFromString() {
        SemanticString r = SemanticString.fromObject("Test String");
        assertEquals("Test String", r.getZhCn());
        assertEquals("Test String", r.getEnUs());
    }

    @Test
    public void testSemanticStringFromMap() {
        Map<String, Object> map = new HashMap<>();
        map.put("zh_cn", "中文");
        map.put("en_us", "English");
        SemanticString r = SemanticString.fromObject(map);
        assertEquals("中文", r.getZhCn());
        assertEquals("English", r.getEnUs());
    }

    @Test
    public void testSemanticStringFromInvalidObject() {
        SemanticString r = SemanticString.fromObject(123);
        assertNull(r.getZhCn());
        assertNull(r.getEnUs());
    }

    @Test
    public void testLinkEndpointCreation() {
        LinkEndpoint ep = new LinkEndpoint("test.domain", "metric_set", "cpu_usage", "host='server1'");
        assertEquals("test.domain", ep.getDomain());
        assertEquals("metric_set", ep.getKind());
        assertEquals("cpu_usage", ep.getName());
        assertEquals("host='server1'", ep.getFilter());
    }

    @Test
    public void testLinkEndpointSetters() {
        LinkEndpoint ep = new LinkEndpoint();
        ep.setDomain("new.domain");
        ep.setKind("log_set");
        ep.setName("application_logs");
        ep.setFilter("app='myapp'");
        assertEquals("new.domain", ep.getDomain());
        assertEquals("log_set", ep.getKind());
        assertEquals("application_logs", ep.getName());
        assertEquals("app='myapp'", ep.getFilter());
    }
}"""
        with open(d / "BaseTypesTest.java", 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ 生成测试: BaseTypesTest.java")

    # ---------- SharedTypeTest ----------

    def _gen_test_shared_types(self, d, shared_types):
        c = ["// Code generated by schema_java_generator_v2.py. DO NOT EDIT.", "",
             "package com.mmodel.shared;", "",
             "import com.mmodel.MModelObject;",
             "import org.junit.jupiter.api.Test;",
             "import static org.junit.jupiter.api.Assertions.*;",
             "import java.time.LocalDateTime;",
             "import java.util.HashMap;",
             "import java.util.Map;",
             "import java.util.List;",
             "import java.util.ArrayList;", "",
             "public class SharedTypeTest {"]

        for type_key, java_name, type_def in shared_types:
            kind = type_def.get('name', type_key.split(':')[0])
            props = self._get_type_props_for_test(type_key)
            c += ["", "    @Test",
                  f"    public void test{java_name}() {{",
                  f"        {java_name} obj = new {java_name}();", "",
                  f'        assertEquals("{kind}", obj.getKind());',
                  f"        assertTrue(obj instanceof MModelObject);"]
            if props:
                c.append("")
                for p in props:
                    c.extend(self._gen_field_test(p, "obj"))
            c.append("    }")

        c.append("}")
        self._write_test(d / "SharedTypeTest.java", c)
        print("✅ 生成测试: SharedTypeTest.java")

    # ---------- SchemaTest ----------

    def _gen_test_schemas(self, d, schema_types):
        c = ["// Code generated by schema_java_generator_v2.py. DO NOT EDIT.", "",
             "package com.mmodel.schema;", "",
             "import com.mmodel.*;",
             "import com.mmodel.shared.*;",
             "import org.junit.jupiter.api.Test;",
             "import static org.junit.jupiter.api.Assertions.*;",
             "import java.util.HashMap;",
             "import java.util.Map;",
             "import java.util.List;",
             "import java.util.ArrayList;", "",
             "public class SchemaTest {"]

        for sn, tk, jn, il in schema_types:
            c += ["", "    @Test", f"    public void test{jn}() {{",
                  f"        {jn} obj = new {jn}();", "",
                  f'        assertEquals("{sn}", obj.getKind());',
                  "        assertTrue(obj instanceof MModelObject);",
                  "        assertTrue(obj instanceof MModelCoreObject);",
                  f"        assertTrue(obj instanceof MModelLinkObject);" if il else
                  f"        assertFalse(obj instanceof MModelLinkObject);",
                  "",
                  "        MetadataV1 metadata = new MetadataV1();",
                  f'        metadata.setName("test_{sn}");',
                  "        obj.setMetadata(metadata);",
                  "        assertEquals(metadata, obj.getMetadata());",
                  f'        assertEquals("test_{sn}", obj.getMetadata().getName());',
                  "",
                  "        SchemaV1 schema = new SchemaV1();",
                  '        schema.setVersion("v1.0.0");',
                  "        obj.setSchema(schema);",
                  "        assertEquals(schema, obj.getSchema());",
                  '        assertEquals("v1.0.0", obj.getSchema().getVersion());',
                  "",
                  "        assertNull(obj.validate());"]
            if il:
                c += ["", "        assertNull(obj.getSrc());", "        assertNull(obj.getDest());"]
            c.append("    }")

        c.append("}")
        self._write_test(d / "SchemaTest.java", c)
        print("✅ 生成测试: SchemaTest.java")

    # ---------- TestMModel ----------

    def _gen_test_mmodel(self, d, schema_types):
        first = next(((sn, tk, jn) for sn, tk, jn, il in schema_types if not il), None)
        if not first:
            return
        sn, tk, jn = first
        ver = tk.split(':')[1] if ':' in tk else 'v1.0.0'
        je = self._java_escape
        json_str = je(f'{{"kind":"{sn}","schema":{{"version":"{ver}"}},"metadata":{{"name":"test"}}}}')

        c = ["// Code generated by schema_java_generator_v2.py. DO NOT EDIT.", "",
             "package com.mmodel;", "",
             "import com.alibaba.fastjson.JSON;",
             f"import com.mmodel.schema.{jn};",
             "import com.mmodel.shared.*;",
             "import org.junit.jupiter.api.Test;",
             "import static org.junit.jupiter.api.Assertions.*;",
             "import java.util.HashMap;",
             "import java.util.Map;", "",
             "public class TestMModel {", "",
             "    @Test",
             "    public void testMetricSetCreation() {",
             f"        {jn} obj = new {jn}();",
             f'        obj.setKind("{sn}");',
             "        SchemaV1 schema = new SchemaV1();",
             f'        schema.setVersion("{ver}");',
             "        obj.setSchema(schema);",
             "        MetadataV1 metadata = new MetadataV1();",
             '        metadata.setName("test_metric");',
             "        SemanticStringV1 description = new SemanticStringV1();",
             '        description.setZhCn("测试指标集");',
             "        metadata.setDescription(description);",
             "        obj.setMetadata(metadata);",
             f'        assertEquals("{sn}", obj.getKind());',
             f'        assertEquals("{ver}", obj.getSchema().getVersion());',
             '        assertEquals("test_metric", obj.getMetadata().getName());',
             '        assertEquals("测试指标集", obj.getMetadata().getDescription().getZhCn());',
             "        String json = JSON.toJSONString(obj);",
             "        assertNotNull(json);",
             f'        assertTrue(json.contains("{sn}"));',
             f'        assertTrue(json.contains("{ver}"));',
             "    }", "",
             "    @Test",
             "    public void testMModelInterfaces() {",
             f"        {jn} obj = new {jn}();",
             "        assertTrue(MModel.isCoreObject(obj));",
             "        assertFalse(MModel.isLinkObject(obj));",
             f'        assertEquals("{sn}", obj.getKind());',
             "    }", "",
             "    @Test",
             "    public void testJsonParsing() {",
             f'        String jsonData = "{json_str}";',
             f"        {jn} obj = MModel.parseJson(jsonData, {jn}.class);",
             "        assertNotNull(obj);",
             f'        assertEquals("{sn}", obj.getKind());',
             f'        assertEquals("{ver}", obj.getSchema().getVersion());',
             '        assertEquals("test", obj.getMetadata().getName());',
             "    }", "",
             "    @Test",
             "    public void testSemanticString() {",
             '        SemanticString ss = new SemanticString("中文描述", "English description");',
             '        assertEquals("中文描述", ss.getZhCn());',
             '        assertEquals("English description", ss.getEnUs());',
             '        assertEquals("中文描述", ss.toString());',
             '        assertEquals("中文描述", ss.get("zh_cn"));',
             '        assertEquals("English description", ss.get("en"));',
             "    }",
             "}"]
        self._write_test(d / "TestMModel.java", c)
        print("✅ 生成测试: TestMModel.java")

    # ---------- TestMModel2 ----------

    def _gen_test_mmodel2(self, d, schema_types):
        if not schema_types:
            return
        je = self._java_escape
        c = ["// Code generated by schema_java_generator_v2.py. DO NOT EDIT.", "",
             "package com.mmodel;", "",
             "import com.mmodel.schema.*;",
             "import org.junit.jupiter.api.Test;",
             "import static org.junit.jupiter.api.Assertions.*;", "",
             "public class TestMModel2 {", "",
             "    @Test",
             "    public void testVersion() {",
             '        assertEquals("2.0.0", MModel.VERSION);',
             "    }"]

        # testParseJsonWithSpecificClass
        sn0, tk0, jn0, _ = schema_types[0]
        ver0 = tk0.split(':')[1] if ':' in tk0 else 'v1.0.0'
        js0 = je(f'{{"kind":"{sn0}","schema":{{"version":"{ver0}"}},"metadata":{{"name":"test"}}}}')
        c += ["", "    @Test",
              "    public void testParseJsonWithSpecificClass() {",
              f'        String json = "{js0}";',
              f"        {jn0} obj = MModel.parseJson(json, {jn0}.class);",
              "        assertNotNull(obj);",
              f'        assertEquals("{sn0}", obj.getKind());',
              "    }"]

        # testParseMModelJson for each type
        for sn, tk, jn, il in schema_types:
            ver = tk.split(':')[1] if ':' in tk else 'v1.0.0'
            js = je(f'{{"kind":"{sn}","schema":{{"version":"{ver}"}},"metadata":{{"name":"test_{sn}"}}}}')
            mn = 'testParseMModelJson' + ''.join(w.capitalize() for w in sn.split('_'))
            c += ["", "    @Test", f"    public void {mn}() {{",
                  f'        String json = "{js}";',
                  "        MModelCoreObject obj = MModel.parseMModelJson(json);",
                  "        assertNotNull(obj);",
                  f'        assertEquals("{sn}", obj.getKind());',
                  f"        assertTrue(obj instanceof {jn});",
                  "    }"]

        # testParseMModelJsonWithCompatibleVersion
        js_compat = je(f'{{"kind":"{sn0}","schema":{{"version":"v0.1.0"}},"metadata":{{"name":"test"}}}}')
        c += ["", "    @Test",
              "    public void testParseMModelJsonWithCompatibleVersion() {",
              f'        String json = "{js_compat}";',
              "        MModelCoreObject obj = MModel.parseMModelJson(json);",
              "        assertNotNull(obj);",
              f'        assertEquals("{sn0}", obj.getKind());',
              "    }"]

        # error cases
        for suffix, raw in [
            ("MissingKind", '{"schema":{"version":"v1.0.0"},"metadata":{"name":"test"}}'),
            ("MissingSchema", '{"kind":"metric_set","metadata":{"name":"test"}}'),
            ("MissingVersion", '{"kind":"metric_set","schema":{},"metadata":{"name":"test"}}'),
            ("UnknownType", '{"kind":"unknown_type","schema":{"version":"v1.0.0"},"metadata":{"name":"test"}}'),
        ]:
            c += ["", "    @Test", f"    public void testParseMModelJson{suffix}() {{",
                  f'        String json = "{je(raw)}";',
                  "        assertThrows(IllegalArgumentException.class, () -> MModel.parseMModelJson(json));",
                  "    }"]

        # testIsCoreObject
        c += ["", "    @Test", "    public void testIsCoreObject() {"]
        for sn, tk, jn, il in schema_types:
            c.append(f"        assertTrue(MModel.isCoreObject(new {jn}()));")
        c += ['        assertFalse(MModel.isCoreObject("test"));',
              "        assertFalse(MModel.isCoreObject(null));",
              "    }"]

        # testIsLinkObject
        c += ["", "    @Test", "    public void testIsLinkObject() {"]
        for sn, tk, jn, il in schema_types:
            c.append(f"        {'assertTrue' if il else 'assertFalse'}(MModel.isLinkObject(new {jn}()));")
        c += ['        assertFalse(MModel.isLinkObject("test"));',
              "        assertFalse(MModel.isLinkObject(null));",
              "    }"]

        # testGetObjectMetadata / Schema
        c += ["", "    @Test", "    public void testGetObjectMetadata() {",
              f"        assertNull(MModel.getObjectMetadata(new {jn0}()));",
              '        assertNull(MModel.getObjectMetadata("test"));',
              "        assertNull(MModel.getObjectMetadata(null));",
              "    }", "",
              "    @Test", "    public void testGetObjectSchema() {",
              f"        assertNull(MModel.getObjectSchema(new {jn0}()));",
              '        assertNull(MModel.getObjectSchema("test"));',
              "        assertNull(MModel.getObjectSchema(null));",
              "    }"]

        # testGetLinkEndpoints
        link_jn = next((jn for _, _, jn, il in schema_types if il), None)
        if link_jn:
            c += ["", "    @Test", "    public void testGetLinkEndpoints() {",
                  f"        LinkEndpoint[] ep = MModel.getLinkEndpoints(new {link_jn}());",
                  "        assertNotNull(ep);",
                  "        assertEquals(2, ep.length);",
                  "        assertNull(ep[0]);",
                  "        assertNull(ep[1]);", "",
                  f"        LinkEndpoint[] nonLink = MModel.getLinkEndpoints(new {jn0}());",
                  "        assertNotNull(nonLink);",
                  "        assertEquals(2, nonLink.length);", "",
                  '        LinkEndpoint[] strEp = MModel.getLinkEndpoints("test");',
                  "        assertNotNull(strEp);",
                  "        assertEquals(2, strEp.length);",
                  "    }"]

        c.append("}")
        self._write_test(d / "TestMModel2.java", c)
        print("✅ 生成测试: TestMModel2.java")

    # ---------- TestJsonParsing ----------

    def _gen_test_json_parsing(self, d):
        content = """\
// Code generated by schema_java_generator_v2.py. DO NOT EDIT.

package com.mmodel;

import com.alibaba.fastjson.JSON;
import com.mmodel.schema.MetricSetV100;
import com.mmodel.shared.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

public class TestJsonParsing {

    @Test
    public void testParseSlsFrontMetricJson() throws IOException {
        String jsonPath = "../../examples/dataset/metricset/sls_front_metric.json";
        String jsonContent = new String(Files.readAllBytes(Paths.get(jsonPath)));

        MModelCoreObject obj = MModel.parseMModelJson(jsonContent);
        assertNotNull(obj);
        assertTrue(obj instanceof MetricSetV100);
        assertEquals("metric_set", obj.getKind());

        MetricSetV100 metricSet = (MetricSetV100) obj;

        SchemaV1 schema = metricSet.getSchema();
        assertNotNull(schema);
        assertEquals("mmodel.aliyun.com", schema.getUrl());
        assertEquals("v0.1.0", schema.getVersion());

        MetadataV1 metadata = metricSet.getMetadata();
        assertNotNull(metadata);
        assertEquals("sls_front.metricset", metadata.getName());
        assertEquals("sls", metadata.getDomain());

        SemanticStringV1 displayName = metadata.getDisplayName();
        assertNotNull(displayName);
        assertEquals("SLS Front Metrics", displayName.getEnUs());
        assertEquals("SLS前端指标", displayName.getZhCn());

        MetricSetV100.MetricSetV100Spec spec = metricSet.getSpec();
        assertNotNull(spec);
        assertEquals("prom", spec.getQueryType());

        MetricSetV100.MetricSetV100SpecLabels labels = spec.getLabels();
        assertNotNull(labels);
        assertTrue(labels.getDynamic());
        assertEquals("fcgi_ram_check_permission_subuser{}", labels.getFilter());

        List<FieldSpecV1> keys = labels.getKeys();
        assertNotNull(keys);
        assertEquals(3, keys.size());

        FieldSpecV1 firstKey = keys.get(0);
        assertEquals("id", firstKey.getName());
        assertEquals("string", firstKey.getType());

        List<MetricV1> metrics = spec.getMetrics();
        assertNotNull(metrics);
        assertEquals(3, metrics.size());

        MetricV1 firstMetric = metrics.get(0);
        assertEquals("fcgi_listconfig_fail", firstMetric.getName());
        assertEquals("avg", firstMetric.getAggregator());
        assertEquals("fcgi_ListConfig_fail{}", firstMetric.getGenerator());
        assertTrue(firstMetric.getGoldenMetric());
        assertEquals("range", firstMetric.getQueryMode());
        assertEquals("KMB", firstMetric.getDataFormat());
        assertEquals("count", firstMetric.getUnit());

        List<String> statistics = firstMetric.getStatistics();
        assertNotNull(statistics);
        assertEquals(3, statistics.size());
        assertTrue(statistics.contains("Avg"));
        assertTrue(statistics.contains("Max"));
        assertTrue(statistics.contains("Min"));
    }

    @Test
    public void testDirectParseAsMetricSet() throws IOException {
        String jsonPath = "../../examples/dataset/metricset/sls_front_metric.json";
        String jsonContent = new String(Files.readAllBytes(Paths.get(jsonPath)));

        MetricSetV100 metricSet = MModel.parseJson(jsonContent, MetricSetV100.class);
        assertNotNull(metricSet);
        assertEquals("metric_set", metricSet.getKind());
        assertNotNull(metricSet.getSchema());
        assertNotNull(metricSet.getMetadata());
        assertNotNull(metricSet.getSpec());
    }

    @Test
    public void testJsonSerialization() throws IOException {
        String jsonPath = "../../examples/dataset/metricset/sls_front_metric.json";
        String jsonContent = new String(Files.readAllBytes(Paths.get(jsonPath)));

        MetricSetV100 metricSet = MModel.parseJson(jsonContent, MetricSetV100.class);
        String serializedJson = JSON.toJSONString(metricSet, true);
        assertNotNull(serializedJson);
        assertTrue(serializedJson.contains("metric_set"));
        assertTrue(serializedJson.contains("sls_front.metricset"));

        MetricSetV100 metricSet2 = MModel.parseJson(serializedJson, MetricSetV100.class);
        assertEquals(metricSet.getKind(), metricSet2.getKind());
        assertEquals(metricSet.getMetadata().getName(), metricSet2.getMetadata().getName());
    }
}"""
        with open(d / "TestJsonParsing.java", 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ 生成测试: TestJsonParsing.java")

    # ---------- TestMetricSetV2 (demo main) ----------

    def _gen_test_metric_set_demo(self, d):
        content = """\
// Code generated by schema_java_generator_v2.py. DO NOT EDIT.

package com.mmodel;

import com.alibaba.fastjson.JSON;
import com.mmodel.schema.*;
import com.mmodel.shared.*;
import java.util.*;

public class TestMetricSetV2 {
    public static void main(String[] args) {
        MetricSetV100 metricSet = new MetricSetV100();
        metricSet.setKind("metric_set");

        SchemaV1 schema = new SchemaV1();
        schema.setVersion("v1.0.0");
        schema.setUrl("mmodel.aliyun.com");
        metricSet.setSchema(schema);

        MetadataV1 metadata = new MetadataV1();
        metadata.setName("test_metric_set");
        metadata.setDomain("test.domain");
        metricSet.setMetadata(metadata);

        MetricSetV100.MetricSetV100Spec spec = new MetricSetV100.MetricSetV100Spec();
        spec.setQueryType("prom");
        spec.setNeedsProcessing(false);

        MetricSetV100.MetricSetV100SpecLabels labels = new MetricSetV100.MetricSetV100SpecLabels();
        labels.setDynamic(true);
        labels.setFilter("label_name!~'__.*'");

        List<FieldSpecV1> keys = new ArrayList<>();
        FieldSpecV1 field = new FieldSpecV1();
        field.setName("host");
        field.setType("string");
        keys.add(field);
        labels.setKeys(keys);
        spec.setLabels(labels);

        List<MetricV1> metrics = new ArrayList<>();
        MetricV1 metric = new MetricV1();
        metric.setName("cpu_usage");
        metric.setType("gauge");
        metric.setUnit("percent");
        metrics.add(metric);
        spec.setMetrics(metrics);

        metricSet.setSpec(spec);

        String json = JSON.toJSONString(metricSet, true);
        System.out.println("生成的JSON:");
        System.out.println(json);

        System.out.println("\\n测试接口方法:");
        System.out.println("Kind: " + metricSet.getKind());
        System.out.println("Schema Version: " + metricSet.getSchema().getVersion());
        System.out.println("Metadata Name: " + metricSet.getMetadata().getName());
        System.out.println("Query Type: " + metricSet.getSpec().getQueryType());
        System.out.println("Labels Dynamic: " + metricSet.getSpec().getLabels().getDynamic());

        System.out.println("\\n测试JSON解析:");
        MetricSetV100 parsed = JSON.parseObject(json, MetricSetV100.class);
        System.out.println("解析后的对象:");
        System.out.println("Kind: " + parsed.getKind());
        System.out.println("Metadata Name: " + parsed.getMetadata().getName());
        System.out.println("Spec Query Type: " + parsed.getSpec().getQueryType());
    }
}"""
        with open(d / "TestMetricSetV2.java", 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ 生成测试: TestMetricSetV2.java")

    # ---------- TestParsingIntegrationTest ----------

    def _gen_test_integration(self, d, schema_types):
        if not schema_types:
            return
        je = self._java_escape
        c = ["// Code generated by schema_java_generator_v2.py. DO NOT EDIT.", "",
             "package com.mmodel.integration;", "",
             "import com.mmodel.*;",
             "import com.mmodel.schema.*;",
             "import com.mmodel.shared.*;",
             "import org.junit.jupiter.api.Test;",
             "import static org.junit.jupiter.api.Assertions.*;", "",
             "import java.util.Map;",
             "import java.util.List;", "",
             "public class TestParsingIntegrationTest {"]

        for sn, tk, jn, il in schema_types:
            ver = tk.split(':')[1] if ':' in tk else 'v1.0.0'
            raw = f'{{"kind":"{sn}","schema":{{"url":"mmodel.aliyun.com","version":"{ver}"}},"metadata":{{"name":"test_{sn}","display_name":{{"zh_cn":"测试{sn}","en_us":"Test {sn}"}},"domain":"test.domain","launch_stage":"ga","tags":{{"category":"test"}}}},"spec":{{"_data":"placeholder"}}}}'
            mn = 'test' + ''.join(w.capitalize() for w in sn.split('_')) + 'JsonParsing'

            c += ["", "    @Test", f"    public void {mn}() {{",
                  f'        String json = "{je(raw)}";', "",
                  "        MModelCoreObject obj = MModel.parseMModelJson(json);",
                  "        assertNotNull(obj);",
                  f"        assertTrue(obj instanceof {jn});",
                  f'        assertEquals("{sn}", obj.getKind());', "",
                  f"        {jn} typed = ({jn}) obj;",
                  "        SchemaV1 schema = typed.getSchema();",
                  "        assertNotNull(schema);",
                  '        assertEquals("mmodel.aliyun.com", schema.getUrl());',
                  f'        assertEquals("{ver}", schema.getVersion());', "",
                  "        MetadataV1 metadata = typed.getMetadata();",
                  "        assertNotNull(metadata);",
                  f'        assertEquals("test_{sn}", metadata.getName());',
                  '        assertEquals("test.domain", metadata.getDomain());',
                  '        assertEquals("ga", metadata.getLaunchStage());', "",
                  "        SemanticStringV1 displayName = metadata.getDisplayName();",
                  "        assertNotNull(displayName);",
                  f'        assertEquals("Test {sn}", displayName.getEnUs());', "",
                  "        Map<String, String> tags = metadata.getTags();",
                  "        assertNotNull(tags);",
                  '        assertEquals("test", tags.get("category"));',
                  "    }"]

        # testMModelInterfaceFunctions
        non_link = next(((sn, tk, jn) for sn, tk, jn, il in schema_types if not il), None)
        link = next(((sn, tk, jn) for sn, tk, jn, il in schema_types if il), None)

        c += ["", "    @Test", "    public void testMModelInterfaceFunctions() {"]
        if non_link:
            sn, tk, jn = non_link
            ver = tk.split(':')[1] if ':' in tk else 'v1.0.0'
            metric_raw = '{"kind":"' + sn + '","schema":{"version":"' + ver + '"},"metadata":{"name":"test"}}'
            c.append(f'        String metricJson = "{je(metric_raw)}";')
            c += ["        MModelCoreObject metricObj = MModel.parseMModelJson(metricJson);",
                  "        assertTrue(MModel.isCoreObject(metricObj));",
                  "        assertFalse(MModel.isLinkObject(metricObj));",
                  "        assertNotNull(MModel.getObjectMetadata(metricObj));",
                  "        assertNotNull(MModel.getObjectSchema(metricObj));"]
        if link:
            sn, tk, jn = link
            ver = tk.split(':')[1] if ':' in tk else 'v1.0.0'
            link_raw = '{"kind":"' + sn + '","schema":{"version":"' + ver + '"},"metadata":{"name":"test"}}'
            c += ["",
                  f'        String linkJson = "{je(link_raw)}";',
                  "        MModelCoreObject linkObj = MModel.parseMModelJson(linkJson);",
                  "        assertTrue(MModel.isCoreObject(linkObj));",
                  "        assertTrue(MModel.isLinkObject(linkObj));", "",
                  "        LinkEndpoint[] endpoints = MModel.getLinkEndpoints(linkObj);",
                  "        assertNotNull(endpoints);",
                  "        assertEquals(2, endpoints.length);"]
        c.append("    }")

        c.append("}")
        self._write_test(d / "TestParsingIntegrationTest.java", c)
        print("✅ 生成测试: TestParsingIntegrationTest.java")

    # ---------- PerformanceTest ----------

    def _gen_test_performance(self, d, schema_types):
        first_nl = next(((sn, tk, jn) for sn, tk, jn, il in schema_types if not il), None)
        if not first_nl:
            return
        sn, tk, jn = first_nl
        ver = tk.split(':')[1] if ':' in tk else 'v1.0.0'
        je = self._java_escape

        base_json = je(f'{{"kind":"{sn}","schema":{{"url":"mmodel.aliyun.com","version":"{ver}"}},"metadata":{{"name":"cpu_metrics_%ITER%","domain":"infrastructure.compute"}}}}')
        mem_json = je(f'{{"kind":"{sn}","schema":{{"version":"{ver}"}},"metadata":{{"name":"test_%d"}}}}')

        c = ["// Code generated by schema_java_generator_v2.py. DO NOT EDIT.", "",
             "package com.mmodel.performance;", "",
             "import com.mmodel.*;",
             "import com.mmodel.schema.*;",
             "import org.junit.jupiter.api.Test;",
             "import static org.junit.jupiter.api.Assertions.*;",
             "import java.util.ArrayList;",
             "import java.util.List;", "",
             "public class PerformanceTest {"]

        # testMassiveJsonParsingPerformance
        c += ["", "    @Test",
              "    public void testMassiveJsonParsingPerformance() {",
              f'        String baseJson = "{base_json}";', "",
              "        int iterations = 1000;",
              "        List<MModelCoreObject> parsedObjects = new ArrayList<>();",
              "        long startTime = System.currentTimeMillis();",
              "        for (int i = 0; i < iterations; i++) {",
              '            String json = baseJson.replace("%ITER%", String.valueOf(i));',
              "            MModelCoreObject obj = MModel.parseMModelJson(json);",
              "            parsedObjects.add(obj);",
              "        }",
              "        long duration = System.currentTimeMillis() - startTime;", "",
              "        assertEquals(iterations, parsedObjects.size());",
              "        for (int i = 0; i < iterations; i++) {",
              f"            assertTrue(parsedObjects.get(i) instanceof {jn});",
              f'            assertEquals("{sn}", parsedObjects.get(i).getKind());',
              "        }", "",
              '        System.out.printf("解析 %d 个JSON对象耗时: %d ms%n", iterations, duration);',
              '        System.out.printf("平均每个对象解析耗时: %.2f ms%n", (double) duration / iterations);',
              '        assertTrue(duration / iterations < 10, "JSON解析性能测试失败，平均解析时间过长");',
              "    }"]

        # testTypeCheckingPerformance
        used = schema_types[:4]
        core_n = len(used)
        link_n = sum(1 for _, _, _, il in used if il)
        c += ["", "    @Test",
              "    public void testTypeCheckingPerformance() {",
              "        List<Object> testObjects = new ArrayList<>();",
              "        for (int i = 0; i < 100; i++) {"]
        for _, _, j, _ in used:
            c.append(f"            testObjects.add(new {j}());")
        c += ['            testObjects.add("普通字符串");',
              "            testObjects.add(Integer.valueOf(42));",
              "        }", "",
              "        int iterations = 10000;",
              "        long startTime = System.currentTimeMillis();",
              "        int coreObjectCount = 0;",
              "        int linkObjectCount = 0;",
              "        for (int i = 0; i < iterations; i++) {",
              "            for (Object obj : testObjects) {",
              "                if (MModel.isCoreObject(obj)) coreObjectCount++;",
              "                if (MModel.isLinkObject(obj)) linkObjectCount++;",
              "            }",
              "        }",
              "        long duration = System.currentTimeMillis() - startTime;", "",
              f"        assertEquals(iterations * 100 * {core_n}, coreObjectCount);",
              f"        assertEquals(iterations * 100 * {link_n}, linkObjectCount);", "",
              "        int totalChecks = iterations * testObjects.size() * 2;",
              '        System.out.printf("执行 %d 次类型检查耗时: %d ms%n", totalChecks, duration);',
              '        System.out.printf("平均每次类型检查耗时: %.4f ms%n", (double) duration / totalChecks);',
              '        assertTrue(duration < 1000, "类型检查性能测试失败");',
              "    }"]

        # testComplexObjectCreationPerformance
        create_types = schema_types[:3]
        obj_n = len(create_types) + 2
        c += ["", "    @Test",
              "    public void testComplexObjectCreationPerformance() {",
              "        int iterations = 5000;",
              "        List<Object> createdObjects = new ArrayList<>();",
              "        long startTime = System.currentTimeMillis();",
              "        for (int i = 0; i < iterations; i++) {"]
        for idx, (s, _, j, _) in enumerate(create_types):
            c += [f"            {j} o{idx} = new {j}();",
                  f'            o{idx}.setKind("{s}");',
                  f"            createdObjects.add(o{idx});"]
        c += ['            createdObjects.add(new SemanticString("中文" + i, "English" + i));',
              '            createdObjects.add(new LinkEndpoint("domain" + i, "kind" + i, "name" + i, "filter" + i));',
              "        }",
              "        long duration = System.currentTimeMillis() - startTime;", "",
              f"        assertEquals(iterations * {obj_n}, createdObjects.size());",
              f'        System.out.printf("创建 %d 个复杂对象耗时: %d ms%n", iterations * {obj_n}, duration);',
              f'        System.out.printf("平均每个对象创建耗时: %.4f ms%n", (double) duration / (iterations * {obj_n}));',
              '        assertTrue(duration < 1000, "对象创建性能测试失败");',
              "    }"]

        # testLargeJsonParsingPerformance
        c += ["", "    @Test",
              "    public void testLargeJsonParsingPerformance() {",
              "        StringBuilder jb = new StringBuilder();",
              '        jb.append("{\\n");',
              f'        jb.append("  \\"kind\\": \\"{sn}\\",\\n");',
              '        jb.append("  \\"schema\\": {\\n");',
              '        jb.append("    \\"url\\": \\"mmodel.aliyun.com\\",\\n");',
              f'        jb.append("    \\"version\\": \\"{ver}\\"\\n");',
              '        jb.append("  },\\n");',
              '        jb.append("  \\"metadata\\": {\\n");',
              '        jb.append("    \\"name\\": \\"large_test\\",\\n");',
              '        jb.append("    \\"domain\\": \\"test.domain\\",\\n");',
              '        jb.append("    \\"tags\\": {\\n");',
              "        for (int i = 0; i < 100; i++) {",
              '            jb.append("      \\"tag").append(i).append("\\": \\"value").append(i).append("\\"");',
              '            if (i < 99) jb.append(",");',
              '            jb.append("\\n");',
              "        }",
              '        jb.append("    }\\n");',
              '        jb.append("  },\\n");',
              '        jb.append("  \\"spec\\": { \\"_data\\": \\"test\\" }\\n");',
              '        jb.append("}");', "",
              "        String largeJson = jb.toString();",
              "        int iterations = 100;",
              "        long startTime = System.currentTimeMillis();",
              "        for (int i = 0; i < iterations; i++) {",
              "            MModelCoreObject obj = MModel.parseMModelJson(largeJson);",
              "            assertNotNull(obj);",
              f"            assertTrue(obj instanceof {jn});",
              "        }",
              "        long duration = System.currentTimeMillis() - startTime;", "",
              '        System.out.printf("解析 %d 个大型JSON对象(~%d字符)耗时: %d ms%n", iterations, largeJson.length(), duration);',
              '        System.out.printf("平均每个大型对象解析耗时: %.2f ms%n", (double) duration / iterations);',
              '        assertTrue(duration / iterations < 50, "大型JSON解析性能测试失败");',
              "    }"]

        # testMemoryUsageTest
        c += ["", "    @Test",
              "    public void testMemoryUsageTest() {",
              "        Runtime runtime = Runtime.getRuntime();",
              "        System.gc();",
              "        long initialMemory = runtime.totalMemory() - runtime.freeMemory();",
              "        List<Object> objects = new ArrayList<>();",
              "        int objectCount = 10000;", "",
              "        for (int i = 0; i < objectCount; i++) {",
              f'            String json = String.format("{mem_json}", i);',
              "            MModelCoreObject obj = MModel.parseMModelJson(json);",
              "            objects.add(obj);",
              "            if (i % 1000 == 0 && i > 0) {",
              "                long cur = runtime.totalMemory() - runtime.freeMemory();",
              '                System.out.printf("创建 %d 个对象后，内存增加: %.2f MB%n", i, (cur - initialMemory) / (1024.0 * 1024.0));',
              "            }",
              "        }", "",
              "        System.gc();",
              "        long totalIncrease = (runtime.totalMemory() - runtime.freeMemory()) - initialMemory;",
              '        System.out.printf("创建 %d 个对象总计内存增加: %.2f MB%n", objectCount, totalIncrease / (1024.0 * 1024.0));',
              '        System.out.printf("平均每个对象内存占用: %.2f KB%n", totalIncrease / (1024.0 * objectCount));',
              "        assertEquals(objectCount, objects.size());",
              '        assertTrue(totalIncrease < 100 * 1024 * 1024, "内存使用测试失败，内存增加过多");',
              "    }"]

        c.append("}")
        self._write_test(d / "PerformanceTest.java", c)
        print("✅ 生成测试: PerformanceTest.java")


def main():
    """主函数"""
    print("🚀 MModel Schema Java SDK Generator V2 启动")
    print("=" * 50)
    
    # 配置路径
    schemas_dir = "schemas"
    output_dir = "generated/java"
    
    # 检查必要的目录
    if not os.path.exists(schemas_dir):
        print(f"❌ schemas目录不存在: {schemas_dir}")
        return
    
    # 创建生成器
    generator = JavaCodeGeneratorV2(schemas_dir, output_dir)
    
    try:
        # 生成所有代码
        generator.generate_all()
        
        print(f"\n✅ Java SDK V2代码已生成到: {output_dir}")
        print("\n📝 使用说明:")
        print("1. 安装Java 8+和Maven")
        print("2. 进入生成的目录: cd generated/java")
        print("3. 编译项目: mvn clean compile")
        print("4. 运行测试: mvn test")
        print("5. 打包JAR: mvn package")
        print("\n🎯 V2版本特性:")
        print("- 使用Java的继承特性实现继承关系")
        print("- 生成简洁、高复用的代码")
        print("- 保留原始schema的结构关系")
        print("- 支持动态类型创建和解析")
        print("- 提供通用接口MModelCoreObject和MModelLinkObject")
        print("- 使用FastJSON进行JSON序列化/反序列化")
        print("- 类型安全的Java类型定义")
        
        print("\n📚 接口使用示例:")
        print("// 判断对象类型")
        print("if (MModel.isCoreObject(obj)) {")
        print("    Object metadata = MModel.getObjectMetadata(obj);")
        print("    Object schema = MModel.getObjectSchema(obj);")
        print("    String kind = ((MModelObject) obj).getKind(); // 获取对象类型")
        print("}")
        print("")
        print("// 处理Link对象")
        print("if (MModel.isLinkObject(obj)) {")
        print("    LinkEndpoint[] endpoints = MModel.getLinkEndpoints(obj);")
        print("    LinkEndpoint src = endpoints[0];")
        print("    LinkEndpoint dest = endpoints[1];")
        print("    System.out.printf(\"Link from %s to %s%n\", src.getName(), dest.getName());")
        print("}")
        print("")
        print("// 自动解析JSON数据")
        print("String jsonData = \"{\\\"kind\\\":\\\"metric_set\\\",\\\"schema\\\":{\\\"version\\\":\\\"v1.0.0\\\"}}\";")
        print("MModelCoreObject obj = MModel.parseMModelJson(jsonData);")
        print("System.out.printf(\"Parsed object kind: %s%n\", obj.getKind());")
        
    except Exception as e:
        print(f"\n❌ 生成过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()