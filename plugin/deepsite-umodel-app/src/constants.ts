import pluginJson from './plugin.json';

export const PLUGIN_BASE_URL = `/a/${pluginJson.id}`;

// Route names; each maps to a plugin.json `includes` nav entry of the same path
// suffix (e.g. ROUTES.UModel -> /a/<id>/umodel). Segments mirror the standalone
// web app's routes.ts (WorkspaceView segments) so both frontends share one
// naming scheme.
export enum ROUTES {
  UModel = 'umodel',
  Topo = 'entity-topo',
  Query = 'query',
  Imports = 'imports',
  Settings = 'settings',
  ApiDebug = 'api-debug',
  Diagnosis = 'diagnosis',
}

export const DEFAULT_ROUTE = ROUTES.UModel;
