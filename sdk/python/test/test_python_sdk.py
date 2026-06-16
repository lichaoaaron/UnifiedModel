#!/usr/bin/env python3
"""
MModel Python SDK 测试程序

这个程序用来验证生成的Python SDK是否可以正常工作。
功能包括：
1. 自动扫描examples目录
2. 解析MModel文件（JSON/YAML）
3. 验证生成的类型系统
4. 转换输出格式
5. 显示详细的测试结果
"""

import os
import sys
import json
import yaml
import argparse
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加生成的Python SDK到路径
GENERATED_SDK_PATH = Path(__file__).parent.parent
if GENERATED_SDK_PATH.exists():
    sys.path.insert(0, str(GENERATED_SDK_PATH))

try:
    # 导入生成的MModel SDK
    from mmodel import *
    SDK_AVAILABLE = True
    print("✅ 成功导入MModel Python SDK")
except ImportError as e:
    print(f"❌ 无法导入MModel Python SDK: {e}")
    print(f"请先运行: python scripts/generators/schema_python_generator_v2.py")
    SDK_AVAILABLE = False


class MModelTester:
    """MModel Python SDK 测试器"""
    
    def __init__(self):
        self.examples_dir = Path(__file__).parent.parent.parent.parent / "examples"
        self.test_results = []
        self.stats = {
            'total_files': 0,
            'success_count': 0,
            'error_count': 0,
            'format_json': 0,
            'format_yaml': 0,
            'types_found': set()
        }
    
    def run_tests(self, input_file: Optional[str] = None, output_file: Optional[str] = None, 
                  output_format: str = "json", pretty: bool = True) -> bool:
        """运行所有测试"""
        print("🚀 开始MModel Python SDK测试")
        print("=" * 60)
        
        if not SDK_AVAILABLE:
            print("❌ SDK不可用，无法运行测试")
            return False
        
        if input_file:
            # 测试单个文件
            success = self._test_single_file(input_file, output_file, output_format, pretty)
        else:
            # 测试整个examples目录
            success = self._test_examples_directory(output_format, pretty)
        
        # 显示测试结果
        self._print_summary()
        
        return success
    
    def _test_single_file(self, input_file: str, output_file: Optional[str], 
                         output_format: str, pretty: bool) -> bool:
        """测试单个文件"""
        print(f"📄 测试单个文件: {input_file}")
        
        if not os.path.exists(input_file):
            print(f"❌ 文件不存在: {input_file}")
            return False
        
        try:
            # 读取文件
            with open(input_file, 'rb') as f:
                data = f.read()
            
            # 检测格式
            input_format = self._detect_format(input_file, data)
            
            # 解析文件
            result = self._parse_file(data, input_format, input_file)
            
            if result['success']:
                # 转换输出格式
                output_data = self._convert_to_format(result['data'], output_format, pretty)
                
                if output_file:
                    # 保存到文件
                    with open(output_file, 'wb') as f:
                        f.write(output_data)
                    print(f"✅ 成功转换并保存到: {output_file}")
                else:
                    # 输出到控制台
                    print(f"\n📤 输出结果 ({output_format}):")
                    print("-" * 40)
                    print(output_data.decode('utf-8'))
                
                return True
            else:
                print(f"❌ 解析失败: {result['error']}")
                return False
                
        except Exception as e:
            print(f"❌ 处理文件时出错: {e}")
            traceback.print_exc()
            return False
    
    def _test_examples_directory(self, output_format: str, pretty: bool) -> bool:
        """测试整个examples目录"""
        print(f"📁 扫描examples目录: {self.examples_dir}")
        
        if not self.examples_dir.exists():
            print(f"❌ examples目录不存在: {self.examples_dir}")
            return False
        
        # 查找所有MModel文件
        mmodel_files = self._find_mmodel_files()
        
        if not mmodel_files:
            print("❌ 未找到任何MModel文件")
            return False
        
        print(f"📊 找到 {len(mmodel_files)} 个文件，开始测试...")
        print()
        
        # 测试每个文件
        for file_path in mmodel_files:
            self._test_file(file_path)
        
        return self.stats['error_count'] == 0
    
    def _find_mmodel_files(self) -> List[Path]:
        """查找所有MModel文件"""
        files = []
        
        # 支持的文件扩展名
        extensions = ['.yaml', '.yml', '.json']
        
        # 递归查找
        for ext in extensions:
            for file_path in self.examples_dir.rglob(f"*{ext}"):
                if self._looks_like_mmodel_file(file_path):
                    files.append(file_path)
        
        return sorted(files)
    
    def _looks_like_mmodel_file(self, file_path: Path) -> bool:
        """只测试MModel定义文件，跳过sample-data中的实体/关系载荷。"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix == '.json':
                    payload = json.load(f)
                else:
                    payload = yaml.safe_load(f)
        except Exception:
            return False
        return isinstance(payload, dict) and isinstance(payload.get('kind'), str)
    
    def _test_file(self, file_path: Path):
        """测试单个文件"""
        self.stats['total_files'] += 1
        
        print(f"📄 测试文件: {file_path.relative_to(self.examples_dir.parent)}")
        
        try:
            # 读取文件
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # 检测格式
            input_format = self._detect_format(str(file_path), data)
            self.stats[f'format_{input_format}'] += 1
            
            # 解析文件
            result = self._parse_file(data, input_format, str(file_path))
            
            if result['success']:
                self.stats['success_count'] += 1
                
                # 记录类型信息
                obj = result['data']
                obj_type = type(obj).__name__
                self.stats['types_found'].add(obj_type)
                
                # 显示解析结果
                print(f"  ✅ 解析成功")
                print(f"     格式: {input_format}")
                print(f"     类型: {obj_type}")
                print(f"     Kind: {obj.get_kind()}")
                
                # 测试接口功能
                self._test_object_interfaces(obj)
                
                self.test_results.append({
                    'file': str(file_path),
                    'status': 'success',
                    'format': input_format,
                    'type': obj_type,
                    'kind': obj.get_kind()
                })
                
            else:
                self.stats['error_count'] += 1
                print(f"  ❌ 解析失败: {result['error']}")
                
                self.test_results.append({
                    'file': str(file_path),
                    'status': 'error',
                    'error': result['error']
                })
        
        except Exception as e:
            self.stats['error_count'] += 1
            error_msg = f"处理文件时出错: {e}"
            print(f"  ❌ {error_msg}")
            
            self.test_results.append({
                'file': str(file_path),
                'status': 'exception',
                'error': error_msg
            })
        
        print()
    
    def _test_object_interfaces(self, obj: Any):
        """测试对象接口功能"""
        try:
            # 测试基础接口
            if is_core_object(obj):
                print(f"     🔹 MModelCoreObject: ✅")
                
                # 测试Metadata
                metadata = get_object_metadata(obj)
                if metadata:
                    print(f"     🔹 Metadata: ✅ (name: {getattr(metadata, 'name', 'N/A')})")
                else:
                    print(f"     🔹 Metadata: ⚠️ (未找到)")
                
                # 测试Schema
                schema = get_object_schema(obj)
                if schema:
                    print(f"     🔹 Schema: ✅ (version: {getattr(schema, 'version', 'N/A')})")
                else:
                    print(f"     🔹 Schema: ⚠️ (未找到)")
            
            # 测试Link接口
            if is_link_object(obj):
                print(f"     🔹 MModelLinkObject: ✅")
                src, dest = get_link_endpoints(obj)
                if src and dest:
                    print(f"     🔹 Link: {src.name} -> {dest.name}")
                else:
                    print(f"     🔹 Link: ⚠️ (端点信息不完整)")
            
            # 测试验证功能
            validation_error = obj.validate()
            if validation_error is None:
                print(f"     🔹 Validation: ✅")
            else:
                print(f"     🔹 Validation: ⚠️ ({validation_error})")
                
        except Exception as e:
            print(f"     🔹 接口测试失败: {e}")
    
    def _detect_format(self, filename: str, data: bytes) -> str:
        """自动检测文件格式"""
        # 先根据文件扩展名判断
        ext = Path(filename).suffix.lower()
        if ext == '.json':
            return 'json'
        elif ext in ['.yaml', '.yml']:
            return 'yaml'
        
        # 根据内容判断
        try:
            content = data.decode('utf-8').strip()
            if content.startswith('{') or content.startswith('['):
                return 'json'
        except:
            pass
        
        return 'yaml'
    
    def _parse_file(self, data: bytes, input_format: str, filename: str) -> Dict[str, Any]:
        """解析文件"""
        try:
            if input_format == 'json':
                obj = parse_mmodel_json(data)
            elif input_format == 'yaml':
                obj = parse_mmodel_yaml(data)
            else:
                return {
                    'success': False,
                    'error': f'不支持的格式: {input_format}'
                }
            
            return {
                'success': True,
                'data': obj
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'{input_format.upper()}解析错误: {e}'
            }
    
    def _convert_to_format(self, data: Any, output_format: str, pretty: bool) -> bytes:
        """转换为目标格式"""
        if output_format == 'json':
            if pretty:
                result = json.dumps(data, indent=2, ensure_ascii=False, default=self._json_serializer)
            else:
                result = json.dumps(data, ensure_ascii=False, default=self._json_serializer)
            return result.encode('utf-8')
        elif output_format == 'yaml':
            result = yaml.dump(data, allow_unicode=True, default_flow_style=False)
            return result.encode('utf-8')
        else:
            raise ValueError(f'不支持的输出格式: {output_format}')
    
    def _json_serializer(self, obj):
        """JSON序列化器，处理特殊对象"""
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        if hasattr(obj, '__class__'):
            return str(obj)
        return None
    
    def _print_summary(self):
        """打印测试总结"""
        print("📊 测试总结")
        print("=" * 60)
        print(f"总文件数:     {self.stats['total_files']}")
        print(f"成功解析:     {self.stats['success_count']}")
        print(f"解析失败:     {self.stats['error_count']}")
        print(f"JSON文件:     {self.stats['format_json']}")
        print(f"YAML文件:     {self.stats['format_yaml']}")
        print(f"成功率:       {self.stats['success_count']/max(1,self.stats['total_files'])*100:.1f}%")
        
        if self.stats['types_found']:
            print(f"\n🔍 发现的类型:")
            for obj_type in sorted(self.stats['types_found']):
                print(f"  - {obj_type}")
        
        if self.stats['error_count'] > 0:
            print(f"\n❌ 失败的文件:")
            for result in self.test_results:
                if result['status'] != 'success':
                    print(f"  - {result['file']}: {result.get('error', '未知错误')}")
        
        print("\n" + "=" * 60)
        
        if self.stats['error_count'] == 0:
            print("🎉 所有测试通过！MModel Python SDK工作正常。")
        else:
            print(f"⚠️  有 {self.stats['error_count']} 个测试失败，请检查。")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MModel Python SDK 测试程序')
    
    parser.add_argument('-i', '--input', help='输入文件路径（可选，默认测试整个examples目录）')
    parser.add_argument('-o', '--output', help='输出文件路径（可选，默认输出到控制台）')
    parser.add_argument('-if', '--input-format', choices=['json', 'yaml'], 
                      help='输入格式（可选，默认自动检测）')
    parser.add_argument('-of', '--output-format', choices=['json', 'yaml'], default='json',
                      help='输出格式（默认: json）')
    parser.add_argument('-p', '--pretty', action='store_true', default=True,
                      help='美化输出（默认: true）')
    parser.add_argument('--no-pretty', dest='pretty', action='store_false',
                      help='禁用美化输出')
    
    args = parser.parse_args()
    
    # 创建测试器
    tester = MModelTester()
    
    # 运行测试
    success = tester.run_tests(
        input_file=args.input,
        output_file=args.output,
        output_format=args.output_format,
        pretty=args.pretty
    )
    
    # 设置退出代码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 
