//! RL System Orchestrator
//!
//! Coordinates all 6 phases of agent skill improvement:
//! 1. Feedback collection after every A2A dispatch
//! 2. Daily self-evaluation & proposal generation
//! 3. Governance voting (Odin + Frigg)
//! 4. Canary deployment with health checks
//! 5. Staged rollout (25% → 50% → 100%)
//! 6. Compliance audit logging

use sqlx::MySqlPool;

use crate::rl_feedback::{compute_feedback_scores, log_dispatch_feedback, compute_daily_metrics};
use crate::rl_agent_self_eval::{agent_self_evaluate, submit_proposal};
use crate::rl_governance_voting::{
    odin_quick_evaluate, frigg_detailed_review, evaluate_consensus, record_approval_votes,
};
use crate::rl_safe_deployment::{
    start_canary_deployment, evaluate_canary_health, check_and_execute_rollback,
};
use crate::rl_audit_trail::{
    log_proposal_submitted, log_odin_vote, log_frigg_vote, log_canary_started,
};

/// Called immediately after every A2A dispatch completes
pub async fn log_dispatch_feedback_on_completion(
    pool: &MySqlPool,
    tenant_id: &str,
    agent_id: i64,
    session_id: &str,
    query: &str,
    response: &str,
    latency_ms: i32,
    model_confidence: f32,
) -> Result<(), Box<dyn std::error::Error>> {
    // Phase 2: Compute feedback scores
    let feedback = compute_feedback_scores(query, response, latency_ms, model_confidence);

    // Log feedback details before moving feedback
    let quality_score = feedback.quality_score;
    let relevance_score = feedback.relevance_score;

    // Log to database
    log_dispatch_feedback(pool, feedback, tenant_id, agent_id, session_id).await?;

    tracing::info!(
        "RL: Dispatch feedback logged; agent={}, quality={:.2}, relevance={:.2}, latency={}ms",
        agent_id,
        quality_score,
        relevance_score,
        latency_ms
    );

    Ok(())
}

