import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { UModelApi } from '../api/client';
import type { WorkspaceMetadata } from '../api/types';
import { useLocalStorageState } from '../lib/storage';
import { notifyError } from '../utils/notify';

// localStorage key kept identical to the standalone web app so a user's selected
// workspace carries over.
const WORKSPACE_KEY = 'openumodel.workspace';

interface WorkspaceContextValue {
  /** Currently selected workspace id, or null when none is chosen. */
  workspace: string | null;
  setWorkspace: (ws: string | null) => void;
  /** All workspaces fetched from the UModel server (via the Go proxy). */
  workspaces: WorkspaceMetadata[];
  loading: boolean;
  reload: () => Promise<void>;
  /** Shared API client targeting the plugin resource proxy. */
  api: UModelApi;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const api = useMemo(() => new UModelApi(), []);
  const [workspace, setWorkspace] = useLocalStorageState<string | null>(WORKSPACE_KEY, null);
  const [workspaces, setWorkspaces] = useState<WorkspaceMetadata[]>([]);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.listWorkspaces();
      setWorkspaces(page.items ?? []);
    } catch (err) {
      notifyError('Failed to load workspaces', err);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    // One-time load of the workspace list on mount. A fetch that flips loading
    // and result state is the intended pattern here, so the cascading-render
    // guard does not apply.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({ workspace, setWorkspace, workspaces, loading, reload, api }),
    [workspace, setWorkspace, workspaces, loading, reload, api]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return ctx;
}
