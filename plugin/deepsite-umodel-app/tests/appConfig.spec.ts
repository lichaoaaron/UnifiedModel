import { test, expect } from './fixtures';

test('saves the app configuration (API Url + API Key)', async ({ appConfigPage, page }) => {
  const apiKey = page.getByRole('textbox', { name: 'API Key' });
  await expect(apiKey).toBeVisible();

  // API Key is optional and stored in secureJsonData. When one is already
  // configured the input is disabled ("configured") — reset it first, and wait
  // until it becomes editable before filling.
  if (await apiKey.isDisabled()) {
    await page.getByRole('button', { name: /reset/i }).click();
    await expect(apiKey).toBeEnabled();
  }
  await apiKey.fill('secret-api-key');

  // Plugin app settings are a single global record shared across tests. Write the
  // same URL the functional test uses (when provided) so parallel runs don't
  // clobber each other's apiUrl.
  const apiUrl = process.env.E2E_UMODEL_API_URL || 'http://umodel.example.com:8080';
  await page.getByRole('textbox', { name: 'API Url' }).clear();
  await page.getByRole('textbox', { name: 'API Url' }).fill(apiUrl);

  // Persist and assert Grafana accepted the settings POST.
  const saveResponse = appConfigPage.waitForSettingsResponse();
  await page.getByRole('button', { name: /Save API settings/i }).click();
  await expect(saveResponse).toBeOK();
});