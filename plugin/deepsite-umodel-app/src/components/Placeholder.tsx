import React from 'react';
import { Alert } from '@grafana/ui';

// Temporary content for pages whose full migration lands in a later P1/P2 step.
export function Placeholder({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Alert title={title} severity="info">
      {children}
    </Alert>
  );
}
