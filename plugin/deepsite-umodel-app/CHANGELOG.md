# Changelog

## 1.0.0 (Unreleased)

Initial release — the UModel console as a Grafana app plugin.

- **Data path:** all backend access is reverse-proxied through the plugin's Go backend (`pkg/plugin/resources.go`, `CallResource`) to the UModel server configured as `jsonData.apiUrl` (+ optional `secureJsonData.apiKey`, injected server-side). No `plugin.json` `routes`; no native Prometheus/Loki/Tempo data source — metric/log/trace are graph entities queried via `/api/v1/query`.
- **Frontend adapted to Grafana:** `AppPlugin.setRootPage` + react-router v6 + `PluginPage`; a `WorkspaceContext` + `Combobox` selector replaces the standalone workspace landing; requests go through `getBackendSrv()`.
- **Six pages, two adaptation styles:** form pages (Imports, Settings) rewritten natively on `@grafana/ui` + `useStyles2`; heavy pages ported and theme-bridged — **UModel** (React Flow `@xyflow/react` + Graphviz WASM, Monaco → `@grafana/ui` CodeEditor), **Topology** (`@cosmos.gl/graph` WebGL), **Query** (SPL workbench) and **API Debugger**.
- **Theme bridge:** `src/design/ThemeBridge.tsx` (`UModelRoot`) maps the ported `--om-*` tokens onto `GrafanaTheme2` (and injects them on `document.body` for portaled overlays; also pins the content to the Grafana page viewport so full-height pages scroll their own panels); the cosmos.gl WebGL canvas background is themed via `CosmosEngineConfig.backgroundColor` from `useTheme2()`. Zero hardcoded colors — light/dark follow Grafana.
- **i18n:** Grafana's official `@grafana/i18n` — `initPluginTranslations` in `module.tsx`, `languages` in `plugin.json`, JSON catalogs under `src/locales/`, extraction via `i18next-cli`; en-US / zh-Hans, locale follows the Grafana user language.
- **Backend:** Go reverse proxy with unit tests (`resources_test.go`).

See [docs/development-guide.md](./docs/development-guide.md) for architecture and the full frontend-adaptation write-up.