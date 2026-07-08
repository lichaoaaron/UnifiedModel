import { defineConfig } from 'eslint/config';
import grafanaI18nPlugin from '@grafana/i18n/eslint-plugin';
import baseConfig from './.config/eslint.config.mjs';

export default defineConfig([
  {
    ignores: [
      '**/logs',
      '**/*.log',
      '**/npm-debug.log*',
      '**/yarn-debug.log*',
      '**/yarn-error.log*',
      '**/.pnpm-debug.log*',
      '**/node_modules/',
      '.yarn/cache',
      '.yarn/unplugged',
      '.yarn/build-state.yml',
      '.yarn/install-state.gz',
      '**/.pnp.*',
      '**/pids',
      '**/*.pid',
      '**/*.seed',
      '**/*.pid.lock',
      '**/lib-cov',
      '**/coverage',
      '**/dist/',
      '**/artifacts/',
      '**/work/',
      '**/ci/',
      'test-results/',
      'playwright-report/',
      'blob-report/',
      'playwright/.cache/',
      'playwright/.auth/',
      '**/.idea',
      '**/.eslintcache',
    ],
  },
  ...baseConfig,
  {
    // UModel, Topology and Query are near-verbatim ports of the standalone web
    // app's graph editors / query workbench. The newer, React-Compiler-aligned
    // react-hooks rules systematically flag legitimate imperative patterns there
    // (reading a ref during render for popover/canvas positioning, fetch/layout
    // effects, WebGL engine wiring) — too many to suppress inline. Relax only
    // those rules, only for the ported COMPONENT files (*.tsx; pure-logic *.ts
    // stay fully strict).
    // TODO: revisit during the @grafana/ui re-skin pass.
    files: [
      'src/features/umodel/**/*.tsx',
      'src/features/entityTopo/**/*.tsx',
      'src/features/query/**/*.tsx',
      'src/features/apiDebug/**/*.tsx',
      'src/features/diagnosis/**/*.tsx',
    ],
    rules: {
      'react-hooks/refs': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/use-memo': 'off',
      'react/display-name': 'off',
    },
  },
  {
    // umodel/, entityTopo/ and diagnosis/ are pure vendored viz/workbench that we
    // re-sync verbatim from web/; exhaustive-deps fires on their intentional
    // imperative patterns (tick subscriptions, engine-rebuild-on-layout,
    // derived-key effects, streaming callback refs) on every sync, so turn it off
    // wholesale here rather than re-applying per-line disables each time —
    // consistent with the three react-hooks rules already relaxed above for the
    // same dirs. query/ and apiDebug/ deliberately keep exhaustive-deps as an
    // error (they read more like our own pages): it still catches real bugs there
    // — e.g. the QueryPage result-table `columns` memo, fixed with useMemo.
    files: [
      'src/features/umodel/**/*.tsx',
      'src/features/entityTopo/**/*.tsx',
      'src/features/diagnosis/**/*.tsx',
    ],
    rules: {
      'react-hooks/exhaustive-deps': 'off',
    },
  },
  {
    // Enforce Grafana's i18n conventions across our own code:
    // - no-untranslated-strings: every user-facing string goes through `t()` / `<Trans>`.
    // - no-translation-top-level: no `t()` at module top level (translations load
    //   asynchronously via initPluginTranslations in module.tsx).
    // The plural-defaults rules don't exist in this @grafana/i18n version and would
    // not apply anyway — `count` here is a plain interpolation value, not i18next
    // pluralization.
    name: 'grafana/i18n-rules',
    files: ['src/**/*.{ts,tsx}'],
    plugins: { '@grafana/i18n': grafanaI18nPlugin },
    rules: {
      '@grafana/i18n/no-untranslated-strings': ['error', { calleesToIgnore: ['^css$', 'use[A-Z].*'] }],
      '@grafana/i18n/no-translation-top-level': 'error',
    },
  },
  {
    // Opt these dirs out of `no-untranslated-strings` (same spirit as the react-hooks
    // relaxations above; must come after the rule is enabled to win):
    // - umodel / entityTopo: vendored viz re-synced verbatim from web/. The rule
    //   there mostly fires on data/symbol literals (sort-arrow glyphs, `field=value`
    //   labels, composed `title` strings); wrapping them would diverge from web/.
    // - diagnosis: the workbench is Chinese-only by design (symptom-matching logic is
    //   inherently zh), so its hardcoded strings are intentional.
    name: 'grafana/i18n-untranslated-optout',
    files: [
      'src/features/umodel/**/*.tsx',
      'src/features/entityTopo/**/*.tsx',
      'src/features/diagnosis/**/*.tsx',
    ],
    rules: {
      '@grafana/i18n/no-untranslated-strings': 'off',
    },
  },
]);
