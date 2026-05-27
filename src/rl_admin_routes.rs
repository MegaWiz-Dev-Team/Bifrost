use axum::{
    extract::{State, Query},
    http::StatusCode,
    response::Json,
    Router,
    routing::get,
};
use serde::{Deserialize, Serialize};
use sqlx::MySqlPool;
use tracing::{info, error};

use bifrost::rl_orchestrator::{
    run_daily_rl_cycle,
    monitor_deployments,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TriggerQuery {
    pub tenant_id: String,
}

/// GET /api/v1/rl/trigger-daily-cycle?tenant_id=asgard_medical
pub async fn trigger_daily_cycle(
    State(pool): State<MySqlPool>,
    Query(params): Query<TriggerQuery>,
) -> (StatusCode, Json<serde_json::Value>) {
    let tenant_id = &params.tenant_id;
    info!("Manually triggering daily RL cycle: tenant={}", tenant_id);

    match run_daily_rl_cycle(&pool, tenant_id).await {
        Ok(_) => {
            info!("✓ Daily RL cycle completed: tenant={}", tenant_id);
            (
                StatusCode::OK,
                Json(serde_json::json!({
                    "status": "success",
                    "message": format!("RL cycle completed for {}", tenant_id),
                    "timestamp": chrono::Utc::now().to_rfc3339()
                })),
            )
        }
        Err(e) => {
            error!("✗ Daily RL cycle failed: tenant={}, error={:?}", tenant_id, e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "status": "error",
                    "message": format!("RL cycle failed: {:?}", e),
                    "timestamp": chrono::Utc::now().to_rfc3339()
                })),
            )
        }
    }
}

/// GET /api/v1/rl/check-deployments
pub async fn check_deployments(
    State(pool): State<MySqlPool>,
) -> (StatusCode, Json<serde_json::Value>) {
    info!("Checking active deployments");

    match monitor_deployments(&pool).await {
        Ok(_) => {
            info!("✓ Deployment monitoring check completed");
            (
                StatusCode::OK,
                Json(serde_json::json!({
                    "status": "success",
                    "message": "Deployment monitoring check completed",
                    "timestamp": chrono::Utc::now().to_rfc3339()
                })),
            )
        }
        Err(e) => {
            error!("✗ Deployment monitoring check failed: {:?}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "status": "error",
                    "message": format!("Deployment check failed: {:?}", e),
                    "timestamp": chrono::Utc::now().to_rfc3339()
                })),
            )
        }
    }
}

/// GET /api/v1/rl/agent-status?tenant_id=asgard_medical
pub async fn get_agent_rl_status(
    State(pool): State<MySqlPool>,
    Query(params): Query<TriggerQuery>,
) -> (StatusCode, Json<serde_json::Value>) {
    let tenant_id = &params.tenant_id;

    let status = match sqlx::query!(
        r#"
        SELECT
            ac.id,
            ac.name,
            CAST(COALESCE(arm.avg_quality_score, 0.0) AS DOUBLE) as avg_quality_score,
            CAST(COALESCE(arm.conversation_count, 0) AS INT) as conversation_count,
            arm.lowest_quality_domain,
            CAST(COALESCE(arm.lowest_quality_score, 0.0) AS DOUBLE) as lowest_quality_score,
            CAST(COALESCE(arm.improvement_opportunity_score, 0.0) AS DOUBLE) as improvement_opportunity_score,
            arm.metric_date
        FROM agent_configs ac
        LEFT JOIN agent_rl_daily_metrics arm ON ac.id = arm.agent_id
            AND arm.tenant_id = ac.tenant_id
        WHERE ac.tenant_id = ? AND ac.is_published = 1
        ORDER BY ac.id
        "#,
        tenant_id
    )
    .fetch_all(&pool)
    .await
    {
        Ok(rows) => {
            let agents_json: Vec<serde_json::Value> = rows
                .iter()
                .map(|row| {
                    serde_json::json!({
                        "id": row.id,
                        "name": &row.name,
                        "avg_quality": row.avg_quality_score,
                        "conversations": row.conversation_count,
                        "weak_domain": &row.lowest_quality_domain,
                        "weak_score": row.lowest_quality_score,
                        "opportunity_score": row.improvement_opportunity_score,
                        "last_updated": &row.metric_date
                    })
                })
                .collect();

            (
                StatusCode::OK,
                Json(serde_json::json!({
                    "tenant_id": tenant_id,
                    "agents": agents_json,
                    "timestamp": chrono::Utc::now().to_rfc3339()
                })),
            )
        }
        Err(e) => {
            error!("Failed to fetch agent status: {:?}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "status": "error",
                    "message": format!("Query failed: {:?}", e),
                    "timestamp": chrono::Utc::now().to_rfc3339()
                })),
            )
        }
    };

    status
}

pub fn build_rl_admin_router(pool: MySqlPool) -> Router {
    Router::new()
        .route("/rl/trigger-daily-cycle", get(trigger_daily_cycle))
        .route("/rl/check-deployments", get(check_deployments))
        .route("/rl/agent-status", get(get_agent_rl_status))
        .with_state(pool)
}