/// Called daily at 02:00 UTC by Bifrost scheduler
pub async fn run_daily_rl_cycle(
    pool: &MySqlPool,
    tenant_id: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    tracing::info!("RL: Starting daily cycle for tenant={}", tenant_id);

    // Get all active agents for this tenant
    let agents = sqlx::query!(
        r#"
        SELECT id, name FROM agent_configs
        WHERE tenant_id = ? AND is_published = 1
        "#,
        tenant_id
    )
    .fetch_all(pool)
    .await?;

    for agent in agents {
        let agent_id = agent.id;
        let agent_name = &agent.name;

        // Step 1: Compute daily metrics
        tracing::info!("RL: Computing daily metrics for agent={}", agent_name);
        compute_daily_metrics(pool, tenant_id, agent_id).await?;

        // Step 2: Agent self-evaluates
        tracing::info!("RL: Running self-evaluation for agent={}", agent_name);
        if let Some(proposal) = agent_self_evaluate(pool, tenant_id, agent_id, agent_name).await? {
            tracing::info!(
                "RL: Agent {} proposed improvement: skill={}, estimated_delta={:.2}",
                agent_name,
                proposal.skill_name,
                proposal.estimated_quality_delta
            );

            // Submit proposal to database
            let proposal_id = submit_proposal(pool, &proposal).await?;
            tracing::info!("RL: Proposal submitted with id={}", proposal_id);

            // Log audit event
            log_proposal_submitted(
                pool,
                tenant_id,
                agent_id,
                agent_name,
                &proposal.id,
                &proposal.skill_name,
                &proposal.improvement_type,
                proposal.estimated_quality_delta,
            )
            .await?;

            // Step 3: Governance voting
            tracing::info!(
                "RL: Starting governance voting for proposal={}",
                proposal.id
            );

            // Odin reviews (30 seconds)
            let odin_vote = odin_quick_evaluate(pool, &proposal).await;
            tracing::info!(
                "RL: Odin vote: decision={:?}, reason={}",
                odin_vote.vote_decision,
                odin_vote.reasoning
            );

            // Log Odin's vote
            log_odin_vote(
                pool,
                tenant_id,
                &proposal.id,
                agent_id,
                agent_name,
                &odin_vote.vote_decision.to_string(),
                &odin_vote.reasoning,
            )
            .await?;

            // Frigg reviews (2-5 minutes) — only if Odin approved
            let frigg_vote = frigg_detailed_review(pool, &proposal, &odin_vote).await;
            tracing::info!(
                "RL: Frigg vote: decision={:?}, reason={}",
                frigg_vote.vote_decision,
                frigg_vote.reasoning
            );

            // Log Frigg's vote
            log_frigg_vote(
                pool,
                tenant_id,
                &proposal.id,
                agent_id,
                agent_name,
                &frigg_vote.vote_decision.to_string(),
                &frigg_vote.reasoning,
                frigg_vote
                    .conditions_for_deployment
                    .as_ref()
                    .map(|c| c.to_string())
                    .as_deref(),
            )
            .await?;

            // Evaluate consensus
            let governance_result = evaluate_consensus(&odin_vote, &frigg_vote);
            tracing::info!(
                "RL: Governance consensus: decision={:?}, can_deploy={}",
                governance_result.consensus_decision,
                governance_result.can_proceed_to_deployment
            );

            // Record votes
            record_approval_votes(pool, tenant_id, &governance_result).await?;

            // Step 4-5: Deploy if approved
            if governance_result.can_proceed_to_deployment {
                tracing::info!(
                    "RL: Approved for deployment: proposal={}",
                    proposal.id
                );

                // Start canary deployment (5% traffic, 2 hours)
                let metrics = start_canary_deployment(
                    pool,
                    &proposal.id,
                    agent_id,
                    &governance_result,
                )
                .await?;

                tracing::info!(
                    "RL: Canary deployment started: proposal={}, phase={}, percentage={}%",
                    proposal.id,
                    "CANARY_IN_PROGRESS",
                    metrics.deployment_percentage
                );

                // Log deployment start
                log_canary_started(pool, tenant_id, &proposal.id, agent_id, agent_name)
                    .await?;
            } else {
                tracing::warn!(
                    "RL: Proposal rejected by governance: proposal={}, decision={:?}",
                    proposal.id,
                    governance_result.consensus_decision
                );
            }
        } else {
            tracing::debug!(
                "RL: Agent {} has no improvement proposal (opportunity_score < 0.6)",
                agent_name
            );
        }
    }

    tracing::info!("RL: Daily cycle completed for tenant={}", tenant_id);
    Ok(())
}

/// Called every 30 seconds by Bifrost scheduler
pub async fn monitor_deployments(pool: &MySqlPool) -> Result<(), Box<dyn std::error::Error>> {
    // Get all active deployments
    let deployments = sqlx::query!(
        r#"
        SELECT
            proposal_id,
            agent_id,
            status
        FROM skill_deployment_log
        WHERE status IN ('CANARY_IN_PROGRESS', 'STAGED_25_PERCENT', 'STAGED_50_PERCENT')
        AND updated_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        "#
    )
    .fetch_all(pool)
    .await?;

    for deployment in deployments {
        let proposal_id = &deployment.proposal_id;
        let agent_id = deployment.agent_id;

        // Check for rollback conditions
        if check_and_execute_rollback(pool, proposal_id, agent_id).await? {
            tracing::error!(
                "RL: Auto-rollback triggered for proposal={}, agent={}",
                proposal_id,
                agent_id
            );
            continue;
        }

        // Evaluate health and advance phase if ready
        let metrics = evaluate_canary_health(pool, proposal_id, agent_id).await?;

        if metrics.rollback_triggered {
            tracing::error!(
                "RL: Health check failed for proposal={}, agent={}",
                proposal_id,
                agent_id
            );
        } else if metrics.current_phase.to_string() != deployment.status.unwrap_or_default() {
            // Phase advanced
            tracing::info!(
                "RL: Deployment phase advanced: proposal={}, agent={}, new_phase={}, percentage={}%",
                proposal_id,
                agent_id,
                metrics.current_phase,
                metrics.deployment_percentage
            );
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rl_orchestrator_module_loads() {
        // Verify the module compiles and loads
        assert!(true);
    }
}
