#!/usr/bin/env python3
"""
MModel Lint - MModel定义文件校验工具 v10.6

终极抽象精简版本

使用方法：
    python mmodel_lint.py --definitions-dir examples/quickstart-multidomain
"""
import os
import sys, yaml, re, logging, argparse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from functools import lru_cache, cached_property
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 配置 =====
DEFAULT_RULES_FILE, MAX_WORKERS = "mmodel_lint_rules.yaml", 4
# entity_set_link 是实体链接，也具备被 Link 的能力
ENTITY_KINDS = frozenset({'entity_set', 'trace_set', 'metric_set', 'log_set', 'event_set', 'entity_set_link'})
CONSTRAINT_TYPES = {'equals', 'not_equals', 'const', 'regex', 'in', 'contains', 'length_min', 'length_max'}

class Logger:
    def __init__(self, level: str = "INFO", use_colors: bool = True):
        self.level = getattr(logging, level.upper())
        self.colors = {'INFO': '\033[32m', 'WARNING': '\033[33m', 'ERROR': '\033[31m', 'RESET': '\033[0m'} if use_colors and sys.stdout.isatty() else {}
    
    def _log(self, level: str, msg: str, icon: str = ""):
        if getattr(logging, level) >= self.level:
            color, reset = self.colors.get(level, ''), self.colors.get('RESET', '')
            print(f"{icon} {color}{msg}{reset}")
    
    def info(self, msg): self._log('INFO', msg, "ℹ️")
    def success(self, msg): self._log('INFO', msg, "✅")
    def progress(self, msg): self._log('INFO', msg, "📄")
    def stats(self, msg): self._log('INFO', msg, "📊")
    def warning(self, msg): self._log('WARNING', msg, "⚠️")
    def error(self, msg): self._log('ERROR', msg, "❌")
    def debug(self, msg): 
        if self.level <= logging.DEBUG: self._log('INFO', msg, "🔍")

logger = Logger()

@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: Tuple[str, ...] = field(default_factory=tuple)
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    file_path: str = ""
    has_issues: bool = field(init=False)
    
    def __post_init__(self): object.__setattr__(self, 'has_issues', bool(self.errors or self.warnings))

@dataclass
class ValidationStats:
    total: int = 0
    valid: int = 0
    errors: int = 0
    warnings: int = 0
    
    @property
    def success_rate(self): return (self.valid / max(self.total, 1)) * 100
    
    def update(self, result):
        self.total += 1
        if result.valid: self.valid += 1
        else: self.errors += 1
        if result.warnings: self.warnings += 1

