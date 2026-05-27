//! Agent Self-Evaluation & Skill Improvement Proposal System
//!
//! Agents analyze their daily feedback to identify weak areas,
//! propose concrete improvements, and submit for Odin/Frigg approval

use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::MySqlPool;
use uuid::Uuid;

/// A skill improvement proposal from an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillImprovementProposal {
    pub id: String,
    pub tenant_id: String,
    pub agent_id: i64,
    pub agent_name: String,

    // What's being improved?
    pub skill_name: String,
    pub improvement_type: String, // 'system_prompt_update', 'parameter_tuning', etc.

    // Current state
    pub current_config: Value,
    pub proposed_config: Value,
    pub config_diff: Value,

    // Analysis
    pub reasoning: String,
    pub weak_areas_identified: Vec<WeakArea>,

    // Impact estimation
    pub estimated_quality_delta: f32,
    pub estimated_latency_delta_ms: i32,
    pub estimated_confidence: f32,

    // Governance
    pub approval_level: String, // 'odin_frigg' = both must approve
    pub status: String,         // 'PENDING_APPROVAL'

    pub created_at: chrono::DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WeakArea {
    pub domain: String,
    pub current_quality: f32,
    pub conversation_count: i32,
    pub improvement_needed: f32,
}

/// Analyze agent's daily feedback and generate self-evaluation
pub async fn agent_self_evaluate(
    pool: &MySqlPool,
    tenant_id: &str,
    agent_id: i64,
    agent_name: &str,
) -> Result<Option<SkillImprovementProposal>, sqlx::Error> {
    // Get daily metrics
    let metrics = sqlx::query!(
        r#"
        SELECT
            conversation_count,
            avg_quality_score,
            lowest_quality_domain,
            lowest_quality_score,
            improvement_opportunity_score
        FROM agent_rl_daily_metrics
        WHERE agent_id = ? AND tenant_id = ?
        ORDER BY metric_date DESC
        LIMIT 1
        "#,
        agent_id,
        tenant_id
    )
    .fetch_optional(pool)
    .await?;

    let metrics = match metrics {
        Some(m) => m,
        None => return Ok(None), // No metrics yet
    };

    let avg_quality = metrics.avg_quality_score.unwrap_or(0.5) as f32;
    let improvement_opp = metrics.improvement_opportunity_score.unwrap_or(0.0) as f32;

    // Only propose improvement if opportunity score > 0.6
    // (means quality is low or variable across domains)
    if improvement_opp < 0.6 {
        tracing::info!(
            "Agent {} has improvement_opportunity={:.2}, skipping proposal (threshold=0.6)",
            agent_id,
            improvement_opp
        );
        return Ok(None);
    }

    // Get weak areas in detail
    let weak_areas = sqlx::query_as!(
        WeakArea,
        r#"
        SELECT
            feedback_domain as "domain!",
            AVG(quality_score) as "current_quality!",
            COUNT(*) as "conversation_count!",
            MAX(0.0) as "improvement_needed!"
        FROM agent_feedback_logs
        WHERE agent_id = ? AND tenant_id = ?
          AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
          AND feedback_domain IS NOT NULL
        GROUP BY feedback_domain
        ORDER BY AVG(quality_score) ASC
        LIMIT 3
        "#,
        agent_id,
        tenant_id
    )
    .fetch_all(pool)
    .await?;

    if weak_areas.is_empty() {
        return Ok(None);
    }

    // Build proposal based on agent's weak areas
    let proposal = build_improvement_proposal(
        agent_id,
        agent_name,
        tenant_id,
        avg_quality,
        &weak_areas,
    )
    .await;

    tracing::info!(
        "Agent {} self-evaluated: proposing {} for {:.2} quality improvement",
        agent_id,
        proposal.skill_name,
        proposal.estimated_quality_delta
    );

    Ok(Some(proposal))
}

