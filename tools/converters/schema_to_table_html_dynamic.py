#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schema to Table HTML Documentation Generator (Dynamic Version)
动态版本的 mmodel schema 到 HTML 表格文档转换器
基于 base.yaml 元数据定义动态生成，减少硬编码
"""

import yaml
import argparse
import os
import sys
from typing import Dict, Any, List, Optional, Union, Set, Tuple
import json
from pathlib import Path

# 添加项目根目录到Python路径，以便导入schema_validator
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.validators.schema_validator import SchemaValidator


class DynamicSchemaToTableHtmlConverter:
    def __init__(self):
        self.tables = []  # 存储所有表格
        self.current_table_id = 0
        self.expanded_schema = None  # 存储对应的expanded schema
        self.original_yaml_content = None  # 存储原始YAML文件内容
        
        # 加载base.yaml元数据定义
        self.base_schema = self._load_base_schema()
        self.metadata_properties = self.base_schema.get("metadata_properties", {})
        self.additional_types = self.base_schema.get("additional_types", {})
        
        # 初始化SchemaValidator以复用其方法
        self.validator = SchemaValidator("expanded_schemas")
        
    def _load_base_schema(self) -> Dict[str, Any]:
        """加载base.yaml文件"""
        base_path = project_root / "schemas" / "base.yaml"
        try:
            with open(base_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ 无法加载base.yaml: {e}")
            return {}
    
    def generate_table_id(self, name: str) -> str:
        """生成唯一的表格ID"""
        self.current_table_id += 1
        safe_name = name.replace(' ', '_').replace('-', '_').replace('.', '_')
        return f"table_{self.current_table_id}_{safe_name}"
    
    def load_expanded_schema(self, kind: str) -> Dict[str, Any]:
        """加载对应的expanded schema"""
        expanded_dir = project_root / 'expanded_schemas'
        expanded_file = expanded_dir / f"{kind}.expanded.yaml"
        
        if expanded_file.exists():
            with open(expanded_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return None
    
    def convert_file(self, yaml_file: str, output_file: str = None) -> str:
        """转换单个YAML文件为HTML"""
        # 读取原始YAML文件内容
        with open(yaml_file, 'r', encoding='utf-8') as f:
            self.original_yaml_content = f.read()
        
        # 解析YAML数据
        data = yaml.safe_load(self.original_yaml_content)
        
        self.tables = []
        self.current_table_id = 0
        
        # 加载对应的expanded schema
        if data and 'kind' in data:
            self.expanded_schema = self.load_expanded_schema(data['kind'])
        
        # 动态生成表格
        self._generate_tables_dynamic(data, os.path.basename(yaml_file))
        
        # 生成HTML
        html_content = self._generate_html(data)
        
        # 写入文件
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"✅ HTML文档已生成: {output_file}")
        
        return html_content
    
    def _generate_tables_dynamic(self, data: Dict[str, Any], file_name: str):
        """动态生成表格数据，基于元数据定义"""
        if not data or not isinstance(data, dict):
            return
        
        # 获取基本信息
        kind = data.get('kind', 'unknown')
        metadata = data.get('metadata', {})
        name = metadata.get('name', file_name)
        
        # 1. 生成基本信息表格（schema, kind, metadata的基本字段）
        self._generate_basic_info_table(data, name)
        
        # 2. 生成metadata详细字段表格
        if metadata:
            self._generate_metadata_table(metadata, name)
        
        # 3. 动态处理spec部分
        if 'spec' in data:
            self._generate_spec_tables(data['spec'], name, kind)
    
    def _generate_basic_info_table(self, data: Dict[str, Any], name: str):
        """生成基本信息表格"""
        info_fields = []
        
        # Kind
        if 'kind' in data:
            info_fields.append({
                'field': 'Kind (类型)',
                'value': data['kind'],
                'type': 'string',
                'configured': True
            })
        
        # Schema信息
        if 'schema' in data:
            schema = data['schema']
            if 'version' in schema:
                info_fields.append({
                    'field': 'Version (版本)',
                    'value': schema['version'],
                    'type': 'string',
                    'configured': True
                })
            if 'url' in schema:
                info_fields.append({
                    'field': 'Schema URL',
                    'value': schema['url'],
                    'type': 'string',
                    'configured': True
                })
        
        # Metadata基本信息
        if 'metadata' in data:
            metadata = data['metadata']
            if 'name' in metadata:
                info_fields.append({
                    'field': 'Name (名称)',
                    'value': metadata['name'],
                    'type': 'string',
                    'configured': True
                })
            if 'domain' in metadata:
                info_fields.append({
                    'field': 'Domain (域)',
                    'value': metadata['domain'],
                    'type': 'string',
                    'configured': True
                })
        
        if info_fields:
            self.tables.append({
                'id': self.generate_table_id('basic_info'),
                'title': f"{name} - 基本信息",
                'type': 'info',
                'data': info_fields
            })
    
    def _generate_metadata_table(self, metadata: Dict[str, Any], name: str):
        """生成metadata表格"""
        fields = []
        
        # 获取expanded metadata定义
        expanded_metadata = self._get_expanded_metadata_properties()
        
        # 处理多语言字段
        multilang_fields = ['display_name', 'description', 'short_description']
        for field_name in multilang_fields:
            if field_name in metadata:
                value = metadata[field_name]
                if isinstance(value, dict):
                    for lang, text in value.items():
                        lang_display = '中文' if lang == 'zh_cn' else 'English'
                        fields.append({
                            'field': f"{field_name} ({lang_display})",
                            'value': text,
                            'type': 'string',
                            'configured': True
                        })
                else:
                    fields.append({
                        'field': field_name,
                        'value': str(value),
                        'type': 'string',
                        'configured': True
                    })
            elif expanded_metadata and field_name in expanded_metadata:
                # 未配置的多语言字段
                fields.append({
                    'field': f"{field_name} (中文)",
                    'value': '<未配置>',
                    'type': 'string',
                    'configured': False
                })
                fields.append({
                    'field': f"{field_name} (English)",
                    'value': '<未配置>',
                    'type': 'string',
                    'configured': False
                })
        
        # 处理其他字段
        skip_fields = ['name', 'domain'] + multilang_fields
        for key, value in metadata.items():
            if key not in skip_fields and self._is_simple_value(value):
                fields.append({
                    'field': key,
                    'value': self._format_value(value),
                    'type': self._get_value_type(value),
                    'configured': True
                })
        
        if fields:
            self.tables.append({
                'id': self.generate_table_id('metadata'),
                'title': f"{name} - 元数据",
                'type': 'fields_table',
                'data': fields
            })
    
    def _generate_spec_tables(self, spec: Dict[str, Any], name: str, kind: str):
        """动态生成spec相关的表格"""
        # 获取expanded spec定义
        expanded_spec = self._get_expanded_spec_properties(kind)
        
        # 1. 生成简单字段表格
        simple_fields = []
        complex_fields = {}
        
        # 只处理实际spec中存在的字段
        if spec:
            for field_name, field_value in spec.items():
                # 获取对应的expanded定义（如果有）
                expanded_field = expanded_spec.get(field_name, {}) if expanded_spec else {}
                
                # 判断字段类型
                field_type = self._get_field_type(field_value, expanded_field)
                
                if field_type == 'simple':
                    # 简单字段
                    simple_fields.append(self._create_simple_field_info(
                        field_name, field_value, expanded_field
                    ))
                elif field_type == 'array_of_objects':
                    # 复杂数组字段（如metrics, fields, labels.keys等）
                    complex_fields[field_name] = {
                        'value': field_value,
                        'expanded': expanded_field,
                        'type': 'array_of_objects'
                    }
                elif field_type == 'object_with_properties':
                    # 对象类型字段（如properties）
                    complex_fields[field_name] = {
                        'value': field_value,
                        'expanded': expanded_field,
                        'type': 'object_with_properties'
                    }
                elif field_type == 'labels':
                    # 特殊处理labels
                    complex_fields[field_name] = {
                        'value': field_value,
                        'expanded': expanded_field,
                        'type': 'labels'
                    }
        
        # 生成简单字段表格
        if simple_fields:
            self.tables.append({
                'id': self.generate_table_id('spec_fields'),
                'title': f"{name} - 规格字段",
                'type': 'fields_table',
                'data': simple_fields
            })
        
        # 生成复杂字段表格
        for field_name, field_info in complex_fields.items():
            self._generate_complex_field_table(
                field_name, field_info, name, spec
            )
    
    def _get_field_type(self, value: Any, expanded_field: Dict) -> str:
        """判断字段类型"""
        # 首先检查expanded定义
        if expanded_field:
            exp_type = expanded_field.get('type')
            if exp_type == 'array':
                constraint = expanded_field.get('constraint', {})
                if 'array' in constraint and 'item' in constraint['array']:
                    item_type = constraint['array']['item'].get('type')
                    if item_type == 'object':
                        return 'array_of_objects'
                return 'simple'
            elif exp_type == 'object':
                # 检查是否有properties
                if 'properties' in expanded_field:
                    # 检查是否是labels类型
                    props = expanded_field['properties']
                    if 'keys' in props:
                        return 'labels'
                    return 'object_with_properties'
                return 'simple'
        
        # 根据实际值判断
        if value is None:
            return 'simple'
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                return 'array_of_objects'
            return 'simple'
        elif isinstance(value, dict):
            # 检查是否是labels
            if 'keys' in value and isinstance(value.get('keys'), list):
                return 'labels'
            # 检查是否有复杂结构
            for v in value.values():
                if isinstance(v, dict) and 'type' in v:
                    return 'object_with_properties'
            return 'simple'
        else:
            return 'simple'
    
    def _create_simple_field_info(self, field_name: str, value: Any, 
                                  expanded_field: Dict) -> Dict:
        """创建简单字段信息"""
        field_info = {
            'field': field_name,
            'configured': value is not None
        }
        
        if value is not None:
            field_info['value'] = self._format_value(value)
            field_info['type'] = self._get_value_type(value)
        else:
            field_info['value'] = '<未配置>'
            field_info['type'] = self._get_expanded_type(expanded_field)
            
            # 添加默认值
            default = self._get_default_value(expanded_field)
            if default is not None:
                field_info['default'] = self._format_value(default)
        
        return field_info
    
    def _generate_complex_field_table(self, field_name: str, field_info: Dict,
                                      parent_name: str, spec: Dict):
        """生成复杂字段的表格"""
        field_type = field_info['type']
        value = field_info['value']
        expanded = field_info['expanded']
        
        if field_type == 'array_of_objects':
            # 生成对象数组表格（如metrics, fields）
            self._generate_object_array_table(
                field_name, value, expanded, parent_name
            )
        elif field_type == 'labels':
            # 特殊处理labels
            self._generate_labels_table(
                value, expanded, parent_name
            )
        elif field_type == 'object_with_properties':
            # 生成properties表格
            self._generate_properties_table(
                value, expanded, parent_name, field_name
            )
    
    def _generate_object_array_table(self, field_name: str, value: Any,
                                     expanded: Dict, parent_name: str):
        """生成对象数组类型的表格"""
        # 获取数组项的属性定义
        item_properties = self._get_array_item_properties(expanded)
        
        # 准备表格数据
        table_data = []
        items = value if value else []
        
        # 如果没有数据，返回提示
        if not items:
            return
        
        # 从实际数据中收集所有出现的字段
        all_fields = set()
        for item in items:
            if isinstance(item, dict):
                all_fields.update(item.keys())
        
        # 构建实际使用的属性定义
        actual_properties = {}
        for field in all_fields:
            if field == '_configured':  # 跳过内部标记
                continue
            # 如果expanded中有定义，使用它；否则创建一个基本定义
            if item_properties and field in item_properties:
                actual_properties[field] = item_properties[field]
            else:
                # 根据实际值推断类型
                sample_value = next((item.get(field) for item in items if field in item), None)
                actual_properties[field] = {
                    'type': self._get_value_type(sample_value)
                }
        
        # 收集所有布尔字段
        bool_fields = []
        for prop_name, prop_def in actual_properties.items():
            # 检查实际值是否都是布尔类型
            all_bool = all(isinstance(item.get(prop_name), bool) for item in items if prop_name in item)
            if all_bool or prop_def.get('type') == 'boolean':
                bool_fields.append(prop_name)
        
        # 为每个项创建表格行
        for item in items:
            table_data.append(self._merge_item_with_properties(
                item, actual_properties, bool_fields
            ))
        
        # 决定表格类型和标题
        display_name = self._get_field_display_name(field_name)
        
        self.tables.append({
            'id': self.generate_table_id(field_name),
            'title': f"{parent_name} - {display_name}",
            'type': 'object_array',
            'data': table_data,
            'columns': self._get_table_columns(actual_properties, bool_fields),
            'bool_fields': bool_fields
        })
    
    def _generate_labels_table(self, value: Any, expanded: Dict, parent_name: str):
        """生成labels表格"""
        # Labels基本信息
        if value and isinstance(value, dict):
            label_info = []
            for key, val in value.items():
                if key != 'keys' and self._is_simple_value(val):
                    label_info.append({
                        'field': key,
                        'value': self._format_value(val),
                        'type': self._get_value_type(val),
                        'configured': True
                    })
            
            if label_info:
                self.tables.append({
                    'id': self.generate_table_id('label_config'),
                    'title': f"{parent_name} - 标签配置",
                    'type': 'fields_table',
                    'data': label_info
                })
        
        # Labels keys作为对象数组处理
        keys_expanded = None
        if expanded and 'properties' in expanded and 'keys' in expanded['properties']:
            keys_expanded = expanded['properties']['keys']
        
        keys_value = value.get('keys', []) if value else []
        self._generate_object_array_table('labels', keys_value, keys_expanded, parent_name)
    
    def _generate_properties_table(self, value: Any, expanded: Dict, 
                                  parent_name: str, field_name: str):
        """生成properties表格"""
        # 获取所有属性
        all_props = {}
        
        # 从expanded中获取属性定义
        if expanded and 'properties' in expanded:
            for prop_name, prop_def in expanded['properties'].items():
                all_props[prop_name] = {
                    'definition': prop_def,
                    'value': None,
                    'configured': False
                }
        
        # 从实际值中更新
        if value and isinstance(value, dict):
            for prop_name, prop_value in value.items():
                if prop_name in all_props:
                    all_props[prop_name]['value'] = prop_value
                    all_props[prop_name]['configured'] = True
                else:
                    all_props[prop_name] = {
                        'definition': {},
                        'value': prop_value,
                        'configured': True
                    }
        
        # 生成表格数据
        table_data = []
        for prop_name, prop_info in sorted(all_props.items()):
            prop_def = prop_info['definition']
            prop_value = prop_info['value']
            configured = prop_info['configured']
            
            row = {
                'name': prop_name,
                'type': prop_value.get('type', prop_def.get('type', 'unknown')) if prop_value else prop_def.get('type', 'unknown'),
                'configured': configured
            }
            
            # 处理描述
            if prop_value and 'description' in prop_value:
                desc = prop_value['description']
            elif prop_def and 'description' in prop_def:
                desc = prop_def['description']
            else:
                desc = None
            
            if desc:
                if isinstance(desc, dict):
                    row['description_zh'] = desc.get('zh_cn', '')
                    row['description_en'] = desc.get('en_us', '')
                else:
                    row['description_zh'] = str(desc)
                    row['description_en'] = ''
            else:
                row['description_zh'] = '<未配置>' if not configured else ''
                row['description_en'] = '<未配置>' if not configured else ''
            
            # 处理约束
            constraints = []
            if prop_value:
                # 从实际值中提取约束
                constraint_fields = ['required', 'pattern', 'min_len', 'max_len', 
                                   'min_value', 'max_value', 'enum', 'format']
                for cf in constraint_fields:
                    if cf in prop_value:
                        constraints.append(f"{cf}: {prop_value[cf]}")
            
            row['constraints'] = constraints
            row['required'] = prop_value.get('required', False) if prop_value else False
            row['default'] = prop_value.get('default_value', '-') if prop_value else '-'
            
            table_data.append(row)
        
        # 创建表格
        display_name = self._get_field_display_name(field_name)
        self.tables.append({
            'id': self.generate_table_id(field_name),
            'title': f"{parent_name} - {display_name}",
            'type': 'properties',
            'data': table_data
        })
    
    def _get_array_item_properties(self, expanded: Dict) -> Dict[str, Any]:
        """获取数组项的属性定义"""
        if not expanded:
            return {}
        
        constraint = expanded.get('constraint', {})
        if 'array' in constraint and 'item' in constraint['array']:
            item = constraint['array']['item']
            if 'properties' in item:
                return item['properties']
        
        return {}
    
    def _merge_item_with_properties(self, item: Dict, properties: Dict,
                                   bool_fields: List[str]) -> Dict:
        """合并项数据与属性定义"""
        merged = {}
        
        # 添加所有属性的默认值
        for prop_name, prop_def in properties.items():
            if prop_name in item:
                merged[prop_name] = item[prop_name]
            else:
                merged[prop_name] = self._get_empty_value(prop_def)
        
        # 保留配置标记
        if '_configured' in item:
            merged['_configured'] = item['_configured']
        
        return merged
    
    def _get_empty_value(self, prop_def: Dict) -> Any:
        """获取属性的空值"""
        prop_type = prop_def.get('type', 'string')
        
        # 先检查默认值
        default = self._get_default_value(prop_def)
        if default is not None:
            return default
        
        # 根据类型返回空值
        if prop_type == 'boolean':
            return False
        elif prop_type in ['number', 'integer', 'float']:
            return 0
        elif prop_type == 'array':
            return []
        elif prop_type == 'object':
            # 检查是否是多语言对象
            if 'properties' in prop_def:
                props = prop_def['properties']
                if set(props.keys()) <= {'zh_cn', 'en_us'}:
                    return {'zh_cn': '', 'en_us': ''}
            return {}
        else:
            return ''
    
    def _get_table_columns(self, properties: Dict, bool_fields: List[str]) -> List[Dict]:
        """获取表格的列定义"""
        columns = []
        
        # 定义特殊列的顺序和显示名称
        special_columns = {
            'name': '名称',
            'display_name': '显示名称',
            'description': '描述',
            'short_description': '简短描述',
            'type': '类型',
            'golden_metric': '黄金指标',
            'unit': '单位',
            'data_format': '数据格式',
            'aggregator': '聚合方式',
            'interval_us': '间隔(us)',
            'default_value': '默认值',
            'launch_stage': '发布阶段',
            'generator': '生成方式',
            'example': '示例',
            'pattern': '正则',
            'default_order': '默认序',
            'domain': '域',
            'required': '必填',
            'primary_key': '主键',
            'min_value': '最小值',
            'max_value': '最大值',
            'min_size': '最小大小',
            'max_size': '最大大小',
            'min_len': '最小长度',
            'max_len': '最大长度',
            'enum': '枚举',
            'format': '格式',
            'advanced': '高级约束',
        }
        
        # 首先添加特殊列
        added_columns = set()
        for col_name, display_name in sorted(special_columns.items()):
            if col_name in properties:
                columns.append({
                    'name': col_name,
                    'display_name': display_name,
                    'type': properties[col_name].get('type', 'string')
                })
                added_columns.add(col_name)
        
        # 添加剩余的列
        for prop_name, prop_def in sorted(properties.items()):
            if prop_name not in added_columns and prop_name not in bool_fields:
                display_name = self._get_field_display_name(prop_name)
                columns.append({
                    'name': prop_name,
                    'display_name': display_name,
                    'type': prop_def.get('type', 'string')
                })
        
        # 最后添加布尔字段组
        if bool_fields:
            columns.append({
                'name': '_bool_fields',
                'display_name': '特性',
                'type': 'bool_group',
                'fields': bool_fields
            })
        
        return columns
    
    def _get_field_display_name(self, field_name: str) -> str:
        """获取字段的显示名称"""
        display_names = {
            'labels': '标签列表',
            'metrics': '指标列表',
            'fields': '字段列表',
            'filters': '过滤器',
            'properties': '属性',
            'spec': '详情',
            'metadata': '元数据'
        }
        return display_names.get(field_name, field_name)
    
    def _get_expanded_metadata_properties(self) -> Dict[str, Any]:
        """获取expanded metadata属性定义"""
        if not self.expanded_schema or 'versions' not in self.expanded_schema:
            return {}
        
        version = self.expanded_schema['versions'][0]
        if 'spec' in version and 'properties' in version['spec']:
            metadata = version['spec']['properties'].get('metadata', {})
            if 'properties' in metadata:
                return metadata['properties']
        
        return {}
    
    def _get_expanded_spec_properties(self, kind: str) -> Dict[str, Any]:
        """获取expanded spec属性定义"""
        if not self.expanded_schema or 'versions' not in self.expanded_schema:
            return {}
        
        version = self.expanded_schema['versions'][0]
        if 'spec' in version and 'properties' in version['spec']:
            return version['spec']['properties']
        
        return {}
    
    def _get_expanded_field_info(self, path: List[str]) -> Dict[str, Any]:
        """从expanded schema中获取字段信息"""
        if not self.expanded_schema:
            return None
        
        current = self.expanded_schema
        
        # 导航到正确的版本
        if 'versions' in current and current['versions']:
            current = current['versions'][0]
        
        # 按路径导航
        for key in path:
            if isinstance(current, dict):
                if 'spec' in current and key in current['spec'].get('properties', {}):
                    current = current['spec']['properties'][key]
                elif 'properties' in current and key in current['properties']:
                    current = current['properties'][key]
                elif key in current:
                    current = current[key]
                else:
                    return None
            else:
                return None
        
        return current
    
    def _get_default_value(self, field_info: Dict) -> Any:
        """获取字段的默认值"""
        if not field_info:
            return None
        
        # 直接的默认值
        if 'default_value' in field_info:
            return field_info['default_value']
        
        # 从constraint中获取默认值
        constraint = field_info.get('constraint', {})
        if isinstance(constraint, dict):
            if 'default_value' in constraint:
                return constraint['default_value']
            # 枚举的默认值
            if 'enum' in constraint and isinstance(constraint['enum'], dict):
                if 'default_value' in constraint['enum']:
                    return constraint['enum']['default_value']
        
        return None
    
    def _get_expanded_type(self, field_info: Dict) -> str:
        """从expanded schema中获取类型信息"""
        if not field_info:
            return 'unknown'
        
        field_type = field_info.get('type', 'unknown')
        
        # 处理数组类型
        if field_type == 'array':
            constraint = field_info.get('constraint', {})
            if 'array' in constraint and 'item' in constraint['array']:
                item_type = constraint['array']['item'].get('type', 'unknown')
                return f'array[{item_type}]'
        
        return field_type
    
    def _is_simple_value(self, value: Any) -> bool:
        """判断是否是简单值"""
        if value is None:
            return True
        elif isinstance(value, (str, int, float, bool)):
            return True
        elif isinstance(value, list):
            # 简单数组
            return all(isinstance(item, (str, int, float, bool)) for item in value)
        else:
            return False
    
    def _format_value(self, value: Any) -> str:
        """格式化值的显示"""
        if isinstance(value, list):
            if self._is_simple_value(value):
                return ', '.join(str(item) for item in value)
            else:
                return json.dumps(value, ensure_ascii=False, indent=2)
        elif isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, indent=2)
        elif isinstance(value, bool):
            return '是' if value else '否'
        else:
            return str(value)
    
    def _get_value_type(self, value: Any) -> str:
        """获取值的类型描述"""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, list):
            if not value:
                return 'array'
            elif all(isinstance(item, (str, int, float, bool)) for item in value):
                item_type = type(value[0]).__name__
                return f'array[{item_type}]'
            else:
                return 'array[object]'
        elif isinstance(value, dict):
            return 'object'
        else:
            return 'unknown'
    
    def _generate_html(self, data: Dict) -> str:
        """生成HTML文档"""
        title = data.get('metadata', {}).get('name', 'Schema Documentation')
        return self._create_html_document(title)
    
    def _create_html_document(self, title: str) -> str:
        """创建HTML文档"""
        # 生成CSS
        css_content = self._generate_css()
        
        # 生成JavaScript
        js_content = self._generate_javascript()
        
        # 生成表格HTML
        tables_html = self._generate_tables_html()
        
        # 生成原始YAML代码块
        yaml_block = self._generate_yaml_block()
        
        # 组装HTML - 使用双大括号转义JavaScript中的大括号
        html_template = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Schema Documentation</title>
    <style>
{css_content}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>{title}</h1>
            <div class="header-actions">
                <button class="btn-primary" onclick="expandAllTables()">展开所有表格</button>
                <button class="btn-secondary" onclick="collapseAllTables()">折叠所有表格</button>
                <button class="btn-secondary" onclick="window.open('/index.html')">返回主页</button>
            </div>
        </header>
        
        <main class="main-content">
            <div class="tables-container">
{tables_html}
            </div>
{yaml_block}
        </main>
    </div>
    
    <script>
{js_content}
    </script>
</body>
</html>'''
        
        return html_template.format(
            title=title,
            css_content=css_content,
            js_content=js_content,
            tables_html=tables_html,
            yaml_block=yaml_block
        )
    
    def _generate_yaml_block(self) -> str:
        """生成原始YAML代码块"""
        if not self.original_yaml_content:
            return ''
            
        return '''
        <div class="table-wrapper yaml-block">
            <div class="table-header">
                <h3 class="table-title">原始 YAML 定义</h3>
                <span class="table-toggle">▶</span>
            </div>
            <div class="table-content collapsed">
                <pre class="yaml-code-block">{yaml_content}</pre>
            </div>
        </div>
        '''.format(yaml_content=self.original_yaml_content)
    
    def _generate_css(self) -> str:
        """生成CSS样式"""
        css = '''
        /* 基础样式 */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        /* 头部样式 */
        .header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 24px;
            margin-bottom: 10px;
            color: #1890ff;
        }
        
        .header-actions {
            display: flex;
            gap: 10px;
        }
        
        .btn-primary, .btn-secondary {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: #1890ff;
            color: white;
        }
        
        .btn-primary:hover {
            background: #40a9ff;
        }
        
        .btn-secondary {
            background: #f0f0f0;
            color: #333;
            border: 1px solid #d9d9d9;
        }
        
        .btn-secondary:hover {
            background: #e0e0e0;
        }
        
        /* 主内容区域 */
        .main-content {
            width: 100%;
        }
        
        /* 表格容器 */
        .tables-container {
            display: flex;
            flex-direction: column;
            gap: 20px;
            max-width: 1600px;  /* 限制最大宽度，避免超宽屏幕上表格过度拉伸 */
            margin: 0 auto;  /* 居中显示 */
        }
        
        .table-wrapper {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .table-header {
            padding: 16px 20px;
            background: #fafafa;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }
        
        .table-header:hover {
            background: #f0f0f0;
        }
        
        .table-title {
            font-size: 16px;
            font-weight: 500;
            color: #333;
        }
        
        .table-toggle {
            font-size: 14px;
            color: #666;
            user-select: none;
        }
        
        .table-content {
            padding: 20px;
            overflow-x: auto;  /* 允许水平滚动 */
            overflow-y: visible;  /* 垂直方向不限制 */
        }
        
        .table-content.collapsed {
            display: none;
        }
        
        /* 数据表格样式 */
        .data-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            table-layout: auto;  /* 自动布局，根据内容调整列宽 */
        }
        
        .data-table th {
            text-align: left;
            padding: 10px;
            background: #fafafa;
            border: 1px solid #e0e0e0;
            font-weight: 500;
            white-space: nowrap;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        
        .data-table td {
            padding: 10px;
            border: 1px solid #e0e0e0;
            vertical-align: top;
        }
        
        .data-table tr:hover {
            background: #f5f5f5;
        }
        
        /* 字段表格样式 */
        .fields-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: auto;  /* 自动布局 */
        }
        
        .fields-table th {
            text-align: left;
            padding: 10px;
            background: #f0f9ff;
            border: 1px solid #b3d9ff;
            font-weight: 500;
        }
        
        .fields-table td {
            padding: 10px;
            border: 1px solid #e0e0e0;
        }
        
        .fields-table .field-name {
            font-weight: 500;
            color: #1890ff;
            white-space: nowrap;  /* 字段名不换行 */
        }
        
        .fields-table .field-type {
            font-family: Consolas, Monaco, "Courier New", monospace;
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 12px;
            white-space: nowrap;  /* 类型不换行 */
        }
        
        /* 针对描述字段的特殊样式 */
        .description-cell {
            min-width: 120px;  /* 描述字段最小宽度 */
            max-width: 300px;  /* 描述字段最大宽度 */
            word-wrap: break-word;
            white-space: pre-wrap;
        }
        
        /* 属性名列 */
        .property-name-cell {
            white-space: nowrap;
            min-width: 80px;
        }
        
        /* 类型列 */
        .type-cell {
            white-space: nowrap;
            min-width: 80px;
        }
        
        /* 布尔值列 */
        .bool-cell {
            text-align: center;
            white-space: nowrap;
            width: 60px;
        }
        
        /* 默认值列 */
        .default-cell {
            white-space: nowrap;
            min-width: 80px;
        }
        
        /* 约束条件列 */
        .constraint-cell {
            min-width: 150px;
        }
        
        /* 处理长名称的换行 */
        .name-cell {
            word-break: break-all;   /*允许在任意字符处换行 */
            /*word-wrap: break-word;   兼容旧浏览器 */
            min-width: 80px;
            max-width: 300px;  /* 限制最大宽度，避免过宽 */
        }
        
        /* metrics表格中的name列特殊处理 */
        .metric-name {
            word-break: break-all;
            /*word-wrap: break-word;*/
            font-weight: 500;
            min-width: 80px;
            display: inline-block; /* 或者使用 block */
        }
        
        /* 未配置字段的样式 */
        .unconfigured {
            color: #999;
            font-style: italic;
        }
        
        .unconfigured-value {
            color: #999;
            font-style: italic;
        }
        
        .unconfigured-field {
            background-color: #fafafa !important;
            color: #999;
        }
        
        .unconfigured-field td {
            color: #999;
        }
        
        .default-value {
            color: #52c41a;
            font-size: 12px;
            margin-left: 8px;
        }
        
        tr.unconfigured-row {
            background-color: #fafafa;
        }
        
        tr.unconfigured-row:hover {
            background-color: #f0f0f0;
        }
        
        tr.unconfigured-row td {
            color: #999;
        }
        
        tr.unconfigured-row .field-name {
            color: #999;
        }
        
        /* 多行文本样式 */
        .multiline-text {
            white-space: pre-wrap;
            word-break: break-word;
        }
        
        /* 标签样式 */
        .tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
            margin-right: 4px;
        }
        
        .tag-type {
            background: #e6f7ff;
            color: #1890ff;
            border: 1px solid #91d5ff;
        }
        
        .tag-boolean {
            background: #f6ffed;
            color: #52c41a;
            border: 1px solid #b7eb8f;
        }
        
        .tag-required {
            background: #fff1f0;
            color: #ff4d4f;
            border: 1px solid #ffccc7;
        }
        
        /* 代码样式 */
        .code {
            font-family: Consolas, Monaco, "Courier New", monospace;
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 12px;
            word-break: break-all;   /*允许在任意字符处换行 */
        }
        
        .code-block {
            display: block;
            background: #f5f5f5;
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: Consolas, Monaco, "Courier New", monospace;
            font-size: 12px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-all;   /*允许在任意字符处换行 */
            min-width: 100px;
            display: inline-block; /* 或者使用 block */
        }
        
        /* 约束信息样式 */
        .constraints-list {
            font-size: 12px;
            color: #666;
            margin-top: 4px;
        }
        
        .constraints-list li {
            margin-left: 20px;
        }
        
        /* 勾选框样式 */
        .bool-checkmark {
            color: #52c41a;
            font-size: 16px;
        }
        
        .bool-cross {
            color: #999;
            font-size: 16px;
        }
        
        /* 布尔字段组 */
        .bool-field-group {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            min-width: 80px;  /* 特性列最小宽度 */
        }
        
        .bool-field-item {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .bool-field-name {
            font-size: 12px;
            color: #666;
        }
        
        /* 多语言字段 */
        .multilang-field {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        
        .lang-label {
            font-size: 11px;
            color: #999;
            font-weight: normal;
        }
        
        /* 滚动条样式 */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #888;
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
        
        /* 响应式设计 */
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .data-table {
                font-size: 12px;
            }
            
            .data-table th,
            .data-table td {
                padding: 6px;
            }
            
            .table-content {
                padding: 10px;
            }
        }
        
        /* YAML代码块样式 */
        .yaml-block {
            margin-top: 40px;
            border-top: 2px solid #e0e0e0;
            padding-top: 20px;
        }
        
        /* 列宽调整相关样式 */
        .resizable-table {
            position: relative;
        }
        
        .resize-handle {
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 5px;
            cursor: col-resize;
            user-select: none;
            /* 半透明的蓝色，hover时更明显 */
            background: transparent;
            /* 添加一个细边框，让用户知道可以拖拽 */
            border-right: 1px solid #e0e0e0;
        }
        
        .resize-handle:hover {
            background: rgba(24, 144, 255, 0.3);
            border-right: 2px solid #1890ff;
        }
        
        .resize-handle.active {
            background: rgba(24, 144, 255, 0.5);
            border-right: 2px solid #1890ff;
        }
        
        /* 可调整列宽的表格头 */
        th.resizable {
            position: relative;
            /* 防止文字被选中 */
            user-select: none;
        }
        
        /* 调整列宽时的视觉反馈线 */
        .resize-line {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 2px;
            background: #1890ff;
            z-index: 1000;
            display: none;
            pointer-events: none;
        }
        
        .yaml-code-block {
            background: #282c34;
            color: #abb2bf;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-family: Consolas, Monaco, "Courier New", monospace;
            font-size: 13px;
            line-height: 1.5;
            white-space: pre;
            tab-size: 2;
        }
        
        .yaml-code-block .key {
            color: #e06c75;
        }
        
        .yaml-code-block .string {
            color: #98c379;
        }
        
        .yaml-code-block .number {
            color: #d19a66;
        }
        
        .yaml-code-block .boolean {
            color: #56b6c2;
        }
        
        .yaml-code-block .null {
            color: #5c6370;
        }
        '''
        return css
    
    def _generate_javascript(self) -> str:
        """生成JavaScript代码"""
        js = '''// 切换表格展开/折叠
function toggleTable(element) {
    const wrapper = element.closest('.table-wrapper');
    const content = wrapper.querySelector('.table-content');
    const toggle = wrapper.querySelector('.table-toggle');
    
    if (content.classList.contains('collapsed')) {
        content.classList.remove('collapsed');
        toggle.textContent = '▼';
    } else {
        content.classList.add('collapsed');
        toggle.textContent = '▶';
    }
}

// 展开所有表格
function expandAllTables() {
    document.querySelectorAll('.table-content').forEach(content => {
        content.classList.remove('collapsed');
    });
    document.querySelectorAll('.table-toggle').forEach(toggle => {
        toggle.textContent = '▼';
    });
}

// 折叠所有表格
function collapseAllTables() {
    document.querySelectorAll('.table-content').forEach(content => {
        content.classList.add('collapsed');
    });
    document.querySelectorAll('.table-toggle').forEach(toggle => {
        toggle.textContent = '▶';
    });
}

// 语法高亮YAML代码
function highlightYAML() {
    // 移除语法高亮功能，直接显示原始YAML内容
    // 避免正则表达式替换导致的显示问题
}

// DOM加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 表格头点击事件 - 使用事件委托
    document.addEventListener('click', function(e) {
        const header = e.target.closest('.table-header');
        if (header) {
            toggleTable(header);
        }
    });
    
    // 初始化YAML语法高亮
    highlightYAML();
    
    // 初始化表格列宽调整功能
    initTableResize();
});

// 表格列宽调整功能
function initTableResize() {
    const tables = document.querySelectorAll('.data-table, .fields-table');
    
    // 先恢复之前保存的列宽
    restoreColumnWidths();
    
    tables.forEach(table => {
        // 为表格添加resizable类
        table.classList.add('resizable-table');
        
        // 获取所有的表头
        const headers = table.querySelectorAll('th');
        
        headers.forEach((header, index) => {
            // 跳过最后一列，最后一列不需要调整
            if (index < headers.length - 1) {
                header.classList.add('resizable');
                
                // 创建拖拽手柄
                const resizeHandle = document.createElement('div');
                resizeHandle.className = 'resize-handle';
                header.appendChild(resizeHandle);
                
                // 添加拖拽事件
                setupColumnResize(resizeHandle, header, table);
            }
        });
    });
}

function setupColumnResize(handle, header, table) {
    let startX = 0;
    let startWidth = 0;
    let currentHeader = header;
    let resizeLine = null;
    
    // 鼠标按下事件
    handle.addEventListener('mousedown', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        startX = e.pageX;
        startWidth = currentHeader.offsetWidth;
        
        // 添加active类
        handle.classList.add('active');
        
        // 创建视觉反馈线
        if (!resizeLine) {
            resizeLine = document.createElement('div');
            resizeLine.className = 'resize-line';
            document.body.appendChild(resizeLine);
        }
        
        // 设置反馈线位置
        const rect = handle.getBoundingClientRect();
        resizeLine.style.left = rect.right + 'px';
        resizeLine.style.top = rect.top + 'px';
        resizeLine.style.height = table.offsetHeight + 'px';
        resizeLine.style.display = 'block';
        
        // 添加临时的全局事件监听
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        
        // 防止文字选中
        document.body.style.userSelect = 'none';
    });
    
    function handleMouseMove(e) {
        const diff = e.pageX - startX;
        const newWidth = Math.max(50, startWidth + diff); // 最小宽度50px
        
        // 更新反馈线位置
        if (resizeLine) {
            const rect = handle.getBoundingClientRect();
            resizeLine.style.left = (rect.left + diff) + 'px';
        }
    }
    
    function handleMouseUp(e) {
        const diff = e.pageX - startX;
        const newWidth = Math.max(50, startWidth + diff);
        
        // 设置新宽度
        currentHeader.style.width = newWidth + 'px';
        currentHeader.style.minWidth = newWidth + 'px';
        currentHeader.style.maxWidth = newWidth + 'px';
        
        // 清理
        handle.classList.remove('active');
        if (resizeLine) {
            resizeLine.style.display = 'none';
        }
        
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.userSelect = '';
        
        // 保存列宽到localStorage（可选）
        saveColumnWidth(table, currentHeader, newWidth);
    }
}

// 保存列宽设置（可选功能）
function saveColumnWidth(table, header, width) {
    // 获取表格的唯一标识
    const tableId = table.closest('.table-wrapper')?.id || '';
    if (!tableId) return;
    
    // 获取列索引
    const columnIndex = Array.from(header.parentElement.children).indexOf(header);
    
    // 保存到localStorage
    const key = `table_width_${tableId}_col_${columnIndex}`;
    localStorage.setItem(key, width);
}

// 恢复列宽设置（可选功能）
function restoreColumnWidths() {
    const tables = document.querySelectorAll('.resizable-table');
    
    tables.forEach(table => {
        const tableId = table.closest('.table-wrapper')?.id || '';
        if (!tableId) return;
        
        const headers = table.querySelectorAll('th');
        headers.forEach((header, index) => {
            const key = `table_width_${tableId}_col_${index}`;
            const savedWidth = localStorage.getItem(key);
            
            if (savedWidth) {
                header.style.width = savedWidth + 'px';
                header.style.minWidth = savedWidth + 'px';
                header.style.maxWidth = savedWidth + 'px';
            }
        });
    });
}
'''
        return js
    
    def _generate_tables_html(self) -> str:
        """生成所有表格的HTML"""
        html_parts = []
        
        for table in self.tables:
            table_html = self._generate_single_table_html(table)
            html_parts.append(table_html)
        
        return '\n'.join(html_parts)
    
    def _generate_single_table_html(self, table: Dict) -> str:
        """生成单个表格的HTML"""
        table_id = table['id']
        title = table['title']
        table_type = table['type']
        data = table['data']
        
        # 表格容器
        html = f'''
        <div class="table-wrapper" id="{table_id}">
            <div class="table-header">
                <h3 class="table-title">{title}</h3>
                <span class="table-toggle">▼</span>
            </div>
            <div class="table-content">
        '''
        
        # 根据类型生成不同的表格内容
        if table_type == 'info':
            html += self._generate_info_table_html(data)
        elif table_type == 'fields_table':
            html += self._generate_fields_table_html(data)
        elif table_type == 'object_array':
            html += self._generate_object_array_table_html(
                data, table.get('columns', []), table.get('bool_fields', [])
            )
        elif table_type == 'properties':
            html += self._generate_properties_table_html(data)
        
        html += '''
            </div>
        </div>
        '''
        
        return html
    
    def _generate_info_table_html(self, data: List[Dict]) -> str:
        """生成基本信息表格HTML"""
        html = '''
        <table class="fields-table">
            <thead>
                <tr>
                    <th>字段</th>
                    <th>值</th>
                    <th>类型</th>
                </tr>
            </thead>
            <tbody>
        '''
        
        for item in data:
            row_class = '' if item.get('configured', True) else ' class="unconfigured-row"'
            html += f'''
            <tr{row_class}>
                <td class="field-name">{item['field']}</td>
                <td>{item['value']}</td>
                <td><span class="field-type">{item['type']}</span></td>
            </tr>
            '''
        
        html += '''
            </tbody>
        </table>
        '''
        return html
    
    def _generate_fields_table_html(self, data: List[Dict]) -> str:
        """生成字段表格HTML"""
        html = '''
        <table class="fields-table">
            <thead>
                <tr>
                    <th>字段名</th>
                    <th>值</th>
                    <th>类型</th>
                    <th>默认值</th>
                </tr>
            </thead>
            <tbody>
        '''
        
        for item in data:
            configured = item.get('configured', True)
            row_class = '' if configured else ' class="unconfigured-row"'
            
            value_display = item['value']
            # 如果值很长，使用代码块显示
            if len(str(value_display)) > 100 or '\n' in str(value_display):
                value_display = f'<pre class="code-block">{value_display}</pre>'
            elif not configured:
                value_display = f'<span class="unconfigured-value">{value_display}</span>'
            
            # 默认值
            default_value = item.get('default', '')
            if default_value and default_value != '-':
                default_display = f'<span class="default-value">{default_value}</span>'
            else:
                default_display = '-'
            
            html += f'''
            <tr{row_class}>
                <td class="field-name">{item['field']}</td>
                <td class="multiline-text">{value_display}</td>
                <td><span class="field-type">{item['type']}</span></td>
                <td>{default_display}</td>
            </tr>
            '''
        
        html += '''
            </tbody>
        </table>
        '''
        return html
    
    def _generate_object_array_table_html(self, data: List[Dict], 
                                         columns: List[Dict], 
                                         bool_fields: List[str]) -> str:
        """生成对象数组表格HTML"""
        if not data:
            return '<p class="unconfigured-value">未配置数据</p>'
        
        html = '''
        <table class="data-table">
            <thead>
                <tr>
        '''
        
        # 生成表头
        for col in columns:
            if col['type'] == 'bool_group':
                html += f'<th>{col["display_name"]}</th>'
            else:
                html += f'<th>{col["display_name"]}</th>'
        
        html += '''
                </tr>
            </thead>
            <tbody>
        '''
        
        # 生成数据行
        for item in data:
            configured = item.get('_configured', True)
            row_class = ' class="unconfigured-field"' if not configured else ''
            
            html += f'<tr{row_class}>'
            
            for col in columns:
                if col['type'] == 'bool_group':
                    # 生成布尔字段组
                    html += '<td>'
                    html += '<div class="bool-field-group">'
                    for bool_field in sorted(col['fields']):
                        value = item.get(bool_field, False)
                        icon = '✅' if value else '❌'
                        html += f'''
                        <div class="bool-field-item">
                            <span class="{('bool-checkmark' if value else 'bool-cross')}">{icon}</span>
                            <span class="bool-field-name">{self._get_bool_field_display_name(bool_field)}</span>
                        </div>
                        '''
                    html += '</div>'
                    html += '</td>'
                else:
                    # 普通字段
                    value = item.get(col['name'], '')
                    html += '<td>'
                    
                    # 处理特殊类型的显示
                    if col['name'] in ['display_name', 'description', 'short_description']:
                        # 多语言字段
                        if isinstance(value, dict):
                            html += '<div class="multilang-field description-cell">'
                            if 'zh_cn' in value and value['zh_cn']:
                                html += f'<div><span class="lang-label">[中文]</span> {value["zh_cn"]}</div>'
                            if 'en_us' in value and value['en_us']:
                                html += f'<div><span class="lang-label">[EN]</span> {value["en_us"]}</div>'
                            if not value.get('zh_cn') and not value.get('en_us'):
                                html += '<span class="unconfigured-value">未配置</span>'
                            html += '</div>'
                        else:
                            html += f'<span class="description-cell">{str(value) if value else "<span class=\"unconfigured-value\">未配置</span>"}</span>'
                    elif col['type'] == 'boolean':
                        icon = '✅' if value else '❌'
                        html += f'<span class="{("bool-checkmark" if value else "bool-cross")}">{icon}</span>'
                    elif col['name'] == 'type':
                        html += f'<span class="tag tag-type">{value}</span>'
                    elif col['name'] == 'launch_stage':
                        html += f'<span class="tag tag-type">{value}</span>'
                    elif col['name'] in ['pattern', 'example', 'unit', 'data_format', 
                                        'aggregator', 'generator']:
                        if value:
                            # 长代码使用代码块
                            if len(str(value)) > 50:
                                html += f'<pre class="code-block">{value}</pre>'
                            else:
                                html += f'<code class="code">{value}</code>'
                        else:
                            html += ''
                    elif col['name'] == 'interval_us':
                        # 格式化数字
                        if isinstance(value, (int, float)):
                            html += f'{value:,}'
                        elif isinstance(value, list):
                            html += ', '.join(f'{v:,}' for v in value)
                        else:
                            html += str(value)
                    elif col['name'] == 'name':
                        # 处理长名称字段
                        html += f'<span class="metric-name">{value}</span>'
                    else:
                        # 其他字段
                        if value or value == 0:
                            html += str(value)
                        elif not configured:
                            html += '<span class="unconfigured-value">未配置</span>'
                        else:
                            html += ''
                    
                    html += '</td>'
            
            html += '</tr>'
        
        html += '''
            </tbody>
        </table>
        '''
        
        return html
    
    def _generate_properties_table_html(self, data: List[Dict]) -> str:
        """生成属性表格HTML"""
        html = '''
        <table class="data-table">
            <thead>
                <tr>
                    <th class="property-name-cell">属性名</th>
                    <th class="type-cell">类型</th>
                    <th class="description-cell">描述（中文）</th>
                    <th class="description-cell">描述（English）</th>
                    <th class="bool-cell">必填</th>
                    <th class="default-cell">默认值</th>
                    <th class="constraint-cell">约束条件</th>
                </tr>
            </thead>
            <tbody>
        '''
        
        for prop in data:
            configured = prop.get('configured', True)
            row_class = '' if configured else ' class="unconfigured-row"'
            
            required = '✅' if prop['required'] else '❌'
            
            # 处理描述
            desc_zh = prop['description_zh'] if configured else f'<span class="unconfigured">{prop["description_zh"]}</span>'
            desc_en = prop['description_en'] if configured else f'<span class="unconfigured">{prop["description_en"]}</span>'
            
            # 处理约束条件
            constraints_html = ''
            if prop['constraints']:
                constraints_html = '<ul class="constraints-list">'
                for constraint in prop['constraints']:
                    constraints_html += f'<li>{constraint}</li>'
                constraints_html += '</ul>'
            
            html += f'''
            <tr{row_class}>
                <td class="property-name-cell"><strong>{prop['name']}</strong></td>
                <td class="type-cell"><span class="tag tag-type">{prop['type']}</span></td>
                <td class="description-cell">{desc_zh}</td>
                <td class="description-cell">{desc_en}</td>
                <td class="bool-cell">{required}</td>
                <td class="default-cell"><code class="code">{prop['default']}</code></td>
                <td class="constraint-cell">{constraints_html}</td>
            </tr>
            '''
        
        html += '''
            </tbody>
        </table>
        '''
        
        return html
    
    def _get_bool_field_display_name(self, field_name: str) -> str:
        """获取布尔字段的显示名称"""
        bool_display_names = {
            'analysable': '可分析',
            'filterable': '可过滤',
            'orderable': '可排序',
            'required': '必填',
            'primary_key': '主键',
            'golden_metric': '黄金指标'
        }
        return bool_display_names.get(field_name, field_name)


def main():
    parser = argparse.ArgumentParser(
        description='动态版本的 mmodel schema 到 HTML 表格文档转换器'
    )
    parser.add_argument('input', help='输入的 YAML 文件路径')
    parser.add_argument('-o', '--output', help='输出的 HTML 文件路径')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"❌ 错误: 文件 {args.input} 不存在")
        return
    
    if not args.input.endswith(('.yaml', '.yml')):
        print(f"❌ 错误: 输入文件必须是 YAML 文件")
        return
    
    # 如果没有指定输出文件，自动生成
    if not args.output:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"{base_name}_table_dynamic.html"
    
    converter = DynamicSchemaToTableHtmlConverter()
    
    try:
        converter.convert_file(args.input, args.output)
        print(f"🎉 转换完成！")
        print(f"📄 输出文件: {args.output}")
        print(f"💡 提示: 可以在浏览器中打开查看")
        
    except Exception as e:
        print(f"❌ 转换失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 