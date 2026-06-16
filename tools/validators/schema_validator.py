#!/usr/bin/env python3
"""
MModel Schema Validator

这个脚本基于base.yaml中定义的元数据规范来验证展开后的schema文件的有效性。

功能：
1. 使用schema_spec验证每个文件的基础结构
2. 使用metadata_properties验证每个元素的合法性
3. 递归验证嵌套结构和约束条件
4. 生成详细的验证报告
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Union


class SchemaValidator:
    def __init__(self, expanded_schemas_dir: str, base_schema_path: str = "schemas/base.yaml", console_log: bool = True):
        self.expanded_schemas_dir = Path(expanded_schemas_dir)
        self.base_schema_path = Path(base_schema_path)
        self.console_log = console_log
        self.validation_errors: List[str] = []
        self.validation_warnings: List[str] = []
        
        # 加载base.yaml作为验证规则
        self.base_schema = self._load_base_schema()
        self.schema_spec = self.base_schema.get("schema_spec", {})
        self.metadata_properties = self.base_schema.get("metadata_properties", {})
        self.additional_types = self.base_schema.get("additional_types", {})
        
    def _load_base_schema(self) -> Dict[str, Any]:
        """加载base.yaml文件"""
        try:
            with open(self.base_schema_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            if self.console_log:
                print(f"❌ 无法加载base.yaml: {e}")
            return {}
    
    def validate_all_schemas(self) -> Dict[str, Any]:
        """验证所有展开后的schema文件"""
        if self.console_log:
            print("🔍 开始基于base.yaml验证展开后的schema文件...")
        
        results = {
            "total_files": 0,
            "valid_files": 0,
            "files_with_errors": 0,
            "files_with_warnings": 0,
            "details": {}
        }
        
        if not self.expanded_schemas_dir.exists():
            if self.console_log:
                print(f"❌ 展开后的schema目录不存在: {self.expanded_schemas_dir}")
            return results
        
        if not self.base_schema:
            if self.console_log:
                print("❌ base.yaml未正确加载，无法进行验证")
            return results
        
        for yaml_file in self.expanded_schemas_dir.glob("*.expanded.yaml"):
            if yaml_file.name == "expansion_report.md":
                continue
                
            if self.console_log:
                print(f"✅ 已加载schema: {yaml_file.stem.replace('.expanded', '')}")
            results["total_files"] += 1
            
            file_result = self._validate_single_schema(yaml_file)
            results["details"][yaml_file.name] = file_result
            
            if file_result["errors"]:
                results["files_with_errors"] += 1
                if self.console_log:
                    print(f"❌ 发现错误: {len(file_result['errors'])} 个")
            elif file_result["warnings"]:
                results["files_with_warnings"] += 1
                if self.console_log:
                    print(f"⚠️  发现警告: {len(file_result['warnings'])} 个")
            else:
                results["valid_files"] += 1
        
        if self.console_log:
            print(f"📊 共加载 {results['total_files']} 个schema定义")
        
        return results
    
    def _validate_single_schema(self, yaml_file: Path) -> Dict[str, Any]:
        """验证单个schema文件"""
        result = {
            "errors": [],
            "warnings": []
        }
        
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            # 使用schema_spec验证文件结构
            self._validate_against_spec(content, self.schema_spec, "root", result)
            
            # 验证每个版本的spec
            if "versions" in content and isinstance(content["versions"], list):
                for i, version in enumerate(content["versions"]):
                    if isinstance(version, dict) and "spec" in version:
                        self._validate_metadata_properties(
                            version["spec"], 
                            f"versions[{i}].spec", 
                            result
                        )
            
        except Exception as e:
            result["errors"].append(f"文件解析失败: {e}")
        
        return result
    
    def _validate_against_spec(self, data: Any, spec: Dict[str, Any], path: str, result: Dict[str, Any]):
        """根据规范验证数据"""
        # 验证类型
        expected_type = spec.get("type")
        if expected_type and not self._check_type(data, expected_type):
            result["errors"].append(f"{path}: 期望类型 {expected_type}, 实际类型 {type(data).__name__}")
            return
        
        # 验证约束
        if "constraint" in spec:
            self._validate_constraints(data, spec["constraint"], path, result)
        
        # 如果是对象类型，验证properties
        if expected_type == "object" and isinstance(data, dict) and "properties" in spec:
            spec_properties = spec["properties"]
            
            # 确保spec_properties不是None
            if spec_properties is not None and isinstance(spec_properties, dict):
                # 检查必填字段
                for prop_name, prop_spec in spec_properties.items():
                    if isinstance(prop_spec, dict) and prop_spec.get("constraint", {}).get("required", False):
                        if prop_name not in data:
                            result["errors"].append(f"{path}: 缺少必填字段 '{prop_name}'")
                    
                    # 如果字段存在，递归验证
                    if prop_name in data:
                        self._validate_against_spec(
                            data[prop_name], 
                            prop_spec, 
                            f"{path}.{prop_name}", 
                            result
                        )
        
        # 如果是数组类型，验证每个元素
        elif expected_type == "array" and isinstance(data, list):
            constraint = spec.get("constraint", {})
            if "array" in constraint and "item" in constraint["array"]:
                item_spec = constraint["array"]["item"]
                for i, item in enumerate(data):
                    self._validate_against_spec(
                        item, 
                        item_spec, 
                        f"{path}[{i}]", 
                        result
                    )
    
    def _validate_metadata_properties(self, data: Any, path: str, result: Dict[str, Any]):
        """根据metadata_properties定义验证元数据"""
        if not isinstance(data, dict):
            return
        
        # 获取metadata_properties的properties定义
        meta_props = self.metadata_properties.get("properties", {})
        
        # 验证type字段
        if "type" in data:
            self._validate_type_field(data["type"], path, result)
        
        # 验证description字段
        if "description" in data:
            # 检查description是否是展开后的semantic_string（object类型）
            if data.get("type") == "object" and "properties" in data:
                # 检查是否有zh_cn和en_us属性，如果有，这可能是一个展开后的semantic_string
                props = data["properties"]
                if isinstance(props, dict) and set(props.keys()) <= {"zh_cn", "en_us"}:
                    # 这是一个展开后的semantic_string，跳过验证
                    pass
            else:
                self._validate_semantic_string(data["description"], f"{path}.description", result)
        
        # 验证release_stage字段
        if "release_stage" in data:
            self._validate_release_stage(data["release_stage"], f"{path}.release_stage", result)
        
        # 验证properties字段
        if "properties" in data and isinstance(data["properties"], dict):
            for prop_name, prop_data in data["properties"].items():
                self._validate_metadata_properties(
                    prop_data, 
                    f"{path}.properties.{prop_name}", 
                    result
                )
        
        # 验证extends字段（展开后不应该存在）
        if "extends" in data:
            result["errors"].append(f"{path}: 展开后的schema中不应包含extends字段")
        
        # 验证constraint字段
        if "constraint" in data:
            self._validate_constraint_definition(data["constraint"], f"{path}.constraint", result)
    
    def _validate_type_field(self, type_value: Any, path: str, result: Dict[str, Any]):
        """验证type字段"""
        # 从base.yaml获取定义的类型
        type_constraint = self.metadata_properties.get("properties", {}).get("type", {}).get("constraint", {})
        base_valid_types = type_constraint.get("enum", {}).get("values", [])
        
        # 扩展支持的类型列表，包括schema中实际使用的类型
        extended_valid_types = {
            # base.yaml中定义的类型
            'object', 'array', 'string', 'number', 'boolean',
            # 扩展的基础类型
            'integer', 'float', 'bool',  # 数值和布尔类型的变体
            'map',  # 映射类型
            'enum',  # 枚举类型
            'any',  # 任意类型
            'json', 'json_object', 'json_array',  # JSON类型
            'time',  # 时间类型
            # 自定义类型
            'semantic_string'  # 语义字符串类型
        }
        
        # 合并两个类型集合
        all_valid_types = set(base_valid_types) | extended_valid_types
        
        if type_value not in all_valid_types:
            result["errors"].append(
                f"{path}.type: 无效的类型 '{type_value}' (常见合法值: {', '.join(sorted(all_valid_types))})"
            )
    
    def _validate_semantic_string(self, value: Any, path: str, result: Dict[str, Any]):
        """验证语义字符串（支持多语言）"""
        if isinstance(value, str):
            # 简单字符串也是有效的
            return
        elif isinstance(value, dict):
            # 检查是否包含至少一种语言
            valid_langs = {"zh_cn", "en_us"}
            if not any(lang in value for lang in valid_langs):
                result["warnings"].append(
                    f"{path}: 语义字符串应包含至少一种语言 (zh_cn 或 en_us)"
                )
            # 验证每个语言字段都是字符串
            for lang in value:
                if lang in valid_langs and not isinstance(value[lang], str):
                    result["errors"].append(
                        f"{path}.{lang}: 语言字段必须是字符串类型"
                    )
        else:
            result["errors"].append(
                f"{path}: 语义字符串必须是字符串或包含多语言的对象"
            )
    
    def _validate_release_stage(self, value: Any, path: str, result: Dict[str, Any]):
        """验证release_stage字段"""
        release_stage_constraint = self.metadata_properties.get("properties", {}).get("release_stage", {}).get("constraint", {})
        valid_stages = release_stage_constraint.get("enum", {}).get("values", [])
        
        if valid_stages and value not in valid_stages:
            result["errors"].append(
                f"{path}: 无效的release_stage值 '{value}' (合法值: {', '.join(valid_stages)})"
            )
    
    def _validate_constraint_definition(self, constraint: Dict[str, Any], path: str, result: Dict[str, Any]):
        """验证constraint定义"""
        if not constraint or not isinstance(constraint, dict):
            return
            
        constraint_props = self.metadata_properties.get("properties", {}).get("constraint", {}).get("properties", {})
        
        if not constraint_props:
            return
        
        # 定义已知的扩展约束类型（不在base.yaml中但被广泛使用）
        extended_constraint_types = {
            # 'oneOf',  # 多选一约束
            # 'entity',  # 实体引用约束
            # 'anyOf',  # 任意匹配约束
            # 'allOf',  # 全部匹配约束
            # 'not',  # 否定约束
        }
            
        for key, value in constraint.items():
            if key not in constraint_props and key not in extended_constraint_types:
                result["warnings"].append(f"{path}.{key}: 未知的约束类型")
            else:
                # 验证特定约束
                if key == "pattern" and isinstance(value, str):
                    try:
                        re.compile(value)
                    except re.error as e:
                        result["errors"].append(f"{path}.pattern: 无效的正则表达式 - {e}")
                
                elif key == "enum" and isinstance(value, dict):
                    if "values" not in value:
                        result["errors"].append(f"{path}.enum: 缺少values字段")
                    elif not isinstance(value["values"], list):
                        result["errors"].append(f"{path}.enum.values: 必须是数组")
                
                elif key == "array" and isinstance(value, dict):
                    if "item" not in value:
                        result["errors"].append(f"{path}.array: 缺少item定义")
                    elif isinstance(value.get("item"), dict):
                        # 递归验证item定义
                        self._validate_metadata_properties(
                            value["item"], 
                            f"{path}.array.item", 
                            result
                        )
                
                elif key == "oneOf" and isinstance(value, list):
                    # 验证oneOf约束：每个选项都应该是有效的类型定义
                    for i, option in enumerate(value):
                        if isinstance(option, dict):
                            # 递归验证每个选项
                            self._validate_metadata_properties(
                                option,
                                f"{path}.oneOf[{i}]",
                                result
                            )
                        else:
                            result["errors"].append(f"{path}.oneOf[{i}]: oneOf的每个选项必须是对象类型")
    
    def _validate_constraints(self, data: Any, constraints: Dict[str, Any], path: str, result: Dict[str, Any]):
        """验证数据是否满足约束条件"""
        if "required" in constraints and constraints["required"]:
            if not data:
                result["errors"].append(f"{path}: 缺少必填字段")

        # 检查pattern约束
        if "pattern" in constraints and isinstance(data, str):
            pattern = constraints["pattern"]
            try:
                if not re.match(pattern, data):
                    result["errors"].append(f"{path}: 不匹配正则表达式 {pattern}")
            except re.error:
                pass  # 正则表达式本身的有效性已在别处验证
        
        # 检查长度约束
        if isinstance(data, str):
            if "min_len" in constraints and len(data) < constraints["min_len"]:
                result["errors"].append(f"{path}: 长度小于最小值 {constraints['min_len']}")
            if "max_len" in constraints and len(data) > constraints["max_len"]:
                result["errors"].append(f"{path}: 长度超过最大值 {constraints['max_len']}")
        
        # 检查数组大小约束
        if isinstance(data, list) and "array" in constraints:
            array_constraints = constraints["array"]
            if "min_size" in array_constraints and len(data) < array_constraints["min_size"]:
                result["errors"].append(f"{path}: 数组大小小于最小值 {array_constraints['min_size']}")
            if "max_size" in array_constraints and len(data) > array_constraints["max_size"]:
                result["errors"].append(f"{path}: 数组大小超过最大值 {array_constraints['max_size']}")

        if "map" in constraints and not isinstance(data, dict):
            result["errors"].append(f"{path}: 不是字典类型")
        
        # 检查枚举约束，如果default_value存在，则不检查枚举约束
        if "enum" in constraints and (("default_value" in constraints and data != "" and data != constraints["default_value"]) or ("default_value" not in constraints)):
            enum_values = constraints["enum"].get("values", [])
            if data not in enum_values:
                result["errors"].append(f"{path}: 值 '{data}' 不在允许的枚举值中: {enum_values}")
        
        # 检查oneOf约束
        if "oneOf" in constraints and isinstance(constraints["oneOf"], list):
            valid_options = []
            matched_count = 0
            
            for i, option_spec in enumerate(constraints["oneOf"]):
                # 创建临时结果来测试每个选项
                temp_result = {"errors": [], "warnings": []}
                self._validate_against_spec(data, option_spec, f"{path}(oneOf[{i}])", temp_result)
                
                # 如果没有错误，说明匹配这个选项
                if not temp_result["errors"]:
                    matched_count += 1
                    valid_options.append(i)
            
            # oneOf要求必须且只能匹配一个选项
            if matched_count == 0:
                result["errors"].append(f"{path}: 数据不符合oneOf中的任何一个选项")
            elif matched_count > 1:
                result["errors"].append(f"{path}: 数据同时符合oneOf中的多个选项 {valid_options}，但只能符合一个")
    
    def _check_type(self, data: Any, expected_type: str) -> bool:
        """检查数据类型是否匹配"""
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "float": float,
            "boolean": bool,
            "bool": bool,  # boolean的别名
            "object": dict,
            "array": list,
            "map": dict,  # map实际上就是字典/对象
            "enum": str,  # 枚举通常是字符串
            "semantic_string": (str, dict),  # 语义字符串可以是字符串或对象
            "any": object,  # 任意类型
            "json": (dict, list),  # JSON可以是对象或数组
            "json_object": dict,
            "json_array": list,
            "time": (str, int, float),  # 时间可能是字符串或数字
        }
        
        if expected_type == "any":
            return True
        
        expected = type_mapping.get(expected_type)
        if expected:
            return isinstance(data, expected)
        
        return True  # 未知类型默认通过
    
    def generate_validation_report(self, results: Dict[str, Any]) -> str:
        """生成验证报告"""
        report = []
        report.append("# MModel Schema 验证报告")
        report.append(f"\n基于 `{self.base_schema_path}` 中定义的元数据规范进行验证\n")
        
        # 统计信息
        report.append("## 📊 验证统计")
        report.append(f"- 总文件数: {results['total_files']}")
        report.append(f"- 验证通过: {results['valid_files']}")
        report.append(f"- 有错误: {results['files_with_errors']}")
        report.append(f"- 有警告: {results['files_with_warnings']}")
        report.append("")
        
        # 详细结果
        report.append("## 📋 详细验证结果")
        
        for filename, file_result in results["details"].items():
            report.append(f"### {filename}")
            
            if not file_result["errors"] and not file_result["warnings"]:
                report.append("✅ **状态**: 验证通过")
            else:
                if file_result["errors"]:
                    report.append("❌ **状态**: 有错误")
                    report.append("**错误列表:**")
                    for error in file_result["errors"]:
                        report.append(f"- {error}")
                
                if file_result["warnings"]:
                    report.append("⚠️ **警告列表:**")
                    for warning in file_result["warnings"]:
                        report.append(f"- {warning}")
            
            report.append("")
        
        # 总结
        total_errors = sum(len(file_result["errors"]) for file_result in results["details"].values())
        total_warnings = sum(len(file_result["warnings"]) for file_result in results["details"].values())
        
        report.append("## 📝 验证总结")
        if total_errors == 0:
            report.append("🎉 所有schema文件都符合base.yaml中定义的元数据规范！")
            if total_warnings > 0:
                report.append(f"⚠️  但发现了 {total_warnings} 个警告，建议查看并修复。")
        else:
            report.append(f"❌ 发现 {total_errors} 个错误需要修复。")
            if total_warnings > 0:
                report.append(f"⚠️  另外还有 {total_warnings} 个警告。")
        
        return "\n".join(report)


def main():
    """主函数"""
    print("🚀 MModel Schema Validator 启动")
    print("=" * 50)
    
    expanded_schemas_dir = "expanded_schemas"
    
    if not os.path.exists(expanded_schemas_dir):
        print(f"❌ 展开后的schema目录不存在: {expanded_schemas_dir}")
        return
    
    validator = SchemaValidator(expanded_schemas_dir)
    
    try:
        # 验证所有schema
        results = validator.validate_all_schemas()
        
        # 生成报告
        report = validator.generate_validation_report(results)
        
        # 保存报告
        report_file = Path(expanded_schemas_dir) / "validation_report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 验证报告已保存到: {report_file}")
        
        # 打印摘要
        print(f"\n📊 验证摘要:")
        print(f"- 总文件数: {results['total_files']}")
        print(f"- 验证通过: {results['valid_files']}")
        print(f"- 有错误: {results['files_with_errors']}")
        print(f"- 有警告: {results['files_with_warnings']}")
        
        if results["files_with_errors"] == 0:
            print("\n🎉 所有schema文件验证通过！")
        else:
            print(f"\n⚠️  发现 {results['files_with_errors']} 个文件有错误，请查看详细报告。")
        
    except Exception as e:
        print(f"\n❌ 验证过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 