use axum::{
    extract::{State, Query},
    http::StatusCode,
    response::Json,
    Router,
    routing::get,
};
use serde::{Deserialize, Serialize};
use sqlx::{MySqlPool, Row};
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

/// GET /api/v1/rl/proposals/pending?status=pending
pub async fn get_pending_proposals(
    State(_pool): State<MySqlPool>,
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> (StatusCode, Json<serde_json::Value>) {
    let status = params.get("status").map(|s| s.as_str()).unwrap_or("pending");
    info!("Fetching proposals with status: {}", status);

    // Mock response - proposals table not yet implemented
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "status": "success",
            "proposals": [],
            "total_count": 0,
            "message": "No proposals yet - RL cycle hasn't run",
            "timestamp": chrono::Utc::now().to_rfc3339()
        })),
    )
}

/// GET /api/v1/rl/proposals/{proposal_id}
pub async fn get_proposal_details(
    State(_pool): State<MySqlPool>,
) -> (StatusCode, Json<serde_json::Value>) {
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "status": "success",
            "proposal": null,
            "message": "Proposal details not yet implemented",
            "timestamp": chrono::Utc::now().to_rfc3339()
        })),
    )
}

/// GET /api/v1/rl/agent-status?tenant_id=asgard_medical
pub async fn get_agent_rl_status(
    State(pool): State<MySqlPool>,
    Query(params): Query<TriggerQuery>,
) -> (StatusCode, Json<serde_json::Value>) {
    let tenant_id = &params.tenant_id;

    let status = match sqlx::query(
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
        "#
    )
    .bind(tenant_id)
    .fetch_all(&pool)
    .await
    {
        Ok(rows) => {
            let agents_json: Vec<serde_json::Value> = rows
                .iter()
                .map(|row| {
                    let id: i64 = row.get("id");
                    let name: String = row.get("name");
                    let avg_quality: f64 = row.get("avg_quality_score");
                    let conversation_count: i64 = row.get("conversation_count");
                    let weak_domain: Option<String> = row.get("lowest_quality_domain");
                    let weak_score: f64 = row.get("lowest_quality_score");
                    let opportunity_score: f64 = row.get("improvement_opportunity_score");
                    let metric_date: Option<String> = row.get("metric_date");

                    serde_json::json!({
                        "id": id,
                        "name": name,
                        "avg_quality": avg_quality,
                        "conversations": conversation_count,
                        "weak_domain": weak_domain,
                        "weak_score": weak_score,
                        "opportunity_score": opportunity_score,
                        "last_updated": metric_date
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
        .route("/rl/proposals/pending", get(get_pending_proposals))
        .route("/rl/proposals/{proposal_id}", get(get_proposal_details))
        .with_state(pool)
}
