//! `/v1/agents*` handlers: list + detail.
//!
//! Both handlers consume a [`TenantContext`] request extension set by the
//! auth middleware in [`crate::middleware`] — they do **not** read
//! `X-Tenant-Id` directly. That keeps the auth decision in one place.
//!
//! Column allow-list (see `docs/design/agent_list_implementation_plan.md`):
//! - List: metadata + capabilities, never persona IP or secrets.
//! - Detail: list shape + `system_prompt`, `personality_traits`, `greeting`,
//!   whitelisted `rag_params`, `created_at`, `updated_at`.
//! - Never returned anywhere: `api_key`, `template_id`, and any future
//!   column that is not explicitly added to the SELECT.

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    routing::get,
    Extension, Json, Router,
};
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use sqlx::{FromRow, MySqlPool};
use std::collections::HashMap;
use tower_governor::{
    governor::GovernorConfigBuilder, key_extractor::SmartIpKeyExtractor, GovernorLayer,
};

use crate::middleware::{self, AuthPath, AuthState, TenantContext};

// ─────────────────────────── List row ────────────────────────────────────

#[derive(Debug, FromRow)]
struct AgentListRow {
    id: i64,
    name: String,
    display_name: Option<String>,
    description: Option<String>,
    avatar_url: Option<String>,
    is_published: i8,
    model_id: String,
    provider: String,
    #[sqlx(rename = "temperature")]
    temperature: Option<f64>,
    max_tokens: Option<i32>,
    top_k: Option<i32>,
    use_rag: Option<i8>,
    use_knowledge_graph: Option<i8>,
    use_pageindex: Option<i8>,
    tools: Option<Value>,
    mcp_servers: Option<Value>,
}

impl AgentListRow {
    fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "avatar_url": self.avatar_url,
            "is_published": self.is_published == 1,
            // Legacy top-level field for one release window. New consumers
            // should read from `capabilities`.
            "model_id": self.model_id,
            "capabilities": capabilities_json(
                &self.model_id,
                &self.provider,
                self.temperature,
                self.max_tokens,
                self.top_k,
                self.use_rag,
                self.use_knowledge_graph,
                self.use_pageindex,
                self.tools.as_ref(),
                self.mcp_servers.as_ref(),
            ),
        })
    }
}

// ─────────────────────────── Detail row ──────────────────────────────────

#[derive(Debug, FromRow)]
struct AgentDetailRow {
    id: i64,
    name: String,
    display_name: Option<String>,
    description: Option<String>,
    avatar_url: Option<String>,
    greeting: Option<String>,
    is_published: i8,
    model_id: String,
    provider: String,
    #[sqlx(rename = "temperature")]
    temperature: Option<f64>,
    max_tokens: Option<i32>,
    top_k: Option<i32>,
    use_rag: Option<i8>,
    use_knowledge_graph: Option<i8>,
    use_pageindex: Option<i8>,
    tools: Option<Value>,
    mcp_servers: Option<Value>,
    personality_traits: Option<Value>,
    rag_params: Option<Value>,
    system_prompt: String,
    created_at: Option<DateTime<Utc>>,
    updated_at: Option<DateTime<Utc>>,
}

impl AgentDetailRow {
    fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "avatar_url": self.avatar_url,
            "greeting": self.greeting,
            "is_published": self.is_published == 1,
            "model_id": self.model_id,
            "system_prompt": self.system_prompt,
            "personality_traits": json_array_or_empty(self.personality_traits.as_ref()),
            "created_at": self.created_at.map(|d| d.to_rfc3339()),
            "updated_at": self.updated_at.map(|d| d.to_rfc3339()),
            "capabilities": capabilities_json(
                &self.model_id,
                &self.provider,
                self.temperature,
                self.max_tokens,
                self.top_k,
                self.use_rag,
                self.use_knowledge_graph,
                self.use_pageindex,
                self.tools.as_ref(),
                self.mcp_servers.as_ref(),
            ),
            "rag_params": rag_params_whitelist(self.rag_params.as_ref()),
        })
    }
}

// ─────────────────────────── Helpers ─────────────────────────────────────

#[allow(clippy::too_many_arguments)]
fn capabilities_json(
    model_id: &str,
    provider: &str,
    temperature: Option<f64>,
    max_tokens: Option<i32>,
    top_k: Option<i32>,
    use_rag: Option<i8>,
    use_knowledge_graph: Option<i8>,
    use_pageindex: Option<i8>,
    tools: Option<&Value>,
    mcp_servers: Option<&Value>,
) -> Value {
    json!({
        "model_id": model_id,
        "provider": provider,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_k": top_k,
        "use_rag": use_rag.map(|v| v == 1).unwrap_or(false),
        "use_knowledge_graph": use_knowledge_graph.map(|v| v == 1).unwrap_or(false),
        "use_pageindex": use_pageindex.map(|v| v == 1).unwrap_or(false),
        "tools": json_array_or_empty(tools),
        "mcp_servers": json_array_or_empty(mcp_servers),
    })
}

