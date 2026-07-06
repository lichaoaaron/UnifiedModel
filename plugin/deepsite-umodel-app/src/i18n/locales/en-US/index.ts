import { enUSApiDebugger } from './apiDebugger';
import { enUSCommon } from './common';
import { enUSEntityTopoExplorer } from './entityTopoExplorer';
import { enUSImports } from './imports';
import { enUSQuery } from './query';
import { enUSSettings } from './settings';
import { enUSUModelExplorer } from './umodelExplorer';

// Mirrors web/src/i18n/locales/en-US minus the `landing` namespace: the
// workspace landing page is not ported (Grafana nav + WorkspaceSelect replace it).
export const enUS = {
  ...enUSApiDebugger,
  ...enUSCommon,
  ...enUSEntityTopoExplorer,
  ...enUSImports,
  ...enUSQuery,
  ...enUSUModelExplorer,
  ...enUSSettings,
} as const;
