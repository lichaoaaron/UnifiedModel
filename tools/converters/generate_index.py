#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MModel HTML 文档索引生成器
自动扫描 docs/html 目录下的 HTML 文件并生成 index.html
支持多语言版本：mixed(混合)、cn(中文)、en(英文)
"""

import os
import re
import json
import argparse
from datetime import datetime
from pathlib import Path

def get_ui_text(key, language='mixed'):
    """获取UI界面文本"""
    ui_texts = {
        'document_center': {
            'mixed': '📚 MModel 文档中心',
            'cn': '📚 MModel 文档中心',
            'en': '📚 MModel Documentation Center'
        },
        'explore_description': {
            'mixed': '探索 MModel 系统的完整文档和规范',
            'cn': '探索 MModel 系统的完整文档和规范',
            'en': 'Explore complete documentation and specifications for MModel system'
        },
        'auto_generated': {
            'mixed': 'ℹ️ 本页面自动生成于 {time}，包含 {count} 个文档，总大小 {size} KB',
            'cn': 'ℹ️ 本页面自动生成于 {time}，包含 {count} 个文档，总大小 {size} KB',
            'en': 'ℹ️ This page was automatically generated at {time}, containing {count} documents, total size {size} KB'
        },
        'search_placeholder': {
            'mixed': '搜索文档...',
            'cn': '搜索文档...',
            'en': 'Search documents...'
        },
        'total_docs': {
            'mixed': '文档总数',
            'cn': '文档总数',
            'en': 'Total Documents'
        },
        'total_size': {
            'mixed': '总大小 (KB)',
            'cn': '总大小 (KB)',
            'en': 'Total Size (KB)'
        },
        'view_button': {
            'mixed': '查看 →',
            'cn': '查看 →',
            'en': 'View →'
        },
        'no_results_title': {
            'mixed': '未找到匹配的文档',
            'cn': '未找到匹配的文档',
            'en': 'No matching documents found'
        },
        'no_results_desc': {
            'mixed': '请尝试使用不同的关键词搜索',
            'cn': '请尝试使用不同的关键词搜索',
            'en': 'Please try searching with different keywords'
        },
        'copyright': {
            'mixed': '&copy; 2024 MModel Documentation Center. 自动生成于 {time}',
            'cn': '&copy; 2024 MModel 文档中心. 自动生成于 {time}',
            'en': '&copy; 2024 MModel Documentation Center. Auto-generated at {time}'
        },
        'regenerate_tip': {
            'mixed': '使用 <code>python scripts/converters/generate_index.py</code> 重新生成此页面',
            'cn': '使用 <code>python scripts/converters/generate_index.py</code> 重新生成此页面',
            'en': 'Use <code>python scripts/converters/generate_index.py</code> to regenerate this page'
        },
        'category_entity': {
            'mixed': '实体',
            'cn': '实体',
            'en': 'Entities'
        },
        'category_telemetry': {
            'mixed': '观测数据',
            'cn': '观测数据',
            'en': 'Telemetry Data'
        },
        'category_storage': {
            'mixed': '存储系统',
            'cn': '存储系统',
            'en': 'Storage Systems'
        },
        'category_connection': {
            'mixed': 'Link 连接',
            'cn': 'Link 连接',
            'en': 'Link Connections'
        },
        'category_general': {
            'mixed': '未分类',
            'cn': '未分类',
            'en': 'General'
        },
        'category_runbook': {
            'mixed': '操作手册',
            'cn': '操作手册',
            'en': 'Runbooks'
        },
        'subtitle_telemetry': {
            'mixed': '观测数据',
            'cn': '观测数据',
            'en': 'Telemetry Data'
        },
        'subtitle_connection': {
            'mixed': 'Link',
            'cn': 'Link',
            'en': 'Link'
        },
        'subtitle_entity': {
            'mixed': '实体',
            'cn': '实体',
            'en': 'Entity'
        },
        'subtitle_storage': {
            'mixed': '存储',
            'cn': '存储',
            'en': 'Storage'
        },
        'subtitle_general': {
            'mixed': '通用',
            'cn': '通用',
            'en': 'General'
        },
        'subtitle_runbook': {
            'mixed': '操作手册',
            'cn': '操作手册',
            'en': 'Runbook'
        },
        'unknown_doc': {
            'mixed': '未知文档',
            'cn': '未知文档',
            'en': 'Unknown Document'
        },
        'default_description': {
            'mixed': 'MModel 系统文档',
            'cn': 'MModel 系统文档',
            'en': 'MModel System Documentation'
        }
    }

    text_dict = ui_texts.get(key, {})
    return text_dict.get(language, text_dict.get('mixed', key))

def extract_title_from_html(file_path, language='mixed'):
    """从 HTML 文件中提取标题信息"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取页面标题
        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
        title = title_match.group(1) if title_match else get_ui_text('unknown_doc', language)

        # 提取主标题
        main_title_match = re.search(r'<h1[^>]*class="main-title"[^>]*>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
        if main_title_match:
            main_title = re.sub(r'<[^>]+>', '', main_title_match.group(1)).strip()
        else:
            # 根据语言模式清理标题
            title_suffixes = [
                ' - MModel Documentation',
                ' - MModel 文档'
            ]
            main_title = title
            for suffix in title_suffixes:
                main_title = main_title.replace(suffix, '')

        # 提取描述
        desc_match = re.search(r'<p class="description-text">(.*?)</p>', content, re.IGNORECASE)
        description = desc_match.group(1) if desc_match else get_ui_text('default_description', language)

        return main_title, description

    except Exception as e:
        print(f"解析文件 {file_path} 时出错: {e}")
        return get_ui_text('unknown_doc', language), get_ui_text('default_description', language)

def categorize_doc(filename, language='mixed'):
    """根据文件名推断文档类别"""
    filename_lower = filename.lower()

    if 'link' in filename_lower:
        return 'connection', '🔗'
    elif 'runbook' in filename_lower:
        return 'runbook', '📚'
    elif 'entity_set' in filename_lower:
        return 'entity', '🏗️'
    elif 'storage' in filename_lower or 'store' in filename_lower or 'prometheus' in filename_lower or 'entity_source' in filename_lower:
        return 'storage', '💾'
    elif 'event' in filename_lower or 'log' in filename_lower or 'metric' in filename_lower or 'trace' in filename_lower or 'profile' in filename_lower or 'telemetry' in filename_lower or 'data' in filename_lower:
        return 'telemetry', '📊'
    else:
        return 'general', '📄'

def get_file_size_kb(file_path):
    """获取文件大小（KB）"""
    try:
        size_bytes = os.path.getsize(file_path)
        return round(size_bytes / 1024)
    except:
        return 0

def scan_html_files(html_dir, language='mixed'):
    """扫描 HTML 目录并收集文档信息"""
    docs = []
    html_path = Path(html_dir)

    if not html_path.exists():
        print(f"目录 {html_dir} 不存在")
        return docs

    for file_path in html_path.glob('*.html'):
        if file_path.name == 'index.html':
            continue  # 跳过索引文件本身

        filename = file_path.name
        title, description = extract_title_from_html(file_path, language)
        category, icon = categorize_doc(filename, language)
        size_kb = get_file_size_kb(file_path)

        # 生成副标题
        subtitle_map = {
            'telemetry': get_ui_text('subtitle_telemetry', language),
            'connection': get_ui_text('subtitle_connection', language),
            'entity': get_ui_text('subtitle_entity', language),
            'storage': get_ui_text('subtitle_storage', language),
            'runbook': get_ui_text('subtitle_runbook', language),
            'general': get_ui_text('subtitle_general', language)
        }
        subtitle = subtitle_map.get(category, get_ui_text('subtitle_general', language))

        docs.append({
            'filename': filename,
            'title': title,
            'subtitle': subtitle,
            'description': description,
            'icon': icon,
            'size': size_kb,
            'category': category
        })

    # 按类型优先排序，然后按文件名排序
    category_order = {
        'entity': 1,
        'telemetry': 2,
        'connection': 3,
        'storage': 4,
        'runbook': 5,
        'general': 6
    }
    docs.sort(key=lambda x: (category_order.get(x['category'], 999), x['filename']))
    return docs

def generate_index_html(docs, output_path, language='mixed'):
    """生成 index.html 文件"""

    total_size = sum(doc['size'] for doc in docs)
    total_docs = len(docs)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 生成 JavaScript 文档数据
    docs_js = json.dumps(docs, ensure_ascii=False, indent=12)

    # 获取UI文本
    document_center = get_ui_text('document_center', language)
    explore_description = get_ui_text('explore_description', language)
    auto_generated_text = get_ui_text('auto_generated', language).format(
        time=current_time, count=total_docs, size=total_size
    )
    search_placeholder = get_ui_text('search_placeholder', language)
    total_docs_text = get_ui_text('total_docs', language)
    total_size_text = get_ui_text('total_size', language)
    view_button = get_ui_text('view_button', language)
    no_results_title = get_ui_text('no_results_title', language)
    no_results_desc = get_ui_text('no_results_desc', language)
    copyright_text = get_ui_text('copyright', language).format(time=current_time)
    regenerate_tip = get_ui_text('regenerate_tip', language)

    # 设置语言
    lang_code = 'zh-CN' if language in ['mixed', 'cn'] else 'en'

    html_template = f'''<!DOCTYPE html>
<html lang="{lang_code}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{document_center}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }}

        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        .main-content {{
            padding: 30px;
        }}

        .search-box {{
            margin-bottom: 25px;
            position: relative;
        }}

        .search-input {{
            width: 100%;
            padding: 12px 45px 12px 15px;
            font-size: 14px;
            border: 2px solid #e1e4e8;
            border-radius: 8px;
            outline: none;
            transition: all 0.3s ease;
        }}

        .search-input:focus {{
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .search-icon {{
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: #666;
            font-size: 16px;
        }}

        .stats {{
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            justify-content: center;
        }}

        .stat-card {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(240, 147, 251, 0.3);
            min-width: 120px;
        }}

        .stat-number {{
            font-size: 1.8em;
            font-weight: 700;
            margin-bottom: 2px;
        }}

        .stat-label {{
            font-size: 0.85em;
            opacity: 0.9;
        }}

        .docs-list {{
            background: #f8f9fa;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #e1e4e8;
        }}

        .category-section {{
            margin-bottom: 0;
        }}

        .category-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 20px;
            font-weight: 600;
            font-size: 1.1em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .category-icon {{
            font-size: 1.2em;
        }}

        .doc-item {{
            background: white;
            border-bottom: 1px solid #e1e4e8;
            padding: 15px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: all 0.2s ease;
        }}

        .doc-item:hover {{
            background: #f1f8ff;
            border-left: 4px solid #667eea;
            padding-left: 16px;
        }}

        .doc-item:last-child {{
            border-bottom: none;
        }}

        .doc-info {{
            flex: 1;
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .doc-icon {{
            font-size: 1.5em;
            width: 40px;
            text-align: center;
        }}

        .doc-details {{
            flex: 1;
        }}

        .doc-title {{
            font-size: 1.1em;
            font-weight: 600;
            color: #333;
            margin-bottom: 3px;
        }}

        .doc-description {{
            font-size: 0.9em;
            color: #666;
            line-height: 1.4;
        }}

        .doc-meta {{
            display: flex;
            align-items: center;
            gap: 15px;
            font-size: 0.85em;
            color: #888;
        }}

        .doc-size {{
            background: #e3f2fd;
            color: #1976d2;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 500;
        }}

        .doc-link {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
            font-size: 0.9em;
            transition: all 0.3s ease;
        }}

        .doc-link:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}

        .no-results {{
            text-align: center;
            padding: 40px 20px;
            color: #666;
        }}

        .no-results-icon {{
            font-size: 3em;
            margin-bottom: 15px;
            opacity: 0.3;
        }}

        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e1e4e8;
            font-size: 0.9em;
        }}

        .update-info {{
            background: #e3f2fd;
            color: #1976d2;
            padding: 8px 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 0.9em;
            text-align: center;
        }}

        @media (max-width: 768px) {{
            .header {{
                padding: 20px;
            }}

            .header h1 {{
                font-size: 2em;
            }}

            .main-content {{
                padding: 20px;
            }}

            .stats {{
                flex-direction: column;
                align-items: center;
            }}

            .doc-item {{
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }}

            .doc-info {{
                width: 100%;
            }}

            .doc-meta {{
                justify-content: space-between;
                width: 100%;
            }}
        }}

        .hidden {{
            display: none !important;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{document_center}</h1>
            <p>{explore_description}</p>
        </div>

        <div class="main-content">
            <div class="update-info">
                {auto_generated_text}
            </div>

            <div class="search-box">
                <input type="text" class="search-input" placeholder="{search_placeholder}" id="searchInput">
                <span class="search-icon">🔍</span>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="totalDocs">{total_docs}</div>
                    <div class="stat-label">{total_docs_text}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="totalSize">{total_size}</div>
                    <div class="stat-label">{total_size_text}</div>
                </div>
            </div>

            <div class="docs-list" id="docsList">
                <!-- 文档列表将通过 JavaScript 动态生成 -->
            </div>

            <div class="no-results hidden" id="noResults">
                <div class="no-results-icon">📄</div>
                <h3>{no_results_title}</h3>
                <p>{no_results_desc}</p>
            </div>
        </div>

        <div class="footer">
            <p>{copyright_text}</p>
            <p style="margin-top: 8px; font-size: 0.8em; opacity: 0.7;">
                {regenerate_tip}
            </p>
        </div>
    </div>

    <script>
        // 文档数据配置（自动生成）
        const docs = {docs_js};

        // 按类别分组文档
        function groupDocsByCategory(docsToGroup) {{
            const grouped = {{}};
            docsToGroup.forEach(doc => {{
                if (!grouped[doc.category]) {{
                    grouped[doc.category] = [];
                }}
                grouped[doc.category].push(doc);
            }});
            return grouped;
        }}

        // 渲染文档列表
        function renderDocs(docsToRender = docs) {{
            const docsList = document.getElementById('docsList');
            const noResults = document.getElementById('noResults');

            if (docsToRender.length === 0) {{
                docsList.innerHTML = '';
                noResults.classList.remove('hidden');
                return;
            }}

            noResults.classList.add('hidden');

            const groupedDocs = groupDocsByCategory(docsToRender);
            const categoryOrder = ['entity', 'telemetry', 'connection', 'storage', 'runbook', 'general'];

            let html = '';

            categoryOrder.forEach(category => {{
                if (groupedDocs[category] && groupedDocs[category].length > 0) {{
                    const categoryName = getCategoryName(category);
                    const categoryIcon = groupedDocs[category][0].icon;

                    html += `
                        <div class="category-section">
                            <div class="category-header">
                                <span class="category-icon">${{categoryIcon}}</span>
                                <span>${{categoryName}} (${{groupedDocs[category].length}})</span>
                            </div>
                    `;

                    groupedDocs[category].forEach(doc => {{
                        html += `
                            <div class="doc-item">
                                <div class="doc-info">
                                    <div class="doc-icon">${{doc.icon}}</div>
                                    <div class="doc-details">
                                        <div class="doc-title">${{doc.title}}</div>
                                        <div class="doc-description">${{doc.description}}</div>
                                    </div>
                                </div>
                                <div class="doc-meta">
                                    <span class="doc-size">${{doc.size}} KB</span>
                                    <a href="${{doc.filename}}" class="doc-link">{view_button}</a>
                                </div>
                            </div>
                        `;
                    }});

                    html += '</div>';
                }}
            }});

            docsList.innerHTML = html;
        }}

        // 获取类别名称
        function getCategoryName(category) {{
            const categoryNames = {{
                'entity': '{get_ui_text("category_entity", language)}',
                'telemetry': '{get_ui_text("category_telemetry", language)}',
                'storage': '{get_ui_text("category_storage", language)}',
                'connection': '{get_ui_text("category_connection", language)}',
                'runbook': '{get_ui_text("category_runbook", language)}',
                'general': '{get_ui_text("category_general", language)}'
            }};
            return categoryNames[category] || category;
        }}

        // 搜索功能
        function setupSearch() {{
            const searchInput = document.getElementById('searchInput');

            searchInput.addEventListener('input', (e) => {{
                const searchTerm = e.target.value.toLowerCase().trim();

                if (searchTerm === '') {{
                    renderDocs(docs);
                    return;
                }}

                const filteredDocs = docs.filter(doc =>
                    doc.title.toLowerCase().includes(searchTerm) ||
                    doc.subtitle.toLowerCase().includes(searchTerm) ||
                    doc.description.toLowerCase().includes(searchTerm) ||
                    getCategoryName(doc.category).toLowerCase().includes(searchTerm)
                );

                renderDocs(filteredDocs);
            }});
        }}

        // 初始化
        document.addEventListener('DOMContentLoaded', () => {{
            renderDocs();
            setupSearch();
        }});
    </script>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='生成 MModel HTML 文档索引')
    parser.add_argument('-l', '--language', choices=['mixed', 'cn', 'en'], default='mixed',
                       help='输出语言模式: mixed(中英文), cn(中文), en(英文), 默认为 mixed')
    parser.add_argument('-d', '--html-dir', help='HTML文档目录路径（可选）')
    parser.add_argument('-o', '--output', help='输出文件路径（可选）')

    args = parser.parse_args()

    # 获取脚本所在目录
    script_dir = Path(__file__).parent

    # 根据语言确定目录名
    if args.html_dir:
        html_dir = Path(args.html_dir)
    else:
        if args.language == 'cn':
            html_dir = script_dir / '..' / '..' / 'docs' / 'html_cn'
        elif args.language == 'en':
            html_dir = script_dir / '..' / '..' / 'docs' / 'html_en'
        else:  # mixed
            html_dir = script_dir / '..' / '..' / 'docs' / 'html'

    # 确定输出文件路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = html_dir / 'index.html'

    print(f"🔍 扫描 HTML 文档 ({args.language} 模式)...")
    docs = scan_html_files(html_dir, args.language)

    if not docs:
        print("❌ 未找到任何 HTML 文档")
        return

    print(f"📄 找到 {len(docs)} 个文档:")
    for doc in docs:
        print(f"  - {doc['filename']} ({doc['size']} KB)")

    print(f"📝 生成索引文件: {output_path}")
    generate_index_html(docs, output_path, args.language)

    print("✅ 索引文件生成完成!")
    print(f"🌐 访问: file://{output_path.absolute()}")
    print(f"🌐 语言模式: {args.language}")

if __name__ == '__main__':
    main() 