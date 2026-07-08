import React from 'react';
import { PluginPage } from '@grafana/runtime';
import { Alert } from '@grafana/ui';
import { useWorkspace } from '../context/WorkspaceContext';
import { UModelRoot } from '../design/ThemeBridge';
import { t } from '@grafana/i18n';
import { WorkspaceSelect } from './WorkspaceSelect';

// Shared page shell: wraps content in a Grafana PluginPage with the workspace
// switcher in the header actions, applies the UModel theme bridge, and gates the
// page content on a selected workspace so child pages can assume one exists.
export function WorkspacePage({ children }: { children?: React.ReactNode }) {
  const { workspace } = useWorkspace();

  return (
    <PluginPage actions={<WorkspaceSelect />}>
      <UModelRoot>
        {workspace ? (
          children
        ) : (
          <Alert title={t('common.noWorkspace.title', 'No workspace selected')} severity="info">
            {t(
              'common.noWorkspace.detail',
              'Pick a workspace from the selector in the top-right to begin. If the list is empty, open the plugin Configuration page and set the UModel server URL (apiUrl).'
            )}
          </Alert>
        )}
      </UModelRoot>
    </PluginPage>
  );
}
