import React from 'react';
import { PluginPage } from '@grafana/runtime';
import { Alert } from '@grafana/ui';
import { useWorkspace } from '../context/WorkspaceContext';
import { UModelRoot } from '../design/ThemeBridge';
import { useI18n } from '../i18n';
import { WorkspaceSelect } from './WorkspaceSelect';

// Shared page shell: wraps content in a Grafana PluginPage with the workspace
// switcher in the header actions, applies the UModel theme bridge, and gates the
// page content on a selected workspace so child pages can assume one exists.
export function WorkspacePage({ children }: { children?: React.ReactNode }) {
  const { workspace } = useWorkspace();
  const { t } = useI18n();

  return (
    <PluginPage actions={<WorkspaceSelect />}>
      <UModelRoot>
        {workspace ? (
          children
        ) : (
          <Alert title={t('common.noWorkspace.title')} severity="info">
            {t('common.noWorkspace.detail')}
          </Alert>
        )}
      </UModelRoot>
    </PluginPage>
  );
}
