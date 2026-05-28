import type {
  PendingProposalsResponse,
  ProposalDetails,
  VoteResponse,
  DeploymentStatus,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Helper for API calls
async function apiCall<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    'X-Tenant-Id': localStorage.getItem('tenantId') || 'asgard_medical',
    ...options?.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// API Functions
export const rlApi = {
  // Get pending proposals
  getPendingProposals: (status?: string, page?: number) =>
    apiCall<PendingProposalsResponse>(
      `/api/v1/rl/proposals/pending?${new URLSearchParams({
        ...(status && { status }),
        ...(page && { page: page.toString() }),
      })}`
    ),

  // Get proposal details
  getProposal: (proposalId: string) =>
    apiCall<ProposalDetails>(`/api/v1/rl/proposals/${proposalId}`),

  // Submit vote
  submitVote: (proposalId: string, voter: 'odin' | 'frigg', decision: 'approve' | 'reject') =>
    apiCall<VoteResponse>('/api/v1/rl/proposals/vote', {
      method: 'POST',
      body: JSON.stringify({
        proposal_id: proposalId,
        voter,
        decision,
      }),
    }),

  // Get deployment status (WebSocket)
  subscribeDeploymentStatus: (proposalId: string, onUpdate: (status: DeploymentStatus) => void) => {
    const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/api/v1/rl/deployments/live?proposal_id=${proposalId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      const status = JSON.parse(event.data) as DeploymentStatus;
      onUpdate(status);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return ws;
  },

  // Trigger daily RL cycle manually
  triggerDailyRLCycle: () =>
    apiCall('/api/v1/rl/trigger-daily-cycle', {
      method: 'GET',
    }),

  // Check deployments
  checkDeployments: () =>
    apiCall('/api/v1/rl/check-deployments'),
};
