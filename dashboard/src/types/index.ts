// RL System Types

export interface Proposal {
  proposal_id: string;
  agent_id: number;
  tenant_id: string;
  status: 'pending' | 'approved' | 'rejected' | 'deployed';
  quality_score_baseline: number;
  quality_score_current: number;
  relevance_score_baseline: number;
  relevance_score_current: number;
  latency_ms_baseline: number;
  latency_ms_current: number;
  confidence_score: number;
  created_at: string;
  updated_at: string;
}

export interface Vote {
  proposal_id: string;
  voter_id: string; // 'odin' | 'frigg'
  decision: 'approve' | 'reject' | null;
  voted_at: string | null;
}

export interface ProposalDetails extends Proposal {
  votes: Vote[];
  improvement_description?: string;
}

export interface DeploymentStatus {
  proposal_id: string;
  agent_id: number;
  deployment_id: string;
  phase: 'canary' | 'staged_25' | 'staged_50' | 'full';
  deployment_percentage: number;
  progress_percent: number;
  quality_score_current: number;
  latency_ms_current: number;
  error_rate: number;
  phase_start_time: string;
  estimated_completion: string;
  status: 'in_progress' | 'completed' | 'rolled_back';
  rollback_triggered?: boolean;
  rollback_reason?: string;
}

export interface PendingProposalsResponse {
  proposals: Proposal[];
  total_count: number;
  page: number;
}

export interface VoteResponse {
  success: boolean;
  message: string;
  deployment_started?: boolean;
  deployment_id?: string;
}

export interface User {
  id: string;
  role: 'odin' | 'frigg' | 'viewer';
  tenant_id: string;
}
