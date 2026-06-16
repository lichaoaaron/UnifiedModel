import { useCallback, useEffect, useState } from 'react'
import { Braces, Play, RefreshCcw, Sparkles } from 'lucide-react'
import type { AgentDiscovery, AgentResource } from '../../api/types'
import { MModelApi } from '../../api/client'
import { Badge, Button, Field, JsonEditor, Panel, Select } from '../../design/components'
import { formatError, parseJson, stringify } from '../../lib/json'

export function AgentPage({ api, workspaceId }: { api: MModelApi; workspaceId: string }) {
  const [discovery, setDiscovery] = useState<AgentDiscovery | null>(null)
  const [selectedResource, setSelectedResource] = useState<AgentResource | null>(null)
  const [resourceResult, setResourceResult] = useState<unknown>(null)
  const [toolName, setToolName] = useState('query_spl_examples')
  const [toolArgs, setToolArgs] = useState('{}')
  const [toolResult, setToolResult] = useState<unknown>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const next = await api.discoverAgent(workspaceId)
      setDiscovery(next)
      setToolName(next.tools.find((tool) => tool.name === 'query_spl_examples')?.name || next.tools[0]?.name || 'query_spl_examples')
      setSelectedResource(next.resources[0] || null)
    } catch (nextError) {
      setError(formatError(nextError))
    } finally {
      setBusy(false)
    }
  }, [api, workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  async function readResource(resource = selectedResource) {
    if (!resource) return
    setBusy(true)
    setError('')
    try {
      setSelectedResource(resource)
      setResourceResult(await api.readAgentResource(workspaceId, resource.uri))
    } catch (nextError) {
      setError(formatError(nextError))
    } finally {
      setBusy(false)
    }
  }

  async function executeTool() {
    setBusy(true)
    setError('')
    setToolResult(null)
    try {
      const args = toolArgs.trim() ? parseJson<Record<string, unknown>>(toolArgs, 'Tool arguments JSON') : {}
      setToolResult(await api.executeAgentTool(workspaceId, toolName, args))
    } catch (nextError) {
      setError(formatError(nextError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page-grid">
      <div className="toolbar">
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Agent Gateway</h2>
          <div className="small muted">Discovery metadata, safe resources, and public tools.</div>
        </div>
        <Button variant="ghost" onClick={() => void load()} disabled={busy}>
          <RefreshCcw size={15} />
          Refresh
        </Button>
      </div>
      {error && <Badge tone="danger">{error}</Badge>}

      <div className="two-column">
        <Panel title={<strong>Tools</strong>} action={discovery && <Badge>{discovery.tools.length}</Badge>}>
          <div className="stack">
            {discovery?.tools.map((tool) => (
              <div key={tool.name} className="workspace-row" style={{ cursor: 'default' }}>
                <span>
                  <strong>{tool.name}</strong>
                  <span className="small muted" style={{ display: 'block', marginTop: 4 }}>{tool.description}</span>
                </span>
                <Badge tone={tool.enabled ? 'success' : 'warning'}>{tool.enabled ? 'enabled' : 'disabled'}</Badge>
              </div>
            ))}
            {!discovery && <div className="muted">No discovery loaded.</div>}
          </div>
        </Panel>

        <Panel title={<strong>Execute Tool</strong>} action={<Sparkles size={16} />}>
          <div className="stack">
            <Field label="Tool">
              <Select value={toolName} onChange={(event) => setToolName(event.target.value)}>
                {(discovery?.tools || []).map((tool) => (
                  <option key={tool.name} value={tool.name} disabled={!tool.enabled}>
                    {tool.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Arguments JSON">
              <JsonEditor value={toolArgs} onChange={setToolArgs} minHeight={130} />
            </Field>
            <Button variant="primary" onClick={() => void executeTool()} disabled={busy || !toolName}>
              <Play size={15} />
              Execute
            </Button>
            <pre className="result-box small">{toolResult ? stringify(toolResult) : 'No tool result yet.'}</pre>
          </div>
        </Panel>
      </div>

      <div className="two-column">
        <Panel title={<strong>Resources</strong>} action={discovery && <Badge>{discovery.resources.length}</Badge>}>
          <div className="stack">
            {discovery?.resources.map((resource) => (
              <button
                key={resource.uri}
                className="workspace-row"
                onClick={() => void readResource(resource)}
                type="button"
              >
                <span>
                  <strong>{resource.name}</strong>
                  <span className="small muted" style={{ display: 'block', marginTop: 4 }}>{resource.description}</span>
                </span>
                <Braces size={16} />
              </button>
            ))}
          </div>
        </Panel>

        <Panel title={<strong>Resource Content</strong>} action={selectedResource && <Badge>{selectedResource.kind}</Badge>}>
          <pre className="result-box small">{resourceResult ? stringify(resourceResult) : 'Select a resource to read.'}</pre>
        </Panel>
      </div>

      <Panel title={<strong>Next Actions</strong>} action={discovery?.next_actions && <Badge>{discovery.next_actions.length}</Badge>}>
        <div style={{ overflow: 'auto' }}>
          <table className="om-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Tool</th>
                <th>Query</th>
              </tr>
            </thead>
            <tbody>
              {(discovery?.next_actions || []).map((action) => (
                <tr key={action.id}>
                  <td className="mono">{action.id}</td>
                  <td>{action.title}</td>
                  <td>{action.tool}</td>
                  <td className="mono small">{action.query_api.body.query}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
