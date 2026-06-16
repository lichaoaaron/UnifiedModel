# 🚀 快速使用指南

将 `expanded.yaml` 文件转换为美观的文档格式，支持 **HTML** 和 **Markdown** 两种输出。

## 🌟 推荐：生成HTML文档（已优化）

```bash
# 方法1: 使用便捷脚本（推荐）
./convert.sh                                    # 默认生成HTML格式
./convert.sh your_file.yaml output.html html    # 指定HTML格式

# 方法2: 使用Python脚本
python3 quick_html.py expanded_schemas/entity_set.expanded.yaml
python3 yaml_to_html.py expanded_schemas/entity_set.expanded.yaml
```

## 📝 生成Markdown文档

```bash
# 使用便捷脚本
./convert.sh your_file.yaml output.md markdown

# 使用Python脚本
python3 quick_convert.py expanded_schemas/entity_set.expanded.yaml
python3 yaml_to_markdown.py expanded_schemas/entity_set.expanded.yaml
```

## 📦 安装依赖

```bash
pip3 install PyYAML
```

## ✨ HTML格式新特性 🆕

### 🌲 树状侧边栏
- ✅ **层级清晰**: 树状结构显示元素归属关系
- ✅ **可折叠展开**: 点击箭头折叠/展开子项
- ✅ **快速导航**: 点击任意项目快速跳转
- ✅ **当前位置高亮**: 自动高亮当前阅读位置

### 📋 属性概览模式
- ✅ **卡片式展示**: 每个属性用卡片形式展示
- ✅ **类型标签**: 彩色类型标识，一目了然
- ✅ **简短描述**: 显示属性的简要说明
- ✅ **点击跳转**: 点击卡片跳转到详细说明

### 🎨 分层展示
- ✅ **先概览后详细**: 先显示所有属性概览，再展示详细信息
- ✅ **层次分明**: 清晰的视觉层级，易于理解
- ✅ **响应式设计**: 自适应不同屏幕尺寸

## 📊 格式对比

### 🌐 HTML格式特点（已优化）
- 🌲 **树状导航**: 清晰的层级关系，支持折叠展开
- 📋 **概览模式**: 先展示概览，再显示详细信息
- 🎨 **专业美观**: 类似专业API文档的界面
- 🏷️ **彩色标签**: 不同类型用不同颜色标识
- 📱 **响应式设计**: 支持桌面和移动设备
- ⚡ **交互体验**: 悬停效果、平滑滚动、智能导航

### 📝 Markdown格式特点
- 🔗 **GitHub友好**: 在GitHub上完美显示
- 📊 **版本控制**: 易于跟踪文档变更
- 💾 **轻量级**: 文件小，加载快
- 🔄 **通用性**: 支持各种Markdown编辑器

## 🎯 使用场景推荐

| 场景 | 推荐格式 | 原因 |
|------|----------|------|
| 📖 **文档阅读** | HTML | 树状导航，概览模式，阅读体验佳 |
| 🔗 **在线分享** | HTML | 专业外观，交互性强 |
| 📚 **API文档** | HTML | 类似Swagger UI的专业体验 |
| 👥 **团队协作** | HTML | 清晰的结构，易于理解 |
| 🔄 **版本管理** | Markdown | 便于Git跟踪变更 |
| 📱 **GitHub展示** | Markdown | 原生支持，显示完美 |

## 📄 输出示例

**输入**: `entity_set.expanded.yaml`

**HTML输出**: `entity_set.expanded.html`
- 🌲 树状侧边栏导航
- 📋 属性概览卡片
- 🎨 渐变色标题
- 🏷️ 彩色类型标签
- 📚 分层详细展示

**Markdown输出**: `entity_set.expanded.md`
- 📝 层级标题结构
- 💼 代码块约束展示
- 🌐 中英文对照
- 📊 表格化信息

## 🚀 一键转换

```bash
# 生成优化的HTML文档（推荐）
./convert.sh

# 生成Markdown文档
./convert.sh "" "" markdown

# 演示两种格式对比
./demo.sh
```

## 🎨 HTML界面预览

### 侧边栏结构
```
📚 目录
├─ 📋 描述
└─ 🏷️ 版本信息
   └─ 版本 v1.0.0
      ├─ metadata
      │  ├─ name
      │  ├─ display_name
      │  └─ description
      └─ schema
         ├─ url
         └─ version
```

### 主体内容布局
```
📋 属性概览
┌─────────────┬─────────────┬─────────────┐
│ name        │ display_name│ description │
│ [string]    │ [object]    │ [object]    │
│ 元素名称... │ 显示名称... │ 元素描述... │
└─────────────┴─────────────┴─────────────┘

详细属性说明
├─ name (string)
│  ├─ 描述: 元素在MModel系统中的名称...
│  └─ 约束: required: true, pattern: ^[a-zA-Z]...
├─ display_name (object)
│  └─ 子属性: zh_cn, en_us
└─ description (object)
   └─ 子属性: zh_cn, en_us
```

---

💡 **推荐**: 优先使用HTML格式，新的树状导航和概览模式让文档阅读更加高效！

## 支持的文件

- ✅ 所有 `expanded.yaml` 格式文件
- ✅ 复杂嵌套结构
- ✅ 多语言描述
- ✅ 各种约束条件

---

💡 **提示**: 生成的 Markdown 文件可以直接提交到 Git 仓库，在 GitHub 上完美显示！ 