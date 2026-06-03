import { useState, useEffect } from 'react';
import { rlApi } from '../api/client';
import type { DeploymentStatus } from '../types';

export function useDeployment(proposalId?: string) {
  const [status, setStatus] = useState<DeploymentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!proposalId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    let ws: WebSocket | null = null;

    try {
      ws = rlApi.subscribeDeploymentStatus(proposalId, (newStatus) => {
        setStatus(newStatus);
        setLoading(false);
        setError(null);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect to deployment status');
      setLoading(false);
    }

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [proposalId]);

  return { status, loading, error };
}
