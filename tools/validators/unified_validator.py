#!/usr/bin/env python3
import os.path
import sys
import yaml
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import io

sys.path.append(str(Path(__file__).parent))
from schema_validator import SchemaValidator
from mmodel_lint import MModelLint, ValidationResult
from mmodel_validator import ConfigValidator
from common_schema_index import MModelIndexManager

# 常量定义
COLORS = {
    'SUCCESS': "#11998e",
    'WARNING': "#f093fb",
    'ERROR': "#fc466b",
    'SYSTEM_ERROR': "#ff4757"
}

CSS_STYLES = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background-color: #f5f5f5; }
.container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 30px; }
.header { text-align: center; border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 30px; }
.header h1 { color: #333; margin: 0 0 10px 0; }
.timestamp { color: #666; font-size: 14px; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
.summary-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }
.summary-card.success { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.summary-card.warning { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.summary-card.error { background: linear-gradient(135deg, #fc466b 0%, #3f5efb 100%); }
.summary-card h3 { margin: 0 0 10px 0; font-size: 24px; }
.summary-card p { margin: 0; opacity: 0.9; }
.domain-section { margin-bottom: 30px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
.domain-header { background: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #ddd; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.domain-header:hover { background: #e9ecef; }
.domain-header h3 { margin: 0; color: #333; }
.domain-stats { display: flex; gap: 20px; align-items: center; }
.status-badge { padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; text-transform: uppercase; }
.status-success { background: #d4edda; color: #155724; }
.status-warning { background: #fff3cd; color: #856404; }
.status-error { background: #f8d7da; color: #721c24; }
.status-system-error { background: #ffebee; color: #c62828; }
.domain-content { display: none; padding: 20px; }
.domain-content.active { display: block; }
.entity-list { display: grid; gap: 15px; }
.entity-item { border: 1px solid #eee; border-radius: 6px; padding: 15px; background: #fafafa; }
.entity-item.invalid { border-color: #dc3545; background: #fff5f5; }
.entity-item.system-error { border-color: #ff4757; background: #fff1f0; }
.entity-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.entity-name { font-weight: bold; color: #333; }
.entity-path { font-size: 12px; color: #666; font-family: 'Courier New', monospace; }
.error-list { margin-top: 10px; }
.error-item { background: #fff; border-left: 4px solid #dc3545; padding: 10px; margin-bottom: 5px; border-radius: 0 4px 4px 0; }
.warning-item { background: #fff; border-left: 4px solid #ffc107; padding: 10px; margin-bottom: 5px; border-radius: 0 4px 4px 0; }
.toggle-arrow { transition: transform 0.3s; }
.toggle-arrow.active { transform: rotate(90deg); }
.filter-bar { margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 6px; display: flex; gap: 15px; align-items: center; }
.filter-btn { padding: 6px 12px; border: 1px solid #ddd; background: white; border-radius: 4px; cursor: pointer; transition: all 0.3s; }
.filter-btn.active { background: #007bff; color: white; border-color: #007bff; }
"""

JS_SCRIPT = """
function toggleDomain(domain) {
    const content = document.getElementById('content-' + domain);
    const arrow = document.getElementById('arrow-' + domain);
    content.classList.toggle('active');
    arrow.classList.toggle('active');
}

function filterEntities(filter) {
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    document.querySelectorAll('.entity-item').forEach(item => {
        const {status, warnings, valid, perfect} = item.dataset;
        const show = {
            'all': true,
            'success': perfect === 'true',
            'error': status === 'error',
            'warning': warnings === 'warning',
            'system_error': status === 'system_error'
        }[filter] || false;

        item.style.display = show ? 'block' : 'none';
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const firstDomain = document.querySelector('.domain-header');
    if (firstDomain) firstDomain.click();
});
"""


@dataclass
class EntityReport:
    """单个实体的验证报告"""
    file_path: str
    domain: str
    kind: str
    name: str
    is_valid: bool
    schema_errors: List[str] = field(default_factory=list)
    schema_warnings: List[str] = field(default_factory=list)
    lint_errors: List[str] = field(default_factory=list)
    lint_warnings: List[str] = field(default_factory=list)
    system_errors: List[str] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return len(self.schema_errors) + len(self.lint_errors)

    @property
    def total_warnings(self) -> int:
        return len(self.schema_warnings) + len(self.lint_warnings)

    @property
    def total_system_errors(self) -> int:
        return len(self.system_errors)

    @property
    def has_issues(self) -> bool:
        return self.total_errors > 0 or self.total_warnings > 0 or self.total_system_errors > 0

    @property
    def is_perfect(self) -> bool:
        return not self.has_issues

    @property
    def status_type(self) -> str:
        if self.total_system_errors > 0:
            return "system_error"
        elif self.total_errors > 0:
            return "error"
        elif self.total_warnings > 0:
            return "warning"
        else:
            return "success"


@dataclass
class DomainStats:
    name: str
    total: int = 0
    valid: int = 0
    system_errors: int = 0
    entities: List[EntityReport] = field(default_factory=list)

    @property
    def rate(self) -> float:
        validatable = self.total - self.system_errors
        return 100.0 if validatable == 0 else (self.valid / validatable) * 100

    @property
    def status(self) -> str:
        if self.system_errors > 0:
            return "SYSTEM_ERROR"
        elif self.rate == 100:
            return "SUCCESS"
        elif self.rate >= 80:
            return "WARNING"
        else:
            return "ERROR"


class CombinedValidator:
    """统一验证器"""

    def __init__(self, definitions_dir: str, expanded_schemas_dir: str = "expanded_schemas",
                 base_schema_path: str = "schemas/base.yaml", rules_config_path: Optional[str] = None, focus_all: bool = False):
        self.definitions_dir = Path(definitions_dir)
        self.schema_validator = None  # 延迟初始化
        self.expanded_schemas_dir = expanded_schemas_dir
        self.base_schema_path = base_schema_path
        self.config_validator = ConfigValidator(expanded_schemas_dir, base_schema_path, console_log=False)
        self.mmodel_lint = MModelLint(definitions_dir, rules_config_path)
        self.domain_stats: Dict[str, DomainStats] = {}
        self.entity_reports: List[EntityReport] = []
        self.config_validation_results: Dict[str, Any] = {}
        hash_file = os.path.join(definitions_dir , ".common_schema.index")
        self.changed_files = MModelIndexManager(work_dir=definitions_dir, quiet=True).get_validation_files(index_file=hash_file, source_dir=definitions_dir, focus_all=focus_all)
        self.focus_all = focus_all

    def run(self, quiet: bool = False) -> bool:
        """运行验证并统计"""
        if not quiet: print("🔍 运行验证...")

        if not self.changed_files:
            if not quiet: print("✅ 没有需要验证的文件")
            return True

        # 初始化schema_validator（根据quiet参数）
        self.schema_validator = SchemaValidator(self.expanded_schemas_dir, self.base_schema_path, console_log=not quiet)

        # 运行验证器
        results = {}
        results['schema'] = self._run_schema_validation()
        with self._suppress_output(quiet):
            results['lint'] = self._run_lint_validation(self.changed_files)
            results['config'] = self._run_config_validation(self.changed_files, quiet)

        if not quiet: self._print_validation_status(results)
        if not results['config']: return False

        # 处理结果
        self._process_results(quiet)
        return True

    def _suppress_output(self, quiet: bool):
        """输出抑制上下文管理器"""

        class OutputSuppressor:
            def __init__(self, should_suppress):
                self.should_suppress = should_suppress
                self.old_stdout = None

            def __enter__(self):
                if self.should_suppress:
                    self.old_stdout = sys.stdout
                    sys.stdout = io.StringIO()
                return self

            def __exit__(self, *args):
                if self.should_suppress and self.old_stdout:
                    sys.stdout = self.old_stdout

        return OutputSuppressor(quiet)

    def _run_schema_validation(self) -> bool:
        try:
            self.schema_validator.validate_all_schemas()
            return True
        except:
            return False

    def _run_lint_validation(self, changed_files: List[str] = None) -> bool:
        try:
            if self.mmodel_lint.load_files(changed_files):
                self.lint_results = self.mmodel_lint.validate_all()
                return True
        except:
            pass
        self.lint_results = {}
        return False

    def _run_config_validation(self, changed_files: List[str], quiet: bool) -> bool:
        try:
            if not quiet: print("📋 验证配置文件Schema合规性...")
            for file_path in changed_files:
                relative_path = str(self.definitions_dir / file_path)
                try:
                    result = self.config_validator.validate_config(file_path)
                    self.config_validation_results[relative_path] = result
                except Exception as e:
                    self.config_validation_results[relative_path] = {
                        "valid": False, "errors": [f"验证过程异常: {e}"], "warnings": []
                    }
            return True
        except:
            return False

    def _print_validation_status(self, results: Dict[str, bool]):
        messages = [
            ("✅ Schema验证完成" if results['schema'] else "❌ Schema验证失败"),
            ("✅ Lint验证完成" if results['lint'] else "⚠️ Lint验证有问题，但继续处理"),
            ("✅ 配置文件Schema验证完成" if results['config'] else "❌ 配置文件验证失败")
        ]
        for msg in messages: print(msg)

    def _process_results(self, quiet: bool):
        """处理验证结果"""
        if not quiet: print("📊 统计实体和收集错误...")

        domain_counts = {}
        processed_files = set()

        # 处理lint成功的文件
        for file_path, lint_result in self.lint_results.items():
            processed_files.add(file_path)
            self._process_single_file(file_path, lint_result, domain_counts)

        # 处理lint失败的文件
        for yaml_file in self.changed_files:
            relative_path = yaml_file
            if relative_path not in processed_files:
                failed_result = ValidationResult(valid=False, errors=(), warnings=(), file_path=relative_path)
                self._process_single_file(relative_path, failed_result, domain_counts, is_lint_failed=True)

        # 创建域统计
        for domain, counts in domain_counts.items():
            self.domain_stats[domain] = DomainStats(
                name=domain, **{k: v for k, v in counts.items() if k != 'entities'}
            )
            self.domain_stats[domain].entities = counts['entities']

    def _process_single_file(self, file_path: str, lint_result: ValidationResult,
                             domain_counts: dict, is_lint_failed: bool = False):
        """处理单个文件"""
        # 提取实体信息
        domain, kind, name, system_errors = self._extract_entity_info(file_path, is_lint_failed)

        # 获取schema验证结果
        schema_errors, schema_warnings = self._get_schema_validation_results(file_path, is_lint_failed)

        # 创建实体报告
        all_system_errors = system_errors
        has_validation_errors = len(schema_errors) > 0 or not lint_result.valid
        is_valid = len(all_system_errors) == 0 and not has_validation_errors

        entity_report = EntityReport(
            file_path=file_path, domain=domain, kind=kind, name=name, is_valid=is_valid,
            schema_errors=schema_errors, schema_warnings=schema_warnings,
            lint_errors=list(lint_result.errors), lint_warnings=list(lint_result.warnings),
            system_errors=all_system_errors
        )

        self.entity_reports.append(entity_report)

        # 更新域计数
        if domain not in domain_counts:
            domain_counts[domain] = {'total': 0, 'valid': 0, 'system_errors': 0, 'entities': []}

        domain_counts[domain]['total'] += 1
        domain_counts[domain]['entities'].append(entity_report)

        if entity_report.total_system_errors > 0:
            domain_counts[domain]['system_errors'] += 1
        elif entity_report.is_valid:
            domain_counts[domain]['valid'] += 1

    def _extract_entity_info(self, file_path: str, is_lint_failed: bool) -> Tuple[str, str, str, List[str]]:
        """提取实体信息"""
        domain = kind = name = 'unknown'
        system_errors = []

        if is_lint_failed:
            system_errors.append("文件在lint阶段加载失败，可能存在YAML语法错误或其他格式问题")

        try:
            with open(self.definitions_dir / file_path, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)

            if not content or not isinstance(content, dict):
                system_errors.append("文件内容为空或格式不正确")
                content = {}

            metadata = content.get('metadata', {})
            domain = metadata.get('domain', 'unknown')
            kind = content.get('kind', 'unknown')
            name = metadata.get('name', 'unknown')

        except FileNotFoundError:
            system_errors.append(f"文件不存在: {file_path}")
        except yaml.YAMLError as e:
            system_errors.append(f"YAML解析失败: {e}")
        except Exception as e:
            system_errors.append(f"文件读取异常: {e}")

        return domain, kind, name, system_errors

    def _get_schema_validation_results(self, file_path: str, is_lint_failed: bool) -> Tuple[List[str], List[str]]:
        """获取schema验证结果"""
        if is_lint_failed or file_path not in self.config_validation_results:
            return [], []

        result = self.config_validation_results[file_path]
        return result.get('errors', []), result.get('warnings', [])

    def output_aone_ci(self) -> List[str]:
        """输出aone-ci格式"""
        lines = []

        # 总体统计
        total = sum(s.total for s in self.domain_stats.values())
        valid = sum(s.valid for s in self.domain_stats.values())
        system_errors = sum(s.system_errors for s in self.domain_stats.values())
        validatable = total - system_errors
        rate = 100.0 if validatable == 0 else (valid / validatable) * 100

        status = "ERROR" if system_errors > 0 else (
            "SUCCESS" if rate == 100 else ("WARNING" if rate >= 80 else "ERROR"))
        lines.append(
            f'CUSTOM={{"name": "{rate:.0f}%", "description": "Summary", "value": "{valid}/{total}", "status": "{status}"}}')

        # 各domain统计
        for domain, stats in sorted(self.domain_stats.items()):
            lines.append(
                f'CUSTOM={{"name": "{stats.rate:.0f}%", "description": "{stats.name}", "value": "{stats.valid}/{stats.total}", "status": "{stats.status}"}}')

        return lines

    def generate_html_report(self, output_path: str = "validation_report.html") -> str:
        """生成HTML验证报告"""
        # 计算统计数据
        total_entities = sum(s.total for s in self.domain_stats.values())
        valid_entities = sum(s.valid for s in self.domain_stats.values())
        system_error_entities = sum(s.system_errors for s in self.domain_stats.values())
        perfect_entities = len([e for e in self.entity_reports if e.is_perfect])
        overall_rate = 100.0 if (total_entities - system_error_entities) == 0 else (valid_entities / (
                    total_entities - system_error_entities)) * 100

        rate_class = 'success' if overall_rate == 100 else ('warning' if overall_rate >= 80 else 'error')
        entities_with_warnings_only = valid_entities - perfect_entities

        # 构建HTML
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MModel 验证报告</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 MModel 验证报告</h1>
            <div class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <div class="summary">
            <div class="summary-card {rate_class}"><h3>{overall_rate:.1f}%</h3><p>验证成功率</p></div>
            <div class="summary-card"><h3>{total_entities}</h3><p>总实体数</p></div>
            <div class="summary-card success"><h3>{perfect_entities}</h3><p>验证通过</p></div>
            <div class="summary-card warning"><h3>{entities_with_warnings_only}</h3><p>验证有警告</p></div>
            <div class="summary-card error"><h3>{total_entities - valid_entities - system_error_entities}</h3><p>验证失败</p></div>
            <div class="summary-card" style="background: linear-gradient(135deg, #ff6b6b 0%, #ffd93d 100%);"><h3>{system_error_entities}</h3><p>非预期错误</p></div>
            <div class="summary-card error"><h3>{sum(e.total_errors for e in self.entity_reports)}</h3><p>总验证错误数</p></div>
            <div class="summary-card warning"><h3>{sum(e.total_warnings for e in self.entity_reports)}</h3><p>总警告数</p></div>
        </div>

        <div class="filter-bar">
            <span>筛选:</span>
            <button class="filter-btn active" onclick="filterEntities('all')">全部</button>
            <button class="filter-btn" onclick="filterEntities('success')">成功</button>
            <button class="filter-btn" onclick="filterEntities('error')">验证错误</button>
            <button class="filter-btn" onclick="filterEntities('warning')">警告</button>
            <button class="filter-btn" onclick="filterEntities('system_error')">非预期错误</button>
        </div>

        <div class="domains">
            {self._build_domains_html()}
        </div>
    </div>
    <script>{JS_SCRIPT}</script>
</body>
</html>"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path

    def _build_domains_html(self) -> str:
        """构建域HTML"""
        domains_html = []

        for domain, stats in sorted(self.domain_stats.items()):
            status_class = "system-error" if stats.system_errors > 0 else (
                "success" if stats.rate == 100 else ("warning" if stats.rate >= 80 else "error"))

            entities_html = []
            for entity in stats.entities:
                entity_class = "system-error" if entity.total_system_errors > 0 else (
                    "valid" if entity.is_valid else "invalid")
                status_badge_class = "status-success" if entity.is_valid else (
                    "status-system-error" if entity.total_system_errors > 0 else "status-error")

                status_text = "✅ 通过" if entity.is_valid else (
                    f"🔥 {entity.total_system_errors}个系统错误" if entity.total_system_errors > 0 else f"❌ {entity.total_errors}个验证错误")
                if entity.total_warnings > 0:
                    status_text += f" ⚠️ {entity.total_warnings}个警告"

                # 构建错误列表
                error_items = []
                for error in entity.system_errors:
                    error_items.append(
                        f'<div class="error-item" style="border-left-color: #ff4757;">🔥 系统错误: {error}</div>')
                for error in entity.schema_errors:
                    error_items.append(f'<div class="error-item">📋 Schema错误: {error}</div>')
                for error in entity.lint_errors:
                    error_items.append(f'<div class="error-item">🔍 Lint错误: {error}</div>')
                for warning in entity.schema_warnings:
                    error_items.append(f'<div class="warning-item">⚠️ Schema警告: {warning}</div>')
                for warning in entity.lint_warnings:
                    error_items.append(f'<div class="warning-item">⚠️ Lint警告: {warning}</div>')

                error_list = f'<div class="error-list">{"".join(error_items)}</div>' if error_items else ""

                entities_html.append(
                    f'''<div class="entity-item {entity_class}" data-status="{entity.status_type}" data-warnings="{'warning' if entity.total_warnings > 0 else ''}" data-valid="{str(entity.is_valid).lower()}" data-perfect="{str(entity.is_perfect).lower()}">
    <div class="entity-header">
        <div>
            <div class="entity-name">🔹 {entity.name} ({entity.kind})</div>
            <div class="entity-path">{entity.file_path}</div>
        </div>
        <div class="status-badge {status_badge_class}">{status_text}</div>
    </div>{error_list}
</div>''')

            domains_html.append(f'''<div class="domain-section">
    <div class="domain-header" onclick="toggleDomain('{domain}')">
        <h3>📁 {domain}</h3>
        <div class="domain-stats">
            <span>{stats.valid}/{stats.total} 通过</span>
            <span class="status-badge status-{status_class}">{stats.status}</span>
            <span class="toggle-arrow" id="arrow-{domain}">▶</span>
        </div>
    </div>
    <div class="domain-content" id="content-{domain}">
        <div class="entity-list">{"".join(entities_html)}</div>
    </div>
</div>''')

        return '\n'.join(domains_html)

    def print_detailed_results(self, quiet: bool = False):
        """打印详细结果"""
        if quiet: return

        # 统计摘要
        total = sum(s.total for s in self.domain_stats.values())
        valid = sum(s.valid for s in self.domain_stats.values())

        entities_with_system_errors = len([e for e in self.entity_reports if e.total_system_errors > 0])
        entities_with_validation_errors = len([e for e in self.entity_reports if e.total_errors > 0])
        entities_with_warnings = len([e for e in self.entity_reports if e.total_warnings > 0])

        print(f"\n📊 验证摘要:")
        print(f"- 总实体数: {total}")
        print(f"- 验证通过: {valid}")
        print(f"- 非预期错误: {entities_with_system_errors} 个")
        print(f"- 验证失败: {entities_with_validation_errors} 个")
        print(f"- 成功率: {(valid / max(total - entities_with_system_errors, 1) * 100):.1f}% (排除非预期错误)")

        print(f"\n📋 错误和警告统计:")
        print(f"- 非预期错误实体: {entities_with_system_errors} 个")
        print(f"- 验证错误实体: {entities_with_validation_errors} 个")
        print(f"- 警告实体: {entities_with_warnings} 个")
        print(f"- 总非预期错误: {sum(e.total_system_errors for e in self.entity_reports)} 个")
        print(f"- 总验证错误: {sum(e.total_errors for e in self.entity_reports)} 个")
        print(f"- 总警告数: {sum(e.total_warnings for e in self.entity_reports)} 个")

        # 详细问题列表
        system_error_entities = [e for e in self.entity_reports if e.total_system_errors > 0]
        validation_error_entities = [e for e in self.entity_reports if
                                     e.total_errors > 0 and e.total_system_errors == 0]
        warning_only_entities = [e for e in self.entity_reports if
                                 e.total_warnings > 0 and e.total_errors == 0 and e.total_system_errors == 0]

        if any([system_error_entities, validation_error_entities, warning_only_entities]):
            print(f"\n📝 详细问题列表:")

            if system_error_entities:
                print(f"\n🚨 非预期错误 ({len(system_error_entities)}个实体):")
                for entity in system_error_entities:
                    print(f"\n🔹 {entity.name} ({entity.file_path})")
                    for error in entity.system_errors:
                        print(f"     🔥 {error}")

            if validation_error_entities:
                print(f"\n❌ 验证错误 ({len(validation_error_entities)}个实体):")
                for entity in validation_error_entities:
                    print(f"\n🔹 {entity.name} ({entity.file_path})")

                    if entity.schema_errors:
                        print(f"   Schema错误 ({len(entity.schema_errors)}个):")
                        for error in entity.schema_errors:
                            print(f"     ❌ {error}")

                    if entity.lint_errors:
                        print(f"   Lint错误 ({len(entity.lint_errors)}个):")
                        for error in entity.lint_errors:
                            print(f"     ❌ {error}")

                    if entity.schema_warnings:
                        print(f"   Schema警告 ({len(entity.schema_warnings)}个):")
                        for warning in entity.schema_warnings:
                            print(f"     ⚠️ {warning}")

                    if entity.lint_warnings:
                        print(f"   Lint警告 ({len(entity.lint_warnings)}个):")
                        for warning in entity.lint_warnings:
                            print(f"     ⚠️ {warning}")

            if warning_only_entities:
                print(f"\n⚠️ 仅有警告 ({len(warning_only_entities)}个实体):")
                for entity in warning_only_entities:
                    print(f"\n🔹 {entity.name} ({entity.file_path})")

                    if entity.schema_warnings:
                        print(f"   Schema警告 ({len(entity.schema_warnings)}个):")
                        for warning in entity.schema_warnings:
                            print(f"     ⚠️ {warning}")

                    if entity.lint_warnings:
                        print(f"   Lint警告 ({len(entity.lint_warnings)}个):")
                        for warning in entity.lint_warnings:
                            print(f"     ⚠️ {warning}")


def main():
    parser = argparse.ArgumentParser(description="MModel Combined Validator")
    parser.add_argument('--definitions-dir', '-d', required=True, help='定义文件目录')
    parser.add_argument('--expanded-schemas-dir', default='expanded_schemas', help='展开schema目录')
    parser.add_argument('--base-schema-path', default='schemas/base.yaml', help='base.yaml路径')
    parser.add_argument('--rules-config', help='Lint规则配置')
    parser.add_argument('--aone-ci-only', action='store_true', help='仅输出aone-ci格式')
    parser.add_argument('--quiet', '-q', action='store_true', help='静默模式')
    parser.add_argument('--html-report', help='生成HTML验证报告，指定输出文件路径')
    parser.add_argument('--warnings-as-errors', action='store_true', help='将警告视为错误，导致脚本返回非0状态码')
    parser.add_argument('--focus-all', action='store_true', help='全量验证')

    args = parser.parse_args()

    try:
        validator = CombinedValidator(
            definitions_dir=args.definitions_dir,
            expanded_schemas_dir=args.expanded_schemas_dir,
            base_schema_path=args.base_schema_path,
            rules_config_path=args.rules_config,
            focus_all=args.focus_all
        )

        if not validator.run(quiet=args.aone_ci_only or args.quiet):
            sys.exit(1)

        # 输出结果
        aone_ci_lines = validator.output_aone_ci()

        if args.aone_ci_only:
            for line in aone_ci_lines:
                print(line)
        else:
            print(f"\n📤 AoneCI格式输出:")
            for line in aone_ci_lines:
                print(line)

            validator.print_detailed_results(quiet=args.quiet)

        # 生成HTML报告
        if args.html_report:
            try:
                html_path = validator.generate_html_report(args.html_report)
                if not args.aone_ci_only:
                    print(f"\n📄 HTML报告已生成: {html_path}")

                    # 在macOS上尝试自动打开浏览器
                    import platform
                    if platform.system() == "Darwin":
                        try:
                            import subprocess
                            subprocess.run(['open', html_path], check=False)
                            print(f"🌐 已在浏览器中打开报告")
                        except:
                            print(f"💡 请手动打开: {html_path}")
                    else:
                        print(f"💡 请在浏览器中打开: {html_path}")
            except Exception as html_error:
                print(f"⚠️ HTML报告生成失败: {html_error}")

        # 汇总验证结果，决定退出码
        total_system_errors = sum(e.total_system_errors for e in validator.entity_reports)
        total_validation_errors = sum(e.total_errors for e in validator.entity_reports)
        total_warnings = sum(e.total_warnings for e in validator.entity_reports)

        has_errors = total_system_errors > 0 or total_validation_errors > 0
        has_warnings = total_warnings > 0

        exit_code = 0
        if has_errors or (has_warnings and args.warnings_as_errors):
            exit_code = 1
            if not args.quiet and not args.aone_ci_only:
                print(f"\n📊 验证结果汇总:")
                if total_system_errors > 0:
                    print(f"   🚨 系统错误: {total_system_errors} 个")
                if total_validation_errors > 0:
                    print(f"   ❌ 验证错误: {total_validation_errors} 个")
                if total_warnings > 0:
                    status = "视为错误" if args.warnings_as_errors else "仅警告"
                    print(f"   ⚠️ 警告: {total_warnings} 个 ({status})")
        elif has_warnings:
            if not args.quiet and not args.aone_ci_only:
                print(f"\n📊 验证结果汇总:")
                print(f"   ⚠️ 警告: {total_warnings} 个 (使用--warnings-as-errors可将警告视为错误)")
        else:
            if not args.quiet and not args.aone_ci_only:
                print(f"\n✅ 验证完全通过，无任何问题！")

        if exit_code != 0:
            sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"❌ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 