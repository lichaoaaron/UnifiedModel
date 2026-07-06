import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { AppRootProps, PluginType } from '@grafana/data';
import { render, waitFor } from '@testing-library/react';
import App from './App';

// The WorkspaceProvider loads workspaces on mount via getBackendSrv. Mock it to
// return an empty list so the default route renders the "no workspace" gate.
jest.mock('@grafana/runtime', () => {
  const actual = jest.requireActual('@grafana/runtime');
  const { of } = jest.requireActual('rxjs');
  return {
    ...actual,
    getBackendSrv: () => ({
      fetch: () => of({ data: JSON.stringify({ items: [] }) }),
    }),
  };
});

describe('Components/App', () => {
  let props: AppRootProps;

  beforeEach(() => {
    props = {
      basename: 'a/deepsite-umodel-app',
      meta: {
        id: 'deepsite-umodel-app',
        name: 'Umodel',
        type: PluginType.app,
        enabled: true,
        jsonData: {},
      },
      query: {},
      path: '',
      onNavChanged: jest.fn(),
    } as unknown as AppRootProps;
  });

  test('renders the workspace gate without an error', async () => {
    const { queryByText } = render(
      <MemoryRouter>
        <App {...props} />
      </MemoryRouter>
    );

    // App, routes and pages are lazy loaded; wait for the default page to render.
    await waitFor(() => expect(queryByText(/no workspace selected/i)).toBeInTheDocument(), { timeout: 2000 });
  });
});
