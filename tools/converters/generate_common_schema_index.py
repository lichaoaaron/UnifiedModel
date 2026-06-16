#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
common_schema_doc HTML 文档索引生成器
按 Domain（第一级目录）、Group（第二级目录）、Kind（YAML中的kind字段）分组
从对应的 YAML 文件中读取 metadata 信息
"""

import os
import re
import json
import yaml
import argparse
from datetime import datetime
from pathlib import Path

def find_corresponding_yaml(html_file_path, common_schema_root):
    """根据 HTML 文件路径查找对应的 YAML 文件"""
    # 将 common_schema_doc 路径转换为 common_schema 路径
    html_path = Path(html_file_path)
    
    # 找到 common_schema_doc 目录的位置
    doc_dir_name = 'common_schema_doc'
    
    # 获取相对于 common_schema_doc 的路径
    path_parts = html_path.parts
    doc_dir_index = None
    for i, part in enumerate(path_parts):
        if part == doc_dir_name:
            doc_dir_index = i
            break
    
    if doc_dir_index is None:
        return None
    
    # 获取 common_schema_doc 之后的相对路径
    relative_parts = path_parts[doc_dir_index + 1:]
    relative_path = Path(*relative_parts) if relative_parts else Path('.')
    
    # 构建对应的 YAML 文件路径
    yaml_path = Path(common_schema_root) / 'common_schema' / relative_path.with_suffix('.yaml')
    
    if yaml_path.exists():
        return yaml_path
    return None

def extract_info_from_yaml(yaml_path):
    """从 YAML 文件中提取 kind 和 metadata 信息"""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        kind = data.get('kind', 'unknown')
        metadata = data.get('metadata', {})
        
        # 获取中文显示名称和描述
        display_name = metadata.get('display_name', {}).get('zh_cn', '未知文档')
        description = metadata.get('description', {}).get('zh_cn', 'MModel 系统文档')
        
        # 如果描述太长，截取前100个字符
        if len(description) > 100:
            description = description[:100] + '...'
        
        return kind, display_name, description
    except Exception as e:
        print(f"解析 YAML 文件 {yaml_path} 时出错: {e}")
        return 'unknown', '未知文档', 'MModel 系统文档'

def scan_html_files(base_dir, common_schema_root):
    """递归扫描 HTML 文件，按 Domain/Group/Kind 分类"""
    docs = {}
    base_path = Path(base_dir)
    
    for html_file in base_path.rglob('*.html'):
        # 跳过 index.html
        if html_file.name == 'index.html':
            continue
            
        rel_path = html_file.relative_to(base_path)
        parts = rel_path.parts
        
        if len(parts) < 3:
            # 必须至少有 Domain/Group/xxx.html
            continue
        
        domain = parts[0]
        group = parts[1]
        filename = str(rel_path)
        
        # 查找对应的 YAML 文件并提取信息
        yaml_path = find_corresponding_yaml(html_file, common_schema_root)
        if yaml_path:
            kind, title, description = extract_info_from_yaml(yaml_path)
        else:
            # 如果找不到 YAML 文件，尝试从 HTML 提取
            kind = 'unknown'
            title = html_file.stem.replace('_', ' ').title()
            description = 'MModel 系统文档'
        
        # 组织数据：三层结构 Domain -> Group -> Kind
        docs.setdefault(domain, {})
        docs[domain].setdefault(group, {})
        docs[domain][group].setdefault(kind, [])
        docs[domain][group][kind].append({
            'filename': filename,
            'title': title,
            'description': description,
            'name': html_file.stem  # 文件名（不含扩展名）
        })
    
    return docs

def get_kind_display_name(kind):
    """获取 kind 的中文显示名称"""
    kind_mapping = {
        'entity_set': '实体集',
        'trace_set': '链路集',
        'data_set': '数据集',
        'link': '关联',
        'storage': '存储',
        'metric_set': '指标集',
        'log_set': '日志集',
        'event_set': '事件集',
        'data_link': '数据关联',
        'entity_set_link': '实体关联',
        'storage_link': '存储关联',
        'sls_metricstore': 'SLS指标存储',
        'sls_logstore': 'SLS日志存储',
        'unknown': '未分类'
    }
    return kind_mapping.get(kind, kind)

def generate_index_html(docs, output_path):
    """生成 index.html 文件，按三级分类，并支持搜索"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    total_docs = sum(
        len(kind_docs) 
        for domain_data in docs.values() 
        for group_data in domain_data.values() 
        for kind_docs in group_data.values()
    )
    
    # 为了 JavaScript 搜索，我们需要将 docs 转换为 JSON
    docs_json = json.dumps(docs, ensure_ascii=False, indent=2)

    html_template = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Common Schema 文档索引</title>
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
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 20px auto;
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
            position: relative;
        }}
        .header h1 {{
            font-size: 2.2em;
            font-weight: 700;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }}
        .header p {{
            font-size: 1em;
            opacity: 0.9;
        }}
        .nav-button {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 10px 20px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9em;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }}
        .nav-button:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            color: white;
            text-decoration: none;
        }}
        .nav-button:active {{
            transform: translateY(0px);
        }}
        .main-content {{
            padding: 25px;
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
            right: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: #aaa;
            font-size: 16px;
        }}
        .stats-bar {{
            text-align: center;
            color: #555;
            margin-bottom: 25px;
            font-size: 0.95em;
            background-color: #f0f3f5;
            padding: 10px;
            border-radius: 8px;
        }}
        .domain-block {{
            margin-bottom: 30px;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            overflow: hidden;
            background-color: #fff;
        }}
        .domain-title {{
            font-size: 1.4em;
            font-weight: bold;
            color: white;
            background: linear-gradient(135deg, #5a67d8 0%, #8c52ff 100%);
            padding: 12px 18px;
            border-bottom: 1px solid #d1d5db;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .domain-content {{
            padding: 0 0 10px 0;
        }}
        .group-block {{
            margin-bottom: 0;
            padding: 0 18px 0px 18px;
        }}
        .group-block:last-child {{
            margin-bottom: 0px;
        }}
        .group-title {{
            font-size: 1.1em;
            font-weight: 600;
            color: #2d3a4b;
            margin-top: 15px;
            margin-bottom: 10px;
            padding: 8px 0px 8px 0;
            border-bottom: 1px dashed #eee;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .group-content {{
            /* padding-left: 10px; */
        }}
        .kind-block {{
            margin-bottom: 10px;
            padding: 0 10px;
        }}
        .kind-title {{
            font-size: 1em;
            font-weight: 500;
            color: #4a5568;
            margin-top: 10px;
            margin-bottom: 8px;
            padding: 6px 10px;
            background-color: #f7fafc;
            border-left: 3px solid #667eea;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .kind-content {{
            padding-left: 10px;
        }}
        .toggle-icon {{
            font-size: 0.8em;
            margin-right: 8px;
            transition: transform 0.2s ease-in-out;
        }}
        .collapsed .toggle-icon {{
            transform: rotate(-90deg);
        }}
        .domain-content.collapsed, .group-content.collapsed, .kind-content.collapsed {{
            display: none;
        }}
        .doc-list {{
            list-style: none;
            padding-left: 0;
        }}
        .doc-item {{
            background: #f9fafd;
            border: 1px solid #e6e9ed;
            border-radius: 8px;
            margin-bottom: 10px;
            padding: 14px 20px;
            transition: box-shadow 0.2s, transform 0.2s;
            display: block;
        }}
        .doc-item:hover {{
            box-shadow: 0 4px 12px rgba(102,126,234,0.15);
            transform: translateY(-2px);
            border-color: #b3c1ff;
        }}
        .doc-title-text {{
            font-weight: 600;
            color: #333;
            font-size: 1.05em;
            margin-bottom: 4px;
        }}
        .doc-desc {{
            color: #555;
            font-size: 0.9em;
            margin-bottom: 8px;
            line-height: 1.5;
        }}
        .doc-link {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9em;
            display: inline-block;
        }}
        .doc-link:hover {{
            text-decoration: underline;
        }}
        .doc-name {{
            color: #999;
            font-size: 0.85em;
            font-family: 'Consolas', 'Monaco', monospace;
        }}
        .no-results {{
            text-align: center;
            padding: 40px 20px;
            color: #666;
            display: none;
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
            margin-top: 20px;
        }}
        @media (max-width: 700px) {{
            .container {{ padding: 10px; margin: 10px; }}
            .header {{ padding: 20px; }}
            .header h1 {{ font-size: 1.8em; }}
            .main-content {{ padding: 15px; }}
            .domain-title {{ font-size: 1.2em; padding: 10px 15px; }}
            .group-title {{ font-size: 1em; }}
            .kind-title {{ font-size: 0.95em; }}
            .doc-item {{ padding: 12px 15px; }}
            .nav-button {{
                position: static;
                display: inline-block;
                margin-top: 15px;
                padding: 8px 16px;
                font-size: 0.85em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 Common Schema 文档索引</h1>
            <p>Common Schema 核心定义与规范说明</p>
            <a href="validation_report/index.html" class="nav-button" >校验结果</a>
        </div>
        <div class="main-content">
            <div class="stats-bar">
                文档最后更新于 {current_time}，共 <span id="totalDocsCount">{total_docs}</span> 个文档。
            </div>
            <div class="search-box">
                <input type="text" class="search-input" placeholder="搜索文档标题、描述或文件名..." id="searchInput">
                <span class="search-icon">🔍</span>
            </div>
            <div id="docsContainer">
                {_generate_html_content(docs)}
            </div>
            <div class="no-results" id="noResults">
                <div class="no-results-icon">📄</div>
                <h3>未找到匹配的文档</h3>
                <p>请尝试其他搜索关键词。</p>
            </div>
        </div>
        <div class="footer">
            <p>&copy; {datetime.now().year} MModel Common Schema Documentation. </p>
            <p>使用 <code>python scripts/converters/generate_common_schema_index.py</code> 重新生成此页面</p>
        </div>
    </div>

    <script>
        const allDocsData = {docs_json};
        const searchInput = document.getElementById('searchInput');
        const docsContainer = document.getElementById('docsContainer');
        const noResultsDiv = document.getElementById('noResults');
        const totalDocsCountSpan = document.getElementById('totalDocsCount');

        const kindDisplayNames = {{
            'entity_set': '实体集',
            'trace_set': '链路集',
            'data_set': '数据集',
            'link': '关联',
            'storage': '存储',
            'metric_set': '指标集',
            'log_set': '日志集',
            'event_set': '事件集',
            'data_link': '数据关联',
            'entity_set_link': '实体关联',
            'storage_link': '存储关联',
            'sls_metricstore': 'SLS指标存储',
            'sls_logstore': 'SLS日志存储',
            'unknown': '未分类'
        }};

        function generateDocItemHTML(doc) {{
            return `<li class="doc-item">
                <div class="doc-title-text">${{doc.title}}</div>
                <div class="doc-desc">${{doc.description}}</div>
                <div class="doc-name">${{doc.name}}</div>
                <a class="doc-link" href="${{doc.filename}}" target="_blank">查看文档 →</a>
            </li>`;
        }}

        function generateKindHTML(kindName, kindDocs, isInitiallyCollapsed = true) {{
            if (kindDocs.length === 0) return '';
            let itemsHTML = kindDocs.map(doc => generateDocItemHTML(doc)).join('');
            const collapsedClass = isInitiallyCollapsed ? 'collapsed' : '';
            const displayName = kindDisplayNames[kindName] || kindName;
            return `<div class="kind-block">
                <div class="kind-title clickable-header ${{collapsedClass}}">
                    <span>${{displayName}}</span>
                    <span class="toggle-icon">▼</span>
                </div>
                <div class="kind-content ${{collapsedClass}}">
                    <ul class="doc-list">${{itemsHTML}}</ul>
                </div>
            </div>`;
        }}

        function generateGroupHTML(groupName, groupData, domainName, isInitiallyCollapsed = true) {{
            let hasVisibleChildrenInSearch = false;
            if (searchInput.value.trim() !== '') {{
                Object.keys(groupData).forEach(kindName => {{
                    if (groupData[kindName] && groupData[kindName].length > 0) {{
                        hasVisibleChildrenInSearch = true;
                    }}
                }});
            }}
            const collapsedClass = isInitiallyCollapsed && !hasVisibleChildrenInSearch ? 'collapsed' : '';

            let kindsHTML = Object.keys(groupData).sort().map(kindName => {{
                const shouldKindCollapse = isInitiallyCollapsed && !hasVisibleChildrenInSearch;
                return generateKindHTML(kindName, groupData[kindName], shouldKindCollapse);
            }}).join('');
            
            if (kindsHTML.trim() === '') return '';

            return `<div class="group-block">
                <div class="group-title clickable-header ${{collapsedClass}}">
                    <span>Group: ${{groupName}}</span>
                    <span class="toggle-icon">▼</span>
                </div>
                <div class="group-content ${{collapsedClass}}">
                    ${{kindsHTML}}
                </div>
            </div>`;
        }}

        function generateDomainHTML(domainName, domainData, isInitiallyCollapsed = true) {{
            let hasVisibleChildrenInSearch = false;
            if (searchInput.value.trim() !== '') {{
                Object.keys(domainData).forEach(groupName => {{
                    Object.keys(domainData[groupName]).forEach(kindName => {{
                        if (domainData[groupName][kindName] && domainData[groupName][kindName].length > 0) {{
                            hasVisibleChildrenInSearch = true;
                        }}
                    }});
                }});
            }}
            const collapsedClassDomain = isInitiallyCollapsed && !hasVisibleChildrenInSearch ? 'collapsed' : '';

            let groupsHTML = Object.keys(domainData).sort().map(groupName => {{
                const shouldGroupCollapse = isInitiallyCollapsed && !hasVisibleChildrenInSearch;
                return generateGroupHTML(groupName, domainData[groupName], domainName, shouldGroupCollapse);
            }}).join('');
            
            if (groupsHTML.trim() === '') return '';

            return `<div class="domain-block">
                <div class="domain-title clickable-header ${{collapsedClassDomain}}">
                    <span>Domain: ${{domainName}}</span>
                    <span class="toggle-icon">▼</span>
                </div>
                <div class="domain-content ${{collapsedClassDomain}}">
                    ${{groupsHTML}}
                </div>
            </div>`;
        }}
        
        function renderDocs(docsToRender, isInitialLoad = false) {{
            let content = '';
            let currentTotalDocs = 0;
            Object.keys(docsToRender).sort().forEach(domainName => {{
                const domainData = docsToRender[domainName];
                let domainHasVisibleDocs = false;
                Object.keys(domainData).forEach(groupName => {{
                    Object.keys(domainData[groupName]).forEach(kindName => {{
                        if(domainData[groupName][kindName] && domainData[groupName][kindName].length > 0) {{
                            domainHasVisibleDocs = true;
                            currentTotalDocs += domainData[groupName][kindName].length;
                        }}
                    }});
                }});

                if(domainHasVisibleDocs) {{
                    const shouldDomainCollapse = isInitialLoad || searchInput.value.trim() === '';
                    content += generateDomainHTML(domainName, domainData, shouldDomainCollapse);
                }}
            }});
            
            docsContainer.innerHTML = content;
            totalDocsCountSpan.textContent = currentTotalDocs;

            if (currentTotalDocs === 0 && searchInput.value.trim() !== '') {{
                noResultsDiv.style.display = 'block';
                docsContainer.innerHTML = '';
            }} else if (content.trim() === '' && Object.keys(allDocsData).length > 0 && searchInput.value.trim() !== '') {{
                noResultsDiv.style.display = 'block';
                docsContainer.innerHTML = '';
            }} else if (Object.keys(allDocsData).length === 0) {{
                noResultsDiv.style.display = 'block';
                noResultsDiv.innerHTML = '<div class="no-results-icon">🤷</div><h3>未找到任何文档</h3><p>common_schema_doc 目录中似乎没有 HTML 文件。</p>';
                docsContainer.innerHTML = '';
            }} else {{
                noResultsDiv.style.display = 'none';
            }}
        }}

        searchInput.addEventListener('input', function() {{
            const searchTerm = this.value.toLowerCase().trim();
            if (!searchTerm) {{
                renderDocs(allDocsData, true);
                return;
            }}

            const filteredDocs = {{}};
            Object.keys(allDocsData).forEach(domainName => {{
                const domainData = allDocsData[domainName];
                const newDomainData = {{}};
                let domainHasResults = false;

                Object.keys(domainData).forEach(groupName => {{
                    const groupData = domainData[groupName];
                    const newGroupData = {{}};
                    let groupHasResults = false;

                    Object.keys(groupData).forEach(kindName => {{
                        const kindDocs = groupData[kindName];
                        const newKindDocs = kindDocs.filter(doc => 
                            doc.title.toLowerCase().includes(searchTerm) ||
                            doc.description.toLowerCase().includes(searchTerm) ||
                            doc.filename.toLowerCase().includes(searchTerm) ||
                            doc.name.toLowerCase().includes(searchTerm)
                        );
                        if (newKindDocs.length > 0) {{
                            newGroupData[kindName] = newKindDocs;
                            groupHasResults = true;
                        }}
                    }});

                    if (groupHasResults) {{
                        newDomainData[groupName] = newGroupData;
                        domainHasResults = true;
                    }}
                }});

                if (domainHasResults) {{
                    filteredDocs[domainName] = newDomainData;
                }}
            }});
            renderDocs(filteredDocs, false);
        }});

        // Event delegation for expand/collapse
        docsContainer.addEventListener('click', function(event) {{
            const header = event.target.closest('.clickable-header');
            if (header) {{
                const contentElement = header.nextElementSibling;
                if (contentElement) {{
                    contentElement.classList.toggle('collapsed');
                    header.classList.toggle('collapsed');
                }}
            }}
        }});

        // Initial render
        renderDocs(allDocsData, true);
    </script>
</body>
</html>'''
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)

# Helper function to be used by generate_index_html
def _generate_html_content(docs):
    """生成初始 HTML 内容，三层结构：Domain -> Group -> Kind"""
    html_content = []
    for domain in sorted(docs.keys()):
        domain_data = docs[domain]
        if not any(group_data for group_data in domain_data.values()): continue

        html_content.append('<div class="domain-block">')
        html_content.append(f'  <div class="domain-title clickable-header collapsed"><span>Domain: {domain}</span><span class="toggle-icon">▼</span></div>')
        html_content.append('  <div class="domain-content collapsed">') 

        for group in sorted(domain_data.keys()):
            group_data = domain_data[group]
            if not any(kind_docs for kind_docs in group_data.values()): continue

            html_content.append('    <div class="group-block">')
            html_content.append(f'      <div class="group-title clickable-header collapsed"><span>Group: {group}</span><span class="toggle-icon">▼</span></div>')
            html_content.append('      <div class="group-content collapsed">')
            
            for kind in sorted(group_data.keys()):
                kind_docs = group_data[kind]
                if not kind_docs: continue
                
                kind_display = get_kind_display_name(kind)
                html_content.append('        <div class="kind-block">')
                html_content.append(f'          <div class="kind-title clickable-header collapsed"><span>{kind_display}</span><span class="toggle-icon">▼</span></div>')
                html_content.append('          <div class="kind-content collapsed">')
                html_content.append('            <ul class="doc-list">')
                
                for doc in sorted(kind_docs, key=lambda d: d['title']):
                    html_content.append('              <li class="doc-item">')
                    html_content.append(f'                <div class="doc-title-text">{doc["title"]}</div>')
                    html_content.append(f'                <div class="doc-desc">{doc["description"]}</div>')
                    html_content.append(f'                <div class="doc-name">{doc["name"]}</div>')
                    html_content.append(f'                <a class="doc-link" href="{doc["filename"]}" target="_blank">查看文档 →</a>')
                    html_content.append('              </li>')
                
                html_content.append('            </ul>')
                html_content.append('          </div>')
                html_content.append('        </div>')
            
            html_content.append('      </div>')
            html_content.append('    </div>')
        
        html_content.append('  </div>')
        html_content.append('</div>')
    return "\n".join(html_content)

def main():
    parser = argparse.ArgumentParser(description='生成 Common Schema 文档索引')
    parser.add_argument('--doc-dir', type=str, 
                      help='common_schema_doc 目录路径，默认为项目根目录下的 common_schema_doc')
    parser.add_argument('--schema-dir', type=str,
                      help='common_schema 目录路径，默认为项目根目录')
    args = parser.parse_args()

    # 确定项目根目录
    project_root = Path(__file__).parent / '..' / '..'
    
    if args.doc_dir:
        base_dir = Path(args.doc_dir)
    else:
        base_dir = project_root / 'common_schema_doc'

    if args.schema_dir:
        common_schema_root = Path(args.schema_dir)
    else:
        common_schema_root = project_root

    if not base_dir.exists():
        print(f"❌ 目录不存在: {base_dir}")
        return

    output_path = base_dir / 'index.html'
    print(f"🔍 扫描 {base_dir} 下 HTML 文档...")
    print(f"📖 从 {common_schema_root / 'common_schema'} 读取 YAML 元数据...")
    
    docs = scan_html_files(base_dir, common_schema_root)
    
    if not docs:
        print("❌ 未找到任何 HTML 文档")
        return
    
    total_count = sum(
        len(kind_docs) 
        for domain in docs.values() 
        for group in domain.values() 
        for kind_docs in group.values()
    )
    print(f"📄 找到 {total_count} 个文档")
    print(f"📝 生成索引文件: {output_path}")
    
    generate_index_html(docs, output_path)
    
    print("✅ 索引文件生成完成!")
    print(f"🌐 访问: file://{output_path.absolute()}")

if __name__ == '__main__':
    main() 