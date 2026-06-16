import { useState } from 'react'
import { Play, SearchCode, Wand2 } from 'lucide-react'
import type { QueryExplain, QueryResult } from '../../api/types'
import { MModelApi } from '../../api/client'
import { Badge, Button, Field, JsonEditor, Panel, TextArea, TextInput } from '../../design/components'
import { formatError, parseJson, stringify } from '../../lib/json'

const examples = [
  { label: '.mmodel', query: ".mmodel with(kind='entity_set') | project domain,name,kind | sort domain,name | limit 20" },
  { label: '.entity', query: ".entity with(domain='devops', name='devops.service', query='checkout', topk=20) | project __entity_id__,display_name,status,owner" },
  {
    label: 'direct',
    query:
      ".topo | graph-call getDirectRelations([(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | project src,relation,dest | limit 20",
  },
  {
    label: 'neighbors',
    query:
      ".topo | graph-call getNeighborNodes('full', 2, [(:\"devops@devops.service\" {__entity_id__: '10000000000000000000000000000101'})]) | limit 20",
  },
  {
    label: 'cypher',
    query:
      '.topo | graph-call cypher(`MATCH (svc:``devops@devops.service`` {__entity_id__: $svc}) OPTIONAL MATCH path = (svc)-[r*1..2]-(neighbor) WITH svc, neighbor, relationships(path) AS rels WHERE neighbor IS NULL OR coalesce(neighbor.__deleted__, false) = false RETURN svc.__entity_id__ AS service_id, neighbor.__entity_id__ AS neighbor_id, [rel IN rels | type(rel)] AS relation_types, size(rels) AS hops ORDER BY hops, neighbor LIMIT 20`) | limit 20',
    parameters: { svc: '10000000000000000000000000000101' },
  },
]

export function QueryPage({ api, workspaceId }: { api: MModelApi; workspaceId: string }) {
  const [query, setQuery] = useState(examples[0].query)
  const [limit, setLimit] = useState('50')
  const [parameters, setParameters] = useState('{}')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [explain, setExplain] = useState<QueryExplain | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(kind: 'execute' | 'explain') {
    setBusy(true)
    setError('')
    try {
      const request = {
        query,
        limit: Number(limit) || undefined,
        parameters: parameters.trim() ? parseJson<Record<string, unknown>>(parameters, 'Parameters JSON') : undefined,
      }
      if (kind === 'execute') {
        const next = await api.query(workspaceId, request)
        setResult(next)
        setExplain(next.explain || null)
      } else {
        const next = await api.explain(workspaceId, request)
        setExplain(next)
      }
    } catch (nextError) {
      setError(formatError(nextError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page-grid">
      <Panel
        title={<strong>Unified SPL Query</strong>}
        action={
          <div className="row">
            <Button variant="secondary" onClick={() => void run('explain')} disabled={busy}>
              <SearchCode size={15} />
              Explain
            </Button>
            <Button variant="primary" onClick={() => void run('execute')} disabled={busy}>
              <Play size={15} />
              Execute
            </Button>
          </div>
        }
      >
        <div className="stack">
          <Field label="SPL">
            <TextArea value={query} onChange={(event) => setQuery(event.target.value)} style={{ minHeight: 116 }} />
          </Field>
          <div className="row" style={{ alignItems: 'end' }}>
            <div style={{ width: 150 }}>
              <Field label="Limit">
                <TextInput value={limit} onChange={(event) => setLimit(event.target.value)} />
              </Field>
            </div>
            <div style={{ flex: 1, minWidth: 260 }}>
              <Field label="Parameters JSON">
                <JsonEditor value={parameters} onChange={setParameters} minHeight={76} />
              </Field>
            </div>
          </div>
          <div className="row">
            {examples.map((item) => (
              <Button
                key={item.label}
                variant="ghost"
                onClick={() => {
                  setQuery(item.query)
                  setParameters(item.parameters ? stringify(item.parameters) : '{}')
                }}
              >
                <Wand2 size={14} />
                {item.label}
              </Button>
            ))}
          </div>
          {error && <Badge tone="danger">{error}</Badge>}
        </div>
      </Panel>

      <div className="two-column">
        <Panel title={<strong>Rows</strong>} action={result && <Badge>{result.rows.length}</Badge>}>
          {result ? <ResultTable result={result} /> : <div className="muted">No result yet.</div>}
        </Panel>
        <Panel title={<strong>Explain</strong>} action={explain?.provider && <Badge tone="indigo">{explain.provider}</Badge>}>
          <pre className="result-box small">{explain ? stringify(explain) : 'No explain plan yet.'}</pre>
        </Panel>
      </div>
    </div>
  )
}

export function ResultTable({ result }: { result: QueryResult }) {
  if (result.rows.length === 0) return <div className="muted">No rows.</div>
  const columns = result.columns.length > 0 ? result.columns : Object.keys(result.rows[0])
  return (
    <div style={{ overflow: 'auto' }}>
      <table className="om-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column} className={typeof row[column] === 'object' ? 'mono small' : undefined}>
                  {formatCell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
