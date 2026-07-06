import pluginJson from '../plugin.json';

// Single source of truth for the plugin id (kept in sync with plugin.json).
export const PLUGIN_ID = pluginJson.id;

// All backend calls go through the plugin's Go backend resource proxy, which
// reverse-proxies to the configured UModel server (apiUrl). The UModelApi client
// targets this base, so e.g. `/api/v1/workspaces` becomes
// `/api/plugins/<id>/resources/api/v1/workspaces`.
export const RESOURCE_BASE = `/api/plugins/${PLUGIN_ID}/resources`;
