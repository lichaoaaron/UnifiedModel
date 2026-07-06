import React from 'react';
import { WorkspacePage } from '../components/WorkspacePage';
import { useWorkspace } from '../context/WorkspaceContext';
import { UModelPage as UModelFeature } from '../features/umodel/UModelPage';

export default function UModelPage() {
  return (
    <WorkspacePage>
      <UModelContent />
    </WorkspacePage>
  );
}

function UModelContent() {
  const { workspace, api } = useWorkspace();
  // Gated by WorkspacePage, so a workspace exists; guard keeps types honest.
  if (!workspace) {
    return null;
  }
  return <UModelFeature api={api} workspaceId={workspace} refreshToken={0} />;
}
