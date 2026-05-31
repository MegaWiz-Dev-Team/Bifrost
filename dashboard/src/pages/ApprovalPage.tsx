import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { rlApi } from '../api/client';
import { useVote } from '../hooks/useVote';
import type { ProposalDetails } from '../types';

export default function ApprovalPage() {
  const { proposalId } = useParams<{ proposalId: string }>();
  const navigate = useNavigate();
  const [proposal, setProposal] = useState<ProposalDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { submitVote, submitting } = useVote();

  useEffect(() => {
    const fetchProposal = async () => {
      try {
        if (!proposalId) throw new Error('No proposal ID');
        const data = await rlApi.getProposal(proposalId);
        setProposal(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load proposal');
      } finally {
        setLoading(false);
      }
    };

    fetchProposal();
  }, [proposalId]);

  const handleVote = async (voter: 'odin' | 'frigg', decision: 'approve' | 'reject') => {
    try {
      if (!proposalId) return;
      await submitVote(proposalId, voter, decision);
      // Refresh proposal
      if (proposalId) {
        const updated = await rlApi.getProposal(proposalId);
        setProposal(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit vote');
    }
  };

  if (loading) {
    return <div className="flex justify-center py-8">Loading proposal...</div>;
  }

  if (error || !proposal) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">Error: {error || 'Proposal not found'}</p>
        <button onClick={() => navigate('/')} className="mt-4 text-blue-600 hover:underline">
          Back to proposals
        </button>
      </div>
    );
  }

  const odinVote = proposal.votes.find((v) => v.voter_id === 'odin');
  const friggVote = proposal.votes.find((v) => v.voter_id === 'frigg');

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto">
        <button
          onClick={() => navigate('/')}
          className="mb-6 text-blue-600 hover:underline"
        >
          ← Back to proposals
        </button>

        <div className="bg-white rounded-lg shadow-lg p-8">
          <h1 className="text-3xl font-bold mb-2">
            Agent: <span className="text-blue-600">{proposal.agent_id}</span>
          </h1>
          <p className="text-gray-600 mb-8">Proposal ID: {proposal.proposal_id}</p>

          {/* Metrics Comparison */}
          <section className="mb-8">
            <h2 className="text-xl font-semibold mb-4">📊 Proposed Improvements</h2>
            <div className="grid grid-cols-2 gap-4">
              <MetricCard
                label="Quality Score"
                before={proposal.quality_score_baseline}
                after={proposal.quality_score_current}
              />
              <MetricCard
                label="Relevance Score"
                before={proposal.relevance_score_baseline}
                after={proposal.relevance_score_current}
              />
              <MetricCard
                label="Latency (ms)"
                before={proposal.latency_ms_baseline}
                after={proposal.latency_ms_current}
                isLatency
              />
              <MetricCard
                label="Confidence"
                before={0.8}
                after={proposal.confidence_score}
              />
            </div>
          </section>

          {/* Voting Panel */}
          <section className="bg-gray-50 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-6">🗳️ Approval Voting</h2>

            <div className="space-y-4">
              <VoteCard
                voter="Odin"
                voteStatus={odinVote?.decision || undefined}
                onVote={(decision) => handleVote('odin', decision)}
                disabled={submitting || !!odinVote?.decision}
              />
              <VoteCard
                voter="Frigg"
                voteStatus={friggVote?.decision || undefined}
                onVote={(decision) => handleVote('frigg', decision)}
                disabled={submitting || !!friggVote?.decision}
              />
            </div>

            <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded">
              {odinVote?.decision && friggVote?.decision ? (
                <p className="text-blue-800 font-semibold">✅ Both approved! Deployment starting...</p>
              ) : (
                <p className="text-blue-800">Waiting for approval from {
                  !odinVote?.decision ? 'Odin' : 'Frigg'
                }...</p>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, before, after, isLatency }: { label: string; before: number; after: number; isLatency?: boolean }) {
  const delta = after - before;
  const deltaPercent = ((delta / before) * 100).toFixed(1);
  const isPositive = isLatency ? delta < 0 : delta > 0;

  return (
    <div className="border rounded-lg p-4">
      <p className="text-gray-600 text-sm">{label}</p>
      <div className="flex items-baseline gap-2 mt-2">
        <span className="text-2xl font-bold">{before.toFixed(2)}</span>
        <span className="text-gray-400">→</span>
        <span className="text-2xl font-bold text-blue-600">{after.toFixed(2)}</span>
      </div>
      <p className={`text-sm mt-1 ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
        {isPositive ? '✅' : '❌'} {isLatency ? '-' : '+'}{Math.abs(parseFloat(deltaPercent))}%
      </p>
    </div>
  );
}

function VoteCard({ voter, voteStatus, onVote, disabled }: { voter: string; voteStatus?: string; onVote: (decision: 'approve' | 'reject') => void; disabled: boolean }) {
  return (
    <div className="flex items-center justify-between p-4 border rounded-lg">
      <div>
        <p className="font-semibold">{voter}</p>
        <p className="text-sm text-gray-600">
          {voteStatus
            ? `✓ Voted ${voteStatus.toUpperCase()}`
            : 'Pending'}
        </p>
      </div>
      {!voteStatus && (
        <div className="flex gap-2">
          <button
            onClick={() => onVote('approve')}
            disabled={disabled}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            Approve
          </button>
          <button
            onClick={() => onVote('reject')}
            disabled={disabled}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
