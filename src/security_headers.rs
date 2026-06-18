//! Security response headers (defense-in-depth alongside ingress).
//!
//! Closes Odin scan 2026-06-14 (Asgard#99) for Bifrost:
//!   * Anti-clickjacking via `X-Frame-Options: SAMEORIGIN` and the
//!     CSP `frame-ancestors 'self'` directive.
//!   * Baseline `Content-Security-Policy` (matches Asgard#99 PR-1 ingress
//!     baseline; permissive enough for the React dashboard inline bootstrap
//!     and Vite-built assets).
//!   * `X-Content-Type-Options: nosniff` on every response.
//!
//! Headers are inserted only when not already present so an upstream ingress
//! (which is the primary control) can override without conflict.

use axum::{
    body::Body,
    http::{header::HeaderName, HeaderValue, Request},
    middleware::Next,
    response::Response,
};

// Mirrors Asgard#99 PR-1 ingress baseline; kept intentionally permissive so the
// dashboard's inline bootstrap + same-origin XHRs to `/v1/*` keep working. The
// ingress applies the same policy and is the authoritative enforcement point.
const CSP_BASELINE: &str = "default-src 'self'; \
     script-src 'self' 'unsafe-inline'; \
     style-src 'self' 'unsafe-inline'; \
     img-src 'self' data: blob:; \
     connect-src 'self'; \
     frame-ancestors 'self'; \
     base-uri 'self'; \
     form-action 'self'; \
     object-src 'none'";

pub async fn set_security_headers(req: Request<Body>, next: Next) -> Response {
    let mut res = next.run(req).await;
    let headers = res.headers_mut();

    insert_if_absent(
        headers,
        HeaderName::from_static("x-frame-options"),
        HeaderValue::from_static("SAMEORIGIN"),
    );
    insert_if_absent(
        headers,
        HeaderName::from_static("x-content-type-options"),
        HeaderValue::from_static("nosniff"),
    );
    insert_if_absent(
        headers,
        HeaderName::from_static("content-security-policy"),
        HeaderValue::from_static(CSP_BASELINE),
    );

    res
}

fn insert_if_absent(
    headers: &mut axum::http::HeaderMap,
    name: HeaderName,
    value: HeaderValue,
) {
    if !headers.contains_key(&name) {
        headers.insert(name, value);
    }
}
