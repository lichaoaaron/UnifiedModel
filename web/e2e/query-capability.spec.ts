import { test, expect } from '@playwright/test'

const TOPO_DIRECT = `.topo | graph-call getDirectRelations([(:"devops@devops.service" {__entity_id__: '10000000000000000000000000000101'})]) | project src,relation,dest | limit 20`

test.describe('Query capability via UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    const demoCard = page.locator('.workspace-id', { hasText: 'demo' }).first()
    await expect(demoCard).toBeVisible({ timeout: 10_000 })
    await demoCard.click()
    await expect(page.locator('text=MModel Explorer')).toBeVisible({ timeout: 5_000 })
  })

  test('workspace landing shows demo workspace', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.workspace-id', { hasText: 'demo' }).first()).toBeVisible({ timeout: 10_000 })
  })

  test('mmodel query returns rows', async ({ page }) => {
    await page.locator('text=Query').click()
    await expect(page.locator('text=Unified SPL Query')).toBeVisible()

    const textarea = page.locator('textarea').first()
    await textarea.fill(".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20")
    await page.locator('button:has-text("Execute")').click()

    await expect(page.locator('.om-table tbody tr').first()).toBeVisible({ timeout: 10_000 })
    const rowCount = await page.locator('.om-table tbody tr').count()
    expect(rowCount).toBeGreaterThanOrEqual(10)
  })

  test('entity query finds checkout service', async ({ page }) => {
    await page.locator('text=Query').click()

    const textarea = page.locator('textarea').first()
    await textarea.fill(".entity with(domain='devops', name='devops.service', query='checkout', topk=20) | project __entity_id__,display_name,status,owner")
    await page.locator('button:has-text("Execute")').click()

    await expect(page.locator('.om-table')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.om-table').locator('text=checkout').first()).toBeVisible()
  })

  test('topo query returns direct relations', async ({ page }) => {
    await page.locator('text=Query').click()

    const textarea = page.locator('textarea').first()
    await textarea.fill(TOPO_DIRECT)
    await page.locator('button:has-text("Execute")').click()

    await expect(page.locator('.om-table tbody tr').first()).toBeVisible({ timeout: 10_000 })
  })

  test('explain shows provider info', async ({ page }) => {
    await page.locator('text=Query').click()

    const textarea = page.locator('textarea').first()
    await textarea.fill(".mmodel with(kind='entity_set') | limit 5")
    await page.locator('button:has-text("Explain")').click()

    await expect(page.locator('text=memory')).toBeVisible({ timeout: 10_000 })
  })

  test('explorer view renders graph', async ({ page }) => {
    await expect(page.locator('text=MModel Explorer')).toBeVisible()
    await page.waitForTimeout(2_000)
    const hasContent = await page.locator('.react-flow, [data-testid="explorer"], canvas, svg').first().isVisible().catch(() => false)
    expect(hasContent || (await page.locator('text=entity_set').count()) > 0).toBeTruthy()
  })

  test('agent view shows discovery tools', async ({ page }) => {
    await page.locator('text=Agent').click()
    await expect(page.locator('strong', { hasText: 'query_spl_execute' }).first()).toBeVisible({ timeout: 10_000 })
  })
})
