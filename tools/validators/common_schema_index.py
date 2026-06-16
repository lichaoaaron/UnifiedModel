#!/usr/bin/env python3
"""
MModel索引管理器 - 改进版
提供高性能的MModel定义文件索引生成和待校验文件列表功能
支持实体引用关系分析
"""

import os
import hashlib
import json
import subprocess
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Dict, Set, List, Tuple, Optional, Any
from datetime import datetime
import yaml
from dataclasses import dataclass, asdict


@dataclass
class MModelEntity:
    """MModel实体信息"""
    domain: str
    kind: str
    name: str
    file_path: str
    file_hash: str
    references: List[str]  # 该文件引用的其他实体的MModel ID列表
    
    @property
    def mmodel_id(self) -> str:
        """MModelID: domain.kind.name"""
        return f"{self.domain}.{self.kind}.{self.name}"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MModelEntity':
        return cls(**data)


class MModelIndexManager:
    """MModel索引管理器 - 改进版"""
    
    def __init__(self, work_dir: str = None, quiet: bool = False):
        self.work_dir = os.path.abspath(work_dir or os.getcwd())
        self.quiet = quiet
        self.git_root = self._find_git_root()
        self.is_git_repo = self.git_root is not None
        
        if not self.quiet:
            print(f"🔍 工作目录: {self.work_dir}")
            print(f"🔍 {'Git仓库' if self.is_git_repo else '非Git环境'}: {self.git_root or 'N/A'}")

    def _run_git_command(self, command: List[str], cwd: str = None) -> Optional[str]:
        """执行Git命令的通用方法"""
        if not self.is_git_repo:
            return None
            
        try:
            result = subprocess.run(
                command,
                cwd=cwd or self.git_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            return result.stdout.strip()
        except Exception as e:
            if not self.quiet:
                print(f"⚠️ Git命令执行失败 {' '.join(command)}: {e}")
            return None

    def _normalize_path(self, file_path: str) -> str:
        """标准化文件路径，转换为相对于工作目录的路径"""
        try:
            return os.path.relpath(os.path.abspath(file_path), self.work_dir)
        except ValueError:
            # 当文件不在工作目录下时返回原始路径
            return file_path

    def _is_mmodel_file(self, file_path: str, patterns: List[str] = None) -> bool:
        """检查文件是否为MModel文件"""
        if patterns is None:
            patterns = ['*.yaml', '*.yml']
        return any(file_path.endswith(pattern.replace('*', '')) for pattern in patterns)

    def _find_git_root(self) -> Optional[str]:
        """查找Git仓库根目录"""
        try:
            # 直接使用subprocess运行Git命令，避免在初始化阶段依赖self.git_root
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            return result.stdout.strip()
        except Exception:
            return None

    def _get_current_commit(self) -> str:
        """获取当前Git提交ID"""
        if not self.is_git_repo:
            return ""
        result = self._run_git_command(['git', 'rev-parse', 'HEAD'])
        return result or ""

    def get_final_modified_files(self, commit_id:str):
        """获取最终态修改的文件列表"""
        added_modified_files = self._run_git_command(['git', 'diff', '--name-only', '--diff-filter=AM', f"{commit_id}", "HEAD"])  # 方法2: 获取详细状态信息用于分析
        status_output = self._run_git_command(['git', 'diff', '--name-status', f"{commit_id}", "HEAD"])

        file_stats = {}
        if status_output:
            for line in status_output.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        status = parts[0]
                        filename = parts[1]
                        file_stats[filename] = status

        deleted_files = set()
        for filename, status in file_stats.items():
            if status == 'D':
                abs_path = os.path.abspath(os.path.join(self.git_root, filename))
                deleted_files.add(abs_path)

        final_files = set()
        if added_modified_files:
            for line in added_modified_files.split('\n'):
                if line:
                    abs_path = os.path.abspath(os.path.join(self.git_root, line))
                    final_files.add(abs_path)

        return final_files, deleted_files
    def _get_commit_file_changes(self, commit: str) -> Tuple[Set[str], Set[str], Set[str]]:
        """获取指定提交的文件变更 - 返回(修改文件, 新增文件, 删除文件)"""
        if not self.is_git_repo or not commit:
            return set(), set(), set()
        
        modified_files = set()
        added_files = set()
        deleted_files = set()
        
        try:
            # 获取指定提交的变更
            result = self._run_git_command(['git', 'show', '--name-status', '--pretty=format:', commit])
            if result:
                for line in result.split('\n'):
                    if not line:
                        continue
                    
                    parts = line.split('\t')
                    if len(parts) < 2:
                        continue
                        
                    status = parts[0]
                    file_path = parts[1]
                    abs_path = os.path.abspath(os.path.join(self.git_root, file_path))
                    
                    # 解析状态
                    if status.startswith('M'):  # 修改
                        modified_files.add(abs_path)
                    elif status.startswith('A'):  # 新增
                        added_files.add(abs_path)
                    elif status.startswith('D'):  # 删除
                        deleted_files.add(abs_path)
                    elif status.startswith('R'):  # 重命名
                        if len(parts) >= 3:
                            old_file = parts[1]
                            new_file = parts[2]
                            deleted_files.add(os.path.abspath(os.path.join(self.git_root, old_file)))
                            added_files.add(os.path.abspath(os.path.join(self.git_root, new_file)))
        except Exception as e:
            if not self.quiet:
                print(f"⚠️ 获取提交变更失败: {e}")
        
        return modified_files, added_files, deleted_files

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算单个文件的MD5哈希"""
        try:
            hash_md5 = hashlib.md5()
            # 增大缓冲区以提高大文件处理性能
            buffer_size = 65536  # 64KB
            with open(file_path, 'rb') as f:
                while chunk := f.read(buffer_size):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return ""

    def _is_link_type(self, kind: str) -> bool:
        """判断是否是Link类型的文件"""
        link_types = {
            'entity_set_link',
            'metric_set_link', 
            'log_set_link',
            'trace_set_link',
            'storage_link',
            'data_link'
        }
        return kind in link_types or 'link' in kind.lower()

    def _extract_entity_references(self, content: Dict[str, Any]) -> List[str]:
        """从文件内容中提取实体引用"""
        references = set()  # 使用集合直接去重
        
        def extract_from_dict(obj: Any):
            """递归提取字典中的实体引用"""
            if isinstance(obj, dict):
                # 检查是否是实体引用格式: {domain: ..., kind: ..., name: ...}
                if all(key in obj for key in ['domain', 'kind', 'name']):
                    domain = obj['domain']
                    kind = obj['kind'] 
                    name = obj['name']
                    # 构造实体引用ID
                    ref_id = f"{domain}.{kind}.{name}"
                    references.add(ref_id)
                
                # 递归处理字典中的值
                for value in obj.values():
                    extract_from_dict(value)
            
            elif isinstance(obj, list):
                # 递归处理列表中的元素
                for item in obj:
                    extract_from_dict(item)
        
        extract_from_dict(content)
        return list(references)

    def _parse_mmodel_file(self, file_path: str) -> Optional[MModelEntity]:
        """解析单个MModel文件（包含引用关系分析）"""
        try:
            with open(os.path.join(self.work_dir, file_path), 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            if not content or not isinstance(content, dict):
                return None
            
            metadata = content.get('metadata', {})
            domain = metadata.get('domain', 'unknown')
            kind = content.get('kind', 'unknown')
            name = metadata.get('name', 'unknown')
            
            # 计算文件哈希
            file_hash = self._calculate_file_hash(file_path)
            if not file_hash:
                return None
            
            # 只对Link类型的文件提取实体引用
            references = []
            if self._is_link_type(kind):
                references = self._extract_entity_references(content)
            
            # 转换为相对路径
            rel_path = self._normalize_path(file_path)
            
            return MModelEntity(
                domain=domain,
                kind=kind,
                name=name,
                file_path=rel_path,
                file_hash=file_hash,
                references=references
            )
        except Exception as e:
            if not self.quiet:
                print(f"⚠️ 解析文件失败 {file_path}: {e}")
            return None

    def _batch_process_files(self, file_paths: List[str]) -> List[Optional[MModelEntity]]:
        """批量处理文件 - 用于进程池"""
        # 使用生成器表达式减少内存占用
        return [self._parse_mmodel_file(file_path) for file_path in file_paths]

    def _find_mmodel_files(self, directory: str, patterns: List[str] = None) -> List[str]:
        """查找MModel定义文件"""
        if patterns is None:
            patterns = ['*.yaml', '*.yml']
        
        directory_path = Path(directory)
        exclude_dirs = {'.git', '__pycache__', '.svn', 'node_modules', '.vscode', '.idea'}
        
        # 使用生成器表达式和集合推导式优化性能
        files = set()
        for pattern in patterns:
            for file_path in directory_path.rglob(pattern):
                if file_path.is_file():
                    # 优化排除目录检查
                    if not any(excluded_dir in file_path.parts for excluded_dir in exclude_dirs):
                        files.add(str(file_path))
        
        # 使用sorted直接排序集合，避免多次列表操作
        all_files = sorted(files)
        result_files = []
        for file in all_files:
            rel_path = os.path.relpath(file, self.work_dir)
            result_files.append(rel_path)
        return result_files

    def generate_index(self, 
                      source_dir: str,
                      index_file: str,
                      patterns: List[str] = None) -> Dict[str, Any]:
        """生成索引文件（包含引用关系）"""
        start_time = time.time()
        
        if not self.quiet:
            print("🚀 开始生成MModel索引文件（含引用关系分析）...")
        
        # 查找所有MModel文件
        mmodel_files = self._find_mmodel_files(source_dir, patterns)
        if not mmodel_files:
            if not self.quiet:
                print("⚠️ 未找到任何MModel定义文件")
            return {}
        
        if not self.quiet:
            print(f"📁 找到 {len(mmodel_files)} 个MModel文件")
        
        # 优化批处理逻辑
        max_workers = min(32, (os.cpu_count() or 1) + 4)
        # 确保至少有一个批次
        batch_size = max(1, len(mmodel_files) // max_workers) if max_workers > 1 else len(mmodel_files)
        batches = [
            mmodel_files[i:i + batch_size]
            for i in range(0, len(mmodel_files), batch_size)
        ]
        
        all_entities = []
        
        if not self.quiet:
            print(f"⚡ 使用 {min(max_workers, len(batches))} 个进程并行处理...")
        
        # 并行处理文件
        if len(batches) > 1:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {
                    executor.submit(self._batch_process_files, batch): batch
                    for batch in batches
                }
                
                processed = 0
                for future in as_completed(future_to_batch):
                    batch_results = future.result()
                    all_entities.extend((e for e in batch_results if e is not None))
                    processed += len(future_to_batch[future])
                    
                    if not self.quiet and len(mmodel_files) > 100 and processed % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        print(f"📊 处理进度: {processed}/{len(mmodel_files)} ({rate:.1f} files/sec)")
        else:
            # 小文件集直接处理，避免进程开销
            all_entities = [e for e in self._batch_process_files(mmodel_files) if e is not None]
        
        # 构建索引数据结构
        index_data = {
            'meta': {  # 缩短字段名
                'v': '4.0',  # 版本号升级，优化为只保存实体ID
                'ts': datetime.now().isoformat(),
                'git': self._get_current_commit(),
                'files': len(mmodel_files),
                'entities': len(all_entities),
                'gen_time': time.time() - start_time
            },
            'entities': {},  # mmodel_id -> file_hash (极简结构，只保存实体ID和文件哈希)
            'refs': {},  # mmodel_id -> [referencing_file_paths] (引用关系)
            'file_mmodel': {},  # file_path -> mmodel_id (用于快速查找文件路径)
        }
        
        # 填充索引数据和构建引用关系 - 使用更高效的方法
        duplicate_ids = {}
        entity_references = {}  # 临时存储：entity_id -> set of files that reference it
        
        # 预分配列表大小以提高性能
        link_files_count = 0
        
        for entity in all_entities:
            mmodel_id = entity.mmodel_id
            file_path = entity.file_path
            
            # 检查重复的MModelID
            if mmodel_id in index_data['entities']:
                if mmodel_id not in duplicate_ids:
                    duplicate_ids[mmodel_id] = []
                duplicate_ids[mmodel_id].append(file_path)
            else:
                # 极简的实体信息 - 只保存实体ID和文件哈希
                index_data['entities'][mmodel_id] = entity.file_hash
                index_data['file_mmodel'][file_path] = mmodel_id
            
            # 只有Link文件且有引用时才保存references到单独的结构中
            if entity.references:
                link_files_count += 1
                # 构建反向引用索引
                for ref_entity_id in entity.references:
                    if ref_entity_id not in entity_references:
                        entity_references[ref_entity_id] = {file_path}  # 使用集合而不是列表
                    else:
                        entity_references[ref_entity_id].add(file_path)
        
        # 转换反向引用索引为列表格式
        # 使用字典推导式提高性能
        index_data['refs'] = {entity_id: list(referencing_files) 
                             for entity_id, referencing_files in entity_references.items()}

        # 统计引用关系
        total_references = sum(len(refs) for refs in index_data['refs'].values())
        referenced_entities = len(index_data['refs'])
        
        # 保存索引文件
        try:
            os.makedirs(os.path.dirname(os.path.abspath(index_file)), exist_ok=True)
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, separators=(',', ':'), ensure_ascii=False)  # 紧凑格式
            
            elapsed = time.time() - start_time
            if not self.quiet:
                print(f"✅ 索引文件已生成: {index_file}")
                print(f"📊 统计: {len(all_entities)} 个实体, {link_files_count} 个Link文件, {total_references} 个引用关系, {referenced_entities} 个被引用实体")
                print(f"⏱️ 总耗时: {elapsed:.2f}秒 (平均 {len(mmodel_files) / elapsed:.1f} files/sec)")
        
        except Exception as e:
            if not self.quiet:
                print(f"❌ 保存索引文件失败: {e}")
            return {}
        
        return index_data

    def _load_index_file(self, index_file: str) -> Dict[str, Any]:
        """加载索引文件"""
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            if not self.quiet:
                print(f"❌ 加载索引文件失败: {e}")
            return {}

    def _get_git_status_files(self) -> Tuple[Set[str], Set[str], Set[str]]:
        """获取Git状态文件 - 返回(修改文件, 新增文件, 删除文件)"""
        if not self.is_git_repo:
            return set(), set(), set()
        
        modified_files = set()
        added_files = set()
        deleted_files = set()
        
        try:
            # 获取工作区状态
            result = self._run_git_command(['git', 'status', '--porcelain'])
            if result:
                for line in result.split('\n'):
                    if not line:
                        continue
                    
                    status = line[:2]
                    file_path = line[3:]
                    abs_path = os.path.abspath(os.path.join(self.git_root, file_path))
                    
                    # 解析状态
                    if 'M' in status or 'T' in status:  # 修改
                        modified_files.add(abs_path)
                    elif 'A' in status or '?' in status:  # 新增或未跟踪
                        added_files.add(abs_path)
                    elif 'D' in status:  # 删除
                        deleted_files.add(abs_path)
                    elif 'R' in status or 'C' in status:  # 重命名或复制
                        if ' -> ' in file_path:
                            old_file, new_file = file_path.split(' -> ')
                            deleted_files.add(os.path.abspath(os.path.join(self.git_root, old_file)))
                            added_files.add(os.path.abspath(os.path.join(self.git_root, new_file)))
        
        except Exception as e:
            if not self.quiet:
                print(f"⚠️ 获取Git状态失败: {e}")
        
        return modified_files, added_files, deleted_files

    def _find_related_files(self, deleted_file: str, index_data: Dict[str, Any]) -> List[str]:
        """查找与删除文件相关的文件（基于引用关系）"""
        related_files = []
        
        # 获取删除文件的相对路径
        rel_deleted_file = self._normalize_path(deleted_file)
        
        # 规范化路径分隔符（Windows/Linux兼容）
        rel_deleted_file = rel_deleted_file.replace(os.sep, '/')
        
        # 如果删除的文件在索引中，找到其MModelID
        mmodel_id = None
        # 检查新版本索引格式（v4.0）- entities只包含entity_id -> file_hash
        if index_data.get('meta', {}).get('v') == '4.0':
            # 新格式：需要通过文件路径反查实体ID
            # 这里我们遍历所有实体ID，并检查对应的文件是否匹配删除的文件
            # 但在v4.0格式中，我们没有直接的文件路径信息，所以跳过这个检查
            # 使用更通用的方法：检查索引中是否有相关实体
            mmodel_id = index_data.get('file_mmodel', {}).get(rel_deleted_file)
        else:
            # 旧版本索引格式  
            for entity_id, entity_data in index_data.get('entities', {}).items():
                if isinstance(entity_data, dict) and entity_data.get('f') == rel_deleted_file:
                    mmodel_id = entity_id
                    break

        if not mmodel_id:
            return related_files
        
        referencing_files = index_data.get('refs', {}).get(mmodel_id, [])
        for ref_file in referencing_files:
            abs_ref_file = os.path.abspath(os.path.join(self.work_dir, ref_file))
            if os.path.exists(abs_ref_file):
                related_files.append(abs_ref_file)
        return related_files

    def get_validation_files(self, 
                           index_file: str,
                           source_dir: str,
                           patterns: List[str] = None,
                           focus_all: bool = False) -> List[str]:
        """获取待校验的文件列表"""
        start_time = time.time()
        
        if not self.quiet:
            print("🔍 开始分析待校验文件（基于引用关系）...")

        if focus_all:
            if not self.quiet:
                print("🔍 全量验证模式，返回所有MModel文件")
            return self._find_mmodel_files(source_dir, patterns)
        else:
            if not self.quiet:
                print("🔍 增量验证模式，基于索引文件")
        
        # 如果不是Git仓库，返回所有MModel文件
        if not self.is_git_repo:
            if not self.quiet:
                print("📁 非Git仓库，返回所有MModel文件")
            all_files = self._find_mmodel_files(source_dir, patterns)
            return all_files
        
        # 加载索引文件
        index_data = self._load_index_file(index_file)
        if not index_data:
            if not self.quiet:
                print("⚠️ 索引文件无效，返回所有MModel文件")
            return self._find_mmodel_files(source_dir, patterns)

        # 检查索引版本
        index_version = index_data.get('metadata', {}).get('version', '1.0')
        has_reference_analysis = 'entity_references' in index_data

        if not self.quiet:
            print(f"📋 索引版本: {index_version}, 引用分析: {'✅' if has_reference_analysis else '❌'}")
        
        # 获取Git状态
        modified_files, added_files, deleted_files = self._get_git_status_files()
        
        if not self.quiet:
            print(f"📊 Git状态: 修改 {len(modified_files)}, 新增 {len(added_files)}, 删除 {len(deleted_files)}")
        
        # 如果索引中有Git提交信息，进行提交间对比
        index_git_commit = index_data.get('meta', {}).get('git', '')
        if index_git_commit:
            commit_changed_files, deleted_files = self.get_final_modified_files(index_git_commit)
            if not self.quiet:
                print(f"🔄 索引提交 {index_git_commit[:8]} 以来的变更文件: {len(commit_changed_files)}")
            # 合并提交变更文件到修改文件集合
            modified_files.update(commit_changed_files)
            deleted_files.update(deleted_files)
        
        validation_files = set()
        
        # 处理修改和新增的文件
        for file_path in modified_files | added_files:
            if self._is_mmodel_file(file_path, patterns):
                validation_files.add(file_path)
        
        # 处理删除的文件 - 查找相关文件
        for deleted_file in deleted_files:
            related_files = self._find_related_files(deleted_file, index_data)
            validation_files.update(related_files)
            
        # 转换为相对路径并排序
        result_files = []
        work_dir = os.path.abspath(self.work_dir)
        for abs_path in validation_files:
            try:
                rel_path = os.path.abspath(abs_path)
                # 确保文件在源目录下且存在
                if os.path.commonpath([rel_path, work_dir]) == work_dir:
                    result_files.append(self._normalize_path(rel_path))
            except ValueError:
                continue
        
        result_files.sort()
        
        elapsed = time.time() - start_time
        if not self.quiet:
            print(f"✅ 分析完成: 找到 {len(result_files)} 个待校验文件")
            print(f"⏱️ 耗时: {elapsed:.2f}秒")
        
        return result_files

    def analyze_entity_references(self, index_file: str) -> None:
        """分析实体引用关系（调试用）"""
        index_data = self._load_index_file(index_file)
        if not index_data:
            print("❌ 无法加载索引文件")
            return
        
        print("🔗 实体引用关系分析:")
        entity_refs = index_data.get('entity_references', {})
        ref_graph = index_data.get('reference_graph', {})
        
        print(f"📊 总计: {len(entity_refs)} 个被引用实体")
        
        # 显示最多被引用的实体
        sorted_refs = sorted(entity_refs.items(), key=lambda x: len(x[1]), reverse=True)
        print("\n🏆 被引用次数最多的实体:")
        for entity_id, files in sorted_refs[:10]:
            print(f"  {entity_id}: {len(files)} 次引用")
            for f in files[:3]:
                print(f"    - {f}")
            if len(files) > 3:
                print(f"    - ... 还有 {len(files) - 3} 个文件")
        
        # 显示引用关系最多的文件
        sorted_graph = sorted(ref_graph.items(), key=lambda x: len(x[1]), reverse=True)
        print("\n📎 引用其他实体最多的文件:")
        for file_path, refs in sorted_graph[:10]:
            if refs:
                print(f"  {file_path}: 引用了 {len(refs)} 个实体")
                for ref in refs[:3]:
                    print(f"    - {ref}")
                if len(refs) > 3:
                    print(f"    - ... 还有 {len(refs) - 3} 个引用")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='MModel索引管理器 - 改进版（支持引用关系分析）')
    parser.add_argument('action', choices=['generate', 'validate'],
                       help='操作类型: generate(生成索引) 或 validate(获取待校验文件) 或 analyze(分析引用关系) 或 modified(获取修改文件列表)')
    
    # 通用参数
    parser.add_argument('-d', '--directory', default='.',
                       help='MModel定义文件目录 (默认: 当前目录)')
    parser.add_argument('-i', '--index-file', default='mmodel_index.json',
                       help='索引文件路径 (默认: mmodel_index.json)')
    parser.add_argument('-p', '--patterns', nargs='+', default=['*.yaml', '*.yml'],
                       help='文件匹配模式 (默认: *.yaml *.yml)')
    parser.add_argument('--quiet', action='store_true', help='静默模式')
    
    args = parser.parse_args()
    
    manager = MModelIndexManager(work_dir=args.directory, quiet=args.quiet)
    
    if args.action == 'generate':
        # 生成索引
        index_data = manager.generate_index(
            source_dir=args.directory,
            index_file=args.index_file,
            patterns=args.patterns
        )
        
        if index_data and not args.quiet:
            print(f"\n🎯 索引生成完成")
            print(f"📄 索引文件: {args.index_file}")
            print(f"📊 实体数量: {index_data['meta']['entities']}")
            print(f"🔗 引用关系: 已分析")
    
    elif args.action == 'validate':
        # 获取待校验文件
        validation_files = manager.get_validation_files(
            index_file=args.index_file,
            source_dir=args.directory,
            patterns=args.patterns
        )
        
        if args.quiet:
            # 静默模式只输出文件列表
            for file_path in validation_files:
                print(file_path)
        else:
            print(f"\n🎯 待校验文件列表:")
            for file_path in validation_files:
                rel_path = os.path.relpath(file_path, args.directory)
                print(f"  {rel_path}")
        
        return validation_files

if __name__ == "__main__":
    main() 