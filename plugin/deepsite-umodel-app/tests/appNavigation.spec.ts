import { test, expect } from './fixtures';
import { ROUTES } from '../src/constants';

// Pages behind the workspace gate: with no workspace selected they render the
// WorkspacePage shell (a workspace selector in the header + a "No workspace
// selected" alert). This assertion is stable regardless of whether the UModel
// backend is reachable, because the provider never auto-selects a workspace.
// All seven nav pages are gated (the API Debugger prefills the {workspace} path
// parameter and the Diagnosis workbench takes a workspaceId, so both are gated).
const GATED_ROUTES = [
  ROUTES.UModel,
  ROUTES.Topo,
  ROUTES.Query,
  ROUTES.Imports,
  ROUTES.Settings,
  ROUTES.ApiDebug,
  ROUTES.Diagnosis,
];

test.describe('navigating app', () => {
  for (const route of GATED_ROUTES) {
    test(`"${route}" renders the workspace shell`, async ({ gotoPage, page }) => {
      await gotoPage(`/${route}`);
      await expect(page.getByText(/no workspace selected/i)).toBeVisible();
    });
  }

  test('workspace selector is present in the page header', async ({ gotoPage, page }) => {
    await gotoPage(`/${ROUTES.Query}`);
    await expect(page.getByPlaceholder('Select workspace')).toBeVisible();
  });
});