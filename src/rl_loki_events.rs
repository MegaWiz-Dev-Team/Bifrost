//! RL Governance Event Logging to Loki
//!
//! Sends all RL events (proposals, votes, deployments) to Loki for audit trail,
//! observability, and governance tracking instead of storing in database tables.

use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::info;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RLGovernanceEvent {
    pub event_type: String,
    pub tenant_id: String,
    pub agent_id: i64,
    pub agent_name: String,
    pub timestamp: String,
    pub details: serde_json::Value,
}

impl RLGovernanceEvent {
    /// Log proposal submission event
    pub fn proposal_submitted(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        skill_name: &str,
        improvement_type: &str,
        estimated_delta: f64,
    ) -> Self {
        let details = serde_json::json!({
            "proposal_id": proposal_id,
            "skill_name": skill_name,
            "improvement_type": improvement_type,
            "estimated_quality_delta": estimated_delta,
        });

        Self {
            event_type: "proposal_submitted".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details,
        }
    }

    /// Log Odin vote event
    pub fn odin_vote(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        decision: &str,
        reasoning: &str,
    ) -> Self {
        Self {
            event_type: "odin_vote".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details: serde_json::json!({
                "proposal_id": proposal_id,
                "decision": decision,
                "reasoning": reasoning,
                "voter": "odin",
            }),
        }
    }

    /// Log Frigg vote event
    pub fn frigg_vote(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        decision: &str,
        reasoning: &str,
        conditions: Option<&str>,
    ) -> Self {
        let mut details = serde_json::json!({
            "proposal_id": proposal_id,
            "decision": decision,
            "reasoning": reasoning,
            "voter": "frigg",
        });

        if let Some(c) = conditions {
            details["conditions_for_deployment"] = serde_json::json!(c);
        }

        Self {
            event_type: "frigg_vote".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details,
        }
    }

    /// Log canary deployment started
    pub fn canary_deployment_started(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        skill_name: &str,
    ) -> Self {
        Self {
            event_type: "canary_deployment_started".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details: serde_json::json!({
                "proposal_id": proposal_id,
                "skill_name": skill_name,
                "phase": "CANARY_IN_PROGRESS",
                "percentage": 5,
            }),
        }
    }

    /// Log deployment phase advancement
    pub fn deployment_advanced(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        old_phase: &str,
        new_phase: &str,
        percentage: i32,
    ) -> Self {
        Self {
            event_type: "deployment_advanced".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details: serde_json::json!({
                "proposal_id": proposal_id,
                "phase_transition": format!("{} -> {}", old_phase, new_phase),
                "deployment_percentage": percentage,
            }),
        }
    }

    /// Log auto-rollback triggered
    pub fn rollback_triggered(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        reason: &str,
        metrics: &serde_json::Value,
    ) -> Self {
        Self {
            event_type: "rollback_triggered".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details: serde_json::json!({
                "proposal_id": proposal_id,
                "reason": reason,
                "metrics": metrics,
            }),
        }
    }

    /// Log proposal rejected by governance
    pub fn proposal_rejected(
        tenant_id: &str,
        agent_id: i64,
        agent_name: &str,
        proposal_id: &str,
        consensus_decision: &str,
        odin_reason: &str,
        frigg_reason: Option<&str>,
    ) -> Self {
        let mut details = serde_json::json!({
            "proposal_id": proposal_id,
            "consensus_decision": consensus_decision,
            "odin_reason": odin_reason,
        });

        if let Some(frigg) = frigg_reason {
            details["frigg_reason"] = serde_json::json!(frigg);
        }

        Self {
            event_type: "proposal_rejected".to_string(),
            tenant_id: tenant_id.to_string(),
            agent_id,
            agent_name: agent_name.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            details,
        }
    }
}

/// Log an RL governance event via structured logging
pub fn log_event(event: RLGovernanceEvent) {
    let event_type = event.event_type.clone();
    let tenant = event.tenant_id.clone();
    let agent = event.agent_name.clone();

    info!(
        event_type = %event_type,
        tenant_id = %tenant,
        agent_id = event.agent_id,
        agent_name = %agent,
        details = %serde_json::to_string(&event.details).unwrap_or_default(),
        timestamp = %event.timestamp,
        "RL Governance Event"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proposal_event_serialization() {
        let event = RLGovernanceEvent::proposal_submitted(
            "asgard_medical",
            1,
            "eir-medical",
            "prop-123",
            "icd10_classification",
            "skill_enhancement",
            0.15,
        );

        assert_eq!(event.event_type, "proposal_submitted");
        assert_eq!(event.tenant_id, "asgard_medical");
        assert_eq!(event.agent_id, 1);

        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("proposal_submitted"));
        assert!(json.contains("prop-123"));
    }

    #[test]
    fn test_rollback_event() {
        let metrics = serde_json::json!({
            "quality_score": 0.65,
            "error_rate": 0.08,
            "latency_ms": 4500,
        });

        let event = RLGovernanceEvent::rollback_triggered(
            "asgard_medical",
            1,
            "eir-medical",
            "prop-123",
            "Quality degradation detected",
            &metrics,
        );

        assert_eq!(event.event_type, "rollback_triggered");
    }
}
