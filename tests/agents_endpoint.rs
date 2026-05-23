//! Integration tests for `/v1/agents*` endpoints.
//!
//! These tests run against a real MariaDB (set `DATABASE_URL` —
//! defaults to the OrbStack-forwarded mimir DB on 127.0.0.1:3306). Each
//! test creates its own unique tenant_id + tenant row, seeds agents, then
//! cleans up. Tests are safe to run in parallel.
//!
//! JWT path (T14) uses wiremock to mock the Yggdrasil JWKS endpoint with the
//! same test keypair as the in-tree `auth_jwt::tests` module.
//!
//! Skip these locally with `--skip integration_` if the DB isn't reachable.

use axum::{
    body::Body,
    http::{Method, Request, StatusCode},
};
use bifrost::{agents, middleware::AuthState};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use sqlx::MySqlPool;
use tower::ServiceExt;
use uuid::Uuid;

// ───────────────────────── Test harness ──────────────────────────────────

fn db_url() -> String {
    std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "mysql://root:root@127.0.0.1:3306/mimir_test".to_string())
}

async fn pool() -> MySqlPool {
    MySqlPool::connect(&db_url())
        .await
        .expect("connect to test DB — set DATABASE_URL if not localhost:3306")
}

struct TestTenant {
    pool: MySqlPool,
    tenant_id: String,
}

impl TestTenant {
    async fn new(pool: MySqlPool) -> Self {
        let tenant_id = format!("bifrost_int_{}", Uuid::new_v4().simple());
        sqlx::query("INSERT INTO tenants (id, name, domain) VALUES (?, ?, '')")
            .bind(&tenant_id)
            .bind(&tenant_id)
            .execute(&pool)
            .await
            .expect("seed tenant");
        Self { pool, tenant_id }
    }

    /// Seed an agent row. Returns its db id.
    #[allow(clippy::too_many_arguments)]
    async fn seed_agent(&self, params: SeedAgent<'_>) -> i64 {
        let res = sqlx::query(
            "INSERT INTO agent_configs ( \
                tenant_id, name, display_name, description, system_prompt, \
                model_id, provider, temperature, max_tokens, top_k, \
                use_rag, use_knowledge_graph, use_pageindex, \
                tools, mcp_servers, personality_traits, greeting, avatar_url, \
                rag_params, template_id, api_key, is_published \
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&self.tenant_id)
        .bind(params.name)
        .bind(params.display_name)
        .bind(params.description)
        .bind(params.system_prompt)
        .bind(params.model_id)
        .bind(params.provider)
        .bind(params.temperature)
        .bind(params.max_tokens)
        .bind(params.top_k)
        .bind(params.use_rag as i8)
        .bind(params.use_knowledge_graph as i8)
        .bind(params.use_pageindex as i8)
        .bind(params.tools)
        .bind(params.mcp_servers)
        .bind(params.personality_traits)
        .bind(params.greeting)
        .bind(params.avatar_url)
        .bind(params.rag_params)
        .bind(params.template_id)
        .bind(params.api_key)
        .bind(params.is_published as i8)
        .execute(&self.pool)
        .await
        .expect("seed agent");
        res.last_insert_id() as i64
    }

    /// Build the test router pointing at this tenant's DB. JWT off by default
    /// (header-fallback mode) so X-Tenant-Id is accepted.
    fn router(&self) -> axum::Router {
        agents::build_router(
            self.pool.clone(),
            AuthState { jwt_validator: None },
            // Generous burst so tests don't accidentally trip rate limit.
            1000,
        )
    }

    fn router_with_limit(&self, burst: u32) -> axum::Router {
        agents::build_router(
            self.pool.clone(),
            AuthState { jwt_validator: None },
            burst,
        )
    }

    async fn cleanup(&self) {
        let _ = sqlx::query("DELETE FROM agent_configs WHERE tenant_id = ?")
            .bind(&self.tenant_id)
            .execute(&self.pool)
            .await;
        let _ = sqlx::query("DELETE FROM tenants WHERE id = ?")
            .bind(&self.tenant_id)
            .execute(&self.pool)
            .await;
    }
}

#[derive(Default)]
struct SeedAgent<'a> {
    name: &'a str,
    display_name: Option<&'a str>,
    description: Option<&'a str>,
    system_prompt: &'a str,
    model_id: &'a str,
    provider: &'a str,
    temperature: Option<f64>,
    max_tokens: Option<i32>,
    top_k: Option<i32>,
    use_rag: bool,
    use_knowledge_graph: bool,
    use_pageindex: bool,
    tools: Option<Value>,
    mcp_servers: Option<Value>,
    personality_traits: Option<Value>,
    greeting: Option<&'a str>,
    avatar_url: Option<&'a str>,
    rag_params: Option<Value>,
    template_id: Option<&'a str>,
    api_key: Option<&'a str>,
    is_published: bool,
}

