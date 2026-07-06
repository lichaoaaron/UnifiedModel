import React, { useState } from 'react';
import { css } from '@emotion/css';
import { GrafanaTheme2, type IconName } from '@grafana/data';
import { Button, Field, RadioButtonGroup, Stack, Tab, TabsBar, TextArea, useStyles2 } from '@grafana/ui';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import { useI18n, type MessageKey } from '../i18n';
import { asArray, parseJson, stringify } from '../lib/json';
import { notifyError, notifySuccess } from '../utils/notify';
import { parseUModelElementsFromJson } from '../features/umodel/UModelPage';

type ImportMode = 'umodel' | 'entity' | 'expire';

const MODES: Array<{ value: ImportMode; labelKey: MessageKey; icon: IconName }> = [
  { value: 'umodel', labelKey: 'imports.mode.umodel', icon: 'upload' },
  { value: 'entity', labelKey: 'imports.mode.entity', icon: 'database' },
  { value: 'expire', labelKey: 'imports.mode.expire', icon: 'check-circle' },
];

const sampleElement = `[
  {
    "kind": "entity_set",
    "domain": "devops",
    "name": "devops.service",
    "spec": { "fields": {} }
  }
]`;

const sampleEntity = `[
  {
    "__domain__": "devops",
    "__entity_type__": "devops.service",
    "__entity_id__": "10000000000000000000000000000101",
    "__method__": "Update",
    "__first_observed_time__": 100,
    "__last_observed_time__": 200,
    "display_name": "checkout-service"
  }
]`;

const sampleRelation = `[
  {
    "__src_domain__": "devops",
    "__src_entity_type__": "devops.service",
    "__src_entity_id__": "10000000000000000000000000000101",
    "__dest_domain__": "devops",
    "__dest_entity_type__": "devops.service",
    "__dest_entity_id__": "10000000000000000000000000000102",
    "__relation_type__": "calls",
    "__method__": "Update",
    "__first_observed_time__": 100,
    "__last_observed_time__": 200
  }
]`;

export default function ImportsPage() {
  return (
    <WorkspacePage>
      <ImportsForm />
    </WorkspacePage>
  );
}

function ImportsForm() {
  const { workspace, api } = useWorkspace();
  const { t } = useI18n();
  const styles = useStyles2(getStyles);

  const expireKindOptions = [
    { label: t('imports.kind.entity'), value: 'entity' as const },
    { label: t('imports.kind.relation'), value: 'relation' as const },
  ];

  const [mode, setMode] = useState<ImportMode>('umodel');
  const [elementsJson, setElementsJson] = useState(sampleElement);
  const [entityJson, setEntityJson] = useState(sampleEntity);
  const [relationJson, setRelationJson] = useState(sampleRelation);
  const [expireKind, setExpireKind] = useState<'entity' | 'relation'>('entity');
  const [expireIds, setExpireIds] = useState('["devops/devops.service/10000000000000000000000000000101"]');
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  // Gated by WorkspacePage, so a workspace exists; guard keeps types honest.
  if (!workspace) {
    return null;
  }

  const run = async (action: 'validate' | 'write' | 'expire') => {
    setBusy(true);
    setResult(null);
    try {
      if (mode === 'umodel') {
        const elements = parseUModelElementsFromJson(elementsJson);
        setResult(
          action === 'validate'
            ? await api.validateUModel(workspace, elements)
            : await api.putUModel(workspace, elements)
        );
      } else if (mode === 'entity') {
        const entities = asArray(
          parseJson<Record<string, unknown> | Array<Record<string, unknown>>>(entityJson, 'Entity JSON')
        );
        const relations = asArray(
          parseJson<Record<string, unknown> | Array<Record<string, unknown>>>(relationJson, 'Relation JSON')
        );
        setResult({
          entities: entities.length > 0 ? await api.writeEntities(workspace, { entities }) : null,
          relations: relations.length > 0 ? await api.writeRelations(workspace, { relations }) : null,
        });
      } else {
        const ids = parseJson<string[]>(expireIds, 'IDs JSON');
        setResult(
          expireKind === 'entity'
            ? await api.expireEntities(workspace, { ids })
            : await api.expireRelations(workspace, { ids })
        );
      }
      notifySuccess(t('common.done'));
    } catch (err) {
      notifyError(t('common.requestFailed'), err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack direction="row" gap={2} wrap="wrap">
      <div className={styles.col}>
        <TabsBar>
          {MODES.map((m) => (
            <Tab
              key={m.value}
              label={t(m.labelKey)}
              icon={m.icon}
              active={mode === m.value}
              onChangeTab={() => setMode(m.value)}
            />
          ))}
        </TabsBar>

        {mode === 'umodel' && (
          <>
            <Field label={t('imports.field.umodelElements')}>
              <TextArea
                rows={16}
                value={elementsJson}
                onChange={(e) => setElementsJson(e.currentTarget.value)}
                className={styles.mono}
              />
            </Field>
            <Stack direction="row" gap={1}>
              <Button variant="secondary" icon="check-circle" disabled={busy} onClick={() => run('validate')}>
                {t('imports.action.validate')}
              </Button>
              <Button variant="primary" icon="arrow-up" disabled={busy} onClick={() => run('write')}>
                {t('imports.action.put')}
              </Button>
            </Stack>
          </>
        )}

        {mode === 'entity' && (
          <>
            <Field label={t('imports.field.entities')}>
              <TextArea
                rows={9}
                value={entityJson}
                onChange={(e) => setEntityJson(e.currentTarget.value)}
                className={styles.mono}
              />
            </Field>
            <Field label={t('imports.field.relations')}>
              <TextArea
                rows={9}
                value={relationJson}
                onChange={(e) => setRelationJson(e.currentTarget.value)}
                className={styles.mono}
              />
            </Field>
            <Stack direction="row" gap={1}>
              <Button variant="primary" icon="database" disabled={busy} onClick={() => run('write')}>
                {t('imports.action.write')}
              </Button>
            </Stack>
          </>
        )}

        {mode === 'expire' && (
          <>
            <Field label={t('imports.field.kind')}>
              <RadioButtonGroup
                options={expireKindOptions}
                value={expireKind}
                onChange={(v) => setExpireKind(v ?? 'entity')}
              />
            </Field>
            <Field label={t('imports.field.ids')}>
              <TextArea
                rows={6}
                value={expireIds}
                onChange={(e) => setExpireIds(e.currentTarget.value)}
                className={styles.mono}
              />
            </Field>
            <Stack direction="row" gap={1}>
              <Button variant="primary" icon="check-circle" disabled={busy} onClick={() => run('expire')}>
                {t('imports.action.expire')}
              </Button>
            </Stack>
          </>
        )}
      </div>

      <div className={styles.col}>
        <h4 className={styles.heading}>{t('imports.result.title')}</h4>
        <pre className={styles.pre}>{result ? stringify(result) : t('imports.result.empty.title')}</pre>
      </div>
    </Stack>
  );
}

const getStyles = (theme: GrafanaTheme2) => ({
  col: css`
    flex: 1 1 420px;
    min-width: 320px;
    display: flex;
    flex-direction: column;
    gap: ${theme.spacing(1)};
  `,
  heading: css`
    margin: 0;
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
    max-height: 70vh;
    font-family: ${theme.typography.fontFamilyMonospace};
    font-size: ${theme.typography.bodySmall.fontSize};
  `,
});
