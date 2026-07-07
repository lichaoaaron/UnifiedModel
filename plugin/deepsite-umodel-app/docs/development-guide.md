# UModel Grafana 插件 — 开发者指南

面向**接手继续开发**本插件的工程师。涵盖：插件前后端架构、项目模块架构，以及**最核心的**——前端如何适配 Grafana（尤其拓扑图等无 `@grafana/ui` 原生组件的部分是怎么适配的）、开发工作流与约束速查。

> 插件 id：`deepsite-umodel-app`（type `app` + Go 后端）。由 `@grafana/create-plugin` 脚手架生成。
> 它把原独立前端 [`web/`](../../../web/)（Vite + React 18）以 Grafana app 插件形式重新落地，所有后端访问经插件 Go 后端反代到 **umodel-server**。

---

## 1. 插件前后端架构

插件 = **前端**（React 18 + react-router，webpack 打成 AMD `module.js`）+ **Go 后端**（`backend:true`，mage 编译 `gpx_umodel_<os>_<arch>`），产物都进 `dist/` 由 Grafana 加载。浏览器**不直连** umodel-server，所有后端访问经 Go 后端**透明反向代理**转发：

```
浏览器（插件前端）
  └─ getBackendSrv().fetch(/api/plugins/deepsite-umodel-app/resources/api/v1/...)
        │  Grafana 同源 + 会话鉴权
        ▼
插件 Go 后端（CallResource）
  └─ pkg/plugin/resources.go: proxyTo() 反代 /api/*、/healthz → apiUrl
        │  注入可选 Bearer(secureJsonData.apiKey)、删 Cookie
        ▼
umodel-server（cmd/umodel-server, REST :8080）
  /api/v1/{workspaces|query|umodel|entitystore|samples|agent|capabilities}
```