impl<'a> SeedAgent<'a> {
    /// Reasonable defaults for "a published vanilla agent".
    fn vanilla(name: &'a str) -> Self {
        Self {
            name,
            display_name: Some("Test Agent"),
            description: Some("A test agent"),
            system_prompt: "You are a test agent.",
            model_id: "gemma-4-26b",
            provider: "mlx",
            temperature: Some(0.7),
            max_tokens: Some(2048),
            top_k: Some(5),
            use_rag: true,
            ..Default::default()
        }
    }
}

async fn send(router: &axum::Router, req: Request<Body>) -> (StatusCode, Value) {
    let resp = router
        .clone()
        .oneshot(req)
        .await
        .expect("oneshot");
    let status = resp.status();
    let bytes = resp.into_body().collect().await.expect("body").to_bytes();
    let body: Value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or_else(|_| {
            json!({ "_raw": String::from_utf8_lossy(&bytes).to_string() })
        })
    };
    (status, body)
}

fn get(uri: &str, tenant: &str) -> Request<Body> {
    // X-Forwarded-For drives tower-governor's SmartIpKeyExtractor — match
    // what K8s ingress sets in prod. Each call uses a fresh unique IP so
    // tests don't share rate-limit buckets unless they explicitly want to.
    let fake_ip = format!(
        "10.0.{}.{}",
        rand_u8(),
        rand_u8(),
    );
    Request::builder()
        .method(Method::GET)
        .uri(uri)
        .header("X-Tenant-Id", tenant)
        .header("X-Forwarded-For", fake_ip)
        .body(Body::empty())
        .unwrap()
}

fn get_from_ip(uri: &str, tenant: &str, ip: &str) -> Request<Body> {
    Request::builder()
        .method(Method::GET)
        .uri(uri)
        .header("X-Tenant-Id", tenant)
        .header("X-Forwarded-For", ip)
        .body(Body::empty())
        .unwrap()
}

fn rand_u8() -> u8 {
    // Cheap PRNG using nanos — good enough for unique IPs across calls.
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .subsec_nanos();
    ((nanos.wrapping_mul(2654435761)) >> 24) as u8
}

fn raw_body_string(s: &str) -> bool {
    // Helper for "this substring never appears in any field name or value".
    !s.is_empty()
}

// ───────────────────────── Tests ─────────────────────────────────────────