/// Coerce nullable JSON array column into `[]` when null/non-array. Protects
/// callers from `null` and prevents 500s on malformed DB rows.
fn json_array_or_empty(v: Option<&Value>) -> Value {
    match v {
        Some(val) if val.is_array() => val.clone(),
        _ => Value::Array(vec![]),
    }
}

/// `rag_params` is a free-form JSON column. Project only the three keys the
/// engine actually consumes (`limit`, `alpha`, `output_format`). Any other
/// key — including future operator-stashed secrets — is dropped before
/// leaving Bifrost.
fn rag_params_whitelist(v: Option<&Value>) -> Value {
    const ALLOWED: &[&str] = &["limit", "alpha", "output_format"];
    let Some(obj) = v.and_then(|v| v.as_object()) else {
        return Value::Null;
    };
    let mut out = serde_json::Map::new();
    for key in ALLOWED {
        if let Some(val) = obj.get(*key) {
            out.insert((*key).to_string(), val.clone());
        }
    }
    if out.is_empty() {
        Value::Null
    } else {
        Value::Object(out)
    }
}

// ─────────────────────────── Router ──────────────────────────────────────

/// Build the `/v1/agents*` sub-router with JWT auth + rate limiting applied.
/// Used by both `main` and integration tests so the test surface matches prod.
///
/// `governor_burst` lets tests dial the limit down (or up) — production calls
/// it with 60.
pub fn build_router(pool: MySqlPool, auth_state: AuthState, governor_burst: u32) -> Router {
    // SmartIp falls back through X-Forwarded-For → X-Real-IP → Forwarded →
    // peer IP. K8s ingress sets X-Forwarded-For so this works in prod; tests
    // set it explicitly to drive deterministic per-IP buckets.
    let governor_conf = std::sync::Arc::new(
        GovernorConfigBuilder::default()
            .per_second(1)
            .burst_size(governor_burst.max(1))
            .key_extractor(SmartIpKeyExtractor)
            .finish()
            .expect("governor config"),
    );

    Router::new()
        .route("/v1/agents", get(list_agents))
        .route("/v1/agents/{agent_id_or_name}", get(get_agent))
        .route_layer(axum::middleware::from_fn_with_state(
            auth_state,
            middleware::require_tenant,
        ))
        .layer(GovernorLayer::new(governor_conf))
        .with_state(pool)
}

// ─────────────────────────── Handlers ────────────────────────────────────

/// `GET /v1/agents` — list agents for the calling tenant.
pub async fn list_agents(
    Extension(ctx): Extension<TenantContext>,
    State(pool): State<MySqlPool>,
    Query(q): Query<HashMap<String, String>>,
) -> impl IntoResponse {
    let include_drafts = matches!(
        q.get("include_drafts").map(String::as_str),
        Some("1" | "true" | "yes")
    );

    let sql = if include_drafts {
        LIST_SQL_ALL
    } else {
        LIST_SQL_PUBLISHED
    };

    let rows: Result<Vec<AgentListRow>, _> = sqlx::query_as(sql)
        .bind(&ctx.tenant_id)
        .fetch_all(&pool)
        .await;

    match rows {
        Ok(rows) => {
            let agents: Vec<Value> = rows.iter().map(AgentListRow::to_json).collect();
            (
                StatusCode::OK,
                Json(json!({
                    "tenant_id": ctx.tenant_id,
                    "agents": agents,
                })),
            )
                .into_response()
        }
        Err(e) => {
            tracing::error!(error = %e, "list_agents: db error");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": "internal_error"})),
            )
                .into_response()
        }
    }
}

/// `GET /v1/agents/{agent_id_or_name}` — detail view.
///
/// Resolution: path segment parses as `i64` → query by `id`; otherwise query
/// by `name`. Both branches filter on tenant_id. A miss returns `404` with
/// the **same body and same code path** whether the agent doesn't exist or
/// exists under a different tenant — no cross-tenant existence oracle.
pub async fn get_agent(
    Extension(ctx): Extension<TenantContext>,
    State(pool): State<MySqlPool>,
    Path(id_or_name): Path<String>,
) -> impl IntoResponse {
    let row: Result<Option<AgentDetailRow>, _> = if let Ok(id) = id_or_name.parse::<i64>() {
        sqlx::query_as(DETAIL_SQL_BY_ID)
            .bind(id)
            .bind(&ctx.tenant_id)
            .fetch_optional(&pool)
            .await
    } else {
        sqlx::query_as(DETAIL_SQL_BY_NAME)
            .bind(&id_or_name)
            .bind(&ctx.tenant_id)
            .fetch_optional(&pool)
            .await
    };

    match row {
        Ok(Some(agent)) => {
            emit_audit(&ctx, agent.id, &agent.name);
            (StatusCode::OK, Json(agent.to_json())).into_response()
        }
        Ok(None) => {
            // DEBUG-only logging — never INFO/WARN with the identifier, to
            // avoid building a probing oracle in logs (M4 in the plan).
            tracing::debug!(
                tenant_id = %ctx.tenant_id,
                lookup = %id_or_name,
                "get_agent: not found"
            );
            (
                StatusCode::NOT_FOUND,
                Json(json!({"error": "agent_not_found"})),
            )
                .into_response()
        }
        Err(e) => {
            tracing::error!(error = %e, "get_agent: db error");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": "internal_error"})),
            )
                .into_response()
        }
    }
}