要点：
- 统一经 `/api/plugins/<id>/resources/*` 反代 → 复用 Grafana 鉴权、无 CORS、密钥只在服务端。
- 本项目**无** Prometheus/Loki/Tempo：metric/log/trace 被建模为图实体，走 `/api/v1/query`（后端再查 OpenSearch），**不引入任何原生 datasource/dashboard**。
- **诊断页是第二上游**：它不查 umodel-server，而是经 `streamProxyTo` 把 `/diagnosis/*` **流式反代**到独立诊断服务（`jsonData.diagnosisUrl`，SSE）——详见 [§5](#5-约束与坑速查)。
- `apiUrl` / `diagnosisUrl`（jsonData）与 `apiKey`（secureJsonData）由 [`provisioning/plugins/apps.yaml`](../provisioning/plugins/apps.yaml) 注入，或在 AppConfig 配置页运行时填。

---

## 2. 项目模块架构

```
plugin/deepsite-umodel-app/
├─ src/                             前端（webpack → dist/module.js）
│  ├─ module.tsx                    入口：AppPlugin().setRootPage(App).addConfigPage(AppConfig)
│  ├─ plugin.json                   插件清单：id/type/backend/executable、includes（导航页 /a/<id>/<route>）
│  ├─ constants.ts                  ROUTES 枚举 + PLUGIN_BASE_URL
│  ├─ declarations.d.ts             *.css 模块声明
│  ├─ components/
│  │  ├─ App/App.tsx                react-router <Routes>：各页路由 + 默认重定向 UModel + Suspense；外层 <I18nProvider>
│  │  ├─ AppConfig/AppConfig.tsx    配置页（jsonData.apiUrl + jsonData.diagnosisUrl + secureJsonData.apiKey）
│  │  ├─ WorkspacePage.tsx          页面外壳：<PluginPage> + Workspace 选择器 + 未选门控 + UModelRoot
│  │  └─ WorkspaceSelect.tsx        @grafana/ui Combobox 工作区选择器
│  ├─ context/WorkspaceContext.tsx  工作区列表 + 选中态（localStorage 'openumodel.workspace'）+ 共享 UModelApi，经 Context 透传
│  ├─ i18n/                         手写国际化（自 web 移植；见 §3.7）
│  │  ├─ index.tsx                  I18nProvider + useI18n + t()/t.rich()；locale ← Grafana 用户语言
│  │  └─ locales/{en-US,zh-CN}/     按命名空间分文件的中英词典（不含 landing）
│  ├─ api/
│  │  ├─ constants.ts               RESOURCE_BASE = /api/plugins/<id>/resources
│  │  ├─ client.ts                  UModelApi：getBackendSrv().fetch 封装 + ApiError 归一化 + normalizeQueryResult 信封归一化 + 60s 超时 + rawRequest（API 调试器专用）
│  │  └─ types.ts                   后端 REST 的 TS 类型（含 QueryExecuteResponse；诊断类型带 Phase 2 注释）
│  ├─ lib/{json,storage}.ts         纯工具（stringify/parseJson/useLocalStorageState）
│  ├─ utils/                        notify.ts（toast）
│  ├─ design/                       「移植 + 主题桥接」基础（见 §3.4）
│  │  ├─ ThemeBridge.tsx            UModelRoot：--om-* 令牌（含 --om-primary 族 / --om-cjk-font / --om-scrim）← GrafanaTheme2，并注入 document.body
│  │  └─ components/index.tsx (+components.css)  web 自研 UI 门面（.om-* 类，原样移植）
│  ├─ pages/                        每个导航页一个入口（薄包装：接 WorkspacePage + useWorkspace）
│  │                                UModel Topo Query Imports Settings ApiDebug Diagnosis
│  └─ features/                     重型可视化 / 重型页面（整目录移植 + 桥接）
│     ├─ umodel/                    UModel 图编辑器：@xyflow/react + @hpcc-js/wasm-graphviz（原 explorer/）
│     ├─ entityTopo/                实体拓扑：cosmos.gl WebGL 引擎（cosmosTopo/）
│     ├─ query/                     SPL 查询工作台：CodeEditor + 表格/图表（内嵌 entityTopo 渲染 .topo）
│     ├─ apiDebug/                  API 调试器：ApiSpec 目录 + CodeEditor 请求体 + 经 api.rawRequest 真实执行
│     └─ diagnosis/workbench/       智能诊断工作台（中文-only）：SSE 流式 → 独立诊断服务；ServiceCallGraph 手写 SVG；storm 模式离线 fixtures
├─ pkg/                             Go 后端（mage → dist/gpx_umodel_<os>_<arch>）
│  ├─ main.go                       app.Manage("deepsite-umodel-app", plugin.NewApp)
│  └─ plugin/
│     ├─ app.go                     读 jsonData.{apiUrl,diagnosisUrl} + secureJsonData.apiKey；CheckHealth（只校 apiUrl）
│     ├─ resources.go               registerRoutes 挂载：/ping；proxyTo() 反代 /api/、/healthz → apiUrl；streamProxyTo() 流式反代 /diagnosis/ → diagnosisUrl
│     └─ resources_test.go          ping + 反代转发 + 未配置 502 单测
├─ provisioning/plugins/apps.yaml   自动启用插件 + 注入 jsonData.{apiUrl,diagnosisUrl} / secureJsonData.apiKey
├─ docker-compose.yaml              dev/e2e 的 Grafana 容器：extends .config 基座，覆盖 grafana_version（默认 12.3.1）
│                                   与 ports（3334:3000；列表字段替换必须 !override，见 §5）
├─ package.json                     前端依赖与脚本（build/dev/test/typecheck/lint/e2e/server/sign）
├─ playwright.config.ts             e2e 配置：auth 项目先 admin 登录存 cookie（playwright/.auth/），
│                                   chromium 项目带该身份跑 tests/*.spec.ts；baseURL 取 GRAFANA_URL
│                                   环境变量（默认 http://localhost:3000）。见 §4 e2e
├─ Magefile.go / go.mod             后端构建（build.BuildAll）/ Go module（go 1.26.4 + grafana-plugin-sdk-go）
├─ go.sum                           Go 依赖校验和锁定，go get / go mod tidy 自动维护——勿手改，随 go.mod 一起提交
├─ tsconfig.json                    仅 extends ./.config/tsconfig.json（脚手架基础 TS 配置）；需自定义编译选项时在此扩展，不改 .config/
├─ eslint.config.mjs                在脚手架基础上为移植目录域内放宽 react-hooks 新规则（见 §3.6）
└─ .config/                         脚手架托管、**禁改**：webpack / externals / docker-compose / Dockerfile / tsconfig …
```

---

## 3. 前端如何适配 Grafana（核心）

本插件前端不是从零写的，而是把独立前端 [`web/`](../../../web/) **移植**进 Grafana。整个适配自始至终只解决五个问题，每个问题对应一个小节：

| 适配要解决的问题 | web/ 原做法 | 插件做法 | 详见 |
|---|---|---|---|
| ① 数据从哪来 | Vite dev 代理直连 umodel-server | `getBackendSrv().fetch()` → 插件 Go 后端反代 | [§3.2](#32-数据通路替代原-vite-代理) |
| ② 页面怎么挂进 Grafana | 独立 SPA 自带路由/外壳/工作区门户页 | `AppPlugin` + `<PluginPage>` + `WorkspaceContext` | [§3.3](#33-路由与外壳) |
| ③ 主题/样式从哪来 | 自研设计令牌，浅色硬编码 | **零硬编码，全部从 `GrafanaTheme2` 派生** | [§3.4](#34-主题适配的两条路径)–[§3.5](#35--没有-grafanaui-原生组件的部分怎么适配) |
| ④ 移植代码过不了新 lint 规则 | —（web 无此约束） | 仅对移植目录域内放宽，新代码保持全严格 | [§3.6](#36-eslint-域内放宽移植代码的取舍) |
| ⑤ 国际化 | web 自带语言切换器 + localStorage | 复用词典，locale 跟随 Grafana 用户语言 | [§3.7](#37-i18n跟随-grafana-用户语言) |

### 3.1 两个决策树：怎么移植、怎么取色

看懂这两个决策树，就看懂了整个适配。

**决策一（按页面）——选移植策略**：对 `web/` 的每个页面只问一件事——`@grafana/ui` 有没有等价组件、且 web 版是否轻量？

- **有等价物且页面轻量**（纯表单）→ **原生重写**。在 `pages/` 里直接用 `@grafana/ui` 重新实现：
  - Imports（导入/写入表单）
  - Settings（工作区设置）
- **无等价物 / 页面已成重型复合体**（重型可视化、内嵌拓扑、Monaco 编辑器、列剖析…）→ **整目录移植 + 主题桥接**。`pages/` 只薄包一层，真实现整目录移植到 `features/`，经 `design/ThemeBridge` 桥接主题：
  - UModel（React Flow + Graphviz WASM，原 Explorer）
  - Topology（cosmos.gl WebGL）
  - Query（Monaco→CodeEditor 查询工作台，内嵌 entityTopo 渲染 `.topo`）
  - API 调试器（原静态 API map，现为 ApiSpec 目录 + Monaco 请求体 + 真实执行）
  - Diagnosis（智能诊断工作台，中文-only；SSE 流式 → 独立诊断服务，见 §5）

**决策二（按元素）——让它跟随主题**：只看元素的渲染介质，A/B 两路通用。

- **`@grafana/ui` 组件** → 天然主题化，无需处理。
- **HTML/CSS** → `useStyles2((theme: GrafanaTheme2) => …)` 或 `var(--om-*)`（桥接令牌，见 [§3.4](#34-主题适配的两条路径) 路径 B）。
- **React 组件 props 取色** → `useTheme2()` 取值传入（如 React Flow 网格/MiniMap，见 [§3.5](#35--没有-grafanaui-原生组件的部分怎么适配)）。
- **WebGL/Canvas（不吃 CSS）** → `useTheme2()` 取色，经引擎配置注入（如 cosmos.gl，见 [§3.5](#35--没有-grafanaui-原生组件的部分怎么适配)）。

颜色/间距/圆角/阴影一律取 `theme.colors.* / theme.spacing() / theme.shape.radius.* / theme.shadows.*`，**不写死 hex**（Grafana best-practices）；明暗主题由 Grafana 驱动，组件零改动跟随。

> 按此思路移植一个页面的操作 checklist，见 [§4「新增/移植一个页面的既定步骤」](#新增移植一个页面的既定步骤)。

### 3.2 数据通路（替代原 Vite 代理）
- 前端基址 `RESOURCE_BASE = /api/plugins/<id>/resources`（[`src/api/constants.ts`](../src/api/constants.ts)，id 从 [`plugin.json`](../src/plugin.json) import 作单一真源）。
- `UModelApi`（[`src/api/client.ts`](../src/api/client.ts)）用 `getBackendSrv().fetch()`（rxjs `lastValueFrom`，`responseType:'text'` 容忍 204），调 `${RESOURCE_BASE}/api/v1/...`。方法名/路径均为 umodel（`importUModel`/`/api/v1/umodel/*`），SPL 方言 `.umodel`。
- **信封归一化**：develop 的 `query/execute` 返回 `QueryExecuteResponse {code,message,success,data:{header,data}}` 而非裸 `{columns,rows}`；客户端 `normalizeQueryResult()` 把它拍平回列/行（`/explain` 无信封，勿包）。
- **超时**：每次调用挂 rxjs `timeout({first: 60_000})`，超时归一化为 `TIMEOUT` `ApiError`。
- **`rawRequest(method,url,body?)`**：API 调试器专用，捕获非 2xx 把 `{status,statusText,ok,payload}` **返回**而非抛出，仍走 getBackendSrv（保住"一切后端访问经 Go 反代"的不变量）。
- 插件 Go 后端 [`resources.go`](../pkg/plugin/resources.go) 的 `proxyTo()` 把 `/api/*`、`/healthz` 透明反代到 `apiUrl`，删 `Cookie`/`Authorization`，可选注入 `Bearer apiKey`。反代**路径无关**——后端只转发、不关心具体 REST 路径。

### 3.3 路由与外壳
- [`module.tsx`](../src/module.tsx)：`AppPlugin().setRootPage(App).addConfigPage(...)`。
- [`App.tsx`](../src/components/App/App.tsx)：react-router v6 `<Routes>`，每页一个 `<Route>`，`*` → `Navigate to /umodel`；外层包 `<I18nProvider>`。ROUTES 段与 web 的 `routes.ts` 对齐（`umodel`/`entity-topo`/`query`/`imports`/`settings`/`api-debug`/`diagnosis`）。**不采用** web 换用的 react-router v7 / BrowserRouter，插件仍用 AppPlugin + 自有 v6 路由。
- 每页用 `<PluginPage>`（`@grafana/runtime`）拿 Grafana 页头/面包屑。
- **工作区**：原 web 用"选 workspace 才进主界面"。这里下沉为 `WorkspaceContext`（列表+选中态，localStorage `'openumodel.workspace'`）+ `WorkspaceSelect`（Combobox，放在 `WorkspacePage` 的页头 actions）+ 未选时空态门控。[`plugin.json`](../src/plugin.json) 的 `includes` 与 `ROUTES` 一一对应。

### 3.4 主题适配的两条路径
**A) `@grafana/ui` 重写**（Imports/Settings）
- 用 `Field/Input/TextArea/Button/Checkbox/RadioButtonGroup/Badge/Tab+TabsBar/InteractiveTable/ConfirmModal/Stack/Text` 等。
- 自定义样式一律 `useStyles2((theme: GrafanaTheme2) => ...)` + `@emotion/css`。
- **`Select` 一律用 `Combobox`**（前者已废弃）。
- 挂载即拉取的 effect 加 `// eslint-disable-next-line react-hooks/set-state-in-effect`（fetch-on-mount 是正当模式）。

**B) 移植 + 主题桥接**（UModel/Topology/Query/API 调试器）—— [`src/design/ThemeBridge.tsx`](../src/design/ThemeBridge.tsx)
- 原 web 用一套 `--om-*` 设计令牌 + `--ume-*`/`--eto-*` 布局令牌（浅色硬编码）。
- `UModelRoot` 把 ~40 个 `--om-*` 令牌**从 `GrafanaTheme2` 计算**并注入根 `div` 的内联 CSS 变量；`WorkspacePage` 用它包裹所有页面内容。`--ume-*`/`--eto-*` 大多 `var(--om-*)`，于是整套 CSS 跟随主题。
- develop 新增的令牌也已桥接：`--om-primary` 族（`primary.main/shade/transparent/border`）、`--om-cjk-font`（`theme.typography.fontFamily` + CJK 回退栈，供中文文案；**漏加会静默字体回退**）、`--om-scrim`（模态遮罩，按 `theme.isDark` 派生——写死浅色遮罩暗色下不可见）。
- 关键细节：**portal 到 `document.body` 的浮层**（节点菜单/focus 面板）在 `.umodel-root` 之外、拿不到 `--om-*`，所以 `UModelRoot` 还把 `--om-*` 用 `useEffect` 注入 `document.body`（仅自定义属性，Grafana 不读取，无污染）。develop 的 `umodel.css` 里 `.ume-node-menu/.ume-focus-panel` 这类浮层带一整套写死浅色的 `--ume-*` 覆盖，移植时改成引用 body 上的 `--om-*`。
- 移植时把 web 残留的写死浅色（`--ume-color-bg-subtle:#fafafa`、`background:#fff`、`border:#e5e7eb`…）逐一改成 `var(--om-*)`；**语义状态色**（警告 amber、危险/删除 red、成功 green、中性 toggle 轨道…）也一律走对应 token（`--om-amber[-text]`/`--om-red[-text]`/`--om-success`/`--ume-color-*`），别当身份色留死——固定深/浅状态色在反色主题下会低对比或隐形。**UI chrome 强调色**（滚动条 thumb、focus/active 边框、模态 scrim、minimap viewport 框）同样走 token（`--om-border-strong`/`--om-text-faint`/`--om-primary-*`/`--om-scrim`）——注意 `--om-indigo`/`--ume-color-accent` 实为 `theme.colors.primary.main` **别名**，设计里的"indigo"其实跟随 Grafana primary，裸 indigo hex（`#4f46e5`/`rgba(91,91,214,…)`）应改 `--om-primary` 族而非当身份色留死。真正**保留** + 注释的只有**数据可视化身份色**（节点/域调色板、排名红橙黄）、**深色 tooltip 上的白字**、**阴影 rgba**、`var(--token, #hex)` 里的兜底 hex，与既有先例一致。
- **逐一改、勿盲目全局替换**：批量 `sed` 把 `#hex` 全替成 token 会误伤**选择器里的 hex**（Tailwind 变体转义类 `.hover\:bg-\[\#hex\]:hover`、`[class~="bg-[#hex]"]` 属性选择器名），生成匹配不到真实类的死规则——只替换**声明值一侧**，选择器里的类名原样保留。诊断工作台的 Tailwind-shim 尤其踩这个坑，详见 [§5](#5-约束与坑速查)。

### 3.5 ★ 没有 `@grafana/ui` 原生组件的部分怎么适配
这是本插件最关键的经验，分三类：

**(1) Monaco 编辑器 → `@grafana/ui` CodeEditor**
- JSON/YAML 编辑：`@monaco-editor/react` 的 `Editor` → `@grafana/ui` `CodeEditor`（已内置、由 Grafana 托管 monaco worker，避免从 CDN 拉 monaco 在内网失败）。
- **DiffEditor 无原生等价物** → 用**并排两个只读 `CodeEditor`**（加 `.ume-diff-sxs` 布局）。

**(2) UModel 图编辑（React Flow + Graphviz WASM，原 Explorer）—— 保留，桥接主题**
- `@xyflow/react`（React Flow）渲染 + `@hpcc-js/wasm-graphviz`（WASM 布局）原样保留（webpack 已开 `asyncWebAssembly`）。
- 布局/画布的 `ume-*` CSS 经 `--om-*` 跟随主题。
- React Flow 的 `Background` 网格点色、`MiniMap` 节点色等**是 props 不是 CSS** → 在组件（`UModelGraphView.tsx`）里 `const theme = useTheme2()`，传 `theme.colors.border.medium`/`theme.colors.text.secondary`。

**(3) Topology 拓扑图（cosmos.gl WebGL）—— 最难，重点看**
- 渲染引擎 `CosmosEngine` 是**命令式类**（非 React），整目录移植保留（[`features/entityTopo/cosmosTopo/`](../src/features/entityTopo/cosmosTopo/)）。
- **WebGL 画布背景色不能用 CSS 变量**（它是传给 GL 上下文的字面量，不是 CSS）。原来 `const BG_COLOR='#ffffff'` 硬编码 → 暗色下整个拓扑区发白。
  适配做法（**通用范式**）：给引擎加可配置项，由能用 `useTheme2()` 的 React 组件把主题色注入：
  - [`types.ts`](../src/features/entityTopo/cosmosTopo/types.ts)：`CosmosEngineConfig.backgroundColor?: string`
  - [`cosmosEngine.ts`](../src/features/entityTopo/cosmosTopo/cosmosEngine.ts)：构造函数 `this.backgroundColor = config?.backgroundColor ?? BG_COLOR`，Graph 配置用 `backgroundColor: this.backgroundColor`
  - [`cosmosTopoGraph.tsx`](../src/features/entityTopo/cosmosTopo/cosmosTopoGraph.tsx)：`const theme = useTheme2()`，`new CosmosEngine(host, { backgroundColor: theme.colors.background.primary, ... })`
- 其余 HTML/CSS 部分照旧：`eto-*` CSS 令牌桥接到 `--om-*`；模块级内联样式常量（隔离条/渲染浮层）用 `var(--om-*)`（元素在主题树内可解析）。
- **手写 SVG（minimap）取色**：SVG **呈现属性**（`fill="…"`/`stroke="…"`）**不解析 `var()`**——`fill="var(--x)"` 当属性写是无效的。两条出路：① 像 `ServiceCallGraph` 那样把 `useTheme2()` 的色值作为 **JS 字面量**传进属性（`fill={c.root}`）；② 去掉内联属性、改由 **CSS 规则**上色（`.eto-cosmos-minimap rect { fill: var(--om-surface) }`——CSS 值里能用 `var()`）。minimap 底色/viewport 框即用②。
- **命令式引擎 ↔ React 的桥接模式**：引擎每帧 `setTick(t=>t+1)`，组件里 `useMemo(() => engine.getXxx(), [engine, tick])` 用 `tick` 强制重算来读最新引擎状态（这类 memo 会被 `exhaustive-deps` 判为"多余依赖"，是**故意**的——`entityTopo` 已在 eslint 域内整体关掉该规则，见 §3.6，故只留说明注释、不必逐行豁免）。

> **一句话范式**：凡 **WebGL/Canvas 这类不吃 CSS** 的渲染，从 `useTheme2()` 取色**注入**进去；凡 **HTML/CSS** 的，用 `var(--om-*)`（桥接令牌）或 `useStyles2(GrafanaTheme2)`。一律不写死 hex。

### 3.6 eslint 域内放宽（移植代码的取舍）
新版 react-hooks 规则（对齐 React Compiler）对命令式可视化**系统性误报**（渲染期读 ref 定位浮层、fetch/布局 effect、引擎接线）。根 [`eslint.config.mjs`](../eslint.config.mjs) 对五个移植目录 `src/features/{umodel,entityTopo,query,apiDebug,diagnosis}/**/*.tsx`（**只组件文件，纯逻辑 `.ts` 保持全严格**）关掉：`react-hooks/refs`、`react-hooks/set-state-in-effect`、`react-hooks/use-memo`、`react/display-name`。

**`react-hooks/exhaustive-deps` 分域处理**（这条最能抓 stale-closure bug）：
- **`umodel` / `entityTopo` / `diagnosis`（纯 vendored 可视化/工作台，逐字从 `web/` 重新同步）** → 用**第二个 override 块直接 `off`**。这些目录里全是命令式引擎/流式回调的故意违规（tick 订阅、引擎只随 layout 重建、派生 key 控触发、SSE 回调 ref），每次 re-sync 都会重新触发；整目录关掉比每回重挂逐行 `disable` 维护成本低，也与上面已对它们关掉的另 3 条规则一致。故意违规处保留**说明性注释**（写清为何这样依赖），但不再需要 `// eslint-disable-next-line` 指令行。
- **`query` / `apiDebug`（更像自研页面）** → **保持 error**。它确实还在抓真问题——如 `QueryPage` 结果表的 `columns` 派生就是被这条规则拦下、用 `useMemo` 正经修掉而非 disable 的。这两处的极少数故意违规仍逐行 `// eslint-disable-next-line` 并写明理由。

### 3.7 i18n（跟随 Grafana 用户语言）
web 侧新增了一套**手写** i18n（`web/src/i18n/`：`I18nContext` + `useI18n()` → `{locale, t}`，`t(key,params)` 插值 + `t.rich()` 渲染内嵌标签，中英词典按命名空间分文件）。移植进插件（[`src/i18n/`](../src/i18n/)）时做两处**刻意差异**：
- **locale 来源换成 Grafana**：`detectLocale()` 读 `config.bootData?.user?.language`（`@grafana/runtime`），`zh*` → `zh-CN`，否则 `en-US`。**去掉** web 的 `LanguageSelect` 切换器、`setLocale`、localStorage 持久化——语言归 Grafana 管。可选链承重：jest 里 `config.bootData` 为 `undefined`。
- **不写 `document.documentElement.lang`**（文档属于 Grafana）。
- 词典全量拷贝，**除 `landing.ts`**（工作区落地页不移植，两个 `index.ts` barrel 去掉它）。移植的 feature（含 `cosmosTopoGraph`）经 `useI18n()` 消费 `t`；插件自身 chrome（原生 Imports/Settings、WorkspacePage 空态）保持英文。
- **`I18nProvider` 放在 `App.tsx` 最外层**（`WorkspaceProvider` 之上）。

---

## 4. 开发工作流

### 质量门（无需 Docker）
```bash
npm run typecheck   # tsc --noEmit (strict)
npm run lint        # eslint（lint:fix 可自动修格式/import 顺序）
npm run test:ci     # jest
npm run build       # webpack production → dist/
mage -v             # 后端编译（否则 backend:true 健康检查失败）
```
### e2e 回归测试（`@grafana/plugin-e2e` + Playwright）

e2e 在**真实 Grafana** 里跑：[`playwright.config.ts`](../playwright.config.ts) 有两个 project——`auth`（用默认 admin 登录、把 cookie 存 `playwright/.auth/`）与 `chromium`（带 admin 身份跑 `tests/*.spec.ts`）。测试从 `./fixtures` 导入 `test`/`expect`（**不要**从 `@playwright/test` 直接导），用 `gotoPage`/`appConfigPage` 等 fixture。写测试的选择器约定见 [`.config/AGENTS/e2e-testing.md`](../.config/AGENTS/e2e-testing.md)。

**测试文件**

| 文件 | 类型 | 依赖后端 |
|---|---|---|
| [`tests/appNavigation.spec.ts`](../tests/appNavigation.spec.ts) | 冒烟：7 个门控页（UModel/Topo/Query/Imports/Settings/ApiDebug/Diagnosis）渲染 "No workspace selected"、选择器存在 | **否**（Provider 不自动选 workspace，未选即空态，与后端可达无关） |
| [`tests/appConfig.spec.ts`](../tests/appConfig.spec.ts) | 冒烟：配置页保存 apiUrl/apiKey（reset 条件化） | 否 |
| [`tests/appQuery.spec.ts`](../tests/appQuery.spec.ts) | 功能：配置 apiUrl → 选 workspace → Query 执行 SPL → 断言结果表出行 | **是**，需可达且有数据的 umodel-server；**按需开启**（见下） |

**前提**
1. 先构建 `dist/`（`npm run build` + `mage -v`）——`npm run server` 会挂 `../dist`。
2. 有一个**装了本插件的** Grafana 在跑（用本插件的 `npm run server`，或指向已挂本插件 `dist/` 的 Grafana）。
3. 首次装浏览器：`npx playwright install chromium`。

**运行**
```bash
# 终端1：起装了本插件的 Grafana
npm run server                              # docker compose；docker ps 看真实端口
GRAFANA_VERSION=12.3.0 npm run server       # 按最低支持版(plugin.json grafanaDependency)测

# 终端2：GRAFANA_URL 指向那个 Grafana 的真实端口
GRAFANA_URL=http://<host>:<port> npm run e2e
npm run e2e -- --ui                          # 交互 UI 模式
npx playwright show-report                   # 看 HTML 报告
```
- `GRAFANA_URL` 指向本机 Grafana 的真实端口（`docker ps` 查映射端口），如 `GRAFANA_URL=http://localhost:<port> npm run e2e`。

**功能测试按需开启**（`appQuery.spec.ts`）——不设环境变量时 `test.skip` 跳过：
```bash
E2E_UMODEL_API_URL=http://host.docker.internal:8080 \  # 容器可达地址，与配置页 apiUrl 同理
  GRAFANA_URL=http://localhost:<port> npm run e2e -- appQuery
# 可选：E2E_WORKSPACE=<名称> 指定选哪个 workspace（默认第一个；需有可查的 .umodel 数据）
```

**易踩坑**
- **目录/server/GRAFANA_URL 三者要都是本插件这一套**：跑参考项目/别的 server 起的 Grafana 装的是别的插件，本插件的路由/页面不存在，用例会全挂。
- `ECONNREFUSED` = 该 host:port 没在监听 → `docker ps` 看真实端口、`curl http://<host>:<port>/api/health` 验证连通。
- **插件 app 配置是全局单条记录**（一个 org 一份）。`fullyParallel` 下多个测试若都改 `apiUrl` 会**互相覆盖**——让写配置的测试用**相同值**（如都取 `E2E_UMODEL_API_URL`），或串行；读配置的功能测试在列表没出时可 `page.reload()` 重拉一次以扛住并发重建的瞬时失败。

### 新增/移植一个页面的既定步骤

1. **@grafana/ui 重写型**：在 `src/pages/XxxPage.tsx` 用 `<WorkspacePage>` + `useWorkspace()` 取 `api/workspace`，用 `@grafana/ui` 组件实现；`useStyles2` 主题化。
2. **移植重型可视化 / 重型页面型**（参考 UModel/Topology/Query/apiDebug）：
   - `cp -r web/src/features/<feat> src/features/<feat>`（import 路径 `../../api`/`../../lib`/`../../design/components`/`../../i18n` 天然对齐）。
   - 每个含 JSX 的 `.tsx` 补 `import React`（本插件经典 JSX runtime；与现有 `from 'react'` 合并避免 `no-duplicate-imports`）。
   - 删 `noUnusedLocals` 报的未用导入/死代码；`@monaco-editor/react` 的 `Editor` → `CodeEditor`（`options`→`monacoOptions`、`onMount`→`onEditorDidMount`、去 `theme="vs"`；DiffEditor → 并排双只读 CodeEditor + `.ume-diff-sxs`）；删 `disableMonacoEditContext`/`preloadMonaco` 引用；根路径静态资源 → `import`。
   - **剪掉不可达的死文件**：整目录拷贝会带进备用/未接入的组件，而 tsc/eslint 只报文件**内**的未用导入、**不报"整个文件没人 import"**——移植后从 `module.tsx` 用 import 说明符（含动态 `import()`）做**传递可达 BFS**，删掉不可达 `.tsx`（注意同名 type 可能仍被 live 代码引用，删组件不删 type）。诊断工作台曾借此删掉 10 个备用 UI 组件（`AgentChatPanel` 链）+ 脚手架残留 `Placeholder.tsx`/`utils.routing.ts`。
   - `pages/` 只薄包一层接入 context；[`App.tsx`](../src/components/App/App.tsx) 加 `<Route>`（用 `ROUTES` 段）、[`plugin.json`](../src/plugin.json) 加 `includes`（**改 plugin.json 需重启 Grafana**）。
   - CSS：写死浅色 → `var(--om-*)`（保留数据身份色/阴影 + 注释）；WebGL/Canvas 取色 → `useTheme2()` 注入。
   - eslint：纯 vendored viz（如又一 cosmos 类）加进 §3.6 第二个 override（`exhaustive-deps: off`）；更"自研"的页面留在第一个 override、逐行豁免故意违规。
3. 跑全套质量门 + 浏览器实测（暗色主题观感）。

> **重新同步 web 的既定套路**：`umodel`/`entityTopo` 等纯 vendored 目录**整目录重拷** + 重施既定适配（`import React`、CodeEditor、`useTheme2` 注入、`CosmosEngineConfig.backgroundColor` + `ITopoGraph`→`TopoGraphApi`、模块级内联样式 → `var(--om-*)`），而**不是** cherry-pick diff——插件经 prettier 重排，与 web 的文本 diff 是整文件级，挑不出来。重拷前先 `git diff --no-index` 出历史适配补丁作参照。

---

## 5. 约束与坑速查
- **禁改** [`.config/**`](../.config/)（脚手架托管）与 [`plugin.json`](../src/plugin.json) 的 `id`/`type`。
- React/react-router/rxjs/`@grafana/*` 是 external，**版本钉死 12.3.1 / React 18**，须与运行的 Grafana 版本一致。
- **改 [`plugin.json`](../src/plugin.json) 必须重启 Grafana**。
- `apiUrl` **不能填 `localhost`**（反代由 Grafana 容器发起）。
- **Go 版本坑**：容器 1.21.6（`.config/Dockerfile` 的 `GO_VERSION`）vs `go.mod` 1.26.4 → 用宿主预编译后端。
- Linux 二进制从 Windows 同步后 `chmod +x`。
- 未签名插件需 `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=deepsite-umodel-app`。
- **compose `extends` 合并坑**：映射类字段（`build.args`、`environment`）逐 key 合并，子文件直接覆盖即可；**列表类字段（`ports` 等）是追加不是替换**——根 [`docker-compose.yaml`](../docker-compose.yaml) 想改掉 base 的端口映射必须写 `ports: !override` 并**整表写全**（含 delve 的 `2345:2345`，漏写即丢失），需 Compose v2.24+。否则 base 的 `3000:3000` 仍生效，宿主 3000 被占时容器起不来。
- 本项目无 Prometheus/Loki/Tempo——可观测数据走 Go 反代，不要去接原生 datasource。
- **后端契约**：REST 前缀是 `/api/v1/umodel/*`；SPL 方言是 `.umodel`/`.entity`/`.entity_set`/`.topo`；`query/execute` 回 `QueryExecuteResponse` 信封，前端必须经 `normalizeQueryResult` 拍平（`/explain` 无信封）。
- **Monaco 只用 `@grafana/ui` CodeEditor**：web 经 `@monaco-editor/react` 从 CDN 拉 monaco，Grafana CSP 下会被拦；一律换 CodeEditor（Grafana 托管 worker）。**坑**：CodeEditor 会在 monaco 外再包一层只有 border 的 `height:auto` 容器 div，直接 `height="100%"` 会因「100% of auto = 0」塌成空框——每个 monaco wrapper 要加 `.xxx-monaco > div { height:100% }` 强制容器填满（见 query/apiDebug/umodel 的 CSS）。
- **页面视口定高**：Grafana PluginPage 的内容区是**会被内容撑高的滚动容器**（`.page-scrollbar-content` 是 `min-height:100%`），所以 `height:100%`/`100vh` 都无法把页面约束到视口——[`ThemeBridge`](../src/design/ThemeBridge.tsx) 的 `UModelRoot` 用 JS 测量自身距视口顶的偏移，把根定为「到视口底」的像素高度（监听 resize）。填充型页面（UModel/Topology/Query/apiDebug）的根 `height:100%` 于是被约束、内部面板各自 `overflow:auto` 独立滚动；短表单页（Imports/Settings）不填满则自然。**移植的可视化页面根不要用 `100vh`**（会从页头下方起算而溢出）。
- **写死浅色的隐蔽处**：web 单主题设计里除 `#hex` 外还有大量**半透明白底**（`background: rgba(255,255,255,0.9)` 毛玻璃面板）与固定深字（`#1f2937`/`#334155`），暗色下会成白块/隐形字——retheme 时 `rgba(255,…)` 面板背景一并改 `var(--om-surface)`，翻暗底后同处的深字改 `var(--om-text)`。CSS 里 `<code>` 受 Grafana 全局 `code{white-space:nowrap}` 影响不换行，文档表用 `table-layout:auto` + `overflow-wrap:anywhere` 自适应（勿写死列宽百分比）。
- **i18n locale 跟随 Grafana**（`config.bootData.user.language`），插件不带语言切换器；`detectLocale` 的可选链承重（jest 下 `bootData` 为空）。
- **诊断工作台（SSE 第二上游）**：只移植 `web/src/features/diagnosis/workbench/`（root 级同名文件是死代码副本，忽略）。它不查 umodel-server，而是接独立诊断服务——加 `jsonData.diagnosisUrl`（[`AppConfig`](../src/components/AppConfig/AppConfig.tsx) 字段 + provisioning，容器可达如 `http://host.docker.internal:18000`）；Go 后端 [`resources.go`](../pkg/plugin/resources.go) 的 `streamProxyTo` 把 `/diagnosis/*` **流式反代**到 diagnosisUrl：**每读一块上游 SSE 就 `w.Write`+`Flusher.Flush()`**（httpadapter 的 ResponseWriter 每次 Flush 发一个 CallResourceResponse 分块；用 `io.Copy` 会攒到结束才吐、破坏流式）。诊断专用 client `Timeout: 300s`（诊断可跑 ~2min，别用 60s 的 `proxyClient`）。前端保留原生 `fetch().body.getReader()`（getBackendSrv 不能流式），`BASE_URL=${RESOURCE_BASE}/diagnosis/api`。storm 模式走 bundled fixtures 离线回放，仅最终报告需后端。诊断页**中文-only**（症状识别正则等本就是中文逻辑）。
- **诊断工作台的 Tailwind-utility-shim（retheme 大坑，非常规）**：诊断页 CSS **不是**手写 `.ume-*`/`.eto-*`，而是一套**手写 Tailwind 工具类 shim**——原 web 靠**运行时 Tailwind CDN（JIT）**生成工具类，Grafana CSP 下加载不了、插件也**无构建期 Tailwind**，所以 JSX 里写的每个工具类（`bg-blue-100`/`text-gray-500`/`hover:bg-[#f3f4f6]`…）都必须在 [`diagnosisWorkbench.css`](../src/features/diagnosis/workbench/diagnosisWorkbench.css) 里**手写一条 shim 规则**（任意值类走 `[class~="bg-[#hex]"]`、命名类走 `.cls`，值一律 `var(--om-*)`），**漏写即该元素无样式**（透明露底/继承色，明暗都错）。只需覆盖**可达组件**（从 `DiagnosisWorkbench` BFS 追 import 的 7 个：`DiagnosisWorkbench`+`DiagnosisReport`/`EmptyState`/`EventRow`/`EventStream`/`HistoryPanel`/`ServiceCallGraph`）——当年整目录拷进来的另一套备用 UI（`AgentChatPanel` 链，10 个组件）**已作为冗余删除**（见 §4 死文件剪枝）。检测法：提取 tsx 里的着色类，对 CSS 求 `.cls` 与 `[class~="cls"]` 两种形式的差集。
- **批量 hex→token 替换会污染变体选择器（务必避免）**：盲目把 CSS 里的 `#hex` 全局替成 `var(--om-*)` 时，会连 **Tailwind 变体转义选择器**里的 hex 一起换——`.hover\:bg-\[\#f3f4f6\]:hover` 被改成 `.hover\:bg-\[\var(--om-surface-subtle)\]:hover`，成了**匹配不到任何真实类的死规则**（hover/disabled/group-hover 态静默失效，发送按钮曾因此在 light 下隐形）。`[class~="bg-[#hex]"]` 平选择器若加了 mask 尚能保住，变体转义选择器最易漏。**根治**：变体规则一律用健壮的 `[class~="hover:bg-[#f3f4f6]"]:hover` **属性选择器**形式（字符串内 `[`/`#` 无需转义、日后再做值级 retheme 也不会污染）。铁证检测：`grep '\var(' *.css`——真实声明值是 `var(` 不带前导反斜杠，命中 `\var(` 即选择器被污染。
- **语义状态色残留 = 某一主题下隐形**：主题化会翻转的 bg 配**固定白图标**，会在某个主题下白压白——发送/停止按钮曾 `bg-[#1e1e1e]`(→`--om-bg`) + `text-white`(→`--om-text-inverse`) 在 light 下双白隐形。修法：抽成**语义类** [`.diag-action-btn`](../src/features/diagnosis/workbench/diagnosisWorkbench.css)（bg=`--om-text`、icon=`--om-text-inverse`，二者**互为反色**→明暗都高对比），不再依赖共享/固定 hex。同轮审计把各移植 CSS 里遗漏的**语义状态色**（umodel 的 amber 差异标题/danger 删除按钮/`#ccc` toggle 轨道、entityTopo 的 danger 按钮/toggle 轨道、query·apiDebug 的 Monaco 白色 bevel）一并转 `--om-*`/移除；**身份色**（节点调色板、排名红橙黄、暗色 tooltip 白字、阴影 rgba、`var(--token,#hex)` 兜底）按既有先例保留。

---

## 6. 参考
- Grafana 插件官方文档（训练数据可能过时，以此为准）：https://grafana.com/developers/plugin-tools/llms.txt
- `@grafana/ui` 组件：https://developers.grafana.com/ui/latest/index.html
- e2e test: https://grafana.com/developers/plugin-tools/e2e-test-a-plugin/
- best-practices：https://grafana.com/developers/plugin-tools/key-concepts/best-practices