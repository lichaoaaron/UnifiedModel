import { useEffect, useState } from 'react'
import { Save, Trash2 } from 'lucide-react'
import type { WorkspaceMetadata } from '../../api/types'
import { MModelApi } from '../../api/client'
import { Badge, Button, Field, JsonEditor, Panel, TextInput } from '../../design/components'
import { formatError, parseJson, stringify } from '../../lib/json'

export function SettingsPage({
  api,
  workspaceId,
  workspace,
  onWorkspaceChange,
  onBack,
}: {
  api: MModelApi
  workspaceId: string
  workspace: WorkspaceMetadata | null
  onWorkspaceChange: (workspace: WorkspaceMetadata | null) => void
  onBack: () => void
}) {
  const [name, setName] = useState(workspace?.name || workspaceId)
  const [description, setDescription] = useState(workspace?.description || '')
  const [labels, setLabels] = useState(stringify(workspace?.labels || {}))
  const [config, setConfig] = useState(stringify(workspace?.config || {}))
  const [replaceLabels, setReplaceLabels] = useState(true)
  const [replaceConfig, setReplaceConfig] = useState(true)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setName(workspace?.name || workspaceId)
    setDescription(workspace?.description || '')
    setLabels(stringify(workspace?.labels || {}))
    setConfig(stringify(workspace?.config || {}))
  }, [workspace, workspaceId])

  async function save() {
    setBusy(true)
    setStatus('')
    try {
      const next = await api.updateWorkspace(workspaceId, {
        name,
        description,
        labels: parseJson<Record<string, string>>(labels, 'Labels JSON'),
        config: parseJson<Record<string, Record<string, unknown>>>(config, 'Config JSON'),
        if_match_version: workspace?.resource_version,
        replace_labels: replaceLabels,
        replace_config: replaceConfig,
      })
      onWorkspaceChange(next)
      setStatus('Saved')
    } catch (error) {
      setStatus(formatError(error))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setStatus('')
    try {
      await api.deleteWorkspace(workspaceId)
      onWorkspaceChange(null)
      onBack()
    } catch (error) {
      setStatus(formatError(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="two-column">
      <Panel
        title={<strong>Workspace Settings</strong>}
        action={workspace && <Badge tone={workspace.status === 'active' ? 'success' : 'warning'}>v{workspace.resource_version}</Badge>}
      >
        <div className="stack">
          <Field label="Name">
            <TextInput value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Description">
            <TextInput value={description} onChange={(event) => setDescription(event.target.value)} />
          </Field>
          <Field label="Labels JSON">
            <JsonEditor value={labels} onChange={setLabels} minHeight={150} />
          </Field>
          <label className="row small muted">
            <input type="checkbox" checked={replaceLabels} onChange={(event) => setReplaceLabels(event.target.checked)} />
            replace labels
          </label>
          <Field label="Config JSON">
            <JsonEditor value={config} onChange={setConfig} minHeight={190} />
          </Field>
          <label className="row small muted">
            <input type="checkbox" checked={replaceConfig} onChange={(event) => setReplaceConfig(event.target.checked)} />
            replace config
          </label>
          {status && <Badge tone={status === 'Saved' ? 'success' : 'danger'}>{status}</Badge>}
          <div className="toolbar">
            <Button variant="danger" onClick={() => void remove()} disabled={busy}>
              <Trash2 size={15} />
              Delete workspace
            </Button>
            <Button variant="primary" onClick={() => void save()} disabled={busy}>
              <Save size={15} />
              Save
            </Button>
          </div>
        </div>
      </Panel>

      <Panel title={<strong>Metadata</strong>}>
        <pre className="result-box small">{workspace ? stringify(workspace) : 'Workspace metadata is not loaded.'}</pre>
      </Panel>
    </div>
  )
}
