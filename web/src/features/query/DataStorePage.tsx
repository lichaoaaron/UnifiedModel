import { useState } from 'react'
import { Play, Route } from 'lucide-react'
import type { QueryResult } from '../../api/types'
import { MModelApi } from '../../api/client'
import { Badge, Button, Field, Panel, Tabs, TextInput } from '../../design/components'
import { formatError } from '../../lib/json'
import { ResultTable } from './QueryPage'

type DataMode = 'entity' | 'topo'

export function DataStorePage({ api, workspaceId }: { api: MModelApi; workspaceId: string }) {
  const [mode, setMode] = useState<DataMode>('entity')
  const [domain, setDomain] = useState('devops')
  const [name, setName] = useState('devops.service')
  const [queryText, setQueryText] = useState('checkout')
  const [seed, setSeed] = useState('10000000000000000000000000000101')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    setError('')
    try {
      const spl = mode === 'entity'
        ? `.entity with(domain='${escapeSPL(domain)}', name='${escapeSPL(name)}', query='${escapeSPL(queryText)}', topk=50) | limit 50`
        : `.topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '${escapeSPL(seed)}'})]) | limit 50`
      setResult(await api.query(workspaceId, { query: spl, limit: 50 }))
    } catch (nextError) {
      setError(formatError(nextError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page-grid">
      <Panel
        title={<strong>Data Store</strong>}
        action={
          <Button variant="primary" disabled={busy} onClick={() => void run()}>
            <Play size={15} />
            Run
          </Button>
        }
      >
        <div className="stack">
          <Tabs
            value={mode}
            onChange={setMode}
            items={[
              { value: 'entity', label: 'Entities', icon: <Route size={14} /> },
              { value: 'topo', label: 'Topology', icon: <Route size={14} /> },
            ]}
          />
          {mode === 'entity' ? (
            <div className="row" style={{ alignItems: 'end' }}>
              <div style={{ width: 160 }}>
                <Field label="Domain">
                  <TextInput value={domain} onChange={(event) => setDomain(event.target.value)} />
                </Field>
              </div>
              <div style={{ width: 220 }}>
                <Field label="Entity set">
                  <TextInput value={name} onChange={(event) => setName(event.target.value)} />
                </Field>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <Field label="Search">
                  <TextInput value={queryText} onChange={(event) => setQueryText(event.target.value)} />
                </Field>
              </div>
            </div>
          ) : (
            <Field label="Seed entity ID">
              <TextInput value={seed} onChange={(event) => setSeed(event.target.value)} />
            </Field>
          )}
          {error && <Badge tone="danger">{error}</Badge>}
        </div>
      </Panel>
      <Panel title={<strong>Result</strong>} action={result && <Badge>{result.rows.length}</Badge>}>
        {result ? <ResultTable result={result} /> : <div className="muted">No result yet.</div>}
      </Panel>
    </div>
  )
}

function escapeSPL(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/'/g, "\\'")
}
