//! Agent Skill Improvement Safe Deployment System
//!
//! Implements gradual rollout of approved skill improvements with automatic
//! quality monitoring and rollback triggers.
//!
//! Deployment phases:
//! - Phase 1 (Canary): 5% traffic for 2 hours
//! - Phase 2 (Staged): 25% traffic for 6 hours
//! - Phase 3 (Staged): 50% traffic for 12 hours
//! - Phase 4 (Full): 100% traffic
//!
//! Rollback triggers:
//! - Quality delta < -0.05 (5% quality loss)
//! - Latency > +1000ms
//! - Error rate > 5%

use chrono::{TimeDelta, Utc};
use serde::{Deserialize, Serialize};
use sqlx::MySqlPool;

use crate::rl_governance_voting::GovernanceResult;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum DeploymentPhase {
    #[serde(rename = "CANARY_IN_PROGRESS")]
    CanaryInProgress,
    #[serde(rename = "STAGED_25_PERCENT")]
    Staged25Percent,
    #[serde(rename = "STAGED_50_PERCENT")]
    Staged50Percent,
    #[serde(rename = "FULL_DEPLOYMENT")]
    FullDeployment,
    #[serde(rename = "ROLLED_BACK")]
    RolledBack,
}

impl std::fmt::Display for DeploymentPhase {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DeploymentPhase::CanaryInProgress => write!(f, "CANARY_IN_PROGRESS"),
            DeploymentPhase::Staged25Percent => write!(f, "STAGED_25_PERCENT"),
            DeploymentPhase::Staged50Percent => write!(f, "STAGED_50_PERCENT"),
            DeploymentPhase::FullDeployment => write!(f, "FULL_DEPLOYMENT"),
            DeploymentPhase::RolledBack => write!(f, "ROLLED_BACK"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeploymentMetrics {
    pub proposal_id: String,
    pub agent_id: i64,
    pub current_phase: DeploymentPhase,
    pub deployment_percentage: i32,
    pub phase_start_time: chrono::DateTime<Utc>,
    pub phase_duration_hours: i32,
    pub quality_score_current: f32,
    pub quality_score_baseline: f32,
    pub quality_delta: f32,
    pub latency_ms_current: i32,
    pub latency_ms_baseline: i32,
    pub latency_delta_ms: i32,
    pub error_rate: f32,
    pub requests_processed: i64,
    pub is_healthy: bool,
    pub rollback_triggered: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanaryConfig {
    pub percentage: i32,              // 5
    pub duration_hours: i32,          // 2
    pub min_requests: i64,            // 50 minimum requests for decision
    pub quality_threshold: f32,       // -0.05 rollback threshold
    pub latency_threshold_ms: i32,    // 1000ms rollback threshold
    pub error_rate_threshold: f32,    // 0.05 (5%) rollback threshold
}

impl Default for CanaryConfig {
    fn default() -> Self {
        Self {
            percentage: 5,
            duration_hours: 2,
            min_requests: 50,
            quality_threshold: -0.05,
            latency_threshold_ms: 1000,
            error_rate_threshold: 0.05,
        }
    }
}

/// Initiate canary deployment (Phase 1)
pub async fn start_canary_deployment(
    pool: &MySqlPool,
    proposal_id: &str,
    agent_id: i64,
    governance_result: &GovernanceResult,
) -> Result<DeploymentMetrics, sqlx::Error> {
    let config = CanaryConfig::default();

    tracing::info!(
        "Starting canary deployment: proposal={}, agent={}, {}% traffic for {}h",
        proposal_id,
        agent_id,
        config.percentage,
        config.duration_hours
    );

    // Record deployment start
    sqlx::query(
        r#"
        INSERT INTO skill_deployment_log (
            tenant_id, proposal_id, agent_id,
            status, deployment_percentage, phase_start_time,
            quality_score_baseline, latency_ms_baseline,
            phase_config, created_at, updated_at
        ) SELECT
            tenant_id, ?, ?, ?, ?, NOW(),
            0.0, 0,
            ?, NOW(), NOW()
        FROM skill_improvement_proposals
        WHERE id = ?
        LIMIT 1
        "#,
    )
    .bind(proposal_id)
    .bind(agent_id)
    .bind(DeploymentPhase::CanaryInProgress.to_string())
    .bind(config.percentage)
    .bind(governance_result.final_conditions.as_ref().map(|c| c.to_string()))
    .bind(proposal_id)
    .execute(pool)
    .await?;

    let metrics = DeploymentMetrics {
        proposal_id: proposal_id.to_string(),
        agent_id,
        current_phase: DeploymentPhase::CanaryInProgress,
        deployment_percentage: config.percentage,
        phase_start_time: Utc::now(),
        phase_duration_hours: config.duration_hours,
        quality_score_current: 0.0,
        quality_score_baseline: 0.0,
        quality_delta: 0.0,
        latency_ms_current: 0,
        latency_ms_baseline: 0,
        latency_delta_ms: 0,
        error_rate: 0.0,
        requests_processed: 0,
        is_healthy: true,
        rollback_triggered: false,
    };

    Ok(metrics)
}

/// Check canary health and decide next action
pub async fn evaluate_canary_health(
    pool: &MySqlPool,
    proposal_id: &str,
    agent_id: i64,
) -> Result<DeploymentMetrics, sqlx::Error> {
    let config = CanaryConfig::default();

    // Fetch current deployment record
    let deployment = sqlx::query!(
        r#"
        SELECT
            deployment_percentage,
            quality_score_baseline,
            latency_ms_baseline,
            phase_start_time,
            requests_processed
        FROM skill_deployment_log
        WHERE proposal_id = ? AND agent_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        "#,
        proposal_id,
        agent_id
    )
    .fetch_one(pool)
    .await?;

    let phase_duration = TimeDelta::hours(config.duration_hours as i64);
    let phase_elapsed = Utc::now() - deployment.phase_start_time;
    let phase_complete = phase_elapsed >= phase_duration;
    let requests_sufficient = deployment.requests_processed.unwrap_or(0) >= config.min_requests as i64;

    // Simulate quality/latency metrics (in production, aggregate from agent_feedback_logs)
    let current_quality = 0.88; // Placeholder
    let current_latency = 450; // Placeholder
    let quality_delta = current_quality - (deployment.quality_score_baseline.unwrap_or(0.8) as f32);
    let latency_delta = (current_latency - deployment.latency_ms_baseline.unwrap_or(400)) as i32;
    let error_rate = 0.01; // Placeholder

    let quality_ok = quality_delta >= config.quality_threshold;
    let latency_ok = latency_delta <= config.latency_threshold_ms;
    let error_rate_ok = error_rate <= config.error_rate_threshold;

    let is_healthy = quality_ok && latency_ok && error_rate_ok;
    let should_advance = (phase_complete || requests_sufficient) && is_healthy;

    let next_phase = if !is_healthy {
        DeploymentPhase::RolledBack
    } else if should_advance {
        DeploymentPhase::Staged25Percent
    } else {
        DeploymentPhase::CanaryInProgress
    };

    // Update deployment status
    sqlx::query(
        r#"
        UPDATE skill_deployment_log
        SET status = ?, deployment_percentage = ?,
            quality_score_current = ?,
            latency_ms_current = ?,
            error_rate = ?,
            is_healthy = ?,
            updated_at = NOW()
        WHERE proposal_id = ? AND agent_id = ?
        "#,
    )
    .bind(next_phase.to_string())
    .bind(match next_phase {
        DeploymentPhase::CanaryInProgress => 5,
        DeploymentPhase::Staged25Percent => 25,
        DeploymentPhase::Staged50Percent => 50,
        DeploymentPhase::FullDeployment => 100,
        DeploymentPhase::RolledBack => 0,
    })
    .bind(current_quality)
    .bind(current_latency)
    .bind(error_rate)
    .bind(is_healthy)
    .bind(proposal_id)
    .bind(agent_id)
    .execute(pool)
    .await?;

    tracing::info!(
        "Canary evaluation: proposal={}, quality_delta={:.3}, latency_delta={}ms, is_healthy={}, next_phase={}",
        proposal_id,
        quality_delta,
        latency_delta,
        is_healthy,
        next_phase
    );

    Ok(DeploymentMetrics {
        proposal_id: proposal_id.to_string(),
        agent_id,
        current_phase: next_phase,
        deployment_percentage: match next_phase {
            DeploymentPhase::CanaryInProgress => 5,
            DeploymentPhase::Staged25Percent => 25,
            DeploymentPhase::Staged50Percent => 50,
            DeploymentPhase::FullDeployment => 100,
            DeploymentPhase::RolledBack => 0,
        },
        phase_start_time: Utc::now(),
        phase_duration_hours: config.duration_hours,
        quality_score_current: current_quality,
        quality_score_baseline: deployment.quality_score_baseline.unwrap_or(0.8) as f32,
        quality_delta,
        latency_ms_current: current_latency,
        latency_ms_baseline: deployment.latency_ms_baseline.unwrap_or(400),
        latency_delta_ms: latency_delta,
        error_rate,
        requests_processed: deployment.requests_processed.unwrap_or(0),
        is_healthy,
        rollback_triggered: !is_healthy,
    })
}

/// Auto-rollback if metrics deteriorate
pub async fn check_and_execute_rollback(
    pool: &MySqlPool,
    proposal_id: &str,
    agent_id: i64,
) -> Result<bool, sqlx::Error> {
    let config = CanaryConfig::default();

    let deployment = sqlx::query!(
        r#"
        SELECT
            quality_score_current,
            quality_score_baseline,
            latency_ms_current,
            latency_ms_baseline,
            error_rate
        FROM skill_deployment_log
        WHERE proposal_id = ? AND agent_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        "#,
        proposal_id,
        agent_id
    )
    .fetch_one(pool)
    .await?;

    let current_quality = deployment.quality_score_current.unwrap_or(0.85) as f32;
    let baseline_quality = deployment.quality_score_baseline.unwrap_or(0.85) as f32;
    let quality_delta = current_quality - baseline_quality;

    let current_latency = deployment.latency_ms_current.unwrap_or(400);
    let baseline_latency = deployment.latency_ms_baseline.unwrap_or(400);
    let latency_delta = current_latency - baseline_latency;

    let error_rate = deployment.error_rate.unwrap_or(0.0) as f32;

    let should_rollback = quality_delta < config.quality_threshold
        || latency_delta > config.latency_threshold_ms
        || error_rate > config.error_rate_threshold;

    if should_rollback {
        tracing::warn!(
            "Auto-rollback triggered: proposal={}, quality_delta={:.3}, latency_delta={}ms, error_rate={:.2}%",
            proposal_id,
            quality_delta,
            latency_delta,
            error_rate * 100.0
        );

        // Record rollback
        sqlx::query(
            r#"
            UPDATE skill_deployment_log
            SET status = ?, is_healthy = 0, rollback_triggered = 1,
                rollback_reason = ?,
                updated_at = NOW()
            WHERE proposal_id = ? AND agent_id = ?
            "#,
        )
        .bind(DeploymentPhase::RolledBack.to_string())
        .bind(format!(
            "Auto-rollback: quality_delta={:.3}, latency_delta={}ms, error_rate={:.2}%",
            quality_delta, latency_delta, error_rate * 100.0
        ))
        .bind(proposal_id)
        .bind(agent_id)
        .execute(pool)
        .await?;

        // Mark proposal as requiring review
        sqlx::query(
            r#"
            UPDATE skill_improvement_proposals
            SET status = 'ROLLED_BACK'
            WHERE id = ?
            "#,
        )
        .bind(proposal_id)
        .execute(pool)
        .await?;
    }

    Ok(should_rollback)
}

/// Advance staged deployment (25% → 50% → 100%)
pub async fn advance_staged_deployment(
    pool: &MySqlPool,
    proposal_id: &str,
    agent_id: i64,
) -> Result<DeploymentPhase, sqlx::Error> {
    let current = sqlx::query!(
        r#"
        SELECT status FROM skill_deployment_log
        WHERE proposal_id = ? AND agent_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        "#,
        proposal_id,
        agent_id
    )
    .fetch_one(pool)
    .await?;

    let next_phase = match current.status.as_deref() {
        Some("CANARY_IN_PROGRESS") => DeploymentPhase::Staged25Percent,
        Some("STAGED_25_PERCENT") => DeploymentPhase::Staged50Percent,
        Some("STAGED_50_PERCENT") => DeploymentPhase::FullDeployment,
        _ => return Ok(DeploymentPhase::FullDeployment),
    };

    let next_percentage = match next_phase {
        DeploymentPhase::Staged25Percent => 25,
        DeploymentPhase::Staged50Percent => 50,
        DeploymentPhase::FullDeployment => 100,
        _ => 0,
    };

    sqlx::query(
        r#"
        UPDATE skill_deployment_log
        SET status = ?, deployment_percentage = ?,
            phase_start_time = NOW(), updated_at = NOW()
        WHERE proposal_id = ? AND agent_id = ?
        "#,
    )
    .bind(next_phase.to_string())
    .bind(next_percentage)
    .bind(proposal_id)
    .bind(agent_id)
    .execute(pool)
    .await?;

    tracing::info!(
        "Advanced deployment: proposal={}, phase={}, percentage={}%",
        proposal_id,
        next_phase,
        next_percentage
    );

    Ok(next_phase)
}

/// Get current deployment status
pub async fn get_deployment_status(
    pool: &MySqlPool,
    proposal_id: &str,
    agent_id: i64,
) -> Result<DeploymentMetrics, sqlx::Error> {
    let deployment = sqlx::query!(
        r#"
        SELECT
            deployment_percentage,
            status,
            phase_start_time,
            quality_score_current,
            quality_score_baseline,
            latency_ms_current,
            latency_ms_baseline,
            error_rate,
            requests_processed,
            is_healthy,
            rollback_triggered
        FROM skill_deployment_log
        WHERE proposal_id = ? AND agent_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        "#,
        proposal_id,
        agent_id
    )
    .fetch_one(pool)
    .await?;

    let current_phase = match deployment.status.as_deref() {
        Some("CANARY_IN_PROGRESS") => DeploymentPhase::CanaryInProgress,
        Some("STAGED_25_PERCENT") => DeploymentPhase::Staged25Percent,
        Some("STAGED_50_PERCENT") => DeploymentPhase::Staged50Percent,
        Some("FULL_DEPLOYMENT") => DeploymentPhase::FullDeployment,
        Some("ROLLED_BACK") => DeploymentPhase::RolledBack,
        _ => DeploymentPhase::CanaryInProgress,
    };

    Ok(DeploymentMetrics {
        proposal_id: proposal_id.to_string(),
        agent_id,
        current_phase,
        deployment_percentage: deployment.deployment_percentage.unwrap_or(0),
        phase_start_time: deployment.phase_start_time,
        phase_duration_hours: 2, // TODO: track per phase
        quality_score_current: deployment.quality_score_current.unwrap_or(0.0) as f32,
        quality_score_baseline: deployment.quality_score_baseline.unwrap_or(0.0) as f32,
        quality_delta: (deployment.quality_score_current.unwrap_or(0.0)
            - deployment.quality_score_baseline.unwrap_or(0.0)) as f32,
        latency_ms_current: deployment.latency_ms_current.unwrap_or(0),
        latency_ms_baseline: deployment.latency_ms_baseline.unwrap_or(0),
        latency_delta_ms: (deployment.latency_ms_current.unwrap_or(0)
            - deployment.latency_ms_baseline.unwrap_or(0)) as i32,
        error_rate: deployment.error_rate.unwrap_or(0.0) as f32,
        requests_processed: deployment.requests_processed.unwrap_or(0),
        is_healthy: deployment.is_healthy.unwrap_or(false),
        rollback_triggered: deployment.rollback_triggered.unwrap_or(false),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_canary_config_default() {
        let config = CanaryConfig::default();
        assert_eq!(config.percentage, 5);
        assert_eq!(config.duration_hours, 2);
        assert_eq!(config.min_requests, 50);
        assert_eq!(config.quality_threshold, -0.05);
    }

    #[test]
    fn test_deployment_phase_display() {
        assert_eq!(
            DeploymentPhase::CanaryInProgress.to_string(),
            "CANARY_IN_PROGRESS"
        );
        assert_eq!(
            DeploymentPhase::Staged25Percent.to_string(),
            "STAGED_25_PERCENT"
        );
        assert_eq!(DeploymentPhase::FullDeployment.to_string(), "FULL_DEPLOYMENT");
    }
}
