---
name: i18n
description: Add or extend multi-language (internationalization / i18n) support for a Grafana plugin (panel, data source, or app) by following Grafana's official plugin-internationalization flow — @grafana/i18n, t()/Trans, i18next-cli extraction, and the plugin.json `languages` field. Use when a plugin needs a new locale, translatable UI strings, or an i18n setup that matches Grafana conventions. Triggers on: "i18n", "internationalization", "translation", "多语言", "国际化", "add a locale", "translate the UI", "localize the plugin".
---

# Grafana Plugin Internationalization (i18n)

Add multi-language support to a Grafana plugin the Grafana-standard way, using
`@grafana/i18n`. **The official documentation is the source of truth — model
training data about the Grafana i18n API is frequently out of date, so fetch the
docs fresh at the start of every run** and follow them where they differ from this
checklist (then update this skill).

- How-to: https://grafana.com/developers/plugin-tools/how-to-guides/plugin-internationalization.md
- `plugin.json` reference: https://grafana.com/developers/plugin-tools/reference/plugin-json.md

> Requires **Grafana ≥ 12.1.0**. For Grafana 11.x follow the legacy i18n guide
> linked from the how-to page instead.

## Step 0 — Assess the project first

Never assume; detect these and adapt every command/path below accordingly:

- **Package manager** — check `packageManager` in `package.json`, else the lockfile
  (`pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, else npm). Use it consistently;
  the examples below show `npm`/`npx` — substitute `yarn`/`yarn dlx` or
  `pnpm`/`pnpm dlx` as appropriate.
- **Plugin type & entry point** — panel/data source/app; entry is `src/module.ts`
  or `src/module.tsx`. This is where translations get initialized.
- **Scenes** — whether `@grafana/scenes` is a dependency (changes the init call).
- **Current i18n state** — is `@grafana/i18n` installed? Is there a `languages`
  field in `plugin.json`? An `i18next.config.ts`? An `i18n-extract` script? Any
  existing/custom translation layer that this work must replace or align with?
- **Grafana version** — `dependencies.grafanaDependency` in `plugin.json`; it must
  allow ≥ 12.1.0.

If the plugin already has a **custom/hand-rolled** i18n layer, decide explicitly
whether to migrate it to `@grafana/i18n` or leave it; do not let two systems cover
the same strings. When the intended scope is unclear, ask the user before writing code.

## Step 1 — Enable the feature toggle (Grafana 12.1.0 only)

Only exactly **12.1.0** needs this; 12.2.0+ has it on by default. If a local dev
Grafana is 12.1.0, enable it in `docker-compose.yaml`:

```yaml
services:
  grafana:
    environment:
      GF_FEATURE_TOGGLES_ENABLE: localizationForPlugins
```

## Step 2 — Declare languages in `plugin.json`

```jsonc
"dependencies": {
  "grafanaDependency": ">=12.1.0",   // or higher; must allow 12.1.0+
  "plugins": []
},
"languages": ["en-US", "es-ES"]      // list every locale you will ship
```

Use BCP-47 tags (`en-US`, `zh-CN`, …). **Any `plugin.json` change requires
restarting the Grafana server to take effect — remind the user.** Do not change the
plugin `id` or `type`.

## Step 3 — Sync build config via create-plugin

The i18n webpack/build plumbing lives in the create-plugin–managed `.config/`
folder. **Do not hand-edit `.config/`** — regenerate it with the official updater:

```bash
npx @grafana/create-plugin@latest update
```

Review the diff and keep it scoped to what i18n needs.

## Step 4 — Initialize translations at plugin load

In the plugin entry module (`src/module.ts[x]`):

```typescript
import { initPluginTranslations } from '@grafana/i18n';
import pluginJson from './plugin.json';

// Without @grafana/scenes:
await initPluginTranslations(pluginJson.id);
```

If the plugin uses `@grafana/scenes`, pass its resource loader:

```typescript
import { loadResources } from '@grafana/scenes';
await initPluginTranslations(pluginJson.id, [loadResources]);
```

Verify the module still loads (typecheck + dev build) after adding the top-level
`await`.

## Step 5 — Mark strings for translation

Import from `@grafana/i18n`. Use **stable, namespaced keys**
(e.g. `components.simplePanel.seriesCount`), and always provide an English default.

- **Non-JSX** (option builders, plain functions): `t('some.key', 'Default text')`.
- **JSX**: the `<Trans>` component — it handles interpolation and embedded elements:

  ```tsx
  import { Trans } from '@grafana/i18n';

  <Trans i18nKey="components.simplePanel.seriesCount">
    Number of series: {{ numberOfSeries: data.series.length }}
  </Trans>
  ```

- **Pluralization** — use the `count` option, never hand-rolled logic:

  ```typescript
  t('panel.counts.folder', '', {
    count: folderCount,
    defaultValue_one: '{{count}} folder',
    defaultValue_other: '{{count}} folders',
  });
  ```
  ```tsx
  <Trans i18nKey="panel.routes.view" count={routes.length}
         tOptions={{ defaultValue_one: 'View route', defaultValue_other: 'View routes' }}>
    View route
  </Trans>
  ```

Do not call `t()` at module top level (the translations aren't loaded yet) — call
it inside components/functions.

## Step 6 — Extract translations with i18next-cli

Install:

```bash
npm install --save-dev i18next-cli
```

Create `i18next.config.ts` at the plugin root:

```typescript
import { defineConfig } from 'i18next-cli';
import pluginJson from './src/plugin.json';

export default defineConfig({
  locales: pluginJson.languages,
  extract: {
    input: ['src/**/*.{tsx,ts}'],
    output: 'src/locales/{{language}}/{{namespace}}.json',
    defaultNS: pluginJson.id,
    functions: ['t', '*.t'],
    transComponents: ['Trans'],
  },
});
```

Add a script and run it:

```jsonc
"scripts": { "i18n-extract": "i18next-cli extract --sync-primary" }
```
```bash
npm run i18n-extract
```

The primary locale's JSON is filled from your default strings; **translate every
other locale's JSON by hand** (or via your translation workflow). Re-run extraction
whenever strings change.

## Step 7 — Expected file layout

```
<plugin-root>/
├── src/
│   ├── locales/
│   │   ├── en-US/<plugin-id>.json
│   │   └── es-ES/<plugin-id>.json
│   ├── module.ts[x]
│   └── plugin.json
├── i18next.config.ts
├── docker-compose.yaml
└── package.json
```

## Step 8 — Enforce with ESLint (optional but recommended)

Add the Grafana i18n rules so untranslated strings fail lint. Extend the plugin's
existing ESLint config rather than forking a new one:

```javascript
import grafanaI18nPlugin from '@grafana/i18n/eslint-plugin';

// within your flat config:
{
  name: 'grafana/i18n-rules',
  plugins: { '@grafana/i18n': grafanaI18nPlugin },
  rules: {
    '@grafana/i18n/no-untranslated-strings': ['error', { calleesToIgnore: ['^css$', 'use[A-Z].*'] }],
    '@grafana/i18n/no-translation-top-level': 'error',
    '@grafana/i18n/t-plural-defaults': 'error',
    '@grafana/i18n/trans-plural-defaults': 'error',
  },
}
```

Scope/ignore the rules for any vendored or generated code that shouldn't be linted.

## Verify

- Typecheck, lint, and build with the project's own scripts (e.g. `npm run
  typecheck`, `npm run lint`, `npm run build`, `npm run test:ci`).
- Run the plugin locally, then switch the Grafana **user/org language** (Profile →
  Language) and confirm the UI strings swap for every declared locale.

## Definition of done

- [ ] Official doc fetched and this run reconciled against it.
- [ ] `plugin.json` `languages` lists every shipped locale; `grafanaDependency`
      allows ≥ 12.1.0; user reminded to **restart Grafana**.
- [ ] `initPluginTranslations` wired into the entry module (with `loadResources`
      if scenes-based).
- [ ] All user-facing strings use `t()` / `<Trans>` with stable keys; no top-level
      `t()` calls.
- [ ] Extraction config + script in place; **every** locale's JSON is complete.
- [ ] `.config/` regenerated via create-plugin, not hand-edited; plugin `id`/`type`
      unchanged.
- [ ] Typecheck/lint/build pass; language toggle verified in a running Grafana.