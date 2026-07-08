import React from 'react';
import { Combobox, type ComboboxOption, IconButton, Stack } from '@grafana/ui';
import { useWorkspace } from '../context/WorkspaceContext';
import { t } from '@grafana/i18n';

// Workspace switcher rendered in the page header actions. Reads/writes the
// shared WorkspaceContext; the list is loaded once by the provider.
export function WorkspaceSelect() {
  const { workspace, setWorkspace, workspaces, loading, reload } = useWorkspace();

  const options: Array<ComboboxOption<string>> = workspaces.map((w) => ({
    label: w.name || w.id,
    value: w.id,
    description: w.id !== (w.name || w.id) ? w.id : undefined,
  }));

  return (
    <Stack direction="row" alignItems="center" gap={1}>
      <Combobox<string>
        width={28}
        placeholder={t('common.selectWorkspace', 'Select workspace')}
        options={options}
        value={workspace}
        loading={loading}
        isClearable
        onChange={(opt) => setWorkspace(opt?.value ?? null)}
      />
      <IconButton name="sync" tooltip={t('common.reloadWorkspaces', 'Reload workspaces')} onClick={() => reload()} />
    </Stack>
  );
}
