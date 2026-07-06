import React from 'react';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import DiagnosisWorkbench from '../features/diagnosis/workbench/DiagnosisWorkbench';

export default function DiagnosisPage() {
  return (
    <WorkspacePage>
      <DiagnosisContent />
    </WorkspacePage>
  );
}

function DiagnosisContent() {
  const { workspace } = useWorkspace();
  // Gated by WorkspacePage, so a workspace exists; guard keeps types honest.
  if (!workspace) {
    return null;
  }
  return <DiagnosisWorkbench workspaceId={workspace} />;
}
