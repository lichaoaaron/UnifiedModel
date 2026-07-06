import React from 'react';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import { ApiMapPage } from '../features/apiDebug/ApiMapPage';

export default function ApiDebugPage() {
  return (
    <WorkspacePage>
      <ApiDebugContent />
    </WorkspacePage>
  );
}

function ApiDebugContent() {
  const { workspace, api } = useWorkspace();
  // Gated by WorkspacePage so a workspace exists — the debugger prefills the
  // {workspace} path parameter from it.
  if (!workspace) {
    return null;
  }
  return <ApiMapPage api={api} workspaceId={workspace} />;
}
