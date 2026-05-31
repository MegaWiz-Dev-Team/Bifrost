import { useState } from 'react';
import { rlApi } from '../api/client';

export function useVote() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitVote = async (proposalId: string, voter: 'odin' | 'frigg', decision: 'approve' | 'reject') => {
    try {
      setSubmitting(true);
      setError(null);
      const response = await rlApi.submitVote(proposalId, voter, decision);
      return response;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit vote';
      setError(message);
      throw err;
    } finally {
      setSubmitting(false);
    }
  };

  return { submitVote, submitting, error };
}
