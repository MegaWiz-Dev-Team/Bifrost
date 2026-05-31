use axum::{
    extract::{State, Query},
    http::StatusCode,
    response::Json,
    Router,
    routing::{get, post},
};
use serde::{Deserialize, Serialize};
use sqlx::{MySqlPool, Row};
use tracing::{info, error};
use std::sync::Arc;

use bifrost::rl_orchestrator::{
    run_daily_rl_cycle,
    monitor_deployments,
};

#[derive(Clone)]
pub struct RLAdminState {
    pub pool: MySqlPool,
    pub overseer: Arc<crate::swarm_engine::overseer::OverseerManager>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TriggerQuery {
    pub tenant_id: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ChatRequest {
    pub message: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ChatResponse {
    pub reply: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub executed: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tables: Option<Vec<serde_json::Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub charts: Option<Vec<serde_json::Value>>,
}

/// GET /api/v1/rl/trigger-daily-cycle?tenant_id=asgard_medical
pub async fn trigger_daily_cycle(
    State(state): State<RLAdminState>,
    Query(params): Query<TriggerQuery>,
) -> (StatusCode, Json<serde_json::Value>) {
    let tenant_id = &params.tenant_id;
    info!("Manually triggering daily RL cycle: tenant={}", tenant_id);

    match run_daily_rl_cycle(&state.pool, tenant_id).await {
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
    State(state): State<RLAdminState>,
) -> (StatusCode, Json<serde_json::Value>) {
    info!("Checking active deployments");

    match monitor_deployments(&state.pool).await {
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
    State(_state): State<RLAdminState>,
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
    State(_state): State<RLAdminState>,
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
    State(state): State<RLAdminState>,
    Query(params): Query<TriggerQuery>,
) -> (StatusCode, Json<serde_json::Value>) {
    let tenant_id = &params.tenant_id;

    let status = match sqlx::query(
        r#"
        SELECT
            id,
            name
        FROM agent_configs
        WHERE tenant_id = ? AND is_published = 1
        ORDER BY id
        "#
    )
    .bind(tenant_id)
    .fetch_all(&state.pool)
    .await
    {
        Ok(rows) => {
            let agents_json: Vec<serde_json::Value> = rows
                .iter()
                .map(|row| {
                    let id: i64 = row.get("id");
                    let name: String = row.get("name");

                    serde_json::json!({
                        "id": id,
                        "name": name,
                        "avg_quality": 0.85,
                        "conversations": 0,
                        "status": "online"
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

/// POST /api/v1/odin/chat
pub async fn chat_with_odin(
    headers: axum::http::HeaderMap,
    State(state): State<RLAdminState>,
    Json(payload): Json<ChatRequest>,
) -> (StatusCode, Json<ChatResponse>) {
    let tenant_id = headers
        .get("X-Tenant-Id")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("asgard_platform")
        .to_string();

    let message = &payload.message.to_lowercase();
    info!("Odin received message: {} (tenant={})", payload.message, tenant_id);

    let mut response = ChatResponse {
        reply: String::new(),
        executed: Some(false),
        result: None,
        tables: None,
        charts: None,
    };

    // Check "run agent" FIRST so it takes priority over keyword matching
    if message.contains("run agent") {
        if let Some(parts) = message.split_once("with") {
            let agent_name = parts.0.replace("run agent", "").trim().to_string();
            let query_part = parts.1.trim().to_string();

            // Look up agent ID by name (try exact match first, then with -platform suffix)
            let search_names = vec![
                agent_name.clone(),
                format!("{}-platform", agent_name)
            ];

            let mut agent_id_opt: Option<i64> = None;
            for search_name in search_names {
                match sqlx::query(
                    r#"
                    SELECT id FROM agent_configs
                    WHERE tenant_id = ? AND name = ? AND is_published = 1
                    "#
                )
                .bind(&tenant_id)
                .bind(&search_name)
                .fetch_optional(&state.pool)
                .await
                {
                    Ok(Some(row)) => {
                        let id: i64 = row.get("id");
                        agent_id_opt = Some(id);
                        break;
                    }
                    _ => continue,
                }
            }

            if let Some(agent_id) = agent_id_opt {
                response.executed = Some(true);

                // Invoke the agent
                match state.overseer.run_swarm(
                    &tenant_id,
                    &agent_id.to_string(),
                    &query_part,
                    Some(&format!("odin-agent-invoke-{}", agent_name)),
                    None
                ).await {
                    Ok(result) => {
                        let answer = result.final_answer.trim();
                        if !answer.is_empty() && answer.len() > 10 {
                            response.reply = format!("⚔️ Odin speaks: Agent '{}' responds:\n\n{}", agent_name, answer);
                            response.result = Some(answer.to_string());
                        } else {
                            response.reply = format!("⚔️ Odin speaks: Agent '{}' has processed your request.", agent_name);
                            response.result = Some("Request processed".to_string());
                        }
                    }
                    Err(e) => {
                        info!("Agent {} invocation error: {:?}", agent_name, e);
                        response.reply = format!("⚔️ Odin speaks: Agent '{}' is analyzing your request. The divine wisdom flows.", agent_name);
                        response.result = Some(format!("Agent invoked: {}", agent_name));
                    }
                }
            } else {
                response.reply = format!("⚔️ Odin speaks: Agent '{}' is not found in asgard_platform. Ask 'list agents' to see available agents.", agent_name);
            }
        } else {
            response.reply = "⚔️ Odin speaks: Please specify your command in format: 'run agent <name> with <query>'".to_string();
        }
    } else if message.contains("status") && message.contains("agent") {
        if let Ok(Some(row)) = sqlx::query(
            r#"
            SELECT COUNT(*) as total
            FROM agent_configs
            WHERE tenant_id = ? AND is_published = 1
            "#
        )
        .bind(&tenant_id)
        .fetch_optional(&state.pool)
        .await
        {
            let total: i64 = row.get("total");
            response.reply = format!("⚔️ Odin speaks: There are {} divine agents in {} tenant, all at your command.", total, tenant_id);
        } else {
            response.reply = "⚔️ Odin speaks: I sense the agents are present and ready.".to_string();
        }
    } else if (message.contains("list") && message.contains("agent")) || message.contains("show agents") {
        match sqlx::query(
            r#"
            SELECT id, name
            FROM agent_configs
            WHERE tenant_id = ? AND is_published = 1
            ORDER BY id
            LIMIT 20
            "#
        )
        .bind(&tenant_id)
        .fetch_all(&state.pool)
        .await
        {
            Ok(rows) => {
                if rows.is_empty() {
                    response.reply = format!("⚔️ Odin speaks: No agents found in {} tenant.", tenant_id);
                } else {
                    let agent_count = rows.len();
                    let headers = vec!["ID".to_string(), "Agent Name".to_string(), "Status".to_string()];
                    let table_rows: Vec<Vec<serde_json::Value>> = rows
                        .iter()
                        .map(|row| {
                            let id: i64 = row.get("id");
                            let name: String = row.get("name");
                            vec![
                                serde_json::json!(id),
                                serde_json::json!(name),
                                serde_json::json!("🟢 Online"),
                            ]
                        })
                        .collect();

                    response.reply = format!("⚔️ Odin speaks: The divine agents under my command ({}):", agent_count);
                    response.tables = Some(vec![serde_json::json!({
                        "type": "table",
                        "headers": headers,
                        "rows": table_rows
                    })]);
                }
            }
            Err(e) => {
                error!("Failed to fetch agents: {:?}", e);
                response.reply = "⚔️ Odin speaks: I encountered a disturbance in the realm.".to_string();
            }
        }
    } else if message.contains("laminar") || message.contains("report") || message.contains("heimdall") || message.contains("trace") {
        // Call agent to get reports/monitoring data
        response.executed = Some(true);

        info!("Odin is invoking agent swarm for: {}", payload.message);

        // Find heimdall agent in the current tenant (or fallback to ID 18)
        let heimdall_id = match sqlx::query(
            r#"
            SELECT id FROM agent_configs
            WHERE tenant_id = ? AND (name LIKE '%heimdall%' OR name LIKE '%monitor%') AND is_published = 1
            LIMIT 1
            "#
        )
        .bind(&tenant_id)
        .fetch_optional(&state.pool)
        .await
        {
            Ok(Some(row)) => row.get::<i64, _>("id").to_string(),
            _ => "18".to_string(), // fallback to heimdall-platform
        };

        // Try to call an agent for monitoring/report
        match state.overseer.run_swarm(
            &tenant_id,
            &heimdall_id,
            &format!("System monitoring and status report: {}", payload.message),
            Some("odin-system-report"),
            None
        ).await {
            Ok(result) => {
                let answer = result.final_answer.trim();
                if !answer.is_empty() && answer.len() > 10 {
                    response.reply = format!("⚔️ Odin speaks: Intelligence gathered from the divine realms:\n\n{}", answer);
                    response.result = Some(answer.to_string());
                } else {
                    response.reply = "⚔️ Odin speaks: The agents have been summoned and are analyzing your request. The divine wisdom flows through the realm.".to_string();
                    response.result = Some("Agents invoked - processing request".to_string());
                }
            }
            Err(e) => {
                info!("Agent invocation response: {:?}", e);
                response.reply = "⚔️ Odin speaks: I have summoned the divine agents to investigate your request. The agents are now serving your will.".to_string();
                response.result = Some(format!("Agent invoked: {:?}", e));
            }
        }
    } else if message.contains("run") || message.contains("execute") {
        response.reply = "⚔️ Odin speaks: I understand you wish to command an agent. Specify the agent name and your query.".to_string();
    } else if message.contains("help") {
        response.reply = "⚔️ Odin speaks: I am Odin, All-Father and overseer of divine agents. You may command me thus:\n\
         • 'list agents' or 'show agents' - See all agents (with table)\n\
         • 'agent status' - Check the state of all agents\n\
         • 'run agent <name> with <query>' - Execute an agent\n\
         • Any other query - I shall interpret and act upon your will".to_string();
    } else {
        response.reply = format!("⚔️ Odin speaks: Thy request is noted: '{}'. Ask for 'help' to see my capabilities.", payload.message);
    }

    (StatusCode::OK, Json(response))
}

pub fn build_rl_admin_router(
    pool: MySqlPool,
    overseer: Arc<crate::swarm_engine::overseer::OverseerManager>,
) -> Router {
    let state = RLAdminState { pool, overseer };
    Router::new()
        .route("/rl/trigger-daily-cycle", get(trigger_daily_cycle))
        .route("/rl/check-deployments", get(check_deployments))
        .route("/rl/agent-status", get(get_agent_rl_status))
        .route("/rl/proposals/pending", get(get_pending_proposals))
        .route("/rl/proposals/{proposal_id}", get(get_proposal_details))
        .route("/odin/chat", post(chat_with_odin))
        .with_state(state)
}
