import React, { useEffect, useState } from 'react';
import { css } from '@emotion/css';
import { GrafanaTheme2 } from '@grafana/data';
import { Badge, Button, Checkbox, ConfirmModal, Field, Input, Stack, TextArea, useStyles2 } from '@grafana/ui';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import { t } from '@grafana/i18n';
import { parseJson, stringify } from '../lib/json';
import { notifyError, notifySuccess } from '../utils/notify';
import type { WorkspaceMetadata } from '../api/types';

export default function SettingsPage() {
  return (
    <WorkspacePage>
      <SettingsForm />
    </WorkspacePage>
  );
}

function SettingsForm() {
  const { workspace, api, reload, setWorkspace } = useWorkspace();
  const styles = useStyles2(getStyles);

  const [meta, setMeta] = useState<WorkspaceMetadata | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [labels, setLabels] = useState('{}');
  const [config, setConfig] = useState('{}');
  // Default to merge (not replace), matching the standalone web Settings page —
  // safer than silently wiping existing labels/config on save.
  const [replaceLabels, setReplaceLabels] = useState(false);
  const [replaceConfig, setReplaceConfig] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (!workspace) {
      return;
    }
    let cancelled = false;
    api
      .getWorkspace(workspace)
      .then((w) => {
        if (cancelled) {
          return;
        }
        setMeta(w);
        setName(w.name || workspace);
        setDescription(w.description || '');
        setLabels(stringify(w.labels || {}));
        setConfig(stringify(w.config || {}));
      })
      .catch((err) => notifyError(t('common.loadWorkspaceFailed', 'Failed to load workspace'), err));
    return () => {
      cancelled = true;
    };
  }, [api, workspace]);

  // Gated by WorkspacePage, so a workspace exists; guard keeps types honest.
  if (!workspace) {
    return null;
  }

  const save = async () => {
    setBusy(true);
    try {
      const next = await api.updateWorkspace(workspace, {
        name,
        description,
        labels: parseJson<Record<string, string>>(labels, 'Labels JSON'),
        config: parseJson<Record<string, Record<string, unknown>>>(config, 'Config JSON'),
        if_match_version: meta?.resource_version,
        replace_labels: replaceLabels,
        replace_config: replaceConfig,
      });
      setMeta(next);
      notifySuccess(t('common.workspaceSaved', 'Workspace saved'));
      void reload();
    } catch (err) {
      notifyError(t('common.saveFailed', 'Save failed'), err);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setConfirmOpen(false);
    try {
      await api.deleteWorkspace(workspace);
      notifySuccess(t('common.workspaceDeleted', 'Workspace deleted'));
      setWorkspace(null);
      void reload();
    } catch (err) {
      notifyError(t('common.deleteFailed', 'Delete failed'), err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack direction="row" gap={2} wrap="wrap">
      <div className={styles.col}>
        <Stack direction="row" gap={1} alignItems="center">
          <h4 className={styles.heading}>{t('settings.title', 'Workspace Settings')}</h4>
          {/* eslint-disable-next-line @grafana/i18n/no-untranslated-strings -- version badge shows data, not translatable copy */}
          {meta && <Badge text={`v${meta.resource_version}`} color={meta.status === 'active' ? 'green' : 'orange'} />}
        </Stack>

        <Field label={t('settings.name', 'Name')}>
          <Input value={name} onChange={(e) => setName(e.currentTarget.value)} />
        </Field>
        <Field label={t('settings.description', 'Description')}>
          <Input value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        </Field>
        <Field label={t('settings.labelsJson.label', 'Labels JSON')}>
          <TextArea
            rows={5}
            value={labels}
            onChange={(e) => setLabels(e.currentTarget.value)}
            className={styles.mono}
          />
        </Field>
        <Checkbox
          className={styles.checkbox}
          label={t('settings.replaceLabels', 'replace labels')}
          value={replaceLabels}
          onChange={(e) => setReplaceLabels(e.currentTarget.checked)}
        />
        <Field label={t('settings.configJson.label', 'Custom Config JSON')}>
          <TextArea
            rows={6}
            value={config}
            onChange={(e) => setConfig(e.currentTarget.value)}
            className={styles.mono}
          />
        </Field>
        <Checkbox
          className={styles.checkbox}
          label={t('settings.replaceConfig', 'replace config')}
          value={replaceConfig}
          onChange={(e) => setReplaceConfig(e.currentTarget.checked)}
        />

        <Stack direction="row" gap={1}>
          <Button variant="destructive" icon="trash-alt" disabled={busy} onClick={() => setConfirmOpen(true)}>
            {t('settings.deleteWorkspace', 'Delete workspace')}
          </Button>
          <Button variant="primary" icon="save" disabled={busy} onClick={save}>
            {t('common.save', 'Save')}
          </Button>
        </Stack>
      </div>

      <div className={styles.col}>
        <h4 className={styles.heading}>{t('settings.metadata.label', 'Metadata')}</h4>
        <pre className={styles.pre}>
          {meta ? stringify(meta) : t('settings.metadata.notLoaded', 'Workspace metadata is not loaded.')}
        </pre>
      </div>

      <ConfirmModal
        isOpen={confirmOpen}
        title={t('settings.deleteConfirm.title', 'Confirm deletion')}
        // eslint-disable-next-line @grafana/i18n/no-untranslated-strings -- both fragments are already localized via t(); the template literal only joins them
        body={`${t('settings.deleteConfirm.detail', 'Delete workspace "{{workspace}}"?', { workspace: name })} ${t('settings.deleteConfirm.tombstone', 'This creates a tombstone for the workspace ID, so the same ID cannot be recreated later.')}`}
        confirmText={t('settings.deleteConfirm.confirm', 'Delete workspace')}
        onConfirm={remove}
        onDismiss={() => setConfirmOpen(false)}
      />
    </Stack>
  );
}

const getStyles = (theme: GrafanaTheme2) => ({
  col: css`
    flex: 1 1 360px;
    min-width: 320px;
    display: flex;
    flex-direction: column;
    gap: ${theme.spacing(1)};
  `,
  heading: css`
    margin: 0;
  `,
  checkbox: css`
    align-self: flex-start;
  `,
  mono: css`
    font-family: ${theme.typography.fontFamilyMonospace};
  `,
  pre: css`
    margin: 0;
    padding: ${theme.spacing(1)};
    background: ${theme.colors.background.secondary};
    border: 1px solid ${theme.colors.border.weak};
    border-radius: ${theme.shape.radius.default};
    overflow: auto;
    max-height: 60vh;
    font-family: ${theme.typography.fontFamilyMonospace};
    font-size: ${theme.typography.bodySmall.fontSize};
  `,
});
