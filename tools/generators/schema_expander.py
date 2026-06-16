#!/usr/bin/env python3
"""
MModel Schema Expander

这个脚本用于解析schemas目录中的所有YAML文件，展开其中的extends和type_ref引用，
生成完整的schema定义，便于独立验证每个schema的有效性。

功能：
1. 递归扫描core目录中的所有.schema.yaml文件
2. 解析includes目录中的共享类型定义
3. 展开extends继承关系
4. 解析type_ref引用
5. 生成完整的、自包含的schema定义
"""

import os
import yaml
import json
import copy
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict


class SchemaExpander:
    def __init__(self, schemas_dir: str):
        self.schemas_dir = Path(schemas_dir)
        self.core_dir = self.schemas_dir / "core"
        self.includes_dir = self.schemas_dir / "includes"
        
        # 存储所有已解析的类型定义
        self.type_definitions: Dict[str, Dict[str, Any]] = {}
        
        # 存储所有schema文件的原始内容
        self.schema_files: Dict[str, Dict[str, Any]] = {}
        
        # 记录处理过程中的循环依赖
        self.processing_stack: Set[str] = set()
        
        # 存储base.yaml中的定义
        self.base_schema_definition: Optional[Dict[str, Any]] = None
        self.constraint_definition: Optional[Dict[str, Any]] = None
        
        # 统计约束合并信息
        self.constraint_merge_stats = {
            'base_constraint_applied': 0,
            'schemas_processed': 0
        }
        
    def load_all_schemas(self):
        """加载所有schema文件"""
        print("🔍 正在加载schema文件...")
        
        # 加载base.yaml中的additional_types
        self._load_base_types()
        
        # 加载includes目录中的共享类型定义
        self._load_includes()
        
        # 加载core目录中的schema文件
        self._load_core_schemas()
        
        print(f"✅ 已加载 {len(self.type_definitions)} 个类型定义")
        print(f"✅ 已加载 {len(self.schema_files)} 个schema文件")
    
    def _load_base_types(self):
        """加载base.yaml中的additional_types和schema定义"""
        base_file = self.schemas_dir / "base.yaml"
        if not base_file.exists():
            return
            
        try:
            with open(base_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            # 保存整个base.yaml的内容供后续使用
            self.base_schema_definition = content
            
            # 加载additional_types
            if content and 'additional_types' in content:
                additional_types = content['additional_types']
                
                # 处理新的结构：additional_types.types 是一个数组
                if 'types' in additional_types and isinstance(additional_types['types'], list):
                    for type_def in additional_types['types']:
                        if 'name' in type_def:
                            type_name = type_def['name']
                            # 为base.yaml中的类型添加默认版本v1
                            type_key = f"{type_name}:v1"
                            
                            # 构建完整的类型定义
                            type_spec = {
                                'type': type_def.get('type', 'object'),
                                'description': type_def.get('description')
                            }
                            
                            # 如果有properties，添加到类型定义中
                            if 'properties' in type_def:
                                type_spec['properties'] = type_def['properties']
                            
                            self.type_definitions[type_key] = type_spec
                            print(f"📌 已加载类型定义: {type_key}")
            
            # 加载constraint定义
            if content and 'additional_types' in content:
                additional_types = content['additional_types']
                if 'types' in additional_types and isinstance(additional_types['types'], list):
                    for type_def in additional_types['types']:
                        if isinstance(type_def, dict) and type_def.get('name') == 'constraint':
                            self.constraint_definition = type_def
                            print(f"🔧 已加载约束属性定义")
                            break
                            
            print(f"📁 已加载base types: {base_file.name}")
        except Exception as e:
            print(f"❌ 加载base.yaml文件失败: {e}")
    
    def _load_includes(self):
        """加载includes目录中的共享类型定义"""
        if not self.includes_dir.exists():
            return
            
        for yaml_file in self.includes_dir.glob("*.schema.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                
                if content and 'name' in content and 'versions' in content:
                    schema_name = content['name']
                    for version in content['versions']:
                        version_name = version['name']
                        type_key = f"{schema_name}:{version_name}"
                        self.type_definitions[type_key] = version.get('spec', {})
                        
                print(f"📁 已加载includes: {yaml_file.name}")
            except Exception as e:
                print(f"❌ 加载includes文件失败 {yaml_file}: {e}")
    
    def _load_core_schemas(self):
        """递归加载core目录中的schema文件"""
        if not self.core_dir.exists():
            return
            
        for yaml_file in self.core_dir.rglob("*.schema.yaml"):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                
                if content and 'name' in content:
                    schema_name = content['name']
                    self.schema_files[schema_name] = content
                    
                    # 同时将其作为类型定义存储
                    if 'versions' in content:
                        for version in content['versions']:
                            version_name = version['name']
                            type_key = f"{schema_name}:{version_name}"
                            self.type_definitions[type_key] = version.get('spec', {})
                
                print(f"📄 已加载schema: {yaml_file.relative_to(self.core_dir)}")
            except Exception as e:
                print(f"❌ 加载schema文件失败 {yaml_file}: {e}")
    
    def expand_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """展开所有schema文件"""
        print("\n🚀 开始展开schema定义...")
        
        expanded_schemas = {}
        
        for schema_name, schema_content in self.schema_files.items():
            print(f"\n📋 正在处理schema: {schema_name}")
            try:
                expanded_schema = self._expand_schema(schema_content)
                expanded_schemas[schema_name] = expanded_schema
                print(f"✅ 成功展开schema: {schema_name}")
                self.constraint_merge_stats['schemas_processed'] += 1
            except Exception as e:
                print(f"❌ 展开schema失败 {schema_name}: {e}")
                
        return expanded_schemas
    
    def _expand_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """展开单个schema文件"""
        expanded = copy.deepcopy(schema)
        
        if 'versions' in expanded:
            for version in expanded['versions']:
                if 'spec' in version:
                    version['spec'] = self._expand_spec(version['spec'])
        
        return expanded
    
    def _expand_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """展开spec定义"""
        if not isinstance(spec, dict):
            return spec
            
        expanded = copy.deepcopy(spec)
        
        # 处理extends继承
        if 'extends' in expanded:
            expanded = self._resolve_extends(expanded)
        
        # 处理type_ref引用
        if 'type_ref' in expanded:
            expanded = self._resolve_type_ref(expanded)
        
        # 合并constraint和default_constraint
        expanded = self._merge_constraints(expanded)
        
        # 通用处理：如果type字段引用的是一个带有constraint的类型定义，则展开它
        if 'type' in expanded and isinstance(expanded['type'], str):
            type_name = expanded['type']
            # 跳过内置基础类型
            builtin_types = {'string', 'number', 'integer', 'boolean', 'bool', 'array', 'object', 'map', 'any', 'enum', 'json'}
            if type_name not in builtin_types:
                # 尝试查找对应的类型定义
                type_def = self._get_type_definition(f"{type_name}:v1")
                if type_def:
                    # 保留原有的description
                    original_description = expanded.get('description')
                    original_constraint = expanded.get('constraint', {})
                    
                    # 特殊处理semantic_string类型
                    if type_name == 'semantic_string':
                        # 将semantic_string展开为object类型
                        expanded['type'] = 'object'
                        expanded['properties'] = copy.deepcopy(type_def.get('properties', {}))
                        
                        # 如果原来有description，保留它
                        if original_description:
                            expanded['description'] = original_description
                        elif 'description' in type_def:
                            expanded['description'] = type_def['description']
                    
                    # 处理其他自定义类型
                    elif 'constraint' in type_def:
                        # 使用类型定义的constraint
                        expanded['constraint'] = copy.deepcopy(type_def['constraint'])
                        
                        # 如果原来有description，保留它
                        if original_description:
                            expanded['description'] = original_description
                        
                        # 合并原有的constraint（不覆盖类型定义中的约束）
                        for key, value in original_constraint.items():
                            if key not in expanded['constraint']:
                                expanded['constraint'][key] = value
                        
                        # 移除type字段，因为现在使用constraint中的类型定义
                        if 'type' in expanded:
                            del expanded['type']
        
        # 递归处理properties
        if 'properties' in expanded and isinstance(expanded['properties'], dict):
            for prop_name, prop_def in expanded['properties'].items():
                expanded['properties'][prop_name] = self._expand_spec(prop_def)
        
        # 处理数组项的type_ref
        if 'constraint' in expanded and isinstance(expanded['constraint'], dict):
            constraint = expanded['constraint']
            if 'array' in constraint and 'item' in constraint['array']:
                constraint['array']['item'] = self._expand_spec(constraint['array']['item'])
            
            if 'map' in constraint and 'value' in constraint['map']:
                constraint['map']['value'] = self._expand_spec(constraint['map']['value'])
        
        return expanded
    
    def _resolve_extends(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """解析extends继承关系"""
        if 'extends' not in spec:
            return spec
            
        result = copy.deepcopy(spec)
        extends_list = result.pop('extends', [])
        
        # 按顺序合并所有继承的类型
        for extend_ref in extends_list:
            if extend_ref in self.processing_stack:
                print(f"⚠️  检测到循环依赖: {extend_ref}")
                continue
                
            self.processing_stack.add(extend_ref)
            try:
                parent_spec = self._get_type_definition(extend_ref)
                if parent_spec:
                    # 递归展开父类型
                    expanded_parent = self._expand_spec(parent_spec)
                    # 合并父类型到当前spec
                    result = self._merge_specs(expanded_parent, result)
            finally:
                self.processing_stack.discard(extend_ref)
        
        return result
    
    def _resolve_type_ref(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """解析type_ref引用"""
        if 'type_ref' not in spec:
            return spec
            
        type_ref = spec['type_ref']
        
        if type_ref in self.processing_stack:
            print(f"⚠️  检测到循环依赖: {type_ref}")
            return spec
            
        self.processing_stack.add(type_ref)
        try:
            referenced_spec = self._get_type_definition(type_ref)
            if referenced_spec:
                # 展开引用的类型
                expanded_ref = self._expand_spec(referenced_spec)
                # 移除type_ref，用展开的定义替换
                result = copy.deepcopy(spec)
                result.pop('type_ref', None)
                # 合并引用的定义
                result = self._merge_specs(expanded_ref, result)
                return result
        finally:
            self.processing_stack.discard(type_ref)
            
        return spec
    
    def _get_type_definition(self, type_ref: str) -> Optional[Dict[str, Any]]:
        """获取类型定义"""
        if type_ref in self.type_definitions:
            return self.type_definitions[type_ref]
        
        # 尝试查找不带版本号的引用
        if ':' not in type_ref:
            # 查找最新版本
            for key in self.type_definitions:
                if key.startswith(f"{type_ref}:"):
                    return self.type_definitions[key]
        
        print(f"⚠️  未找到类型定义: {type_ref}")
        return None
    
    def _merge_specs(self, parent: Dict[str, Any], child: Dict[str, Any]) -> Dict[str, Any]:
        """合并两个spec定义，子类覆盖父类"""
        result = copy.deepcopy(parent)
        
        for key, value in child.items():
            if key == 'properties' and key in result:
                # 合并properties
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = {**result[key], **value}
                else:
                    result[key] = value
            elif key == 'constraint' and key in result:
                # 合并constraint
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = {**result[key], **value}
                else:
                    result[key] = value
            else:
                # 其他字段直接覆盖
                result[key] = value
        
        return result
    
    def _merge_constraints(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """合并constraint，以schema中的定义为主"""
        if not isinstance(spec, dict):
            return spec
        
        result = copy.deepcopy(spec)
        
        # 移除default_constraint处理，因为已经不再支持这个字段
        
        # 从base.yaml中查找默认约束规则，但schema中的约束优先
        if self.base_schema_definition and 'constraint' not in result:
            # 只有当schema中没有定义constraint时，才应用base.yaml的默认约束
            result = self._apply_base_default_constraints(result)
        
        return result
    
    def _apply_base_default_constraints(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """从base.yaml的定义中查找并应用默认约束"""
        if not isinstance(spec, dict) or not self.base_schema_definition:
            return spec
        
        result = copy.deepcopy(spec)
        
        # 查找schema_spec、metadata_properties或constraint中是否有对应的default_constraint
        base_definitions = []
        
        # 安全地获取base定义
        schema_spec = self.base_schema_definition.get('schema_spec')
        if schema_spec:
            base_definitions.append(schema_spec)
            
        metadata_properties = self.base_schema_definition.get('metadata_properties')
        if metadata_properties:
            base_definitions.append(metadata_properties)
            
        constraint = self.constraint_definition
        if constraint:
            base_definitions.append(constraint)
        
        # 获取当前字段的类型
        field_type = result.get('type')
        
        if not field_type:
            return result
        
        for base_def in base_definitions:
            if isinstance(base_def, dict) and 'properties' in base_def:
                properties = base_def['properties']
                if isinstance(properties, dict):
                    # 遍历base定义中的所有属性
                    for prop_name, prop_def in properties.items():
                        # 如果类型匹配，并且base定义中有default_constraint
                        if (isinstance(prop_def, dict) and 
                            prop_def.get('type') == field_type and 
                            'default_constraint' in prop_def):
                            
                            default_constraint = prop_def['default_constraint']
                            current_constraint = result.get('constraint', {})
                            
                            # 合并约束：优先使用current_constraint中的值
                            merged_constraint = copy.deepcopy(default_constraint)
                            if isinstance(current_constraint, dict):
                                merged_constraint.update(current_constraint)
                            
                            result['constraint'] = merged_constraint
                            # print(f"📋 从base.yaml应用了类型'{field_type}'的默认约束")
                            self.constraint_merge_stats['base_constraint_applied'] += 1
                            break
        
        return result
    
    def save_expanded_schemas(self, expanded_schemas: Dict[str, Dict[str, Any]], output_dir: str):
        """保存展开后的schema文件"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"\n💾 正在保存展开后的schema到: {output_path}")
        
        # 创建自定义的YAML Dumper来改善多行字符串格式
        class CustomYamlDumper(yaml.SafeDumper):
            def represent_str(self, data):
                # 检查是否为多行字符串或长字符串
                if '\n' in data or len(data) > 80:
                    # 对于包含换行符或很长的字符串，使用折叠标量 >
                    return self.represent_scalar('tag:yaml.org,2002:str', data, style='>')
                return self.represent_scalar('tag:yaml.org,2002:str', data)

        # 注册自定义的字符串表示器
        CustomYamlDumper.add_representer(str, CustomYamlDumper.represent_str)
        
        for schema_name, schema_content in expanded_schemas.items():
            output_file = output_path / f"{schema_name}.expanded.yaml"
            
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    yaml.dump(schema_content, f, 
                             Dumper=CustomYamlDumper,
                             default_flow_style=False, 
                             allow_unicode=True, 
                             sort_keys=False, 
                             indent=2,
                             width=120)
                print(f"✅ 已保存: {output_file.name}")
            except Exception as e:
                print(f"❌ 保存失败 {output_file}: {e}")
    
    def generate_summary_report(self, expanded_schemas: Dict[str, Dict[str, Any]]) -> str:
        """生成展开结果的摘要报告"""
        report = []
        report.append("# MModel Schema 展开报告\n")
        
        report.append(f"## 📊 统计信息")
        report.append(f"- 共处理schema文件: {len(expanded_schemas)}")
        report.append(f"- 共加载类型定义: {len(self.type_definitions)}")
        report.append("")
        
        report.append("## 📋 处理的Schema列表")
        for schema_name, schema_content in expanded_schemas.items():
            versions = schema_content.get('versions', [])
            version_count = len(versions)
            report.append(f"- **{schema_name}**: {version_count} 个版本")
        
        report.append("")
        report.append("## 🔗 可用的类型定义")
        type_groups = defaultdict(list)
        for type_ref in sorted(self.type_definitions.keys()):
            type_name = type_ref.split(':')[0]
            type_groups[type_name].append(type_ref)
        
        for type_name, refs in type_groups.items():
            report.append(f"- **{type_name}**: {', '.join(refs)}")
        
        return "\n".join(report)


def main():
    """主函数"""
    print("🚀 MModel Schema Expander 启动")
    print("=" * 50)
    
    # 配置路径
    schemas_dir = "schemas"
    output_dir = "expanded_schemas"
    
    if not os.path.exists(schemas_dir):
        print(f"❌ schemas目录不存在: {schemas_dir}")
        return
    
    # 创建展开器
    expander = SchemaExpander(schemas_dir)
    
    try:
        # 加载所有schema文件
        expander.load_all_schemas()
        
        # 展开所有schema
        expanded_schemas = expander.expand_all_schemas()
        
        # 显示约束合并统计信息
        print(f"\n📊 约束合并统计:")
        print(f"   - 处理的schema数量: {expander.constraint_merge_stats['schemas_processed']}")
        print(f"   - 应用base.yaml默认约束: {expander.constraint_merge_stats['base_constraint_applied']}")
        
        # 保存结果
        expander.save_expanded_schemas(expanded_schemas, output_dir)
        
        # 生成报告
        report = expander.generate_summary_report(expanded_schemas)
        
        # 保存报告
        report_file = Path(output_dir) / "expansion_report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 展开报告已保存到: {report_file}")
        print("\n🎉 Schema展开完成！")
        
    except Exception as e:
        print(f"\n❌ 处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 