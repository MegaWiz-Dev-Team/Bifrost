//! Request middleware for `/v1/agents*`: JWT auth + tenant extraction.
//!
//! Auth precedence:
//! 1. `Authorization: Bearer <jwt>` → validated against Yggdrasil, tenant from
//!    `urn:zitadel:iam:org:id` claim.
//! 2. `X-Tenant-Id` header → fallback when no JWT. Emits a WARN log so
//!    operators can spot header-only callers (and gate them off in prod).
//! 3. Neither → `401 Unauthorized`.
//!
//! JWT wins over header when both present (header silently ignored).
//! A `TenantContext` request extension is set so handlers can read tenant_id
//! and the auth path used for audit emission.
//!
//! If `YGGDRASIL_ISSUER` / `JWT_AUDIENCE` env vars are not set at startup,
//! the validator is `None` and only the header path works (with WARN). This
//! preserves the existing dev workflow while production deployments wire
//! the env vars to enforce JWT.

use std::sync::Arc;

use axum::{
    body::Body,
    extract::State,
    http::{header, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};

use crate::auth_jwt::{Claims, JwtValidator};

/// Per-request tenant + auth metadata. Inserted as a request extension by
/// [`require_tenant`] so downstream handlers and the audit emitter can read
/// it without re-parsing headers.
#[derive(Debug, Clone)]
pub struct TenantContext {
    pub tenant_id: String,
    pub auth_path: AuthPath,
    /// JWT `sub` claim, if auth_path == Jwt. Used for audit events.
    pub jwt_sub: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthPath {
    Jwt,
    HeaderFallback,
}

/// Shared state for the middleware. Held inside `AppState` and cloned per
/// request (Arc-backed → cheap).
#[derive(Clone)]
pub struct AuthState {
    pub jwt_validator: Option<Arc<JwtValidator>>,
}

impl AuthState {
    /// Build from env vars. Returns an `AuthState` with `jwt_validator = None`
    /// if either env var is absent — operators must set both to enforce JWT.
    pub fn from_env() -> Self {
        let issuer = std::env::var("YGGDRASIL_ISSUER").ok();
        let audience = std::env::var("JWT_AUDIENCE").ok();
        match (issuer, audience) {
            (Some(iss), Some(aud)) if !iss.is_empty() && !aud.is_empty() => {
                tracing::info!(issuer = %iss, audience = %aud, "JWT validator enabled");
                Self {
                    jwt_validator: Some(Arc::new(JwtValidator::new(iss, aud))),
                }
            }
            _ => {
                tracing::warn!(
                    "JWT validator disabled — YGGDRASIL_ISSUER/JWT_AUDIENCE unset; \
                     /v1/agents* will accept X-Tenant-Id header only"
                );
                Self { jwt_validator: None }
            }
        }
    }
}

/// Middleware: extract tenant from JWT (preferred) or X-Tenant-Id header
/// (fallback with WARN). Returns 401 if neither path yields a tenant.
///
/// Sets [`TenantContext`] as a request extension on success.
pub async fn require_tenant(
    State(auth): State<AuthState>,
    mut req: Request<Body>,
    next: Next,
) -> Response {
    // 1. JWT path
    let bearer = req
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(str::to_string);

    if let (Some(token), Some(validator)) = (bearer.as_ref(), auth.jwt_validator.as_ref()) {
        match validator.validate(token).await {
            Ok(claims) => match tenant_from_claims(&claims) {
                Some(tenant_id) => {
                    let ctx = TenantContext {
                        tenant_id,
                        auth_path: AuthPath::Jwt,
                        jwt_sub: Some(claims.sub.clone()),
                    };
                    req.extensions_mut().insert(ctx);
                    return next.run(req).await;
                }
                None => {
                    tracing::warn!(sub = %claims.sub, "JWT valid but missing tenant claim");
                    return unauthorized("invalid_tenant_claim");
                }
            },
            Err(e) => {
                tracing::warn!(error = %e, "JWT validation failed");
                return unauthorized("invalid_token");
            }
        }
    }

    // 2. Header fallback — only allowed when JWT was not presented
    if let Some(tenant_id) = req
        .headers()
        .get("X-Tenant-Id")
        .and_then(|v| v.to_str().ok())
        .filter(|v| !v.is_empty())
        .map(str::to_string)
    {
        tracing::warn!(
            tenant_id = %tenant_id,
            "/v1/agents request using X-Tenant-Id header fallback (no JWT)"
        );
        let ctx = TenantContext {
            tenant_id,
            auth_path: AuthPath::HeaderFallback,
            jwt_sub: None,
        };
        req.extensions_mut().insert(ctx);
        return next.run(req).await;
    }

    // 3. Neither path → 401
    unauthorized("missing_credentials")
}

fn tenant_from_claims(claims: &Claims) -> Option<String> {
    claims
        .tenant_id
        .as_ref()
        .filter(|v| !v.is_empty())
        .cloned()
}

fn unauthorized(reason: &'static str) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(serde_json::json!({"error": "unauthorized", "reason": reason})),
    )
        .into_response()
}