/// Build a specific improvement proposal based on weak areas
async fn build_improvement_proposal(
    agent_id: i64,
    agent_name: &str,
    tenant_id: &str,
    current_quality: f32,
    weak_areas: &[WeakArea],
) -> SkillImprovementProposal {
    let weakest = &weak_areas[0];

    // Determine improvement strategy based on agent and domain
    let (improvement_type, estimated_delta, latency_delta, reasoning) =
        match (agent_id, weakest.domain.as_str()) {
            (27, "SRE") => (
                "system_prompt_update",
                0.12,
                200,
                "Need deeper SRE knowledge. Will study Google SRE book principles, \
                 add error budget framework, and include production reliability patterns."
                    .to_string(),
            ),
            (27, "compliance") => (
                "system_prompt_update",
                0.08,
                150,
                "Compliance reasoning needs strengthening. Will add ISO frameworks, \
                 regulatory alignment checks, and governance patterns."
                    .to_string(),
            ),
            (27, _) => (
                "system_prompt_update",
                0.10,
                100,
                format!(
                    "Quality is low in {} domain. Will expand reasoning depth and add \
                     domain-specific examples.",
                    weakest.domain
                ),
            ),
            _ => (
                "parameter_tuning",
                0.07,
                50,
                "Will increase reasoning depth and improve response quality through \
                 parameter adjustments."
                    .to_string(),
            ),
        };

    // Mock current config (in production, fetch from agent_configs)
    let current_config = json!({
        "model_id": "gemini-3.1-pro-preview",
        "temperature": 0.30,
        "top_k": 5,
        "system_prompt_version": 1
    });

    // Build proposed config
    let mut proposed_config = current_config.clone();
    if let Some(obj) = proposed_config.as_object_mut() {
        if improvement_type == "system_prompt_update" {
            obj["system_prompt_version"] = json!(2);
            obj["top_k"] = json!(8);
            obj["temperature"] = json!(0.25);
        } else {
            obj["temperature"] = json!(0.28);
            obj["top_k"] = json!(6);
        }
    }

    let config_diff = json!({
        "temperature": format!("[{} → {}]", 0.30, 0.25),
        "top_k": format!("[{} → {}]", 5, 8),
        "improvement_type": improvement_type
    });

    SkillImprovementProposal {
        id: Uuid::new_v4().to_string(),
        tenant_id: tenant_id.to_string(),
        agent_id,
        agent_name: agent_name.to_string(),
        skill_name: format!("{}_v2_{}", agent_name, weakest.domain),
        improvement_type: improvement_type.to_string(),
        current_config,
        proposed_config,
        config_diff,
        reasoning,
        weak_areas_identified: weak_areas.to_vec(),
        estimated_quality_delta: estimated_delta,
        estimated_latency_delta_ms: latency_delta,
        estimated_confidence: 0.82,
        approval_level: "odin_frigg".to_string(),
        status: "PENDING_APPROVAL".to_string(),
        created_at: Utc::now(),
    }
}

/// Submit proposal to database for review
pub async fn submit_proposal(
    pool: &MySqlPool,
    proposal: &SkillImprovementProposal,
) -> Result<i64, sqlx::Error> {
    let result = sqlx::query(
        r#"
        INSERT INTO skill_improvement_proposals (
            tenant_id, agent_id,
            skill_name, improvement_type,
            current_config, proposed_config, config_diff,
            reasoning, weak_areas_identified,
            estimated_quality_delta, estimated_latency_delta_ms,
            estimated_confidence,
            approval_level, status,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(&proposal.tenant_id)
    .bind(proposal.agent_id)
    .bind(&proposal.skill_name)
    .bind(&proposal.improvement_type)
    .bind(proposal.current_config.to_string())
    .bind(proposal.proposed_config.to_string())
    .bind(proposal.config_diff.to_string())
    .bind(&proposal.reasoning)
    .bind(serde_json::to_string(&proposal.weak_areas_identified).unwrap_or_default())
    .bind(proposal.estimated_quality_delta)
    .bind(proposal.estimated_latency_delta_ms)
    .bind(proposal.estimated_confidence)
    .bind(&proposal.approval_level)
    .bind(&proposal.status)
    .execute(pool)
    .await?;

    tracing::info!(
        "Proposal submitted: agent={}, skill={}, id={}",
        proposal.agent_id,
        proposal.skill_name,
        result.last_insert_id()
    );

    Ok(result.last_insert_id() as i64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_proposal_building() {
        let weak_areas = vec![WeakArea {
            domain: "SRE".to_string(),
            current_quality: 0.65,
            conversation_count: 12,
            improvement_needed: 0.30,
        }];

        let proposal = futures::executor::block_on(build_improvement_proposal(
            27,
            "frigg",
            "asgard_platform",
            0.91,
            &weak_areas,
        ));

        assert!(proposal.estimated_quality_delta > 0.0);
        assert_eq!(proposal.approval_level, "odin_frigg");
        assert_eq!(proposal.status, "PENDING_APPROVAL");
    }
}
