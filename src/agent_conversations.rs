//! Agent-to-Agent (A2A) conversation tracking and visualization API.
//!
//! Provides endpoints for:
//! - `/v1/agents/{agent_id}/dispatch-log` — Historical dispatch calls
//! - `/v1/tenants/{tenant_id}/swarm-topology` — Active agent topology
//! - `/v1/tenants/{tenant_id}/agents` — List agents with status
//! - WS `/v1/agents/{agent_id}/dispatch-stream` — Real-time dispatch events

use axum::{
    extract::{Path, Query, State, ws::{WebSocket, WebSocketUpgrade}},
    http::StatusCode,
    response::IntoResponse,
    Extension, Json, Router,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::MySqlPool;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::middleware::{AuthState, TenantContext};

// ─────────────────────────── Data Models ──────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DispatchLogEntry {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub session_id: String,
    pub source_agent_id: i64,
    pub source_agent_name: String,
    pub target_agent_id: i64,
    pub target_agent_name: String,
    pub dispatch_message: String,
    pub response_message: Option<String>,
    pub latency_ms: i32,
    pub status: String, // 'success', 'error', 'timeout'
    pub error_message: Option<String>,
    pub confidence_score: Option<f32>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AgentNode {
    pub id: i64,
    pub name: String,
    pub display_name: String,
    pub status: String, // 'active', 'idle', 'error'
    pub model_id: String,
    pub latency_ms: i32,
    pub tier: i32, // 1=orchestrator (Odin), 2=advisor (Frigg), 3+=specialists
    pub is_online: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SwarmEdge {
    pub source: i64,
    pub target: i64,
    pub latency_ms: i32,
    pub dispatch_count: i32,
    pub success_rate: f32,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SwarmTopology {
    pub nodes: Vec<AgentNode>,
    pub edges: Vec<SwarmEdge>,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DispatchStreamMessage {
    pub message_type: String, // 'dispatch_start', 'dispatch_response', 'dispatch_error'
    pub timestamp: DateTime<Utc>,
    pub session_id: String,
    pub source_agent: AgentNode,
    pub target_agent: AgentNode,
    pub content: serde_json::Value,
    pub latency_ms: Option<i32>,
}

// ─────────────────────────── Query Models ──────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct DispatchLogQuery {
    #[serde(default)]
    pub from: Option<String>, // ISO 8601 timestamp
    #[serde(default)]
    pub to: Option<String>,
    #[serde(default)]
    pub limit: Option<i32>,
    #[serde(default)]
    pub offset: Option<i32>,
    #[serde(default)]
    pub source_agent_id: Option<i64>,
    #[serde(default)]
    pub target_agent_id: Option<i64>,
    #[serde(default)]
    pub status: Option<String>, // 'success', 'error', etc.
}

// ─────────────────────────── Handlers ──────────────────────────────────────

/// GET /v1/agents/{agent_id}/dispatch-log
/// Get conversation history for an agent (what it dispatched and received)
pub async fn get_dispatch_log(
    Path(agent_id): Path<i64>,
    Query(query): Query<DispatchLogQuery>,
    State(pool): State<sqlx::MySqlPool>,
    Extension(ctx): Extension<TenantContext>,
) -> impl IntoResponse {
    let limit = query.limit.unwrap_or(50).min(500);
    let offset = query.offset.unwrap_or(0);

    // TODO: Query from agent_dispatch_logs table (created in Phase 3)
    // For now, return mock data
    let entries = vec![
        DispatchLogEntry {
            id: Uuid::new_v4().to_string(),
            timestamp: Utc::now(),
            session_id: "session-123".to_string(),
            source_agent_id: 22,
            source_agent_name: "odin-platform".to_string(),
            target_agent_id: 27,
            target_agent_name: "frigg-platform".to_string(),
            dispatch_message: "What are the SRE best practices for this architecture?".to_string(),
            response_message: Some("Based on Google SRE book principles...".to_string()),
            latency_ms: 2500,
            status: "success".to_string(),
            error_message: None,
            confidence_score: Some(0.95),
        },
    ];

    (StatusCode::OK, Json(serde_json::json!({
        "data": entries,
        "limit": limit,
        "offset": offset,
        "total": entries.len(),
    }))).into_response()
}

/// GET /v1/tenants/{tenant_id}/agents
/// List all agents in a tenant with status and latency
pub async fn list_tenant_agents(
    Path(tenant_id): Path<String>,
    State(pool): State<sqlx::MySqlPool>,
    Extension(ctx): Extension<TenantContext>,
) -> impl IntoResponse {
    // TODO: Query from agent_configs + get live status from overseer
    let agents = vec![
        AgentNode {
            id: 22,
            name: "odin-platform".to_string(),
            display_name: "Odin — Master Orchestrator".to_string(),
            status: "active".to_string(),
            model_id: "gemini-3.5-flash".to_string(),
            latency_ms: 300,
            tier: 1,
            is_online: true,
        },
        AgentNode {
            id: 27,
            name: "frigg-platform".to_string(),
            display_name: "Frigg — Advisor".to_string(),
            status: "active".to_string(),
            model_id: "gemini-3.1-pro-preview".to_string(),
            latency_ms: 2500,
            tier: 2,
            is_online: true,
        },
    ];

    (StatusCode::OK, Json(serde_json::json!({
        "agents": agents,
        "timestamp": Utc::now(),
    }))).into_response()
}

/// GET /v1/tenants/{tenant_id}/swarm-topology
/// Get network topology (nodes + edges) for visualization
pub async fn get_swarm_topology(
    Path(tenant_id): Path<String>,
    State(pool): State<sqlx::MySqlPool>,
    Extension(ctx): Extension<TenantContext>,
) -> impl IntoResponse {
    let topology = SwarmTopology {
        nodes: vec![
            AgentNode {
                id: 22,
                name: "odin".to_string(),
                display_name: "Odin".to_string(),
                status: "active".to_string(),
                model_id: "gemini-3.5-flash".to_string(),
                latency_ms: 300,
                tier: 1,
                is_online: true,
            },
            AgentNode {
                id: 27,
                name: "frigg".to_string(),
                display_name: "Frigg".to_string(),
                status: "active".to_string(),
                model_id: "gemini-3.1-pro-preview".to_string(),
                latency_ms: 2500,
                tier: 2,
                is_online: true,
            },
        ],
        edges: vec![
            SwarmEdge {
                source: 22,
                target: 27,
                latency_ms: 2500,
                dispatch_count: 45,
                success_rate: 0.98,
            },
        ],
        timestamp: Utc::now(),
    };

    (StatusCode::OK, Json(topology)).into_response()
}

/// WS /v1/agents/{agent_id}/dispatch-stream
/// WebSocket for real-time dispatch event streaming
pub async fn dispatch_stream_handler(
    Path(agent_id): Path<i64>,
    ws: WebSocketUpgrade,
    State(pool): State<sqlx::MySqlPool>,
    Extension(ctx): Extension<TenantContext>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_dispatch_stream(socket, agent_id, ctx))
}

async fn handle_dispatch_stream(
    mut socket: WebSocket,
    agent_id: i64,
    ctx: TenantContext,
) {
    // TODO: Implement real-time stream from Bifrost memory/event bus
    tracing::info!("WebSocket connected for agent {}, tenant {}", agent_id, ctx.tenant_id);

    // For now, send a test message then close
    let test_msg = DispatchStreamMessage {
        message_type: "dispatch_start".to_string(),
        timestamp: Utc::now(),
        session_id: Uuid::new_v4().to_string(),
        source_agent: AgentNode {
            id: 22,
            name: "odin".to_string(),
            display_name: "Odin".to_string(),
            status: "active".to_string(),
            model_id: "gemini-3.5-flash".to_string(),
            latency_ms: 300,
            tier: 1,
            is_online: true,
        },
        target_agent: AgentNode {
            id: 27,
            name: "frigg".to_string(),
            display_name: "Frigg".to_string(),
            status: "active".to_string(),
            model_id: "gemini-3.1-pro-preview".to_string(),
            latency_ms: 2500,
            tier: 2,
            is_online: true,
        },
        content: serde_json::json!({
            "message": "Analyzing system reliability..."
        }),
        latency_ms: None,
    };

    if let Ok(msg_json) = serde_json::to_string(&test_msg) {
        let _ = socket.send(axum::extract::ws::Message::Text(msg_json)).await;
    }

    tracing::info!("WebSocket closed for agent {}", agent_id);
}

// ─────────────────────────── Router Builder ──────────────────────────────

pub fn build_router(pool: MySqlPool, auth_state: AuthState) -> Router {
    Router::new()
        .route(
            "/v1/agents/:agent_id/dispatch-log",
            axum::routing::get(get_dispatch_log),
        )
        .route(
            "/v1/tenants/:tenant_id/agents",
            axum::routing::get(list_tenant_agents),
        )
        .route(
            "/v1/tenants/:tenant_id/swarm-topology",
            axum::routing::get(get_swarm_topology),
        )
        .route(
            "/v1/agents/:agent_id/dispatch-stream",
            axum::routing::get(dispatch_stream_handler),
        )
        .with_state(pool)
}
