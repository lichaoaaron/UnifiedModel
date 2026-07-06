import React from 'react';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import { QueryPage as QueryFeature } from '../features/query/QueryPage';

export default function QueryPage() {
  return (
    <WorkspacePage>
      <QueryContent />
    </WorkspacePage>
  );
}

function QueryContent() {
  const { workspace, api } = useWorkspace();
  // Gated by WorkspacePage, so a workspace exists; guard keeps types honest.
  if (!workspace) {
    return null;
  }
  return <QueryFeature api={api} workspaceId={workspace} />;
}
