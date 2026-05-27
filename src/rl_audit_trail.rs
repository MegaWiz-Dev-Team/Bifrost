//! Agent RL System Audit Trail & Compliance Logging
//!
//! Comprehensive logging of all reinforcement learning events for regulatory
//! compliance, forensics, and system transparency.
//!
//! Logged events:
//! - Agent self-evaluations and proposals
//! - Governance voting decisions (Odin + Frigg)
//! - Deployment phases and transitions
//! - Auto-rollback triggers and reasons
//! - Configuration changes and system impacts

use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::MySqlPool;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AuditEventType {
    #[serde(rename = "AGENT_SELF_EVAL")]
    AgentSelfEval,
    #[serde(rename = "PROPOSAL_SUBMITTED")]
    ProposalSubmitted,
    #[serde(rename = "ODIN_VOTE")]
    OdinVote,
    #[serde(rename = "FRIGG_VOTE")]
    FriggVote,
    #[serde(rename = "CANARY_STARTED")]
    CanaryStarted,
    #[serde(rename = "CANARY_PASSED")]
    CanaryPassed,
    #[serde(rename = "CANARY_FAILED")]
    CanaryFailed,
    #[serde(rename = "STAGED_ADVANCED")]
    StagedAdvanced,
    #[serde(rename = "AUTO_ROLLBACK")]
    AutoRollback,
    #[serde(rename = "DEPLOYMENT_COMPLETE")]
    DeploymentComplete,
    #[serde(rename = "PROPOSAL_REJECTED")]
    ProposalRejected,
}

impl std::fmt::Display for AuditEventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            AuditEventType::AgentSelfEval => "AGENT_SELF_EVAL",
            AuditEventType::ProposalSubmitted => "PROPOSAL_SUBMITTED",
            AuditEventType::OdinVote => "ODIN_VOTE",
            AuditEventType::FriggVote => "FRIGG_VOTE",
            AuditEventType::CanaryStarted => "CANARY_STARTED",
            AuditEventType::CanaryPassed => "CANARY_PASSED",
            AuditEventType::CanaryFailed => "CANARY_FAILED",
            AuditEventType::StagedAdvanced => "STAGED_ADVANCED",
            AuditEventType::AutoRollback => "AUTO_ROLLBACK",
            AuditEventType::DeploymentComplete => "DEPLOYMENT_COMPLETE",
            AuditEventType::ProposalRejected => "PROPOSAL_REJECTED",
        };
        write!(f, "{}", s)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub tenant_id: String,
    pub event_type: AuditEventType,
    pub agent_id: i64,
    pub agent_name: String,
    pub proposal_id: Option<String>,
    pub event_details: Value,
    pub actor_agent_id: i64, // Who triggered this event (Odin, system, etc.)
    pub actor_agent_name: String,
    pub impact_summary: String,
    pub compliance_flags: Option<Vec<String>>,
    pub created_at: chrono::DateTime<Utc>,
}

/// Log agent self-evaluation event
pub async fn log_self_evaluation(
    pool: &MySqlPool,
    tenant_id: &str,
    agent_id: i64,
    agent_name: &str,
    improvement_opportunity_score: f32,
    weak_domains: &[String],
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "improvement_opportunity_score": improvement_opportunity_score,
        "weak_domains": weak_domains,
        "timestamp": Utc::now().to_rfc3339()
    });

    let impact_summary = format!(
        "Agent {} evaluated itself; opportunity_score={:.2}; weak_domains={}",
        agent_name,
        improvement_opportunity_score,
        weak_domains.join(",")
    );

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::AgentSelfEval.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(event_details.to_string())
    .bind(agent_id) // Agent evaluating itself
    .bind(agent_name)
    .bind(impact_summary)
    .execute(pool)
    .await?;

    tracing::info!(
        "Audit logged: type={}, agent={}, opportunity={:.2}",
        AuditEventType::AgentSelfEval,
        agent_name,
        improvement_opportunity_score
    );

    Ok(())
}

/// Log proposal submission event
pub async fn log_proposal_submitted(
    pool: &MySqlPool,
    tenant_id: &str,
    agent_id: i64,
    agent_name: &str,
    proposal_id: &str,
    skill_name: &str,
    improvement_type: &str,
    estimated_quality_delta: f32,
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "proposal_id": proposal_id,
        "skill_name": skill_name,
        "improvement_type": improvement_type,
        "estimated_quality_delta": estimated_quality_delta,
        "approval_level": "odin_frigg"
    });

    let impact_summary = format!(
        "Proposal submitted by {}; skill={}, type={}, estimated_improvement={:.2}",
        agent_name, skill_name, improvement_type, estimated_quality_delta
    );

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name, proposal_id,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::ProposalSubmitted.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(proposal_id)
    .bind(event_details.to_string())
    .bind(agent_id) // Self-submitted
    .bind(agent_name)
    .bind(impact_summary)
    .execute(pool)
    .await?;

    tracing::info!(
        "Audit logged: type={}, proposal={}, agent={}, quality_delta={:.2}",
        AuditEventType::ProposalSubmitted,
        proposal_id,
        agent_name,
        estimated_quality_delta
    );

    Ok(())
}

