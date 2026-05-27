//! Bifrost library crate. The binary in `main.rs` is the production entry
//! point; this lib exists so integration tests in `tests/` can reach the
//! HTTP-layer modules (`auth_jwt`, `middleware`, `agents`) without going
//! through the swarm-engine / overseer init path.

pub mod auth_jwt;
pub mod middleware;
pub mod agents;
pub mod rl_feedback;           // RL feedback collection and scoring
pub mod rl_agent_self_eval;    // Agent self-evaluation & improvement proposals
pub mod rl_governance_voting;  // Odin + Frigg approval voting
pub mod rl_safe_deployment;    // Canary & staged rollout with monitoring
pub mod rl_audit_trail;        // Compliance audit logging
pub mod rl_orchestrator;       // RL system coordinator
