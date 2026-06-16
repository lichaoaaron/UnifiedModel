import { useState } from 'react'
import { CheckCircle2, DatabaseZap, FileInput, Send, Sparkles, UploadCloud } from 'lucide-react'
import { MModelApi } from '../../api/client'
import { Badge, Button, Field, JsonEditor, Panel, Tabs, TextInput } from '../../design/components'
import { asArray, formatError, parseJson, stringify } from '../../lib/json'
import { parseMModelElementsFromJson } from '../explorer/ExplorerPage'

type ImportMode = 'path' | 'mmodel' | 'entity' | 'expire'

const sampleElement = `[
  {
    "kind": "entity_set",
    "domain": "devops",
    "name": "devops.service",
    "spec": {
      "fields": {}
    }
  }
]`

const sampleEntity = `[
  {
    "__domain__": "devops",
    "__entity_type__": "devops.service",
    "__entity_id__": "10000000000000000000000000000101",
    "__method__": "Update",
    "__first_observed_time__": 100,
    "__last_observed_time__": 200,
    "display_name": "checkout-service"
  },
  {
    "__domain__": "devops",
    "__entity_type__": "devops.service",
    "__entity_id__": "10000000000000000000000000000102",
    "__method__": "Update",
    "__first_observed_time__": 100,
    "__last_observed_time__": 200,
    "display_name": "catalog-api"
  }
]`

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
]`

export function ImportsPage({
  api,
  workspaceId,
  onChanged,
}: {
  api: MModelApi
  workspaceId: string
  onChanged: () => void
}) {
  const [mode, setMode] = useState<ImportMode>('path')
  const [path, setPath] = useState('examples/quickstart-multidomain')
  const [commonPacks, setCommonPacks] = useState('[]')
  const [elementsJson, setElementsJson] = useState(sampleElement)
  const [entityJson, setEntityJson] = useState(sampleEntity)
  const [relationJson, setRelationJson] = useState(sampleRelation)
  const [expireKind, setExpireKind] = useState<'entity' | 'relation'>('entity')
  const [expireIds, setExpireIds] = useState('["devops/devops.service/10000000000000000000000000000101"]')
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(action: 'validate' | 'write' | 'import' | 'sample' | 'expire') {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      if (action === 'sample') {
        const next = await api.importSampleData(workspaceId)
        setResult(next)
        onChanged()
      } else if (action === 'import') {
        const next = await api.importMModel(workspaceId, {
          path,
          common_schema_packs: commonPacks.trim() ? parseJson<string[]>(commonPacks, 'Common schema packs JSON') : undefined,
        })
        setResult(next)
        onChanged()
      } else if (mode === 'mmodel') {
        const elements = parseMModelElementsFromJson(elementsJson)
        const next = action === 'validate'
          ? await api.validateMModel(workspaceId, elements)
          : await api.putMModel(workspaceId, elements)
        setResult(next)
        if (action === 'write') onChanged()
      } else if (mode === 'entity') {
        const entities = asArray(parseJson<Record<string, unknown> | Array<Record<string, unknown>>>(entityJson, 'Entity JSON'))
        const relations = asArray(parseJson<Record<string, unknown> | Array<Record<string, unknown>>>(relationJson, 'Relation JSON'))
        const entityResult = entities.length > 0 ? await api.writeEntities(workspaceId, { entities }) : null
        const relationResult = relations.length > 0 ? await api.writeRelations(workspaceId, { relations }) : null
        setResult({ entities: entityResult, relations: relationResult })
      } else {
        const ids = parseJson<string[]>(expireIds, 'IDs JSON')
        const next = expireKind === 'entity'
          ? await api.expireEntities(workspaceId, { ids })
          : await api.expireRelations(workspaceId, { ids })
        setResult(next)
      }
    } catch (nextError) {
      setError(formatError(nextError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="two-column">
      <Panel
        title={<strong>Imports & Writes</strong>}
        action={
          <Tabs
            value={mode}
            onChange={setMode}
            items={[
              { value: 'path', label: 'Path', icon: <FileInput size={14} /> },
              { value: 'mmodel', label: 'MModel', icon: <UploadCloud size={14} /> },
              { value: 'entity', label: 'EntityStore', icon: <DatabaseZap size={14} /> },
              { value: 'expire', label: 'Expire', icon: <CheckCircle2 size={14} /> },
            ]}
          />
        }
      >
        <div className="stack">
          {mode === 'path' && (
            <>
              <Field label="Server-side path">
                <TextInput value={path} onChange={(event) => setPath(event.target.value)} />
              </Field>
              <Field label="Common schema packs JSON">
                <JsonEditor value={commonPacks} onChange={setCommonPacks} minHeight={90} />
              </Field>
              <div className="toolbar">
                <Button variant="primary" disabled={busy || !path.trim()} onClick={() => void run('import')}>
                  <FileInput size={15} />
                  Import from path
                </Button>
                <Button variant="secondary" disabled={busy} onClick={() => void run('sample')}>
                  <Sparkles size={15} />
                  Import quickstart sample data
                </Button>
              </div>
            </>
          )}

          {mode === 'mmodel' && (
            <>
              <Field label="MModel elements JSON">
                <JsonEditor value={elementsJson} onChange={setElementsJson} minHeight={420} />
              </Field>
              <div className="toolbar">
                <Button variant="secondary" disabled={busy} onClick={() => void run('validate')}>
                  <CheckCircle2 size={15} />
                  Validate
                </Button>
                <Button variant="primary" disabled={busy} onClick={() => void run('write')}>
                  <Send size={15} />
                  Put elements
                </Button>
              </div>
            </>
          )}

          {mode === 'entity' && (
            <>
              <Field label="Entities JSON">
                <JsonEditor value={entityJson} onChange={setEntityJson} minHeight={230} />
              </Field>
              <Field label="Relations JSON">
                <JsonEditor value={relationJson} onChange={setRelationJson} minHeight={230} />
              </Field>
              <Button variant="primary" disabled={busy} onClick={() => void run('write')}>
                <DatabaseZap size={15} />
                Write entity and relation data
              </Button>
            </>
          )}

          {mode === 'expire' && (
            <>
              <Field label="Kind">
                <select className="om-select" value={expireKind} onChange={(event) => setExpireKind(event.target.value as 'entity' | 'relation')}>
                  <option value="entity">entity</option>
                  <option value="relation">relation</option>
                </select>
              </Field>
              <Field label="IDs JSON">
                <JsonEditor value={expireIds} onChange={setExpireIds} minHeight={160} />
              </Field>
              <Button variant="primary" disabled={busy} onClick={() => void run('expire')}>
                <CheckCircle2 size={15} />
                Expire
              </Button>
            </>
          )}

          {error && <Badge tone="danger">{error}</Badge>}
        </div>
      </Panel>

      <Panel title={<strong>Response</strong>}>
        <pre className="result-box small">{result ? stringify(result) : 'No response yet.'}</pre>
      </Panel>
    </div>
  )
}
