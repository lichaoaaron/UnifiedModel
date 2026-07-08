import { defineConfig } from 'i18next-cli';
import pluginJson from './src/plugin.json';

// Grafana plugin i18n extraction.
// Docs: https://grafana.com/developers/plugin-tools/how-to-guides/plugin-internationalization
export default defineConfig({
  locales: pluginJson.languages,
  extract: {
    input: ['src/**/*.{tsx,ts}'],
    output: 'src/locales/{{language}}/{{namespace}}.json',
    defaultNS: pluginJson.id,
    functions: ['t', '*.t'],
    transComponents: ['Trans'],
    // The JSON catalogs are the source of truth (ported wholesale from the previous
    // TS dictionaries). They include keys referenced only dynamically — API-debugger
    // spec titles/descriptions, query examples, import modes, count units — which
    // static extraction cannot see. Never prune them.
    removeUnusedKeys: false,
    // `count` is used purely as an interpolation value (Chinese-style "N items",
    // no grammatical plural). Manual singular/plural pairs use explicit `*Other`
    // keys instead. Don't let extraction synthesize i18next `_one`/`_other`
    // variants — the empty secondary-language variants would shadow the real value.
    disablePlurals: true,
  },
});