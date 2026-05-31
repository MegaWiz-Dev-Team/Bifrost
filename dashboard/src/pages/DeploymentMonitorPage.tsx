import { useParams, useNavigate } from 'react-router-dom';
import { useDeployment } from '../hooks/useDeployment';

export default function DeploymentMonitorPage() {
  const { proposalId } = useParams<{ proposalId: string }>();
  const navigate = useNavigate();
  const { status, loading, error } = useDeployment(proposalId);

  if (!proposalId) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-2xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">Invalid proposal ID</p>
          </div>
        </div>
      </div>
    );
  }

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
          <h1 className="text-3xl font-bold mb-8">
            🚀 Deployment Monitor
          </h1>
          <p className="text-gray-600 mb-8">Proposal: {proposalId}</p>

          {loading ? (
            <div className="text-center py-8">
              <p className="text-gray-600">Connecting to deployment monitor...</p>
              <div className="mt-4 inline-block animate-spin">
                <div className="border-4 border-gray-200 border-t-blue-600 rounded-full w-8 h-8"></div>
              </div>
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-red-800">Error: {error}</p>
            </div>
          ) : status ? (
            <div className="space-y-6">
              {/* Status Overview */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
                <h2 className="text-lg font-semibold mb-4">Deployment Status</h2>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-gray-600 text-sm">Current Phase</p>
                    <p className="text-xl font-bold text-blue-600 mt-1">
                      {status.phase.replace('_', ' ').toUpperCase()}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-600 text-sm">Deployment Progress</p>
                    <p className="text-xl font-bold text-blue-600 mt-1">
                      {status.deployment_percentage}%
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-600 text-sm">Overall Progress</p>
                    <p className="text-xl font-bold text-blue-600 mt-1">
                      {status.progress_percent}%
                    </p>
                  </div>
                </div>
              </div>

              {/* Phase Timeline */}
              <div className="space-y-4">
                <h2 className="text-lg font-semibold">Deployment Phases</h2>
                <PhaseIndicator
                  name="Canary"
                  percent={5}
                  duration="2h"
                  active={status.phase === 'canary'}
                  completed={status.deployment_percentage > 5}
                />
                <PhaseIndicator
                  name="Staged 25%"
                  percent={25}
                  duration="2h"
                  active={status.phase === 'staged_25'}
                  completed={status.deployment_percentage >= 25}
                />
                <PhaseIndicator
                  name="Staged 50%"
                  percent={50}
                  duration="2h"
                  active={status.phase === 'staged_50'}
                  completed={status.deployment_percentage >= 50}
                />
                <PhaseIndicator
                  name="Full Rollout"
                  percent={100}
                  duration="2h"
                  active={status.phase === 'full'}
                  completed={status.deployment_percentage === 100}
                />
              </div>

              {/* Metrics */}
              <div className="space-y-4">
                <h2 className="text-lg font-semibold">Live Metrics</h2>
                <div className="grid grid-cols-2 gap-4">
                  <div className="border rounded-lg p-4">
                    <p className="text-gray-600 text-sm">Quality Score</p>
                    <p className="text-2xl font-bold text-blue-600 mt-1">
                      {status.quality_score_current.toFixed(2)}
                    </p>
                  </div>
                  <div className="border rounded-lg p-4">
                    <p className="text-gray-600 text-sm">Latency (ms)</p>
                    <p className="text-2xl font-bold text-blue-600 mt-1">
                      {status.latency_ms_current}
                    </p>
                  </div>
                  <div className="border rounded-lg p-4">
                    <p className="text-gray-600 text-sm">Error Rate</p>
                    <p className="text-2xl font-bold text-blue-600 mt-1">
                      {(status.error_rate * 100).toFixed(2)}%
                    </p>
                  </div>
                  <div className="border rounded-lg p-4">
                    <p className="text-gray-600 text-sm">Status</p>
                    <p className={`text-lg font-bold mt-1 ${
                      status.status === 'completed'
                        ? 'text-green-600'
                        : status.status === 'rolled_back'
                        ? 'text-red-600'
                        : 'text-blue-600'
                    }`}>
                      {status.status === 'in_progress' ? '⚙️' : status.status === 'completed' ? '✅' : '🔄'} {status.status}
                    </p>
                  </div>
                </div>
              </div>

              {/* Status Message */}
              <div className={`rounded-lg p-4 ${
                status.rollback_triggered
                  ? 'bg-red-50 border border-red-200'
                  : status.status === 'completed'
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-blue-50 border border-blue-200'
              }`}>
                <p className={`${
                  status.rollback_triggered
                    ? 'text-red-800'
                    : status.status === 'completed'
                    ? 'text-green-800'
                    : 'text-blue-800'
                }`}>
                  {status.rollback_triggered
                    ? `⚠️ Deployment rolled back: ${status.rollback_reason}`
                    : status.status === 'completed'
                    ? '✅ Deployment completed successfully'
                    : '⚙️ Deployment in progress...'}
                </p>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-600">No deployment status available</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PhaseIndicator({
  name,
  percent,
  duration,
  active,
  completed,
}: {
  name: string;
  percent: number;
  duration: string;
  active: boolean;
  completed: boolean;
}) {
  const status = completed ? 'complete' : active ? 'active' : 'upcoming';

  const statusColors = {
    upcoming: 'bg-gray-50 border-gray-200',
    active: 'bg-blue-50 border-blue-200',
    complete: 'bg-green-50 border-green-200',
  };

  const statusIcons = {
    upcoming: '⏳',
    active: '⚙️',
    complete: '✅',
  };

  return (
    <div className={`border rounded-lg p-4 ${statusColors[status]}`}>
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">
            {statusIcons[status]} {name}
          </h3>
          <p className="text-sm text-gray-600 mt-1">
            {percent}% traffic ({duration})
          </p>
        </div>
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
          active
            ? 'bg-blue-100 text-blue-800'
            : completed
            ? 'bg-green-100 text-green-800'
            : 'bg-gray-100 text-gray-800'
        }`}>
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      </div>
    </div>
  );
}
