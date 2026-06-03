import { useState, useEffect } from 'react';
import { rlApi } from '../api/client';
import type { Proposal } from '../types';

export function useProposals(status?: string) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    const fetchProposals = async () => {
      try {
        setLoading(true);
        const data = await rlApi.getPendingProposals(status);
        setProposals(data.proposals);
        setTotalCount(data.total_count);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch proposals');
        setProposals([]);
      } finally {
        setLoading(false);
      }
    };

    fetchProposals();
  }, [status]);

  return { proposals, loading, error, totalCount };
}
