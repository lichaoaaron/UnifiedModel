import { defineConfig } from 'eslint/config';
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
]);