/// Log Odin's governance vote
pub async fn log_odin_vote(
    pool: &MySqlPool,
    tenant_id: &str,
    proposal_id: &str,
    agent_id: i64,
    agent_name: &str,
    vote_decision: &str,
    reasoning: &str,
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "vote_decision": vote_decision,
        "reasoning": reasoning,
        "vote_type": "safety_gates"
    });

    let impact_summary = format!(
        "Odin reviewed proposal {} for agent {}; decision={}, focus=safety_gates",
        proposal_id, agent_name, vote_decision
    );

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name, proposal_id,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::OdinVote.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(proposal_id)
    .bind(event_details.to_string())
    .bind(22) // Odin's agent_id
    .bind("odin")
    .bind(impact_summary)
    .execute(pool)
    .await?;

    tracing::info!(
        "Audit logged: type={}, proposal={}, vote={}, actor=odin",
        AuditEventType::OdinVote,
        proposal_id,
        vote_decision
    );

    Ok(())
}

/// Log Frigg's governance vote
pub async fn log_frigg_vote(
    pool: &MySqlPool,
    tenant_id: &str,
    proposal_id: &str,
    agent_id: i64,
    agent_name: &str,
    vote_decision: &str,
    reasoning: &str,
    conditions: Option<&str>,
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "vote_decision": vote_decision,
        "reasoning": reasoning,
        "conditions": conditions,
        "vote_type": "advisory_review"
    });

    let impact_summary = format!(
        "Frigg reviewed proposal {} for agent {}; decision={}, focus=domain_expertise{}",
        proposal_id,
        agent_name,
        vote_decision,
        conditions
            .map(|c| format!("; conditions={}", c))
            .unwrap_or_default()
    );

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name, proposal_id,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::FriggVote.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(proposal_id)
    .bind(event_details.to_string())
    .bind(27) // Frigg's agent_id
    .bind("frigg")
    .bind(impact_summary)
    .execute(pool)
    .await?;

    tracing::info!(
        "Audit logged: type={}, proposal={}, vote={}, actor=frigg",
        AuditEventType::FriggVote,
        proposal_id,
        vote_decision
    );

    Ok(())
}

/// Log canary deployment start
pub async fn log_canary_started(
    pool: &MySqlPool,
    tenant_id: &str,
    proposal_id: &str,
    agent_id: i64,
    agent_name: &str,
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "deployment_phase": "canary",
        "traffic_percentage": 5,
        "duration_hours": 2,
        "rollback_quality_threshold": -0.05,
        "rollback_latency_threshold_ms": 1000
    });

    let impact_summary = format!(
        "Canary deployment started for agent {}; proposal={}; 5% traffic for 2 hours",
        agent_name, proposal_id
    );

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name, proposal_id,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::CanaryStarted.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(proposal_id)
    .bind(event_details.to_string())
    .bind(22) // System/Odin triggered
    .bind("system")
    .bind(impact_summary)
    .execute(pool)
    .await?;

    tracing::info!(
        "Audit logged: type={}, proposal={}, agent={}, phase=canary",
        AuditEventType::CanaryStarted,
        proposal_id,
        agent_name
    );

    Ok(())
}

/// Log auto-rollback trigger
pub async fn log_auto_rollback(
    pool: &MySqlPool,
    tenant_id: &str,
    proposal_id: &str,
    agent_id: i64,
    agent_name: &str,
    rollback_reason: &str,
    quality_delta: f32,
    latency_delta_ms: i32,
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "rollback_reason": rollback_reason,
        "quality_delta": quality_delta,
        "latency_delta_ms": latency_delta_ms,
        "triggered_by": "automatic_monitoring",
        "rollback_time": Utc::now().to_rfc3339()
    });

    let impact_summary = format!(
        "Auto-rollback triggered for agent {}; proposal={}; reason: {}; quality_delta={:.3}, latency_delta={}ms",
        agent_name, proposal_id, rollback_reason, quality_delta, latency_delta_ms
    );

    let compliance_flags = vec![
        "CRITICAL".to_string(),
        "AUTOMATIC_MITIGATION".to_string(),
    ];

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name, proposal_id,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, compliance_flags, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::AutoRollback.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(proposal_id)
    .bind(event_details.to_string())
    .bind(22) // System automated
    .bind("system")
    .bind(impact_summary)
    .bind(serde_json::to_string(&compliance_flags).unwrap_or_default())
    .execute(pool)
    .await?;

    tracing::warn!(
        "Audit logged: type={}, proposal={}, agent={}, reason={}",
        AuditEventType::AutoRollback,
        proposal_id,
        agent_name,
        rollback_reason
    );

    Ok(())
}

