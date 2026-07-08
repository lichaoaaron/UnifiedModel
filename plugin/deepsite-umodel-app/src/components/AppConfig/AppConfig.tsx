import React, { ChangeEvent, useState } from 'react';
import { lastValueFrom } from 'rxjs';
import { css } from '@emotion/css';
import { AppPluginMeta, GrafanaTheme2, PluginConfigPageProps, PluginMeta } from '@grafana/data';
import { getBackendSrv } from '@grafana/runtime';
import { Button, Field, FieldSet, Input, SecretInput, useStyles2 } from '@grafana/ui';
import { t } from '@grafana/i18n';
import { testIds } from '../testIds';

type AppPluginSettings = {
  apiUrl?: string;
  diagnosisUrl?: string;
};

type State = {
  // The URL to reach our custom API.
  apiUrl: string;
  // Base URL of the separate diagnosis service the Diagnosis page streams from
  // (optional — only that page needs it).
  diagnosisUrl: string;
  // Tells us if the API key secret is set.
  isApiKeySet: boolean;
  // A secret key for our custom API.
  apiKey: string;
};

export interface AppConfigProps extends PluginConfigPageProps<AppPluginMeta<AppPluginSettings>> {}

const AppConfig = ({ plugin }: AppConfigProps) => {
  const s = useStyles2(getStyles);
  const { enabled, pinned, jsonData, secureJsonFields } = plugin.meta;
  const [state, setState] = useState<State>({
    apiUrl: jsonData?.apiUrl || '',
    diagnosisUrl: jsonData?.diagnosisUrl || '',
    apiKey: '',
    isApiKeySet: Boolean(secureJsonFields?.apiKey),
  });

  // Only the UModel server URL is required. The API key is optional because
  // umodel-server is currently unauthenticated.
  const isSubmitDisabled = !state.apiUrl;

  const onResetApiKey = () =>
    setState({
      ...state,
      apiKey: '',
      isApiKeySet: false,
    });

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    setState({
      ...state,
      [event.target.name]: event.target.value.trim(),
    });
  };

  const onSubmit = () => {
    if (isSubmitDisabled) {
      return;
    }

    updatePluginAndReload(plugin.meta.id, {
      enabled,
      pinned,
      jsonData: {
        apiUrl: state.apiUrl,
        diagnosisUrl: state.diagnosisUrl,
      },
      // This cannot be queried later by the frontend.
      // We don't want to override it in case it was set previously and left untouched now.
      secureJsonData: state.isApiKeySet
        ? undefined
        : {
            apiKey: state.apiKey,
          },
    });
  };

  return (
    <form onSubmit={onSubmit}>
      <FieldSet label={t('appConfig.fieldSet.apiSettings', 'API Settings')}>
        <Field
          label={t('appConfig.apiKey.label', 'API Key')}
          description={t(
            'appConfig.apiKey.description',
            'Optional bearer token for the UModel server. Leave empty — the server is currently unauthenticated.'
          )}
        >
          <SecretInput
            width={60}
            id="config-api-key"
            data-testid={testIds.appConfig.apiKey}
            name="apiKey"
            value={state.apiKey}
            isConfigured={state.isApiKeySet}
            placeholder={t('appConfig.apiKey.placeholder', 'Your secret API key')}
            onChange={onChange}
            onReset={onResetApiKey}
          />
        </Field>

        <Field
          label={t('appConfig.apiUrl.label', 'API Url')}
          description={t(
            'appConfig.apiUrl.description',
            'Base URL of the UModel server (cmd/umodel-server). Must be reachable from the Grafana server — never use localhost when Grafana runs in Docker (e.g. http://host.docker.internal:8080 for local dev).'
          )}
          className={s.marginTop}
        >
          <Input
            width={60}
            name="apiUrl"
            id="config-api-url"
            data-testid={testIds.appConfig.apiUrl}
            value={state.apiUrl}
            placeholder={t('appConfig.apiUrl.placeholder', 'E.g.: http://host.docker.internal:8080')}
            onChange={onChange}
          />
        </Field>

        <Field
          label={t('appConfig.diagnosisUrl.label', 'Diagnosis Url')}
          description={t(
            'appConfig.diagnosisUrl.description',
            "Optional. Base URL of the diagnosis service used by the Diagnosis page (SSE). Reachable from the Grafana server, same as API Url (e.g. http://host.docker.internal:18000). Leave empty if you don't use the Diagnosis page."
          )}
          className={s.marginTop}
        >
          <Input
            width={60}
            name="diagnosisUrl"
            id="config-diagnosis-url"
            value={state.diagnosisUrl}
            placeholder={t('appConfig.diagnosisUrl.placeholder', 'E.g.: http://host.docker.internal:18000')}
            onChange={onChange}
          />
        </Field>

        <div className={s.marginTop}>
          <Button type="submit" data-testid={testIds.appConfig.submit} disabled={isSubmitDisabled}>
            {t('appConfig.submit', 'Save API settings')}
          </Button>
        </div>
      </FieldSet>
    </form>
  );
};

export default AppConfig;

const getStyles = (theme: GrafanaTheme2) => ({
  colorWeak: css`
    color: ${theme.colors.text.secondary};
  `,
  marginTop: css`
    margin-top: ${theme.spacing(3)};
  `,
});

const updatePluginAndReload = async (pluginId: string, data: Partial<PluginMeta<AppPluginSettings>>) => {
  try {
    await updatePlugin(pluginId, data);

    // Reloading the page as the changes made here wouldn't be propagated to the actual plugin otherwise.
    // This is not ideal, however unfortunately currently there is no supported way for updating the plugin state.
    window.location.reload();
  } catch (e) {
    console.error('Error while updating the plugin', e);
  }
};

const updatePlugin = async (pluginId: string, data: Partial<PluginMeta>) => {
  const response = await getBackendSrv().fetch({
    url: `/api/plugins/${pluginId}/settings`,
    method: 'POST',
    data,
  });

  return lastValueFrom(response);
};
