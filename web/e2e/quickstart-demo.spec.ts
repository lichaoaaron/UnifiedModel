import { test, expect } from '@playwright/test'

const API = 'http://localhost:8080'

async function queryAPI(query: string, parameters?: Record<string, unknown>) {
  const resp = await fetch(`${API}/api/v1/query/demo/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, parameters }),
  })
  if (!resp.ok) throw new Error(`query failed: ${resp.status} ${await resp.text()}`)
  return resp.json() as Promise<{ rows: Record<string, unknown>[]; columns: string[] }>
}

test.describe('Quickstart demo data validation', () => {
  test('workspace exists', async () => {
    const resp = await fetch(`${API}/api/v1/workspaces`)
    expect(resp.ok).toBeTruthy()
    const data = (await resp.json()) as { items: { id: string }[] }
    const ids = data.items.map((w) => w.id)
    expect(ids).toContain('demo')
  })

  test('model has sufficient entity_sets', async () => {
    const result = await queryAPI(".mmodel with(kind='entity_set') | limit 100")
    expect(result.rows.length).toBeGreaterThanOrEqual(30)
  })

  test('devops entities exist', async () => {
    const result = await queryAPI(".entity with(domain='devops', name='devops.service') | limit 20")
    expect(result.rows.length).toBeGreaterThan(0)
  })

  test('topology has relations', async () => {
    const result = await queryAPI(
      `.topo | graph-call getDirectRelations([(:"devops@devops.service" {__entity_id__: '10000000000000000000000000000101'})]) | limit 10`,
    )
    expect(result.rows.length).toBeGreaterThan(0)
  })

  test('all domains present in model', async () => {
    for (const domain of ['devops', 'k8s', 'automaker', 'game', 'supplier']) {
      const result = await queryAPI(`.mmodel with(kind='entity_set') | where domain = '${domain}' | limit 100`)
      expect(result.rows.length).toBeGreaterThan(0)
    }
  })

  test('cross-domain relations exist', async () => {
    const result = await queryAPI(".topo with(relation_type='maps') | project src,relation,dest | limit 10")
    expect(result.rows.length).toBeGreaterThan(0)
    const row = result.rows[0]
    expect(row.relation).toBe('maps')
  })

  test('entity count matches expected range', async () => {
    const domains = ['devops', 'k8s', 'automaker', 'game', 'supplier']
    let total = 0
    for (const domain of domains) {
      const result = await queryAPI(`.entity with(domain='${domain}') | limit 100`)
      total += result.rows.length
    }
    expect(total).toBeGreaterThanOrEqual(80)
  })

  test('agent discovery returns tools and resources', async () => {
    const resp = await fetch(`${API}/api/v1/agent/demo/discover`)
    expect(resp.ok).toBeTruthy()
    const data = (await resp.json()) as {
      workspace: string
      tools: { name: string }[]
      resources: { uri: string }[]
    }
    expect(data.workspace).toBe('demo')
    expect(data.tools.length).toBeGreaterThan(0)
    expect(data.resources.length).toBeGreaterThan(0)
    expect(data.tools.map((t) => t.name)).toContain('query_spl_execute')
  })
})
