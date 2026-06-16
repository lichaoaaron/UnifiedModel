#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YAML to HTML Documentation Generator (重构版)
将 expanded.yaml 文件转换为美观的 HTML 文档格式
使用分离的配置文件和模板，提高可维护性
"""

import yaml
import argparse
import os
from typing import Dict, Any, List
import json
import sys
# 添加config目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config"))
from config import *


class YamlToHtmlConverter:
    def __init__(self, language='mixed'):
        """
        初始化转换器
        Args:
            language: 语言模式，支持 'mixed'(中英文), 'cn'(中文), 'en'(英文)
        """
        self.output = []
        self.toc = []  # 目录
        self.current_level = 0
        self.property_index = {}  # 属性索引，用于生成概览
        self.language = language
    
    def _get_localized_text(self, text_obj: Any, fallback: str = '') -> str:
        """
        根据语言模式获取本地化文本
        Args:
            text_obj: 文本对象，可能是字符串或包含zh_cn/en_us的字典
            fallback: 回退文本
        Returns:
            本地化后的文本
        """
        if isinstance(text_obj, dict):
            if self.language == 'cn':
                return text_obj.get('zh_cn', fallback)
            elif self.language == 'en':
                return text_obj.get('en_us', fallback)
            else:  # mixed
                zh_text = text_obj.get('zh_cn', '')
                en_text = text_obj.get('en_us', '')
                if zh_text and en_text:
                    return f"{zh_text} / {en_text}"
                return zh_text or en_text or fallback
        elif isinstance(text_obj, str):
            return text_obj
        else:
            return fallback
    
    def _get_ui_text(self, key: str) -> str:
        """
        获取UI界面文本
        Args:
            key: 文本键
        Returns:
            对应语言的UI文本
        """
        ui_texts = {
            'oneof_options': {'cn': '可选类型（oneOf）', 'en': 'Optional Types (oneOf)', 'mixed': '可选类型（oneOf）'},
            'option_number': {'cn': '选项', 'en': 'Option', 'mixed': '选项'},
            'description': {'cn': '📋 描述', 'en': '📋 Description', 'mixed': '📋 描述'},
            'version_info': {'cn': '🏷️ 版本信息', 'en': '🏷️ Version Information', 'mixed': '🏷️ 版本信息'},
            'version': {'cn': '版本', 'en': 'Version', 'mixed': '版本'},
            'spec': {'cn': '⚙️ 规格说明', 'en': '⚙️ Specifications', 'mixed': '⚙️ 规格说明'},
            'properties_overview': {'cn': '📋 属性概览', 'en': '📋 Properties Overview', 'mixed': '📋 属性概览'},
            'constraints': {'cn': '约束条件：', 'en': 'Constraints:', 'mixed': '约束条件：'},
            'required': {'cn': '必填', 'en': 'Required', 'mixed': '必填'},
            'yes': {'cn': '是', 'en': 'Yes', 'mixed': '是'},
            'no': {'cn': '否', 'en': 'No', 'mixed': '否'},
            'optional_values': {'cn': '可选值', 'en': 'Optional Values', 'mixed': '可选值'},
            'chinese': {'cn': '中文', 'en': 'Chinese', 'mixed': '🇨🇳 中文'},
            'english': {'cn': '英文', 'en': 'English', 'mixed': '🇺🇸 English'},
            'child_properties': {'cn': '子属性：', 'en': 'Child Properties:', 'mixed': '子属性：'},
            'array_items': {'cn': '数组项属性：', 'en': 'Array Item Properties:', 'mixed': '数组项属性：'},
            'map_values': {'cn': '映射值属性：', 'en': 'Map Value Properties:', 'mixed': '映射值属性：'},
            'view': {'cn': '查看', 'en': 'View', 'mixed': '查看'},
            'toc': {'cn': '📚 目录', 'en': '📚 Table of Contents', 'mixed': '📚 目录'},
            'expand_all': {'cn': '展开全部', 'en': 'Expand All', 'mixed': '展开全部'},
            'collapse_all': {'cn': '折叠全部', 'en': 'Collapse All', 'mixed': '折叠全部'},
            'expand_3_levels': {'cn': '展开3层', 'en': 'Expand 3 Levels', 'mixed': '展开3层'},
            'constraint_required': {'cn': '必填', 'en': 'Required', 'mixed': '必填'},
            'constraint_pattern': {'cn': '正则表达式', 'en': 'Pattern', 'mixed': '正则表达式'},
            'constraint_min_len': {'cn': '最小长度', 'en': 'Min Length', 'mixed': '最小长度'},
            'constraint_max_len': {'cn': '最大长度', 'en': 'Max Length', 'mixed': '最大长度'},
            'constraint_default_value': {'cn': '默认值', 'en': 'Default Value', 'mixed': '默认值'},
            'constraint_enum_values': {'cn': '可选值', 'en': 'Enum Values', 'mixed': '可选值'},
            'constraint_min_size': {'cn': '最小大小', 'en': 'Min Size', 'mixed': '最小大小'},
            'constraint_max_size': {'cn': '最大大小', 'en': 'Max Size', 'mixed': '最大大小'},
            'constraint_array_min_size': {'cn': '数组最小长度', 'en': 'Array Min Size', 'mixed': '数组最小长度'},
            'constraint_array_max_size': {'cn': '数组最大长度', 'en': 'Array Max Size', 'mixed': '数组最大长度'},
            'constraint_array_item_type': {'cn': '数组项类型', 'en': 'Array Item Type', 'mixed': '数组项类型'},
            'constraint_map_min_size': {'cn': '映射最小条目数', 'en': 'Map Min Size', 'mixed': '映射最小条目数'},
            'constraint_map_max_size': {'cn': '映射最大条目数', 'en': 'Map Max Size', 'mixed': '映射最大条目数'},
            'constraint_key': {'cn': '键（Key）约束', 'en': 'Key Constraints', 'mixed': '键（Key）约束'},
            'constraint_value': {'cn': '值（Value）约束', 'en': 'Value Constraints', 'mixed': '值（Value）约束'},
            'type': {'cn': '类型', 'en': 'Type', 'mixed': '类型'}

        }
        
        text_dict = ui_texts.get(key, {})
        if self.language == 'cn':
            return text_dict.get('cn', key)
        elif self.language == 'en':
            return text_dict.get('en', key)
        else:  # mixed
            return text_dict.get('mixed', key)

    def convert_file(self, yaml_file: str, output_file: str = None) -> str:
        """转换YAML文件为HTML"""
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        self.output = []
        self.toc = []
        self.current_level = 0
        self.property_index = {}
        
        # 生成HTML内容
        html_content = self._generate_html(data)
        
        # 如果指定了输出文件，写入文件
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"✅ HTML文档已生成: {output_file}")
        
        return html_content
    
    def _generate_html(self, data: Dict[str, Any]) -> str:
        """生成完整的HTML文档"""
        # 生成内容
        self._generate_content(data)
        
        # 读取模板文件
        template_content = self._load_template()
        css_content = self._load_css()
        js_content = self._load_javascript()
        
        # 生成完整的HTML页面
        content_html = '\n'.join(self.output)
        toc_html = self._generate_tree_toc()
        
        title = data.get('name', 'MModel Documentation')
        # 添加语言后缀到标题
        if self.language == 'cn':
            title_suffix = ' - MModel 文档'
        elif self.language == 'en':
            title_suffix = ' - MModel Documentation'
        else:  # mixed
            title_suffix = ' - MModel Documentation'
        
        return template_content.format(
            title=title + title_suffix,
            css_content=css_content,
            javascript_content=js_content,
            toc=toc_html,
            content=content_html
        )
    
    def _load_template(self) -> str:
        """加载HTML模板"""
        template_path = os.path.join('templates', 'template.html')
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # 如果模板文件不存在，使用内置模板
            return self._get_fallback_template()
    
    def _load_css(self) -> str:
        """加载并处理CSS样式"""
        css_path = os.path.join('templates', 'style.css')
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_template = f.read()
        else:
            # 如果CSS文件不存在，使用内置样式
            css_template = self._get_fallback_css()
        
        # 生成类型标签样式
        type_badge_styles = self._generate_type_badge_styles()
        
        # 格式化CSS，插入配置变量
        return css_template.format(
            # 基础配置
            font_family=BASE_CONFIG['font_family'],
            line_height=BASE_CONFIG['line_height'],
            text_color=BASE_CONFIG['text_color'],
            background_color=BASE_CONFIG['background_color'],
            font_size=BASE_CONFIG['font_size'],
            
            # 侧边栏配置
            sidebar_width=SIDEBAR_CONFIG['width'],
            sidebar_background=SIDEBAR_CONFIG['background'],
            sidebar_border_color=SIDEBAR_CONFIG['border_color'],
            sidebar_padding=SIDEBAR_CONFIG['padding'],
            sidebar_shadow=SIDEBAR_CONFIG['shadow'],
            sidebar_title_font_size=SIDEBAR_CONFIG['title_font_size'],
            sidebar_title_margin_bottom=SIDEBAR_CONFIG['title_margin_bottom'],
            
            # 目录配置
            toc_item_margin=TOC_CONFIG['item_margin'],
            toc_toggle_size=TOC_CONFIG['toggle_size'],
            toc_toggle_font_size=TOC_CONFIG['toggle_font_size'],
            toc_toggle_margin_right=TOC_CONFIG['toggle_margin_right'],
            toc_link_padding=TOC_CONFIG['link_padding'],
            toc_link_border_radius=TOC_CONFIG['link_border_radius'],
            toc_link_font_size=TOC_CONFIG['link_font_size'],
            toc_level1_font_size=TOC_CONFIG['level1_font_size'],
            toc_level2_font_size=TOC_CONFIG['level2_font_size'],
            toc_level3_font_size=TOC_CONFIG['level3_font_size'],
            toc_children_margin_left=TOC_CONFIG['children_margin_left'],
            toc_children_padding_left=TOC_CONFIG['children_padding_left'],
            
            # 主内容区配置
            main_margin_left=MAIN_CONFIG['margin_left'],
            main_padding=MAIN_CONFIG['padding'],
            main_mobile_padding=MAIN_CONFIG['mobile_padding'],
            
            # 标题配置
            header_padding=HEADER_CONFIG['padding'],
            header_border_radius=HEADER_CONFIG['border_radius'],
            header_margin_bottom=HEADER_CONFIG['margin_bottom'],
            header_shadow=HEADER_CONFIG['shadow'],
            header_title_font_size=HEADER_CONFIG['title_font_size'],
            header_title_margin_bottom=HEADER_CONFIG['title_margin_bottom'],
            
            # 章节配置
            section_padding=SECTION_CONFIG['padding'],
            section_border_radius=SECTION_CONFIG['border_radius'],
            section_margin_bottom=SECTION_CONFIG['margin_bottom'],
            section_shadow=SECTION_CONFIG['shadow'],
            section_title_font_size=SECTION_CONFIG['title_font_size'],
            section_title_margin_bottom=SECTION_CONFIG['title_margin_bottom'],
            section_title_border_width=SECTION_CONFIG['title_border_width'],
            section_title_padding_bottom=SECTION_CONFIG['title_padding_bottom'],
            
            # 描述项配置
            desc_item_margin_bottom=DESCRIPTION_CONFIG['item_margin_bottom'],
            desc_item_padding=DESCRIPTION_CONFIG['item_padding'],
            desc_item_border_radius=DESCRIPTION_CONFIG['item_border_radius'],
            desc_item_border_width=DESCRIPTION_CONFIG['item_border_width'],
            desc_subtitle_margin_bottom=DESCRIPTION_CONFIG['subtitle_margin_bottom'],
            desc_subtitle_font_size=DESCRIPTION_CONFIG['subtitle_font_size'],
            desc_text_font_size=DESCRIPTION_CONFIG['text_font_size'],
            desc_text_line_height=DESCRIPTION_CONFIG['text_line_height'],
            
            # 版本配置
            version_card_margin_bottom=VERSION_CONFIG['card_margin_bottom'],
            version_card_border_radius=VERSION_CONFIG['card_border_radius'],
            version_card_shadow=VERSION_CONFIG['card_shadow'],
            version_title_padding=VERSION_CONFIG['title_padding'],
            version_title_font_size=VERSION_CONFIG['title_font_size'],
            version_description_padding=VERSION_CONFIG['description_padding'],
            version_spec_padding=VERSION_CONFIG['spec_padding'],
            version_spec_title_margin_bottom=VERSION_CONFIG['spec_title_margin_bottom'],
            version_spec_title_font_size=VERSION_CONFIG['spec_title_font_size'],
            
            # 概览配置
            overview_margin_bottom=OVERVIEW_CONFIG['margin_bottom'],
            overview_title_margin_bottom=OVERVIEW_CONFIG['title_margin_bottom'],
            overview_title_font_size=OVERVIEW_CONFIG['title_font_size'],
            overview_grid_min_width=OVERVIEW_CONFIG['grid_min_width'],
            overview_grid_gap=OVERVIEW_CONFIG['grid_gap'],
            overview_item_border_radius=OVERVIEW_CONFIG['item_border_radius'],
            overview_item_padding=OVERVIEW_CONFIG['item_padding'],
            overview_header_margin_bottom=OVERVIEW_CONFIG['header_margin_bottom'],
            overview_name_font_size=OVERVIEW_CONFIG['name_font_size'],
            overview_desc_font_size=OVERVIEW_CONFIG['desc_font_size'],
            overview_hover_transform=OVERVIEW_CONFIG['hover_transform'],
            overview_hover_shadow=OVERVIEW_CONFIG['hover_shadow'],
            
            # 属性配置
            property_detail_margin_bottom=PROPERTY_CONFIG['detail_margin_bottom'],
            property_detail_border_radius=PROPERTY_CONFIG['detail_border_radius'],
            property_detail_shadow=PROPERTY_CONFIG['detail_shadow'],
            property_header_padding=PROPERTY_CONFIG['header_padding'],
            property_name_font_size=PROPERTY_CONFIG['name_font_size'],
            property_description_padding=PROPERTY_CONFIG['description_padding'],
            property_desc_item_margin_bottom=PROPERTY_CONFIG['desc_item_margin_bottom'],
            property_desc_item_font_size=PROPERTY_CONFIG['desc_item_font_size'],
            property_desc_item_line_height=PROPERTY_CONFIG['desc_item_line_height'],
            
            # 类型标签配置
            type_badge_padding=TYPE_BADGE_CONFIG['padding'],
            type_badge_border_radius=TYPE_BADGE_CONFIG['border_radius'],
            type_badge_font_size=TYPE_BADGE_CONFIG['font_size'],
            type_badge_letter_spacing=TYPE_BADGE_CONFIG['letter_spacing'],
            type_badge_styles=type_badge_styles,
            
            # Release Stage标签配置
            release_stage_padding=RELEASE_STAGE_CONFIG['padding'],
            release_stage_border_radius=RELEASE_STAGE_CONFIG['border_radius'],
            release_stage_font_size=RELEASE_STAGE_CONFIG['font_size'],
            release_stage_letter_spacing=RELEASE_STAGE_CONFIG['letter_spacing'],
            release_stage_margin_left=RELEASE_STAGE_CONFIG['margin_left'],
            
            # 约束配置
            constraint_section_padding=CONSTRAINT_CONFIG['section_padding'],
            constraint_title_margin_bottom=CONSTRAINT_CONFIG['title_margin_bottom'],
            constraint_title_font_size=CONSTRAINT_CONFIG['title_font_size'],
            constraint_list_gap=CONSTRAINT_CONFIG['list_gap'],
            constraint_item_padding=CONSTRAINT_CONFIG['item_padding'],
            constraint_item_border_radius=CONSTRAINT_CONFIG['item_border_radius'],
            constraint_item_font_size=CONSTRAINT_CONFIG['item_font_size'],
            constraint_label_margin_right=CONSTRAINT_CONFIG['label_margin_right'],
            constraint_value_padding=CONSTRAINT_CONFIG['value_padding'],
            constraint_value_border_radius=CONSTRAINT_CONFIG['value_border_radius'],
            constraint_value_font_size=CONSTRAINT_CONFIG['value_font_size'],
            constraint_enum_gap=CONSTRAINT_CONFIG['enum_gap'],
            constraint_enum_margin_top=CONSTRAINT_CONFIG['enum_margin_top'],
            constraint_enum_padding=CONSTRAINT_CONFIG['enum_padding'],
            constraint_enum_border_radius=CONSTRAINT_CONFIG['enum_border_radius'],
            constraint_enum_font_size=CONSTRAINT_CONFIG['enum_font_size'],
            
            # 嵌套配置
            nested_padding=NESTED_CONFIG['padding'],
            nested_title_margin_bottom=NESTED_CONFIG['title_margin_bottom'],
            nested_title_font_size=NESTED_CONFIG['title_font_size'],
            
            # 滚动条配置
            scrollbar_width=SCROLLBAR_CONFIG['width'],
            scrollbar_track_color=SCROLLBAR_CONFIG['track_color'],
            scrollbar_thumb_color=SCROLLBAR_CONFIG['thumb_color'],
            scrollbar_thumb_hover_color=SCROLLBAR_CONFIG['thumb_hover_color'],
            scrollbar_thumb_border_radius=SCROLLBAR_CONFIG['thumb_border_radius'],
            
            # 颜色配置
            primary_color=COLORS['primary'],
            secondary_color=COLORS['secondary'],
            border_color=COLORS['border'],
            hover_bg_color=COLORS['hover_bg'],
            light_color=COLORS['light'],
            gradient_primary=COLORS['gradient_primary'],
            gradient_secondary=COLORS['gradient_secondary'],
            blue_border_color=COLORS['blue_border'],
            red_border_color=COLORS['red_border'],
            
            # 响应式配置
            mobile_breakpoint=BREAKPOINTS['mobile'],
            
            # 动画配置
            transition_duration=ANIMATION_CONFIG['transition_duration'],
            hover_transition=ANIMATION_CONFIG['hover_transition'],
        )
    
    def _generate_type_badge_styles(self) -> str:
        """生成类型标签和release_stage标签样式"""
        styles = []
        
        # 生成类型标签样式
        for type_name, colors in TYPE_COLORS.items():
            styles.append(f".type-{type_name} {{ background: {colors['bg']}; color: {colors['color']}; }}")
        
        # 生成release_stage标签样式
        for stage_name, colors in RELEASE_STAGE_COLORS.items():
            styles.append(f".stage-{stage_name} {{ background: {colors['bg']}; color: {colors['color']}; border: 1px solid {colors['border']}; }}")
        
        return '\n'.join(styles)
    
    def _load_javascript(self) -> str:
        """加载JavaScript"""
        js_path = os.path.join('templates', 'script.js')
        if os.path.exists(js_path):
            with open(js_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # 如果JS文件不存在，使用内置脚本
            return self._get_fallback_javascript()
    
    def _generate_content(self, data: Dict[str, Any]):
        """生成主要内容"""
        if 'name' in data:
            self.output.append(f'<div class="header">')
            self.output.append(f'<h1 class="main-title">{data["name"]}</h1>')
            self.output.append(f'</div>')
        
        if 'description' in data:
            self._add_description_section(data['description'])
        
        if 'versions' in data:
            self._add_versions(data['versions'])
    
    def _add_description_section(self, description: Any):
        """添加描述部分"""
        desc_title = self._get_ui_text('description')
        self.output.append('<section class="description-section" id="description">')
        self.output.append(f'<h2>{desc_title}</h2>')
        self.toc.append({
            'id': 'description',
            'title': desc_title,
            'level': 1,
            'children': []
        })
        
        if self.language == 'mixed' and isinstance(description, dict):
            # 混合模式：显示中英文分别的标题
            if 'zh_cn' in description:
                self.output.append('<div class="description-item">')
                self.output.append(f'<h3>{self._get_ui_text("chinese")}</h3>')
                self.output.append(f'<p class="description-text">{description["zh_cn"]}</p>')
                self.output.append('</div>')
            
            if 'en_us' in description:
                self.output.append('<div class="description-item">')
                self.output.append(f'<h3>{self._get_ui_text("english")}</h3>')
                self.output.append(f'<p class="description-text">{description["en_us"]}</p>')
                self.output.append('</div>')
        else:
            # 单语言模式：直接显示文本
            desc_text = self._get_localized_text(description)
            if desc_text:
                self.output.append(f'<p class="description-text">{desc_text}</p>')
        
        self.output.append('</section>')
    
    def _add_versions(self, versions: List[Dict[str, Any]]):
        """添加版本信息"""
        version_info_title = self._get_ui_text('version_info')
        self.output.append('<section class="versions-section" id="versions">')
        self.output.append(f'<h2>{version_info_title}</h2>')
        
        versions_toc = {
            'id': 'versions',
            'title': version_info_title,
            'level': 1,
            'children': []
        }
        
        for i, version in enumerate(versions):
            version_id = f"version-{i}"
            if 'name' in version:
                version_prefix = self._get_ui_text('version')
                self.output.append(f'<div class="version-card" id="{version_id}">')
                self.output.append(f'<h3 class="version-title">{version_prefix} {version["name"]}</h3>')
                
                version_toc = {
                    'id': version_id,
                    'title': f'{version_prefix} {version["name"]}',
                    'level': 2,
                    'children': []
                }
                
                if 'description' in version:
                    self._add_version_description(version['description'])
                
                if 'spec' in version:
                    spec_children = self._add_spec(version['spec'], version_id)
                    version_toc['children'] = spec_children
                
                versions_toc['children'].append(version_toc)
                self.output.append('</div>')
        
        self.toc.append(versions_toc)
        self.output.append('</section>')
    
    def _add_version_description(self, description: Any):
        """添加版本描述"""
        self.output.append('<div class="version-description">')
        
        if self.language == 'mixed' and isinstance(description, dict):
            if 'zh_cn' in description:
                chinese_label = self._get_ui_text('chinese').replace('🇨🇳 ', '')
                self.output.append(f'<p><strong>{chinese_label}：</strong>{description["zh_cn"]}</p>')
            if 'en_us' in description:
                english_label = self._get_ui_text('english').replace('🇺🇸 ', '')
                self.output.append(f'<p><strong>{english_label}：</strong>{description["en_us"]}</p>')
        else:
            desc_text = self._get_localized_text(description)
            if desc_text:
                self.output.append(f'<p>{desc_text}</p>')
        
        self.output.append('</div>')
    
    def _add_spec(self, spec: Dict[str, Any], parent_id: str):
        """添加规格说明"""
        spec_title = self._get_ui_text('spec')
        self.output.append('<div class="spec-section">')
        self.output.append(f'<h4>{spec_title}</h4>')
        
        spec_children = []
        if 'properties' in spec:
            # 先生成属性概览
            self._add_properties_overview(spec['properties'], parent_id)
            # 再生成详细属性
            spec_children = self._add_properties(spec['properties'], parent_id, level=1)
        
        self.output.append('</div>')
        return spec_children
    
    def _add_properties_overview(self, properties: Dict[str, Any], parent_id: str):
        """添加属性概览"""
        overview_title = self._get_ui_text('properties_overview')
        self.output.append('<div class="properties-overview">')
        self.output.append(f'<h5>{overview_title}</h5>')
        self.output.append('<div class="overview-grid">')
        
        for prop_name, prop_data in properties.items():
            prop_id = f"{parent_id}-{prop_name}"
            if isinstance(prop_data, dict) and 'type' in prop_data:
                type_class = self._get_type_class(prop_data['type'])
                description = self._get_short_description(prop_data.get('description', ''))
                
                self.output.append(f'<div class="overview-item">')
                self.output.append(f'<a href="#{prop_id}" class="overview-link">')
                self.output.append(f'<div class="overview-header">')
                self.output.append(f'<span class="overview-name">{prop_name}</span>')
                self.output.append(f'<span class="type-badge {type_class}">{prop_data["type"]}</span>')
                self.output.append(f'</div>')
                if description:
                    self.output.append(f'<div class="overview-desc">{description}</div>')
                self.output.append(f'</a>')
                self.output.append(f'</div>')
        
        self.output.append('</div>')
        self.output.append('</div>')
    
    def _add_properties(self, properties: Dict[str, Any], parent_id: str, level: int = 1):
        """添加属性详细说明"""
        children = []
        
        for prop_name, prop_data in properties.items():
            prop_id = f"{parent_id}-{prop_name}"
            
            prop_toc = {
                'id': prop_id,
                'title': prop_name,
                'level': level + 2,
                'children': []
            }
            
            # 添加属性详细卡片
            self.output.append(f'<div class="property-detail" id="{prop_id}">')
            self.output.append(f'<div class="property-header">')
            self.output.append(f'<h{4+level} class="property-name">{prop_name}</h{4+level}>')
            
            if isinstance(prop_data, dict):
                # 创建标签容器
                badges = []
                
                # 添加类型标签
                if 'type' in prop_data:
                    type_class = self._get_type_class(prop_data['type'])
                    badges.append(f'<span class="type-badge {type_class}">{prop_data["type"]}</span>')
                
                # 添加release_stage标签
                if 'release_stage' in prop_data:
                    release_stage = prop_data['release_stage']
                    stage_class = self._get_release_stage_class(release_stage)
                    stage_text = self._get_release_stage_text(release_stage)
                    badges.append(f'<span class="release-stage-badge {stage_class}">{stage_text}</span>')
                
                # 如果有标签，添加标签容器
                if badges:
                    self.output.append('<div class="property-badges">')
                    self.output.extend(badges)
                    self.output.append('</div>')
                
                self.output.append('</div>')  # 关闭 property-header
                
                # 添加描述
                if 'description' in prop_data:
                    self._add_property_description(prop_data['description'])
                
                # 收集所有约束信息（包括字段级别的特殊约束）
                all_constraints = {}
                
                # 如果有 constraint 字段，先添加它
                if 'constraint' in prop_data and prop_data['constraint']:
                    all_constraints = prop_data['constraint'].copy()
                
                # 检查字段级别的特殊约束
                field_level_constraints = ['max_value', 'min_value', 'default_value']
                for constraint_key in field_level_constraints:
                    if constraint_key in prop_data and constraint_key not in all_constraints:
                        all_constraints[constraint_key] = prop_data[constraint_key]
                
                # 如果有任何约束，显示它们
                if all_constraints:
                    self._add_constraints_html(all_constraints)
                
                # 递归处理嵌套属性
                if 'properties' in prop_data:
                    child_props_label = self._get_ui_text('child_properties')
                    self.output.append('<div class="nested-properties">')
                    self.output.append(f'<h6>{child_props_label}</h6>')
                    nested_children = self._add_properties(prop_data['properties'], prop_id, level + 1)
                    prop_toc['children'] = nested_children
                    self.output.append('</div>')
                
                # 处理数组项
                if prop_data.get('type') == 'array' and 'constraint' in prop_data:
                    array_children = self._handle_array_items(prop_data['constraint'], prop_id, level)
                    if array_children:
                        prop_toc['children'].extend(array_children)
                
                # 处理映射值
                if prop_data.get('type') == 'map' and 'constraint' in prop_data:
                    map_children = self._handle_map_values(prop_data['constraint'], prop_id, level)
                    if map_children:
                        prop_toc['children'].extend(map_children)
            
            self.output.append('</div>')  # 关闭 property-detail
            children.append(prop_toc)
        
        return children
    
    def _add_property_description(self, description: Any):
        """添加属性描述"""
        self.output.append('<div class="property-description">')
        
        if self.language == 'mixed' and isinstance(description, dict):
            if 'zh_cn' in description:
                chinese_label = self._get_ui_text('chinese').replace('🇨🇳 ', '')
                self.output.append(f'<div class="desc-item"><strong>{chinese_label}：</strong>{description["zh_cn"]}</div>')
            if 'en_us' in description:
                english_label = self._get_ui_text('english').replace('🇺🇸 ', '')
                self.output.append(f'<div class="desc-item"><strong>{english_label}：</strong>{description["en_us"]}</div>')
        else:
            desc_text = self._get_localized_text(description)
            if desc_text:
                self.output.append(f'<div class="desc-item">{desc_text}</div>')
        
        self.output.append('</div>')
    
    def _add_constraints_html(self, constraint: Any):
        """添加约束信息的HTML版本"""
        if not constraint:
            return
        
        constraints_title = self._get_ui_text('constraints')
        self.output.append('<div class="constraints-section">')
        self.output.append(f'<h6>{constraints_title}</h6>')
        self.output.append('<div class="constraints-list">')
        
        if isinstance(constraint, dict):
            # 处理基本约束
            basic_constraints = {
                'required': ('constraint_required', self._format_boolean),
                'pattern': ('constraint_pattern', self._format_code),
                'min_len': ('constraint_min_len', self._format_number),
                'max_len': ('constraint_max_len', self._format_number),
                'default_value': ('constraint_default_value', self._format_value),
            }
            
            # 显示基本约束
            for key, (label_key, formatter) in basic_constraints.items():
                if key in constraint:
                    value = constraint[key]
                    formatted_value = formatter(value) if formatter else str(value)
                    label = self._get_ui_text(label_key)
                    self.output.append(f'<div class="constraint-item">')
                    self.output.append(f'<span class="constraint-label">{label}:</span>')
                    self.output.append(formatted_value)
                    self.output.append('</div>')
            
            # 处理枚举约束
            if 'enum' in constraint:
                self._add_enum_constraint(constraint['enum'])
            
            # 处理数组约束
            if 'array' in constraint:
                self._add_array_constraint(constraint['array'])
            
            # 处理映射约束
            if 'map' in constraint:
                self._add_map_constraint(constraint['map'])
            
            # 处理 oneOf 约束
            if 'oneOf' in constraint:
                self._add_oneof_constraint(constraint['oneOf'])
            
            # 处理高级约束
            # if 'advanced' in constraint:
            #     self._add_advanced_constraint(constraint['advanced'])
        
        self.output.append('</div>')  # 关闭 constraints-list
        self.output.append('</div>')  # 关闭 constraints-section
    
    def _format_boolean(self, value):
        """格式化布尔值"""
        yes_text = self._get_ui_text('yes')
        no_text = self._get_ui_text('no')
        return f'<code class="constraint-value">{yes_text if value else no_text}</code>'
    
    def _format_code(self, value):
        """格式化代码值"""
        return f'<code class="constraint-value">{value}</code>'
    
    def _format_number(self, value):
        """格式化数字值"""
        return f'<code class="constraint-value">{value}</code>'
    
    def _format_value(self, value):
        """格式化通用值"""
        if isinstance(value, str):
            return f'<code class="constraint-value">{value}</code>'
        elif isinstance(value, bool):
            return self._format_boolean(value)
        elif isinstance(value, (int, float)):
            return self._format_number(value)
        else:
            return f'<code class="constraint-value">{json.dumps(value, ensure_ascii=False)}</code>'
    
    def _add_enum_constraint(self, enum_data):
        """添加枚举约束"""
        if isinstance(enum_data, dict):
            if 'values' in enum_data and enum_data['values']:
                enum_values_label = self._get_ui_text('constraint_enum_values')
                self.output.append('<div class="constraint-item full-width">')
                self.output.append(f'<span class="constraint-label">{enum_values_label}:</span>')
                self.output.append('<div class="enum-values">')
                for value in enum_data['values']:
                    self.output.append(f'<code class="enum-value">{value}</code>')
                self.output.append('</div>')
                self.output.append('</div>')
            
            if 'default_value' in enum_data:
                default_value_label = self._get_ui_text('constraint_default_value')
                self.output.append(f'<div class="constraint-item">')
                self.output.append(f'<span class="constraint-label">{default_value_label}:</span>')
                self.output.append(f'<code class="constraint-value">{enum_data["default_value"]}</code>')
                self.output.append('</div>')
    
    def _add_array_constraint(self, array_constraint):
        """添加数组约束"""
        if isinstance(array_constraint, dict):
            # 数组大小约束
            if 'min_size' in array_constraint:
                min_size_label = self._get_ui_text('constraint_array_min_size')
                self.output.append(f'<div class="constraint-item">')
                self.output.append(f'<span class="constraint-label">{min_size_label}:</span>')
                self.output.append(f'<code class="constraint-value">{array_constraint["min_size"]}</code>')
                self.output.append('</div>')
            
            if 'max_size' in array_constraint:
                max_size_label = self._get_ui_text('constraint_array_max_size')
                self.output.append(f'<div class="constraint-item">')
                self.output.append(f'<span class="constraint-label">{max_size_label}:</span>')
                self.output.append(f'<code class="constraint-value">{array_constraint["max_size"]}</code>')
                self.output.append('</div>')
            
            # 数组项类型约束
            if 'item' in array_constraint and isinstance(array_constraint['item'], dict):
                if 'type' in array_constraint['item']:
                    item_type_label = self._get_ui_text('constraint_array_item_type')
                    self.output.append(f'<div class="constraint-item">')
                    self.output.append(f'<span class="constraint-label">{item_type_label}:</span>')
                    type_value = array_constraint['item']['type']
                    type_class = self._get_type_class(type_value)
                    self.output.append(f'<span class="type-badge {type_class}">{type_value}</span>')
                    self.output.append('</div>')
                
                # 如果数组项有约束，递归显示
                if 'constraint' in array_constraint['item']:
                    array_constraints_text = self._get_ui_text('constraint_array_min_size').replace('最小长度', '约束').replace('Min Size', 'Constraints')  # 临时解决方案
                    self.output.append('<div class="nested-constraint">')
                    self.output.append(f'<span class="constraint-label">数组项约束:</span>')
                    self._add_constraints_html(array_constraint['item']['constraint'])
                    self.output.append('</div>')
    
    def _add_map_constraint(self, map_constraint):
        """添加映射约束"""
        if isinstance(map_constraint, dict):
            # 映射大小约束
            if 'min_size' in map_constraint:
                min_size_label = self._get_ui_text('constraint_map_min_size')
                self.output.append(f'<div class="constraint-item">')
                self.output.append(f'<span class="constraint-label">{min_size_label}:</span>')
                self.output.append(f'<code class="constraint-value">{map_constraint["min_size"]}</code>')
                self.output.append('</div>')
            
            if 'max_size' in map_constraint:
                max_size_label = self._get_ui_text('constraint_map_max_size')
                self.output.append(f'<div class="constraint-item">')
                self.output.append(f'<span class="constraint-label">{max_size_label}:</span>')
                self.output.append(f'<code class="constraint-value">{map_constraint["max_size"]}</code>')
                self.output.append('</div>')
            
            # 键约束
            if 'key' in map_constraint and isinstance(map_constraint['key'], dict):
                key_label = self._get_ui_text('constraint_key')
                self.output.append('<div class="nested-constraint">')
                self.output.append(f'<span class="constraint-label">{key_label}:</span>')
                self._add_map_key_value_constraint(map_constraint['key'], 'key')
                self.output.append('</div>')
            
            # 值约束
            if 'value' in map_constraint and isinstance(map_constraint['value'], dict):
                value_label = self._get_ui_text('constraint_value')
                self.output.append('<div class="nested-constraint">')
                self.output.append(f'<span class="constraint-label">{value_label}:</span>')
                self._add_map_key_value_constraint(map_constraint['value'], 'value')
                self.output.append('</div>')
    
    def _add_map_key_value_constraint(self, kv_constraint, kv_type):
        """添加映射的键或值约束"""
        if 'type' in kv_constraint:
            self.output.append(f'<div class="constraint-item">')
            type_value = kv_constraint['type']
            type_class = self._get_type_class(type_value)
            self.output.append(f'<span>{self._get_ui_text("type")}: <span class="type-badge {type_class}">{type_value}</span></span>')
            self.output.append('</div>')
        
        if 'constraint' in kv_constraint:
            self._add_constraints_html(kv_constraint['constraint'])
    
    def _add_oneof_constraint(self, oneof_data):
        """添加 oneOf 约束"""
        if isinstance(oneof_data, list) and oneof_data:
            self.output.append('<div class="constraint-item full-width">')
            self.output.append(f'<span class="constraint-label">{self._get_ui_text("oneof_options")}:</span>')
            self.output.append('<div class="oneof-options">')
            
            for i, option in enumerate(oneof_data):
                self.output.append(f'<div class="oneof-option">')
                self.output.append(f'<span class="option-number">{self._get_ui_text("option_number")} {i + 1}:</span>')
                
                if isinstance(option, dict):
                    if 'type' in option:
                        type_value = option['type']
                        type_class = self._get_type_class(type_value)
                        self.output.append(f'<span class="type-badge {type_class}">{type_value}</span>')
                    
                    if 'description' in option:
                        desc = self._get_description_text(option['description'])
                        if desc:
                            self.output.append(f'<span class="option-desc">{desc}</span>')
                    
                    # 如果选项有约束，递归显示
                    if 'constraint' in option:
                        self.output.append('<div class="option-constraint">')
                        self._add_constraints_html(option['constraint'])
                        self.output.append('</div>')
                
                self.output.append('</div>')
            
            self.output.append('</div>')
            self.output.append('</div>')
    
    def _add_advanced_constraint(self, advanced_data):
        """添加高级约束"""
        pass
        # if isinstance(advanced_data, dict):
        #     # 检查列表
        #     if 'check_list' in advanced_data and advanced_data['check_list']:
        #         self.output.append('<div class="constraint-item full-width">')
        #         self.output.append('<span class="constraint-label">检查列表:</span>')
        #         self.output.append('<div class="check-list">')
        #         for check in advanced_data['check_list']:
        #             self.output.append(f'<div class="check-item">• {check}</div>')
        #         self.output.append('</div>')
        #         self.output.append('</div>')
            
        #     # 条件必填
        #     if 'required_when' in advanced_data:
        #         self.output.append(f'<div class="constraint-item">')
        #         self.output.append(f'<span class="constraint-label">条件必填:</span>')
        #         self.output.append(f'<code class="constraint-value">{advanced_data["required_when"]}</code>')
        #         self.output.append('</div>')
    
    def _handle_array_items(self, constraint: Dict, parent_id: str, level: int):
        """处理数组项"""
        children = []
        if isinstance(constraint, dict) and 'array' in constraint:
            array_constraint = constraint['array']
            if 'item' in array_constraint and isinstance(array_constraint['item'], dict):
                if 'properties' in array_constraint['item']:
                    array_items_label = self._get_ui_text('array_items')
                    self.output.append('<div class="array-items">')
                    self.output.append(f'<h6>{array_items_label}</h6>')
                    children = self._add_properties(array_constraint['item']['properties'], f"{parent_id}-items", level + 1)
                    self.output.append('</div>')
        return children
    
    def _handle_map_values(self, constraint: Dict, parent_id: str, level: int):
        """处理映射值"""
        children = []
        if isinstance(constraint, dict) and 'map' in constraint:
            map_constraint = constraint['map']
            if 'value' in map_constraint and isinstance(map_constraint['value'], dict):
                if 'properties' in map_constraint['value']:
                    map_values_label = self._get_ui_text('map_values')
                    self.output.append('<div class="map-values">')
                    self.output.append(f'<h6>{map_values_label}</h6>')
                    children = self._add_properties(map_constraint['value']['properties'], f"{parent_id}-values", level + 1)
                    self.output.append('</div>')
        return children
    
    def _get_type_class(self, type_name: str) -> str:
        """获取类型对应的CSS类"""
        type_classes = {
            'string': 'type-string',
            'integer': 'type-number',
            'float': 'type-number',
            'boolean': 'type-boolean',
            'object': 'type-object',
            'array': 'type-array',
            'map': 'type-map',
            'enum': 'type-enum',
            'time': 'type-time'
        }
        return type_classes.get(type_name, 'type-default')
    
    def _get_release_stage_class(self, release_stage: str) -> str:
        """获取release_stage对应的CSS类"""
        stage_classes = {
            'experimental': 'stage-experimental',
            'preview': 'stage-preview',
            'beta': 'stage-beta',
            'ga': 'stage-ga',
            'deprecated': 'stage-deprecated'
        }
        return stage_classes.get(release_stage, 'stage-default')
    
    def _get_release_stage_text(self, release_stage: str) -> str:
        """获取release_stage对应的显示文本"""
        stage_texts = {
            'experimental': 'Experimental',
            'preview': 'Preview',
            'beta': 'Beta',
            'ga': 'GA',
            'deprecated': 'Deprecated'
        }
        return stage_texts.get(release_stage, release_stage)
    
    def _get_description_text(self, description: Any) -> str:
        """获取描述文本"""
        return self._get_localized_text(description, '')
    
    def _get_short_description(self, description: Any) -> str:
        """获取简短描述文本"""
        text = self._get_description_text(description)
        if len(text) > 60:
            return text[:60] + '...'
        return text
    
    def _generate_tree_toc(self) -> str:
        """生成树状目录HTML"""
        if not self.toc:
            return ''
        
        def render_toc_item(item, parent_level=0):
            html = []
            html.append(f'<li>')
            html.append(f'<div class="toc-item">')
            
            # 根据层级决定是否默认展开（只展开前3层）
            is_expanded = item['level'] <= 3
            
            if item['children']:
                toggle_icon = '▼' if is_expanded else '▶'
                html.append(f'<span class="toc-toggle" onclick="toggleTocItem(this)">{toggle_icon}</span>')
            else:
                html.append(f'<span class="toc-spacer"></span>')
            
            html.append(f'<a href="#{item["id"]}" class="toc-link level-{item["level"]}">{item["title"]}</a>')
            html.append(f'</div>')
            
            if item['children']:
                # 根据层级决定是否添加 collapsed 类
                collapsed_class = '' if is_expanded else ' collapsed'
                html.append(f'<ul class="toc-children{collapsed_class}">')
                for child in item['children']:
                    html.extend(render_toc_item(child, item['level']))
                html.append(f'</ul>')
            
            html.append(f'</li>')
            return html
        
        toc_html = ['<ul class="toc-tree">']
        for item in self.toc:
            toc_html.extend(render_toc_item(item))
        toc_html.append('</ul>')
        
        return '\n'.join(toc_html)
    
    def _get_fallback_template(self) -> str:
        """获取内置HTML模板（当模板文件不存在时使用）"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - MModel Documentation</title>
    <style>
        {css_content}
    </style>
