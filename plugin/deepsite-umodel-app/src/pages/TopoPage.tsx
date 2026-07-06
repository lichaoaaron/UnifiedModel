import React from 'react';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import { EntityTopoPage } from '../features/entityTopo/EntityTopoPage';

export default function TopoPage() {
  return (
    <WorkspacePage>
      <TopoContent />
    </WorkspacePage>
  );
}

function TopoContent() {
  const { workspace, api } = useWorkspace();
  // Gated by WorkspacePage, so a workspace exists; guard keeps types honest.
  if (!workspace) {
    return null;
  }
  return <EntityTopoPage api={api} workspaceId={workspace} refreshToken={0} />;
}
