import { useNavigate } from 'react-router-dom';
import type { Proposal } from '../types';

interface ProposalListProps {
  proposals: Proposal[];
}

export default function ProposalList({ proposals }: ProposalListProps) {
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-1 gap-4">
      {proposals.map((proposal) => (
        <div
          key={proposal.proposal_id}
          onClick={() => navigate(`/proposals/${proposal.proposal_id}`)}
          className="bg-white rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow"
        >
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                Agent: <span className="text-blue-600">{proposal.agent_id}</span>
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                Proposal ID: {proposal.proposal_id}
              </p>
            </div>
            <div className="flex gap-2">
              <span
                className={`px-3 py-1 rounded-full text-xs font-medium ${
                  proposal.status === 'pending'
                    ? 'bg-yellow-100 text-yellow-800'
                    : proposal.status === 'approved'
                    ? 'bg-green-100 text-green-800'
                    : 'bg-red-100 text-red-800'
                }`}
              >
                {proposal.status.charAt(0).toUpperCase() + proposal.status.slice(1)}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded p-3">
              <p className="text-xs text-gray-600">Quality Score</p>
              <p className="text-lg font-semibold text-blue-600 mt-1">
                {proposal.quality_score_current.toFixed(2)}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                from {proposal.quality_score_baseline.toFixed(2)}
              </p>
            </div>

            <div className="bg-gray-50 rounded p-3">
              <p className="text-xs text-gray-600">Relevance Score</p>
              <p className="text-lg font-semibold text-blue-600 mt-1">
                {proposal.relevance_score_current.toFixed(2)}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                from {proposal.relevance_score_baseline.toFixed(2)}
              </p>
            </div>

            <div className="bg-gray-50 rounded p-3">
              <p className="text-xs text-gray-600">Latency (ms)</p>
              <p className="text-lg font-semibold text-blue-600 mt-1">
                {proposal.latency_ms_current}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                from {proposal.latency_ms_baseline}
              </p>
            </div>

            <div className="bg-gray-50 rounded p-3">
              <p className="text-xs text-gray-600">Confidence</p>
              <p className="text-lg font-semibold text-blue-600 mt-1">
                {proposal.confidence_score.toFixed(2)}
              </p>
              <p className="text-xs text-gray-500 mt-1">likelihood</p>
            </div>
          </div>

          <div className="mt-4 text-sm text-gray-600">
            Created {new Date(proposal.created_at).toLocaleDateString()}
          </div>
        </div>
      ))}
    </div>
  );
}