</head>
<body>
    <div class="container">
        <nav class="sidebar">
            <h3>📚 目录</h3>
            {toc}
        </nav>
        
        <main class="main-content">
            {content}
        </main>
    </div>
    
    <script>
        {javascript_content}
    </script>
</body>
</html>'''
    
    def _get_fallback_css(self) -> str:
        """获取内置CSS样式（当CSS文件不存在时使用）"""
        # 这里可以放置一个简化的CSS样式作为后备
        return "/* 后备CSS样式 */ body { font-family: Arial, sans-serif; }"
    
    def _get_fallback_javascript(self) -> str:
        """获取内置JavaScript（当JS文件不存在时使用）"""
        return '''
        function toggleTocItem(element) {
            const children = element.parentElement.nextElementSibling;
            if (children && children.classList.contains('toc-children')) {
                children.classList.toggle('collapsed');
                element.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
            }
        }
        '''


def main():
    parser = argparse.ArgumentParser(description='将 expanded.yaml 转换为美观的 HTML 文档（重构版）')
    parser.add_argument('input_file', help='输入的 YAML 文件路径')
    parser.add_argument('-o', '--output', help='输出的 HTML 文件路径（可选）')
    parser.add_argument('-l', '--language', choices=['mixed', 'cn', 'en'], default='mixed',
                       help='输出语言模式: mixed(中英文), cn(中文), en(英文), 默认为 mixed')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"❌ 错误: 文件 {args.input_file} 不存在")
        return
    
    # 如果没有指定输出文件，自动生成
    if not args.output:
        base_name = os.path.splitext(args.input_file)[0]
        lang_suffix = '' if args.language == 'mixed' else f'_{args.language}'
        args.output = f"{base_name}{lang_suffix}.html"
    
    try:
        converter = YamlToHtmlConverter(language=args.language)
        converter.convert_file(args.input_file, args.output)
        print(f"🎉 转换完成！可以在浏览器中打开: {args.output}")
        print(f"💡 提示: 可以直接双击 HTML 文件在浏览器中查看")
        print(f"🌐 语言模式: {args.language}")
        print(f"🔧 配置文件: config.py")
        print(f"📁 模板目录: templates/")
    except Exception as e:
        print(f"❌ 转换失败: {str(e)}")


if __name__ == "__main__":
    main() 