# ===== 核心校验器 =====
class MModelLint:
    def __init__(self, definitions_dir: str, rules_config_path: Optional[str] = None):
        self.definitions_dir = Path(definitions_dir)
        self.rules_config_path = Path(rules_config_path) if rules_config_path else Path(__file__).parent / DEFAULT_RULES_FILE
        self.definition_files, self.entity_definitions, self.stats = {}, {}, ValidationStats()
        self._regex_cache, self._regex_patterns = {}, {
            'variable': re.compile(r'\{([^}]+)\}'), 'condition_eq': re.compile(r'^(.+?)\s*==\s*(.+)$'),
            'condition_in': re.compile(r'^(.+?)\s+in\s+\[(.+)\]$'), 'json_path': re.compile(r'^\$\.(.+)$'),
        }
    
    @cached_property
    def rules(self):
        try:
            with open(self.rules_config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"规则配置加载失败: {e}")
            return {'validation_rules': []}
    
    def _regex(self, name): return self._regex_patterns.get(name)
    
    def _compile(self, pattern):
        if pattern not in self._regex_cache:
            try: self._regex_cache[pattern] = re.compile(pattern)
            except re.error as e: raise ValueError(f"无效正则: {pattern} - {e}")
        return self._regex_cache[pattern]
    
    @lru_cache(maxsize=128)
    def _resolve(self, path: str, ctx_key: str):
        ctx = self.definition_files.get(ctx_key, {})
        if path == "$filename": return ctx.get('filename', '')
        if match := self._regex('json_path').match(path):
            obj = ctx.get('content', {})
            for part in match.group(1).split('.'):
                if isinstance(obj, dict) and part in obj: obj = obj[part]
                else: return None
            return obj
        return ctx.get(path) if path == 'filename' else None
    
    def _parse_format_value(self, pattern, var_names, target_value, constraints=None, ctx_key=None):
        """
        改进的格式解析方法，支持基于约束的智能匹配
        优先使用约束信息来辅助解析，提高准确性
        """
        if not var_names:
            return {} if pattern == target_value else None
        
        # 如果有约束信息，尝试使用约束辅助解析
        if constraints and ctx_key:
            parsed_result = self._try_constraint_based_parsing(pattern, var_names, target_value, constraints, ctx_key)
            if parsed_result is not None:
                logger.debug(f"约束辅助解析成功: pattern='{pattern}', target='{target_value}', result={parsed_result}")
                return parsed_result
        
        # 回退到基于正则表达式的解析
        return self._regex_based_parsing(pattern, var_names, target_value)
    
    def _try_constraint_based_parsing(self, pattern, var_names, target_value, constraints, ctx_key):
        """
        基于约束的智能解析：利用约束条件来辅助格式解析
        """
        try:
            # 收集已知的变量值
            known_values = {}
            for var_name in var_names:
                constraint = constraints.get(var_name, {})
                for ctype, cvalue in constraint.items():
                    if ctype == 'equals' and isinstance(cvalue, str) and cvalue.startswith('$.'):
                        # 从上下文中解析约束值
                        expected_value = self._resolve(cvalue, ctx_key)
                        if expected_value is not None:
                            known_values[var_name] = str(expected_value)
                            break
            
            if len(known_values) < len(var_names):
                return None  # 约束信息不足，回退到正则解析
            
            # 构建预期的格式字符串，然后验证是否匹配
            expected_format = pattern
            for var_name, var_value in known_values.items():
                expected_format = expected_format.replace(f"{{{var_name}}}", var_value)
            
            if expected_format == target_value:
                logger.debug(f"约束验证成功: expected='{expected_format}', actual='{target_value}'")
                return known_values
            else:
                logger.debug(f"约束验证失败: expected='{expected_format}', actual='{target_value}'")
                return None
                
        except Exception as e:
            logger.debug(f"约束辅助解析失败: {e}")
            return None
    
    def _regex_based_parsing(self, pattern, var_names, target_value):
        """
        基于正则表达式的格式解析（改进版）
        使用更智能的匹配策略来处理复杂情况
        """
        # 特殊处理：如果只有一个变量，直接返回
        if len(var_names) == 1:
            return {var_names[0]: target_value}
        
        # 对于多个变量，使用改进的分割策略
        return self._smart_split_parsing(pattern, var_names, target_value)
    
    def _smart_split_parsing(self, pattern, var_names, target_value):
        """
        智能分割解析：处理复杂的多变量格式
        """
        try:
            # 分析模式中的分隔符
            separators = []
            remaining_pattern = pattern
            
            for i, var_name in enumerate(var_names):
                var_placeholder = f"{{{var_name}}}"
                start_pos = remaining_pattern.find(var_placeholder)
                
                if start_pos == -1:
                    return None
                
                # 提取变量前的分隔符
                if start_pos > 0:
                    separator = remaining_pattern[:start_pos]
                    if separator:
                        separators.append(separator)
                
                # 更新剩余模式
                end_pos = start_pos + len(var_placeholder)
                remaining_pattern = remaining_pattern[end_pos:]
            
            # 添加最后的分隔符（如果存在）
            if remaining_pattern:
                separators.append(remaining_pattern)
            
            # 使用分隔符进行分割
            if len(separators) == len(var_names) - 1:
                return self._split_by_separators(target_value, separators, var_names)
            
            # 如果分隔符数量不匹配，回退到正则表达式方法
            return self._fallback_regex_parsing(pattern, var_names, target_value)
            
        except Exception as e:
            logger.debug(f"智能分割解析失败: {e}")
            return self._fallback_regex_parsing(pattern, var_names, target_value)
    
    def _split_by_separators(self, target_value, separators, var_names):
        """
        根据分隔符列表分割目标字符串
        """
        result = {}
        remaining_value = target_value
        
        for i, var_name in enumerate(var_names[:-1]):  # 除了最后一个变量
            sep = separators[i] if i < len(separators) else None
            if not sep:
                continue
                
            # 找到分隔符的位置
            sep_pos = remaining_value.find(sep)
            if sep_pos == -1:
                return None
            
            # 提取变量值
            var_value = remaining_value[:sep_pos]
            result[var_name] = var_value
            
            # 更新剩余字符串
            remaining_value = remaining_value[sep_pos + len(sep):]
        
        # 处理最后一个变量
        last_var = var_names[-1]
        if len(separators) == len(var_names):
            # 有结尾分隔符
            last_sep = separators[-1]
            if remaining_value.endswith(last_sep):
                result[last_var] = remaining_value[:-len(last_sep)]
            else:
                return None
        else:
            # 没有结尾分隔符，剩余的全部是最后一个变量的值
            result[last_var] = remaining_value
        
        return result
    
    def _fallback_regex_parsing(self, pattern, var_names, target_value):
        """
        回退到原来的正则表达式解析方法
        """
        # 构建正则表达式
        regex_pattern = pattern
        var_positions = []
        
        for var_name in var_names:
            var_pattern = f"{{{var_name}}}"
            pos = regex_pattern.find(var_pattern)
            if pos != -1:
                var_positions.append((pos, var_name, var_pattern))
        
        # 按位置倒序排列，从后往前替换
        var_positions.sort(key=lambda x: x[0], reverse=True)
        
        for pos, var_name, var_pattern in var_positions:
            # 使用非贪婪匹配，但最后一个变量可以贪婪匹配
            is_last_var = pos == max(p[0] for p in var_positions)
            capture_group = f"(?P<{var_name}>.*)" if is_last_var else f"(?P<{var_name}>.*?)"
            regex_pattern = regex_pattern.replace(var_pattern, capture_group, 1)
        
        # 转义处理
        temp_pattern = regex_pattern
        protected_groups = {}
        group_counter = 0
        
        import re as re_module
        for match in re_module.finditer(r'\(\?P<[^>]+>.*?\)', temp_pattern):
            placeholder = f"__GROUP_{group_counter}__"
            protected_groups[placeholder] = match.group()
            temp_pattern = temp_pattern.replace(match.group(), placeholder, 1)
            group_counter += 1
        
        escaped_pattern = re_module.escape(temp_pattern)
        
        for placeholder, group in protected_groups.items():
            escaped_pattern = escaped_pattern.replace(re_module.escape(placeholder), group)
        
        try:
            compiled_regex = self._compile(f"^{escaped_pattern}$")
            match = compiled_regex.match(target_value)
            
            if match:
                result = match.groupdict()
                logger.debug(f"回退正则解析成功: pattern='{pattern}', target='{target_value}', result={result}")
                return result
            else:
                logger.debug(f"回退正则解析失败: pattern='{pattern}', target='{target_value}'")
                return None
                
        except Exception as e:
            logger.debug(f"回退正则解析异常: {e}")
            return None

    def _validate_constraint(self, name, value, constraint, ctx_key):
        if not isinstance(constraint, dict): 
            return f'{name}的约束配置必须是字典格式'
        
        for ctype, cvalue in constraint.items():
            if ctype not in CONSTRAINT_TYPES: 
                continue
            
            try:
                if ctype in ('equals', 'not_equals'):
                    # 解析约束值
                    if isinstance(cvalue, str) and cvalue.startswith('$.'):
                        # JSON path引用
                        field_val = str(self._resolve(cvalue, ctx_key) or '')
                    else:
                        # 直接值
                        field_val = str(cvalue)
                    
                    logger.debug(f"约束校验 - name: {name}, value: '{value}', constraint_type: {ctype}, expected: '{field_val}'")
                    
                    is_eq = field_val == value
                    if ctype == 'equals' and not is_eq: 
                        return f'{name}必须等于{cvalue}的值({field_val})，实际：{value}'
                    elif ctype == 'not_equals' and is_eq: 
                        return f'{name}不能等于{cvalue}的值({field_val})'
                
                elif ctype == 'const' and str(cvalue) != value: 
                    return f'{name}必须等于{cvalue}，实际：{value}'
                
                elif ctype == 'regex':
                    if not self._compile(f"^{cvalue}$").match(value): 
                        return f'{name}格式不符合规则：{cvalue}'
                
                elif ctype == 'in' and value not in cvalue: 
                    return f'{name}必须是以下值之一：{cvalue}，实际：{value}'
                
                elif ctype == 'contains' and cvalue not in value: 
                    return f'{name}必须包含：{cvalue}'
                
                elif ctype in ('length_min', 'length_max'):
                    length = len(value)
                    if ctype == 'length_min' and length < cvalue: 
                        return f'{name}长度不能少于{cvalue}个字符，实际：{length}'
                    elif ctype == 'length_max' and length > cvalue: 
                        return f'{name}长度不能超过{cvalue}个字符，实际：{length}'
                        
            except ValueError as e: 
                return f'{name}的约束配置错误：{e}'
            except Exception as e:
                logger.debug(f"约束校验异常: {e}")
                return f'{name}约束校验失败：{e}'
        
        return None

    def _validate(self, rule, context, ctx_key):
        if not (value_path := rule.get('value')): 
            return None
        if (target_value := self._resolve(value_path, ctx_key)) is None: 
            return None
        
        target_value = str(target_value)
        msg = rule.get('message', '')
        rule_type = rule.get('type', '')
        
        logger.debug(f"开始校验规则: {rule.get('name', 'unnamed')}, type: {rule_type}, target_value: '{target_value}'")
        
        try:
            # 格式校验
            if rule_type == 'format':
                if not (pattern := rule.get('format', '')): 
                    return None
                
                var_names = self._regex('variable').findall(pattern)
                if not var_names:
                    # 没有变量，直接比较
                    return None if pattern == target_value else (msg or '格式不匹配')
                
                # 获取约束信息
                constraints = rule.get('format_constraints', {})
                
                # 解析格式，传递约束信息以启用智能解析
                parsed_vars = self._parse_format_value(pattern, var_names, target_value, constraints, ctx_key)
                
                if parsed_vars is None:
                    return msg or f'格式不正确，期望格式：{pattern}'
                
                # 校验约束
                if constraints:
                    for var_name, var_value in parsed_vars.items():
                        if constraint := constraints.get(var_name):
                            if error := self._validate_constraint(var_name, var_value, constraint, ctx_key):
                                return msg or error
            
            # 模式校验
            elif rule_type == 'pattern':
                if not (pattern := rule.get('pattern', '')): 
                    return None
                if not self._compile(pattern).match(target_value): 
                    return msg or '模式不匹配'
            
            # 实体存在性校验
            elif rule_type == 'telemetry_data_set_exists':
                not_found = (len(self.find_target_files(directory=str(self.definitions_dir), patterns=[f'{target_value}.yaml', f'{target_value}.yml'])) == 0)
                if not_found:
                    return (msg or f"引用的实体'{target_value}'不存在").replace('{value}', target_value)
            
            # 自定义校验类型扩展点
            elif rule_type == 'custom':
                return self._validate_custom(rule, target_value, context, ctx_key)
            
            else: 
                return f"不支持的校验类型：{rule_type}"
            
        except Exception as e:
            logger.debug(f"校验规则执行异常: {e}")
            return f"校验规则执行失败：{e}"
        
        return None
    def find_target_files(self,
                          directory: str,
                          patterns: List[str] = None) -> List[str]:
        """查找目标文件"""
        if patterns is None:
            patterns = ['*.yaml', '*.yml']

        files = []
        directory_path = Path(directory)
        # 排除的目录
        exclude_dirs = {
            '.git', '__pycache__', '.svn', 'node_modules', '.vscode', '.idea'
        }

        for pattern in patterns:
            for file_path in directory_path.rglob(pattern):
                if file_path.is_file():
                    # 检查是否在排除目录中
                    if not any(excluded in file_path.parts
                               for excluded in exclude_dirs):
                        files.append(str(file_path))
        return sorted(files)

    def _validate_custom(self, rule, target_value, context, ctx_key):
        """
        自定义校验方法的扩展点，子类可以重写此方法来添加自定义校验逻辑
        """
        custom_type = rule.get('custom_type', '')
        
        # 这里可以添加更多自定义校验逻辑的实现
        if custom_type == 'domain_consistency':
            # 示例：域名一致性校验
            expected_domain = self._resolve('$.metadata.domain', ctx_key)
            if expected_domain and not target_value.startswith(f"{expected_domain}."):
                return rule.get('message', f'名称必须以域名 {expected_domain} 开头')
        
        return f"不支持的自定义校验类型：{custom_type}"
    
    def _should_apply(self, rule, context):
        condition = rule.get('when', 'true')
        if condition == 'true': 
            return True
        
        try:
            if match := self._regex('condition_eq').match(condition):
                left, right = match.groups()
                return str(context.get(left.strip())) == right.strip().strip("'\"")
            if match := self._regex('condition_in').match(condition):
                left, right = match.groups()
                items = [item.strip().strip("'\"") for item in right.split(',')]
                return str(context.get(left.strip(), '')) in items
        except: 
            pass
        return False
    
    def load_files(self, changed_files : List[str] = None, focus_all: bool = False):
        logger.info("开始加载定义文件...")
        
        if not self.definitions_dir.exists():
            logger.error(f"目录不存在: {self.definitions_dir}")
            return False

        if changed_files and not focus_all:
            yaml_files = [self.definitions_dir / file_path for file_path in changed_files]
        else:
            yaml_files = list(self.definitions_dir.rglob("*.yaml"))

        if not yaml_files:
            logger.error("未找到任何YAML文件")
            return False
        
        logger.progress(f"找到 {len(yaml_files)} 个YAML文件，使用 {MAX_WORKERS} 个线程并发处理...")
        
        success_count = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self._load_file, f): f for f in yaml_files}
            
            for future in as_completed(futures):
                yaml_file = futures[future]
                try:
                    if result := future.result():
                        file_data, entity_data = result
                        relative_path = yaml_file.relative_to(self.definitions_dir)
                        file_data['filename'] = relative_path.name
                        self.definition_files[str(relative_path)] = file_data
                        self.entity_definitions.update(entity_data)
                        success_count += 1
                        logger.success(f"已加载: {relative_path}")
                except Exception as e:
                    logger.error(f"加载失败 {yaml_file}: {e}")
        
        logger.stats(f"成功加载 {success_count}/{len(yaml_files)} 个文件，索引 {len(self.entity_definitions)} 个实体")
        return success_count > 0
    
    def _load_file(self, yaml_file):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            if not content or not isinstance(content, dict): return None
            
            file_data = {'content': content, 'relative_path': yaml_file.relative_to(self.definitions_dir)}
            entity_data = {}
            
            if content.get('kind') in ENTITY_KINDS:
                if name := content.get('metadata', {}).get('name'): entity_data[name] = content
            
            return file_data, entity_data
        except: return None
    
    def validate_all(self):
        logger.info("开始校验...")
        
        results = {}
        for file_path, file_info in self.definition_files.items():
            context = {
                'content': file_info['content'], 'filename': file_info['relative_path'].name,
                'kind': file_info['content'].get('kind', ''), 
                'metadata': file_info['content'].get('metadata', {}),
                'spec': file_info['content'].get('spec', {})
            }
            
            errors, warnings = [], []
            for rule in self.rules.get('validation_rules', []):
                if self._should_apply(rule, context):
                    if error_msg := self._validate(rule, context, file_path):
                        (warnings if rule.get('level') == 'warning' else errors).append(error_msg)
            
            valid = len(errors) == 0
            result = ValidationResult(valid=valid, errors=tuple(errors), warnings=tuple(warnings), file_path=file_path)
            
            results[file_path] = result
            self.stats.update(result)
        
        return results
    
    def generate_report(self, results):
        sections = [
            "# MModel Lint 校验报告 v10.6\n",
            f"""## 📊 校验摘要
- **总文件数**: {self.stats.total}
- **校验通过**: {self.stats.valid}
- **有错误**: {self.stats.errors}
- **有警告**: {self.stats.warnings}
- **成功率**: {self.stats.success_rate:.1f}%
""",
        ]
        
        if self.stats.errors > 0:
            sections.append("## 📋 校验问题详情\n")
            for file_path, result in results.items():
                if result.has_issues:
                    sections.append(f"### `{file_path}`")
                    for error in result.errors: sections.append(f"- ❌ {error}")
                    for warning in result.warnings: sections.append(f"- ⚠️ {warning}")
                    sections.append("")
        else:
            sections.append("## ✅ 所有文件校验通过！\n")
        
        return "\n".join(sections)
    
    def run(self):
        logger.info("🚀 MModel Lint v10.6 启动")
        if not self.load_files(): return {}
        return self.validate_all()