/// Emit a structured audit event for a successful detail read (M2).
///
/// Best-effort, fail-open: this is `tracing::info!` only — the OTLP layer
/// installed in `main()` forwards it to the configured collector (Tyr).
/// A collector outage degrades to local logs but does not fail the request.
fn emit_audit(ctx: &TenantContext, agent_id: i64, agent_name: &str) {
    let auth_path = match ctx.auth_path {
        AuthPath::Jwt => "jwt",
        AuthPath::HeaderFallback => "header_fallback",
    };
    tracing::info!(
        event = "agent.detail.read",
        tenant_id = %ctx.tenant_id,
        agent_id,
        agent_name,
        auth_path,
        jwt_sub = ctx.jwt_sub.as_deref().unwrap_or(""),
        "agent detail accessed"
    );
}

// ─────────────────────────── SQL ─────────────────────────────────────────

// SQL — pre-bound queries, never string-concatenated with caller input.
// Column list is an explicit allow-list: new columns added to `agent_configs`
// are invisible until added here on purpose.

const LIST_SQL_PUBLISHED: &str = "SELECT \
    id, name, display_name, description, avatar_url, is_published, \
    model_id, provider, CAST(temperature AS DOUBLE) AS temperature, max_tokens, top_k, \
    use_rag, use_knowledge_graph, use_pageindex, tools, mcp_servers \
    FROM agent_configs WHERE tenant_id = ? AND is_published = 1 ORDER BY id";

const LIST_SQL_ALL: &str = "SELECT \
    id, name, display_name, description, avatar_url, is_published, \
    model_id, provider, CAST(temperature AS DOUBLE) AS temperature, max_tokens, top_k, \
    use_rag, use_knowledge_graph, use_pageindex, tools, mcp_servers \
    FROM agent_configs WHERE tenant_id = ? ORDER BY id";

const DETAIL_SQL_BY_ID: &str = "SELECT \
    id, name, display_name, description, avatar_url, greeting, is_published, \
    model_id, provider, CAST(temperature AS DOUBLE) AS temperature, max_tokens, top_k, \
    use_rag, use_knowledge_graph, use_pageindex, tools, mcp_servers, \
    personality_traits, rag_params, system_prompt, created_at, updated_at \
    FROM agent_configs WHERE id = ? AND tenant_id = ?";

const DETAIL_SQL_BY_NAME: &str = "SELECT \
    id, name, display_name, description, avatar_url, greeting, is_published, \
    model_id, provider, CAST(temperature AS DOUBLE) AS temperature, max_tokens, top_k, \
    use_rag, use_knowledge_graph, use_pageindex, tools, mcp_servers, \
    personality_traits, rag_params, system_prompt, created_at, updated_at \
    FROM agent_configs WHERE name = ? AND tenant_id = ?";

// ─────────────────────────── Unit tests ──────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rag_params_whitelist_drops_unknown_keys() {
        let input = json!({
            "limit": 10,
            "alpha": 0.5,
            "output_format": "json",
            "secret_key": "hunter2",
            "internal_collection": "private",
        });
        let out = rag_params_whitelist(Some(&input));
        let obj = out.as_object().expect("object");
        assert_eq!(obj.len(), 3);
        assert!(obj.contains_key("limit"));
        assert!(obj.contains_key("alpha"));
        assert!(obj.contains_key("output_format"));
        assert!(!obj.contains_key("secret_key"));
        assert!(!obj.contains_key("internal_collection"));
    }

    #[test]
    fn rag_params_whitelist_null_input_returns_null() {
        assert!(rag_params_whitelist(None).is_null());
    }

    #[test]
    fn rag_params_whitelist_non_object_returns_null() {
        let arr = json!([1, 2, 3]);
        assert!(rag_params_whitelist(Some(&arr)).is_null());
    }

    #[test]
    fn rag_params_whitelist_empty_after_filter_returns_null() {
        let input = json!({"only_unknown": "x"});
        assert!(rag_params_whitelist(Some(&input)).is_null());
    }

    #[test]
    fn json_array_or_empty_null_becomes_array() {
        assert_eq!(json_array_or_empty(None), json!([]));
    }

    #[test]
    fn json_array_or_empty_non_array_becomes_array() {
        let v = json!({"oops": "wrong shape"});
        assert_eq!(json_array_or_empty(Some(&v)), json!([]));
    }

    #[test]
    fn json_array_or_empty_passes_arrays_through() {
        let v = json!(["vector_search", "ocr_extract"]);
        assert_eq!(json_array_or_empty(Some(&v)), v);
    }
}
