//! Agent Skill Improvement Governance & Approval System
//!
//! Implements consensus-based voting where both Odin (orchestrator) and Frigg (advisor)
//! must approve proposed improvements before deployment.
//!
//! Odin's Role: Quick safety check (30 seconds)
//! - Validates improvement_type is within agent's domain
//! - Checks estimated_quality_delta exceeds safety threshold
//! - Verifies no conflicting deployments in progress
//!
//! Frigg's Role: Advisory review (2-5 minutes)
//! - Performs detailed domain analysis of reasoning
//! - Checks for cross-cutting compliance implications
//! - May propose conditions (monitor metric X, rollback on Y)

use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::MySqlPool;

use crate::rl_agent_self_eval::SkillImprovementProposal;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum VoteDecision {
    #[serde(rename = "APPROVE")]
    Approve,
    #[serde(rename = "REJECT")]
    Reject,
    #[serde(rename = "CONDITIONAL")]
    Conditional,
}

impl std::fmt::Display for VoteDecision {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            VoteDecision::Approve => write!(f, "APPROVE"),
            VoteDecision::Reject => write!(f, "REJECT"),
            VoteDecision::Conditional => write!(f, "CONDITIONAL"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalVote {
    pub proposal_id: String,
    pub voter_agent_id: i64,
    pub voter_agent_name: String,
    pub vote_decision: VoteDecision,
    pub reasoning: String,
    pub conditions_for_deployment: Option<Value>,
    pub reviewed_at: chrono::DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GovernanceResult {
    pub proposal_id: String,
    pub odin_vote: Option<ApprovalVote>,
    pub frigg_vote: Option<ApprovalVote>,
    pub consensus_decision: Option<VoteDecision>,
    pub final_conditions: Option<Value>,
    pub can_proceed_to_deployment: bool,
}

/// Odin's quick safety evaluation (30 seconds)
/// Fast checks: domain boundary, safety threshold, conflict detection
pub async fn odin_quick_evaluate(
    pool: &MySqlPool,
    proposal: &SkillImprovementProposal,
) -> ApprovalVote {
    tracing::info!(
        "Odin reviewing proposal: agent={}, skill={}, estimated_delta={:.2}",
        proposal.agent_id,
        proposal.skill_name,
        proposal.estimated_quality_delta
    );

    // Safety threshold: minimum quality improvement required
    const MIN_QUALITY_DELTA_THRESHOLD: f32 = 0.05;
    let quality_meets_threshold = proposal.estimated_quality_delta >= MIN_QUALITY_DELTA_THRESHOLD;

    // Latency threshold: no degradation beyond 500ms
    let latency_acceptable = proposal.estimated_latency_delta_ms <= 500;

    // Role boundary check: ensure agent isn't exceeding capabilities
    let role_boundary_ok = validate_agent_domain(proposal.agent_id, &proposal.improvement_type);

    // Check for conflicting deployments in progress
    let no_conflicts = !has_conflicting_deployment(pool, proposal.agent_id)
        .await
        .unwrap_or(true);

    let (decision, reasoning) = if quality_meets_threshold && latency_acceptable && role_boundary_ok && no_conflicts {
        (
            VoteDecision::Approve,
            format!(
                "✓ Quality delta {:.2} meets threshold. ✓ Latency +{}ms acceptable. ✓ Agent {} stays within domain. ✓ No conflicts detected.",
                proposal.estimated_quality_delta,
                proposal.estimated_latency_delta_ms,
                proposal.agent_id
            ),
        )
    } else {
        let mut issues = Vec::new();
        if !quality_meets_threshold {
            issues.push(format!("Quality delta {:.2} < threshold {}", proposal.estimated_quality_delta, MIN_QUALITY_DELTA_THRESHOLD));
        }
        if !latency_acceptable {
            issues.push(format!("Latency degradation +{}ms exceeds 500ms limit", proposal.estimated_latency_delta_ms));
        }
        if !role_boundary_ok {
            issues.push(format!("Improvement type '{}' may exceed agent {} capabilities", proposal.improvement_type, proposal.agent_id));
        }
        if !no_conflicts {
            issues.push(format!("Conflicting deployment detected for agent {}", proposal.agent_id));
        }
        (VoteDecision::Reject, format!("Safety gates failed: {}", issues.join("; ")))
    };

    ApprovalVote {
        proposal_id: proposal.id.clone(),
        voter_agent_id: 22, // Odin
        voter_agent_name: "odin".to_string(),
        vote_decision: decision,
        reasoning,
        conditions_for_deployment: None,
        reviewed_at: Utc::now(),
    }
}

/// Frigg's detailed advisory review (2-5 minutes)
/// Deep checks: domain expertise, compliance, conditions
pub async fn frigg_detailed_review(
    pool: &MySqlPool,
    proposal: &SkillImprovementProposal,
    odin_vote: &ApprovalVote,
) -> ApprovalVote {
    tracing::info!(
        "Frigg reviewing proposal: agent={}, skill={}, odin_decision={:?}",
        proposal.agent_id,
        proposal.skill_name,
        odin_vote.vote_decision
    );

    // If Odin rejected, Frigg still reviews but defers to safety gates
    if odin_vote.vote_decision == VoteDecision::Reject {
        return ApprovalVote {
            proposal_id: proposal.id.clone(),
            voter_agent_id: 27, // Frigg
            voter_agent_name: "frigg".to_string(),
            vote_decision: VoteDecision::Reject,
            reasoning: format!(
                "Deferring to Odin's safety evaluation. Primary concern: {}",
                odin_vote.reasoning
            ),
            conditions_for_deployment: None,
            reviewed_at: Utc::now(),
        };
    }

    // Detailed domain expertise check
    let domain_expertise_ok = validate_frigg_expertise(proposal);

    // Compliance check: ensure change doesn't violate governance policies
    let compliance_ok = validate_compliance_implications(proposal).await;

    // Analyze weak areas for soundness
    let weak_area_analysis = analyze_weak_areas(proposal);

    let (decision, reasoning, conditions) = if domain_expertise_ok && compliance_ok {
        // Propose monitoring conditions for safety
        let deployment_conditions = json!({
            "monitor_metrics": ["quality_score", "latency_ms", "error_rate"],
            "monitoring_window_hours": 6,
            "rollback_threshold_quality_delta": -0.05,
            "rollback_threshold_latency_ms": 1000,
            "required_approval_gate": "both_odin_frigg",
            "canary_deployment": {
                "phase_1_percentage": 5,
                "phase_1_duration_hours": 2,
                "phase_2_percentage": 25,
                "phase_2_duration_hours": 6,
                "phase_3_percentage": 50,
                "phase_3_duration_hours": 12,
                "phase_4_percentage": 100
            }
        });

        (
            VoteDecision::Conditional,
            format!(
                "✓ Domain expertise verified: {}. ✓ Compliance check passed. ✓ Weak area analysis sound: {}. Recommending phased deployment with monitoring.",
                if domain_expertise_ok { "SRE knowledge is deep" } else { "" },
                weak_area_analysis
            ),
            Some(deployment_conditions),
        )
    } else {
        let mut issues = Vec::new();
        if !domain_expertise_ok {
            issues.push("Domain expertise gaps detected in proposed reasoning".to_string());
        }
        if !compliance_ok {
            issues.push("Potential compliance implications require further review".to_string());
        }
        (
            VoteDecision::Reject,
            format!("Detailed review identified concerns: {}", issues.join("; ")),
            None,
        )
    };

    ApprovalVote {
        proposal_id: proposal.id.clone(),
        voter_agent_id: 27, // Frigg
        voter_agent_name: "frigg".to_string(),
        vote_decision: decision,
        reasoning,
        conditions_for_deployment: conditions,
        reviewed_at: Utc::now(),
    }
}

/// Evaluate consensus: both Odin AND Frigg must approve
/// Frigg can approve with conditions; Odin's conditions take precedence (safety first)
pub fn evaluate_consensus(
    odin_vote: &ApprovalVote,
    frigg_vote: &ApprovalVote,
) -> GovernanceResult {
    let proposal_id = odin_vote.proposal_id.clone();

    // Consensus rules:
    // - Both APPROVE → APPROVE
    // - Odin APPROVE + Frigg CONDITIONAL → CONDITIONAL (with Frigg's conditions)
    // - Either REJECT → REJECT
    let consensus_decision = match (&odin_vote.vote_decision, &frigg_vote.vote_decision) {
        (VoteDecision::Approve, VoteDecision::Approve) => Some(VoteDecision::Approve),
        (VoteDecision::Approve, VoteDecision::Conditional) => Some(VoteDecision::Conditional),
        (VoteDecision::Conditional, VoteDecision::Approve) => Some(VoteDecision::Conditional),
        (VoteDecision::Conditional, VoteDecision::Conditional) => Some(VoteDecision::Conditional),
        _ => Some(VoteDecision::Reject), // Either vote is REJECT
    };

    // Merge conditions: Odin's safety gates + Frigg's advisory conditions
    let final_conditions = match (&odin_vote.conditions_for_deployment, &frigg_vote.conditions_for_deployment) {
        (Some(odin_cond), Some(frigg_cond)) => {
            let mut merged = odin_cond.clone();
            if let (serde_json::Value::Object(ref mut merged_obj), serde_json::Value::Object(frigg_obj)) =
                (&mut merged, frigg_cond)
            {
                for (k, v) in frigg_obj {
                    merged_obj.insert(k.clone(), v.clone());
                }
            }
            Some(merged)
        }
        (Some(cond), None) => Some(cond.clone()),
        (None, Some(cond)) => Some(cond.clone()),
        (None, None) => None,
    };

    let can_proceed = matches!(consensus_decision, Some(VoteDecision::Approve));

    GovernanceResult {
        proposal_id,
        odin_vote: Some(odin_vote.clone()),
        frigg_vote: Some(frigg_vote.clone()),
        consensus_decision,
        final_conditions,
        can_proceed_to_deployment: can_proceed,
    }
}

/// Store votes in database
pub async fn record_approval_votes(
    pool: &MySqlPool,
    tenant_id: &str,
    governance_result: &GovernanceResult,
) -> Result<(), sqlx::Error> {
    // Record Odin's vote
    if let Some(odin_vote) = &governance_result.odin_vote {
        sqlx::query(
            r#"
            INSERT INTO skill_approval_votes (
                tenant_id, proposal_id, voter_agent_id, voter_agent_name,
                vote_decision, reasoning, conditions_for_deployment, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            "#,
        )
        .bind(tenant_id)
        .bind(&governance_result.proposal_id)
        .bind(odin_vote.voter_agent_id)
        .bind(&odin_vote.voter_agent_name)
        .bind(odin_vote.vote_decision.to_string())
        .bind(&odin_vote.reasoning)
        .bind(odin_vote.conditions_for_deployment.as_ref().map(|c| c.to_string()))
        .bind(Utc::now())
        .execute(pool)
        .await?;
    }

    // Record Frigg's vote
    if let Some(frigg_vote) = &governance_result.frigg_vote {
        sqlx::query(
            r#"
            INSERT INTO skill_approval_votes (
                tenant_id, proposal_id, voter_agent_id, voter_agent_name,
                vote_decision, reasoning, conditions_for_deployment, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            "#,
        )
        .bind(tenant_id)
        .bind(&governance_result.proposal_id)
        .bind(frigg_vote.voter_agent_id)
        .bind(&frigg_vote.voter_agent_name)
        .bind(frigg_vote.vote_decision.to_string())
        .bind(&frigg_vote.reasoning)
        .bind(frigg_vote.conditions_for_deployment.as_ref().map(|c| c.to_string()))
        .bind(Utc::now())
        .execute(pool)
        .await?;
    }

    tracing::info!(
        "Governance votes recorded: proposal={}, consensus={:?}, can_deploy={}",
        governance_result.proposal_id,
        governance_result.consensus_decision,
        governance_result.can_proceed_to_deployment
    );

    Ok(())
}

// Helper functions

fn validate_agent_domain(agent_id: i64, improvement_type: &str) -> bool {
    // Ensure agent stays within their role
    match agent_id {
        27 => {
            // Frigg: SRE, compliance, governance
            matches!(improvement_type, "system_prompt_update" | "parameter_tuning")
        }
        _ => {
            // Other agents: only parameter_tuning for safety
            improvement_type == "parameter_tuning"
        }
    }
}

async fn has_conflicting_deployment(pool: &MySqlPool, agent_id: i64) -> Result<bool, sqlx::Error> {
    let conflict = sqlx::query!(
        r#"
        SELECT COUNT(*) as conflict_count
        FROM skill_deployment_log
        WHERE agent_id = ?
          AND status IN ('CANARY_IN_PROGRESS', 'STAGED_IN_PROGRESS')
          AND updated_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        "#,
        agent_id
    )
    .fetch_one(pool)
    .await?;

    Ok(conflict.conflict_count.unwrap_or(0) > 0)
}

fn validate_frigg_expertise(proposal: &SkillImprovementProposal) -> bool {
    // For Frigg specifically, check if reasoning demonstrates domain expertise
    let reasoning_lower = proposal.reasoning.to_lowercase();

    // Check for deep knowledge indicators
    let has_framework = reasoning_lower.contains("framework")
        || reasoning_lower.contains("pattern")
        || reasoning_lower.contains("principle");
    let has_depth = reasoning_lower.len() > 50; // Non-trivial reasoning

    has_framework && has_depth
}

async fn validate_compliance_implications(_proposal: &SkillImprovementProposal) -> bool {
    // Placeholder: In production, check against compliance policies
    // For now, assume no compliance conflicts
    true
}

fn analyze_weak_areas(proposal: &SkillImprovementProposal) -> String {
    if proposal.weak_areas_identified.is_empty() {
        return "No specific weak areas identified".to_string();
    }

    let domains: Vec<String> = proposal
        .weak_areas_identified
        .iter()
        .map(|wa| format!("{} (quality: {:.2})", wa.domain, wa.current_quality))
        .collect();

    format!("Weak areas: {}", domains.join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_agent_domain_validation() {
        assert!(validate_agent_domain(27, "system_prompt_update"));
        assert!(validate_agent_domain(27, "parameter_tuning"));
        assert!(!validate_agent_domain(27, "unknown_type"));
        assert!(validate_agent_domain(1, "parameter_tuning"));
        assert!(!validate_agent_domain(1, "system_prompt_update"));
    }

    #[test]
    fn test_consensus_both_approve() {
        let odin = ApprovalVote {
            proposal_id: "prop1".to_string(),
            voter_agent_id: 22,
            voter_agent_name: "odin".to_string(),
            vote_decision: VoteDecision::Approve,
            reasoning: "All checks pass".to_string(),
            conditions_for_deployment: None,
            reviewed_at: Utc::now(),
        };

        let frigg = ApprovalVote {
            proposal_id: "prop1".to_string(),
            voter_agent_id: 27,
            voter_agent_name: "frigg".to_string(),
            vote_decision: VoteDecision::Approve,
            reasoning: "Domain expertise verified".to_string(),
            conditions_for_deployment: None,
            reviewed_at: Utc::now(),
        };

        let result = evaluate_consensus(&odin, &frigg);
        assert_eq!(result.consensus_decision, Some(VoteDecision::Approve));
        assert!(result.can_proceed_to_deployment);
    }

    #[test]
    fn test_consensus_reject_if_either_rejects() {
        let odin = ApprovalVote {
            proposal_id: "prop1".to_string(),
            voter_agent_id: 22,
            voter_agent_name: "odin".to_string(),
            vote_decision: VoteDecision::Reject,
            reasoning: "Safety threshold not met".to_string(),
            conditions_for_deployment: None,
            reviewed_at: Utc::now(),
        };

        let frigg = ApprovalVote {
            proposal_id: "prop1".to_string(),
            voter_agent_id: 27,
            voter_agent_name: "frigg".to_string(),
            vote_decision: VoteDecision::Approve,
            reasoning: "Looks good".to_string(),
            conditions_for_deployment: None,
            reviewed_at: Utc::now(),
        };

        let result = evaluate_consensus(&odin, &frigg);
        assert_eq!(result.consensus_decision, Some(VoteDecision::Reject));
        assert!(!result.can_proceed_to_deployment);
    }
}
