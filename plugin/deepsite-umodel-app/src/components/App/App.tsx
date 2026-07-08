import React, { Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppRootProps } from '@grafana/data';
import { LoadingPlaceholder } from '@grafana/ui';
import { DEFAULT_ROUTE, ROUTES } from '../../constants';
import { WorkspaceProvider } from '../../context/WorkspaceContext';

const UModelPage = React.lazy(() => import('../../pages/UModelPage'));
const TopoPage = React.lazy(() => import('../../pages/TopoPage'));
const QueryPage = React.lazy(() => import('../../pages/QueryPage'));
const ImportsPage = React.lazy(() => import('../../pages/ImportsPage'));
const SettingsPage = React.lazy(() => import('../../pages/SettingsPage'));
const ApiDebugPage = React.lazy(() => import('../../pages/ApiDebugPage'));
const DiagnosisPage = React.lazy(() => import('../../pages/DiagnosisPage'));

function App(_props: AppRootProps) {
  return (
    <WorkspaceProvider>
      <Suspense fallback={<LoadingPlaceholder text="" />}>
        <Routes>
          <Route path={ROUTES.UModel} element={<UModelPage />} />
          <Route path={ROUTES.Topo} element={<TopoPage />} />
          <Route path={ROUTES.Query} element={<QueryPage />} />
          <Route path={ROUTES.Imports} element={<ImportsPage />} />
          <Route path={ROUTES.Settings} element={<SettingsPage />} />
          <Route path={ROUTES.ApiDebug} element={<ApiDebugPage />} />
          <Route path={ROUTES.Diagnosis} element={<DiagnosisPage />} />
          {/* Default page */}
          <Route path="*" element={<Navigate to={DEFAULT_ROUTE} replace />} />
        </Routes>
      </Suspense>
    </WorkspaceProvider>
  );
}

export default App;