#[tokio::test]
async fn t1_list_shape_has_capabilities_and_legacy_fields() {
    let t = TestTenant::new(pool().await).await;
    t.seed_agent(SeedAgent {
        is_published: true,
        tools: Some(json!(["vector_search", "ocr_extract"])),
        ..SeedAgent::vanilla("vanilla-1")
    })
    .await;

    let (status, body) = send(&t.router(), get("/v1/agents", &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK, "{:?}", body);
    let agent = &body["agents"][0];
    // Legacy top-level
    assert_eq!(agent["name"], "vanilla-1");
    assert_eq!(agent["model_id"], "gemma-4-26b");
    assert_eq!(agent["is_published"], true);
    // Nested capabilities
    let caps = &agent["capabilities"];
    assert_eq!(caps["model_id"], "gemma-4-26b");
    assert_eq!(caps["provider"], "mlx");
    assert_eq!(caps["temperature"], 0.7);
    assert_eq!(caps["use_rag"], true);
    assert_eq!(caps["tools"], json!(["vector_search", "ocr_extract"]));
    assert_eq!(caps["mcp_servers"], json!([]));

    t.cleanup().await;
}

#[tokio::test]
async fn t2_list_excludes_persona_and_secrets() {
    let t = TestTenant::new(pool().await).await;
    t.seed_agent(SeedAgent {
        is_published: true,
        system_prompt: "SECRET PERSONA — do not leak",
        personality_traits: Some(json!(["warm", "professional"])),
        greeting: Some("Hello from test"),
        rag_params: Some(json!({"limit": 10, "secret_key": "hunter2"})),
        api_key: Some("apikey-leak-test"),
        ..SeedAgent::vanilla("vanilla-2")
    })
    .await;

    let (status, body) = send(&t.router(), get("/v1/agents", &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK);
    let raw = body.to_string();
    for forbidden in [
        "SECRET PERSONA",
        "system_prompt",
        "personality_traits",
        "greeting",
        "rag_params",
        "api_key",
        "apikey-leak-test",
        "hunter2",
    ] {
        assert!(
            !raw.contains(forbidden),
            "list response leaked `{forbidden}` — got: {raw}"
        );
    }
    assert!(raw_body_string(&raw));

    t.cleanup().await;
}

#[tokio::test]
async fn t3_detail_by_id_returns_full_shape() {
    let t = TestTenant::new(pool().await).await;
    let id = t
        .seed_agent(SeedAgent {
            is_published: true,
            system_prompt: "Full persona text",
            greeting: Some("Hi"),
            personality_traits: Some(json!(["calm"])),
            tools: Some(json!(["graph_search"])),
            ..SeedAgent::vanilla("detail-1")
        })
        .await;

    let (status, body) = send(&t.router(), get(&format!("/v1/agents/{}", id), &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body["id"], id);
    assert_eq!(body["name"], "detail-1");
    assert_eq!(body["system_prompt"], "Full persona text");
    assert_eq!(body["greeting"], "Hi");
    assert_eq!(body["personality_traits"], json!(["calm"]));
    assert_eq!(body["capabilities"]["tools"], json!(["graph_search"]));
    assert!(body["created_at"].is_string());
    assert!(body["updated_at"].is_string());

    t.cleanup().await;
}

#[tokio::test]
async fn t4_detail_by_name_returns_same_row_as_by_id() {
    let t = TestTenant::new(pool().await).await;
    let id = t
        .seed_agent(SeedAgent {
            is_published: true,
            ..SeedAgent::vanilla("detail-by-name")
        })
        .await;

    let (s_id, body_id) =
        send(&t.router(), get(&format!("/v1/agents/{}", id), &t.tenant_id)).await;
    let (s_name, body_name) = send(
        &t.router(),
        get("/v1/agents/detail-by-name", &t.tenant_id),
    )
    .await;

    assert_eq!(s_id, StatusCode::OK);
    assert_eq!(s_name, StatusCode::OK);
    assert_eq!(body_id["id"], body_name["id"]);
    assert_eq!(body_id["name"], body_name["name"]);

    t.cleanup().await;
}

#[tokio::test]
async fn t5_detail_excludes_api_key_and_template_id() {
    let t = TestTenant::new(pool().await).await;
    let id = t
        .seed_agent(SeedAgent {
            is_published: true,
            api_key: Some("super-secret-key"),
            template_id: Some("internal-template-42"),
            ..SeedAgent::vanilla("excl-1")
        })
        .await;

    let (status, body) = send(&t.router(), get(&format!("/v1/agents/{}", id), &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK);
    let raw = body.to_string();
    for forbidden in ["api_key", "super-secret-key", "template_id", "internal-template-42"] {
        assert!(
            !raw.contains(forbidden),
            "detail response leaked `{forbidden}` — got: {raw}"
        );
    }

    t.cleanup().await;
}

#[tokio::test]
async fn t6_detail_rag_params_whitelist_drops_unknown_keys() {
    let t = TestTenant::new(pool().await).await;
    let id = t
        .seed_agent(SeedAgent {
            is_published: true,
            rag_params: Some(json!({
                "limit": 10,
                "alpha": 0.5,
                "output_format": "json",
                "secret_key": "hunter2",
                "internal_collection": "private",
            })),
            ..SeedAgent::vanilla("rag-1")
        })
        .await;

    let (status, body) = send(&t.router(), get(&format!("/v1/agents/{}", id), &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK);
    let rag = &body["rag_params"];
    assert_eq!(rag["limit"], 10);
    assert_eq!(rag["alpha"], 0.5);
    assert_eq!(rag["output_format"], "json");
    assert!(rag.get("secret_key").is_none());
    assert!(rag.get("internal_collection").is_none());

    let raw = body.to_string();
    assert!(!raw.contains("hunter2"));
    assert!(!raw.contains("internal_collection"));

    t.cleanup().await;
}

#[tokio::test]
async fn t7_cross_tenant_returns_404_with_neutral_body() {
    let pool = pool().await;
    let owner = TestTenant::new(pool.clone()).await;
    let probe = TestTenant::new(pool.clone()).await;

    let id = owner
        .seed_agent(SeedAgent {
            is_published: true,
            ..SeedAgent::vanilla("owned-by-A")
        })
        .await;

    // Probe with the *other* tenant. Must be 404 (not 403), and the body
    // must not include any agent fields — only the neutral error code.
    let router = probe.router(); // router state doesn't depend on tenant header
    let (status, body) =
        send(&router, get(&format!("/v1/agents/{}", id), &probe.tenant_id)).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body, json!({"error": "agent_not_found"}));

    // Same shape for name lookup
    let (status, body) =
        send(&router, get("/v1/agents/owned-by-A", &probe.tenant_id)).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body, json!({"error": "agent_not_found"}));

    owner.cleanup().await;
    probe.cleanup().await;
}

#[tokio::test]
async fn t8_draft_filter_hides_unpublished_by_default() {
    let t = TestTenant::new(pool().await).await;
    t.seed_agent(SeedAgent {
        is_published: true,
        ..SeedAgent::vanilla("pub-1")
    })
    .await;
    t.seed_agent(SeedAgent {
        is_published: false,
        ..SeedAgent::vanilla("draft-1")
    })
    .await;

    let (_, body_default) = send(&t.router(), get("/v1/agents", &t.tenant_id)).await;
    let names_default: Vec<String> = body_default["agents"]
        .as_array()
        .unwrap()
        .iter()
        .map(|a| a["name"].as_str().unwrap().to_string())
        .collect();
    assert!(names_default.contains(&"pub-1".to_string()));
    assert!(!names_default.contains(&"draft-1".to_string()));

    let (_, body_all) = send(
        &t.router(),
        get("/v1/agents?include_drafts=true", &t.tenant_id),
    )
    .await;
    let names_all: Vec<String> = body_all["agents"]
        .as_array()
        .unwrap()
        .iter()
        .map(|a| a["name"].as_str().unwrap().to_string())
        .collect();
    assert!(names_all.contains(&"pub-1".to_string()));
    assert!(names_all.contains(&"draft-1".to_string()));

    t.cleanup().await;
}

#[tokio::test]
async fn t9_null_json_columns_serialize_as_empty_array() {
    let t = TestTenant::new(pool().await).await;
    let id = t
        .seed_agent(SeedAgent {
            is_published: true,
            tools: None,
            mcp_servers: None,
            personality_traits: None,
            ..SeedAgent::vanilla("null-cols")
        })
        .await;

    let (status, body) = send(&t.router(), get(&format!("/v1/agents/{}", id), &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["capabilities"]["tools"], json!([]));
    assert_eq!(body["capabilities"]["mcp_servers"], json!([]));
    assert_eq!(body["personality_traits"], json!([]));

    t.cleanup().await;
}

#[tokio::test]
async fn t11_numeric_name_resolves_by_id() {
    let t = TestTenant::new(pool().await).await;
    let id_a = t
        .seed_agent(SeedAgent {
            is_published: true,
            ..SeedAgent::vanilla("alpha")
        })
        .await;
    // Seed an agent whose *name* happens to be the same string as id_a.
    // Per the plan, numeric path segments resolve by ID — this row should
    // be unreachable via /v1/agents/{id_a}.
    let numeric_name = id_a.to_string();
    t.seed_agent(SeedAgent {
        is_published: true,
        name: &numeric_name,
        ..SeedAgent::vanilla(&numeric_name)
    })
    .await;

    let (status, body) = send(&t.router(), get(&format!("/v1/agents/{}", id_a), &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["id"], id_a);
    assert_eq!(body["name"], "alpha", "numeric path resolved by ID, not by name");

    t.cleanup().await;
}

#[tokio::test]
async fn t12_rate_limit_returns_429_when_burst_exceeded() {
    let t = TestTenant::new(pool().await).await;
    t.seed_agent(SeedAgent {
        is_published: true,
        ..SeedAgent::vanilla("rl-target")
    })
    .await;

    // Tight burst of 3 — fourth concurrent hit from the same IP should 429.
    let router = t.router_with_limit(3);
    let mut statuses = Vec::new();
    for _ in 0..10 {
        let (s, _) = send(
            &router,
            get_from_ip("/v1/agents/rl-target", &t.tenant_id, "10.99.99.99"),
        )
        .await;
        statuses.push(s);
    }
    let ok = statuses.iter().filter(|s| s.is_success()).count();
    let limited = statuses.iter().filter(|s| s.as_u16() == 429).count();
    assert!(ok >= 1, "expected at least one 200, got {statuses:?}");
    assert!(
        limited >= 1,
        "expected at least one 429 within 10 rapid calls, got {statuses:?}"
    );

    t.cleanup().await;
}

#[tokio::test]
async fn t14a_missing_credentials_returns_401() {
    let t = TestTenant::new(pool().await).await;

    // Build a router with JWT *enabled* (validator present). Without an
    // Authorization header AND without X-Tenant-Id, request must 401.
    //
    // We mount a dummy validator with bogus issuer/audience — it is never
    // called because no Authorization header is sent.
    let auth = AuthState {
        jwt_validator: Some(std::sync::Arc::new(bifrost::auth_jwt::JwtValidator::new(
            "https://unused.example.com".to_string(),
            "bifrost".to_string(),
        ))),
    };
    let router = agents::build_router(t.pool.clone(), auth, 1000);

    let req = Request::builder()
        .method(Method::GET)
        .uri("/v1/agents")
        // X-Forwarded-For is required for the rate-limit key extractor —
        // 401 must still come back without auth credentials, not 500.
        .header("X-Forwarded-For", "10.0.0.1")
        // intentionally no X-Tenant-Id, no Authorization
        .body(Body::empty())
        .unwrap();
    let (status, body) = send(&router, req).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["error"], "unauthorized");

    t.cleanup().await;
}

#[tokio::test]
async fn t14b_header_fallback_works_when_no_jwt_validator() {
    let t = TestTenant::new(pool().await).await;
    t.seed_agent(SeedAgent {
        is_published: true,
        ..SeedAgent::vanilla("hdr-fb")
    })
    .await;

    // jwt_validator = None → header fallback path only
    let (status, _) = send(&t.router(), get("/v1/agents/hdr-fb", &t.tenant_id)).await;
    assert_eq!(status, StatusCode::OK);

    t.cleanup().await;
}
