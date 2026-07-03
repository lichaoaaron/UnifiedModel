import type { UModelApi } from '../../api/client'
import DiagnosisWorkbench from './workbench/DiagnosisWorkbench'

export function DiagnosisPage({ workspaceId }: { api: UModelApi; workspaceId: string }) {
  return <DiagnosisWorkbench workspaceId={workspaceId} />
}