/// Log successful deployment completion
pub async fn log_deployment_complete(
    pool: &MySqlPool,
    tenant_id: &str,
    proposal_id: &str,
    agent_id: i64,
    agent_name: &str,
    final_quality_delta: f32,
) -> Result<(), sqlx::Error> {
    let event_details = json!({
        "deployment_phases": ["CANARY_IN_PROGRESS", "STAGED_25_PERCENT", "STAGED_50_PERCENT", "FULL_DEPLOYMENT"],
        "final_quality_delta": final_quality_delta,
        "completion_time": Utc::now().to_rfc3339()
    });

    let impact_summary = format!(
        "Deployment completed for agent {}; proposal={}; final_quality_improvement={:.2}",
        agent_name, proposal_id, final_quality_delta
    );

    sqlx::query(
        r#"
        INSERT INTO agent_rl_audit_trail (
            tenant_id, event_type, agent_id, agent_name, proposal_id,
            event_details, actor_agent_id, actor_agent_name,
            impact_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(tenant_id)
    .bind(AuditEventType::DeploymentComplete.to_string())
    .bind(agent_id)
    .bind(agent_name)
    .bind(proposal_id)
    .bind(event_details.to_string())
    .bind(22) // System completed
    .bind("system")
    .bind(impact_summary)
    .execute(pool)
    .await?;

    tracing::info!(
        "Audit logged: type={}, proposal={}, agent={}, quality_improvement={:.2}",
        AuditEventType::DeploymentComplete,
        proposal_id,
        agent_name,
        final_quality_delta
    );

    Ok(())
}

/// Retrieve audit trail for a proposal
pub async fn get_audit_trail(
    pool: &MySqlPool,
    tenant_id: &str,
    proposal_id: &str,
) -> Result<Vec<AuditEntry>, sqlx::Error> {
    let entries = sqlx::query_as!(
        AuditEntry,
        r#"
        SELECT
            tenant_id,
            event_type as "event_type: String",
            agent_id,
            agent_name,
            proposal_id,
            event_details,
            actor_agent_id,
            actor_agent_name,
            impact_summary,
            compliance_flags,
            created_at
        FROM agent_rl_audit_trail
        WHERE tenant_id = ? AND proposal_id = ?
        ORDER BY created_at ASC
        "#,
        tenant_id,
        proposal_id
    )
    .fetch_all(pool)
    .await?;

    Ok(entries
        .into_iter()
        .map(|e| {
            let event_type = match e.event_type.as_str() {
                "AGENT_SELF_EVAL" => AuditEventType::AgentSelfEval,
                "PROPOSAL_SUBMITTED" => AuditEventType::ProposalSubmitted,
                "ODIN_VOTE" => AuditEventType::OdinVote,
                "FRIGG_VOTE" => AuditEventType::FriggVote,
                "CANARY_STARTED" => AuditEventType::CanaryStarted,
                "CANARY_PASSED" => AuditEventType::CanaryPassed,
                "CANARY_FAILED" => AuditEventType::CanaryFailed,
                "STAGED_ADVANCED" => AuditEventType::StagedAdvanced,
                "AUTO_ROLLBACK" => AuditEventType::AutoRollback,
                "DEPLOYMENT_COMPLETE" => AuditEventType::DeploymentComplete,
                _ => AuditEventType::ProposalRejected,
            };
            AuditEntry {
                tenant_id: e.tenant_id,
                event_type,
                agent_id: e.agent_id,
                agent_name: e.agent_name,
                proposal_id: e.proposal_id,
                event_details: e.event_details,
                actor_agent_id: e.actor_agent_id,
                actor_agent_name: e.actor_agent_name,
                impact_summary: e.impact_summary,
                compliance_flags: e.compliance_flags.and_then(|f| serde_json::from_str::<Vec<String>>(&f).ok()),
                created_at: e.created_at,
            }
        })
        .collect())
}

/// Export audit trail for compliance reporting
pub async fn export_compliance_report(
    pool: &MySqlPool,
    tenant_id: &str,
) -> Result<Value, sqlx::Error> {
    let entries = sqlx::query!(
        r#"
        SELECT
            event_type,
            COUNT(*) as event_count,
            COUNT(DISTINCT agent_id) as agents_affected,
            MAX(created_at) as latest_event
        FROM agent_rl_audit_trail
        WHERE tenant_id = ?
        GROUP BY event_type
        "#,
        tenant_id
    )
    .fetch_all(pool)
    .await?;

    let report = json!({
        "tenant_id": tenant_id,
        "generated_at": Utc::now().to_rfc3339(),
        "summary": {
            "total_entries": entries.len(),
            "events_by_type": entries.iter().map(|e| {
                json!({
                    "type": e.event_type,
                    "count": e.event_count,
                    "agents_affected": e.agents_affected
                })
            }).collect::<Vec<_>>()
        }
    });

    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audit_event_type_display() {
        assert_eq!(AuditEventType::AgentSelfEval.to_string(), "AGENT_SELF_EVAL");
        assert_eq!(AuditEventType::OdinVote.to_string(), "ODIN_VOTE");
        assert_eq!(AuditEventType::FriggVote.to_string(), "FRIGG_VOTE");
        assert_eq!(AuditEventType::AutoRollback.to_string(), "AUTO_ROLLBACK");
    }
}
