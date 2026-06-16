#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import yaml
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

# 添加SDK路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from mmodel import mmodel
except ImportError as e:
    print(f"错误: 无法导入mmodel模块: {e}")
    print("请确保先运行 python scripts/generators/schema_python_generator_v2.py 生成SDK")
    sys.exit(1)

class MModelCLI:
    def __init__(self):
        self.stats = {
            'total_files': 0,
            'parsed_files': 0,
            'failed_files': 0,
            'types_found': set(),
            'errors': []
        }
    
    def find_mmodel_files(self, directory: str) -> List[str]:
        """查找目录中所有的MModel文件"""
        patterns = ['*.json', '*.yaml', '*.yml']
        mmodel_files = []
        
        for pattern in patterns:
            # 递归查找所有匹配的文件
            files = glob.glob(os.path.join(directory, '**', pattern), recursive=True)
            mmodel_files.extend(files)
        
        return sorted(mmodel_files)
    
    def detect_format(self, filepath: str, content: bytes) -> str:
        """自动检测文件格式"""
        # 先根据扩展名判断
        ext = Path(filepath).suffix.lower()
        if ext == '.json':
            return 'json'
        elif ext in ['.yaml', '.yml']:
            return 'yaml'
        
        # 根据内容判断
        try:
            content_str = content.decode('utf-8').strip()
            if content_str.startswith('{') or content_str.startswith('['):
                return 'json'
        except:
            pass
        
        return 'yaml'
    
    def parse_file(self, filepath: str) -> Optional[Any]:
        """解析单个MModel文件"""
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            
            # 检测格式
            format_type = self.detect_format(filepath, content)
            
            # 解析文件
            if format_type == 'json':
                result = mmodel.parse_mmodel_json(content)
            else:
                result = mmodel.parse_mmodel_yaml(content)
            
            # 记录统计信息
            if hasattr(result, '__class__'):
                type_name = result.__class__.__name__
                self.stats['types_found'].add(type_name)
            
            self.stats['parsed_files'] += 1
            return result
            
        except Exception as e:
            self.stats['failed_files'] += 1
            error_msg = f"{filepath}: {str(e)}"
            self.stats['errors'].append(error_msg)
            return None
    
    def convert_to_format(self, data: Any, output_format: str, pretty: bool = True) -> bytes:
        """转换数据到指定格式"""
        # 如果data有to_dict方法，转换为字典
        if hasattr(data, 'to_dict'):
            data = data.to_dict()
        elif hasattr(data, '__dict__'):
            # 如果是dataclass或普通对象，转换为字典
            import dataclasses
            if dataclasses.is_dataclass(data):
                data = dataclasses.asdict(data)
            else:
                data = vars(data)
        
        if output_format == 'json':
            if pretty:
                return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode('utf-8')
            else:
                return json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        elif output_format == 'yaml':
            return yaml.dump(data, allow_unicode=True, default_flow_style=False).encode('utf-8')
        else:
            raise ValueError(f"不支持的输出格式: {output_format}")
    
    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("📊 解析统计")
        print("="*60)
        print(f"📄 总文件数: {self.stats['total_files']}")
        print(f"✅ 成功解析: {self.stats['parsed_files']}")
        print(f"❌ 解析失败: {self.stats['failed_files']}")
        
        if self.stats['types_found']:
            print(f"\n🏷️  发现的类型 ({len(self.stats['types_found'])}):")
            for type_name in sorted(self.stats['types_found']):
                print(f"   - {type_name}")
        
        if self.stats['errors']:
            print(f"\n❌ 错误信息:")
            for error in self.stats['errors'][:5]:  # 只显示前5个错误
                print(f"   - {error}")
            if len(self.stats['errors']) > 5:
                print(f"   ... 还有 {len(self.stats['errors']) - 5} 个错误")
    
    def run(self, args):
        """运行CLI工具"""
        start_time = time.time()
        
        # 确定输入路径
        input_path = args.input
        if os.path.isfile(input_path):
            # 单个文件
            files = [input_path]
        elif os.path.isdir(input_path):
            # 目录
            print(f"🔍 扫描目录: {input_path}")
            files = self.find_mmodel_files(input_path)
            print(f"📁 找到 {len(files)} 个文件")
        else:
            print(f"错误: 路径不存在: {input_path}")
            sys.exit(1)
        
        self.stats['total_files'] = len(files)
        
        if not files:
            print("❌ 未找到任何MModel文件")
            return
        
        # 处理文件
        results = []
        for i, filepath in enumerate(files, 1):
            rel_path = os.path.relpath(filepath)
            print(f"[{i}/{len(files)}] 处理: {rel_path}")
            
            result = self.parse_file(filepath)
            if result:
                results.append({
                    'file': rel_path,
                    'data': result
                })
                
                # 如果有输出选项，处理单个文件转换
                if args.output or args.output_format != 'json' or len(files) == 1:
                    try:
                        output_data = self.convert_to_format(result, args.output_format, args.pretty)
                        
                        if args.output:
                            # 输出到文件
                            if len(files) == 1:
                                output_file = args.output
                            else:
                                # 多个文件时，生成对应的输出文件名
                                name = Path(filepath).stem
                                ext = 'json' if args.output_format == 'json' else 'yaml'
                                output_file = os.path.join(args.output, f"{name}.{ext}")
                                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                            
                            with open(output_file, 'wb') as f:
                                f.write(output_data)
                            print(f"   ✅ 已保存到: {output_file}")
                        elif not args.quiet:
                            # 输出到标准输出（仅单个文件）
                            if len(files) == 1:
                                print("\n" + "="*60)
                                print("📄 输出内容")
                                print("="*60)
                                print(output_data.decode('utf-8'))
                    except Exception as e:
                        print(f"   ❌ 转换失败: {e}")
        
        # 打印统计信息
        if not args.quiet:
            self.print_statistics()
            
            end_time = time.time()
            print(f"\n⏱️  总耗时: {end_time - start_time:.2f} 秒")
        
        # 设置退出码
        if self.stats['failed_files'] > 0:
            sys.exit(1)

def create_parser():
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='MModel CLI - MModel文件解析和转换工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 解析单个文件
  %(prog)s -i metric.json
  
  # 解析目录中所有文件
  %(prog)s -i examples/dataset/
  
  # JSON转YAML
  %(prog)s -i metric.json -o metric.yaml -of yaml
  
  # 批量转换目录
  %(prog)s -i examples/dataset/ -o output/ -of yaml
  
  # 只显示统计信息
  %(prog)s -i examples/dataset/ --quiet
        """
    )
    
    parser.add_argument('-i', '--input', required=True,
                       help='输入文件或目录路径 (必需)')
    
    parser.add_argument('-o', '--output',
                       help='输出文件或目录路径 (可选，默认输出到标准输出)')
    
    parser.add_argument('-of', '--output-format', choices=['json', 'yaml'], default='json',
                       help='输出格式: json, yaml (默认: json)')
    
    parser.add_argument('-p', '--pretty', action='store_true', default=True,
                       help='美化输出 (默认: true)')
    
    parser.add_argument('--no-pretty', dest='pretty', action='store_false',
                       help='不美化输出')
    
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='静默模式，只显示统计信息')
    
    return parser

def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 创建CLI实例并运行
    cli = MModelCLI()
    cli.run(args)

if __name__ == '__main__':
    main() 