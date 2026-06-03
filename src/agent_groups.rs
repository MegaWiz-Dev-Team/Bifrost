//! `/v1/agent-groups*` handlers: list agent groups for the calling tenant.
//!
//! Agent groups provide hierarchical organization of agents by category
//! (boundary, specialty, router, test, etc). Each tenant can customize
//! their group structure.

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::get,
    Extension, Json, Router,
};
use serde_json::{json, Value};
use sqlx::{FromRow, MySqlPool};
use tower_governor::{
    governor::GovernorConfigBuilder, key_extractor::SmartIpKeyExtractor, GovernorLayer,
};

use crate::middleware::{self, AuthState, TenantContext};

// ─────────────────────────── List row ────────────────────────────────────

#[derive(Debug, FromRow)]
struct AgentGroupRow {
    id: i64,
    name: String,
    display_name: Option<String>,
    description: Option<String>,
    sort_order: i32,
    icon_emoji: Option<String>,
    color_hex: Option<String>,
    is_active: i8,
    agent_count: Option<i64>,
}

impl AgentGroupRow {
    fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "sort_order": self.sort_order,
            "icon_emoji": self.icon_emoji,
            "color_hex": self.color_hex,
            "is_active": self.is_active == 1,
            "agent_count": self.agent_count.unwrap_or(0),
        })
    }
}

// ─────────────────────────── Router ──────────────────────────────────────

/// Build the `/v1/agent-groups*` sub-router with JWT auth + rate limiting applied.
pub fn build_router(pool: MySqlPool, auth_state: AuthState, governor_burst: u32) -> Router {
    let governor_conf = std::sync::Arc::new(
        GovernorConfigBuilder::default()
            .per_second(1)
            .burst_size(governor_burst.max(1))
            .key_extractor(SmartIpKeyExtractor)
            .finish()
            .expect("governor config"),
    );

    Router::new()
        .route("/v1/agent-groups", get(list_agent_groups))
        .route_layer(axum::middleware::from_fn_with_state(
            auth_state,
            middleware::require_tenant,
        ))
        .layer(GovernorLayer::new(governor_conf))
        .with_state(pool)
}

// ─────────────────────────── Handlers ────────────────────────────────────

/// `GET /v1/agent-groups` — list agent groups for the calling tenant.
pub async fn list_agent_groups(
    Extension(ctx): Extension<TenantContext>,
    State(pool): State<MySqlPool>,
) -> impl IntoResponse {
    let rows: Result<Vec<AgentGroupRow>, _> = sqlx::query_as(LIST_SQL)
        .bind(&ctx.tenant_id)
        .fetch_all(&pool)
        .await;

    match rows {
        Ok(rows) => {
            let groups: Vec<Value> = rows.iter().map(AgentGroupRow::to_json).collect();
            (
                StatusCode::OK,
                Json(json!({
                    "tenant_id": ctx.tenant_id,
                    "groups": groups,
                })),
            )
                .into_response()
        }
        Err(e) => {
            tracing::error!(error = %e, "list_agent_groups: db error");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": "internal_error"})),
            )
                .into_response()
        }
    }
}

// ─────────────────────────── SQL ─────────────────────────────────────────

const LIST_SQL: &str = "SELECT \
    ag.id, ag.name, ag.display_name, ag.description, ag.sort_order, \
    ag.icon_emoji, ag.color_hex, ag.is_active, \
    COUNT(ac.id) as agent_count \
    FROM agent_groups ag \
    LEFT JOIN agent_configs ac ON ag.id = ac.agent_group_id AND ag.tenant_id = ac.tenant_id \
    WHERE ag.tenant_id = ? AND ag.is_active = 1 \
    GROUP BY ag.id \
    ORDER BY ag.sort_order, ag.name";