def main():
    parser = argparse.ArgumentParser(
        description="MModel Lint v10.6 - MModel定义文件校验工具（终极抽象精简版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s -d examples/quickstart-multidomain
  %(prog)s --definitions-dir ./schemas --rules-config custom_rules.yaml
  %(prog)s -d examples/quickstart-multidomain --save-report report.md
        """
    )
    
    parser.add_argument('--definitions-dir', '-d', required=True, help='定义文件目录路径')
    parser.add_argument('--rules-config', '-r', help='校验规则配置文件路径')
    parser.add_argument('--log-level', '-l', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO', help='日志级别')
    parser.add_argument('--no-colors', action='store_true', help='禁用彩色输出')
    parser.add_argument('--quiet', '-q', action='store_true', help='静默模式，只输出错误')
    parser.add_argument('--save-report', '-s', help='保存报告到指定文件（可选）')
    
    args = parser.parse_args()
    
    global logger
    logger = Logger(level='ERROR' if args.quiet else args.log_level, use_colors=not args.no_colors)
    
    try:
        validator = MModelLint(args.definitions_dir, args.rules_config)
        results = validator.run()
        
        if not results:
            logger.error("没有文件被校验")
            sys.exit(1)
        
        report = validator.generate_report(results)
        if not args.quiet: print(report)
        
        # 可选的文件保存
        if args.save_report:
            try:
                with open(args.save_report, 'w', encoding='utf-8') as f: f.write(report)
                logger.info(f"校验报告已保存到: {args.save_report}")
            except Exception as e: logger.warning(f"保存报告失败: {e}")
        
        if validator.stats.errors == 0:
            logger.success(f"所有校验通过！总计 {validator.stats.total} 个文件")
            sys.exit(0)
        else:
            logger.error(f"校验失败：{validator.stats.errors} 个文件有错误")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.warning("用户中断校验")
        sys.exit(130)
    except Exception as e:
        logger.error(f"校验失败: {e}")
        if args.log_level == 'DEBUG':
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__": main()
