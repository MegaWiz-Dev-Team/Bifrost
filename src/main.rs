use axum::{
    extract::{Path, State, Json},
    http::HeaderMap,
    routing::{get, post},
    response::IntoResponse,
    Router,
};
use opentelemetry_otlp::WithExportConfig;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use mimir_core_ai::services::{db::DbPool, llm_router::LlmRouter, qdrant::QdrantService};
use std::sync::Arc;
use tokio::net::TcpListener;
use serde::Deserialize;

// Import the swarm engine modules (bin-only — heavyweight deps not needed
// by integration tests, so they stay outside the library crate).
pub mod swarm_engine;
pub mod memory;
pub mod retrieval;

// HTTP-layer modules live in `lib.rs` so integration tests can reach them.
use bifrost::{agents, auth_jwt as _, middleware};

#[derive(Clone)]
pub struct AppState {
    pub overseer: Arc<swarm_engine::overseer::OverseerManager>,
    /// Direct pool handle for the agent-registry list endpoint. sqlx pools are
    /// already cheap to clone (internally Arc'd).
    pub pool: sqlx::MySqlPool,
}

#[derive(Deserialize)]
struct RunAgentRequest {
    query: String,
    session_id: Option<String>,
    patient_id: Option<String>,
    /// B-50d transparent OCR path. Base64-encoded image (no `data:` prefix).
    /// When present, Bifrost OCRs via Syn before entering the swarm and
    /// prepends extracted text to the query.
    #[serde(default)]
    image_base64: Option<String>,
    #[serde(default)]
    image_filename: Option<String>,
    /// Optional smart-router hint forwarded to Syn (`handwriting` |
    /// `printed_thai` | `mixed`).
    #[serde(default)]
    doc_type: Option<String>,
}

async fn run_agent(
    headers: HeaderMap,
    Path(agent_id): Path<String>,
    State(state): State<AppState>,
    Json(payload): Json<RunAgentRequest>,
) -> impl IntoResponse {
    let tenant_id = headers
        .get("X-Tenant-Id")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("default")
        .to_string();

    // B-50d — if an image is attached, run OCR before the swarm. The
    // extracted text is prepended to the user's query inside a marker block
    // so the LLM can distinguish document content from typed words.
    let effective_query = if let Some(image_b64) = payload.image_base64.as_deref() {
        let syn_base = std::env::var("SYN_API_URL")
            .unwrap_or_else(|_| "http://syn-api.asgard.svc:8080".to_string());
        let opts = swarm_engine::ocr_preprocess::OcrPreprocessOpts {
            filename: payload.image_filename.clone(),
            doc_type: payload.doc_type.clone(),
            hint_lang: None,
            high_stakes: false,
        };
        match swarm_engine::ocr_preprocess::preprocess_image(
            &syn_base, &tenant_id, image_b64, &opts,
        ).await {
            Ok(ocr) => {
                let text = ocr.extracted_text.unwrap_or_default();
                let block = swarm_engine::ocr_preprocess::format_ocr_block(
                    &text, &ocr.engine_used, &ocr.audit_id,
                );
                format!("{}{}", block, payload.query)
            }
            Err(swarm_engine::ocr_preprocess::OcrPreprocessError::PhiStrict { detail }) => {
                return (
                    axum::http::StatusCode::FORBIDDEN,
                    axum::Json(serde_json::json!({
                        "error": "phi_strict",
                        "detail": detail,
                    }))
                ).into_response();
            }
            Err(swarm_engine::ocr_preprocess::OcrPreprocessError::BudgetExceeded { detail }) => {
                return (
                    axum::http::StatusCode::PAYMENT_REQUIRED,
                    axum::Json(serde_json::json!({
                        "error": "budget_exceeded",
                        "detail": detail,
                    }))
                ).into_response();
            }
            Err(e) => {
                // Engine failure or transport error — surface to caller so
                // the user can re-try / re-upload. Don't silently drop the
                // image and proceed text-only.
                return (
                    axum::http::StatusCode::BAD_GATEWAY,
                    axum::Json(serde_json::json!({
                        "error": "ocr_failed",
                        "detail": e.to_string(),
                    }))
                ).into_response();
            }
        }
    } else {
        payload.query.clone()
    };

    match state.overseer.run_swarm(&tenant_id, &agent_id, &effective_query, payload.session_id.as_deref(), payload.patient_id.as_deref()).await {
        Ok(response) => (axum::http::StatusCode::OK, axum::Json(response)).into_response(),
        Err(e) => (
            axum::http::StatusCode::INTERNAL_SERVER_ERROR,
            axum::Json(serde_json::json!({"error": e.to_string()}))
        ).into_response(),
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Start OpenTelemetry OTLP Pipeline (endpoint configurable via OTEL_EXPORTER_OTLP_ENDPOINT)
    let otel_endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .unwrap_or_else(|_| "http://localhost:4317".to_string());
    let tracer = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(
            opentelemetry_otlp::new_exporter()
                .tonic()
                .with_endpoint(otel_endpoint),
        )
        .install_batch(opentelemetry_sdk::runtime::Tokio)
        .expect("Failed to initialize OTLP Tracer");

    let telemetry_layer = tracing_opentelemetry::layer().with_tracer(tracer);

    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::from_default_env().add_directive("bifrost=info".parse().unwrap()))
        .with(tracing_subscriber::fmt::layer())
        .with(telemetry_layer)
        .init();

    tracing::info!("Starting Bifrost-RS (Standalone Agent Engine)");

    // Initialize dependencies
    dotenvy::dotenv().ok();
    
    // Inject Vault secrets into the environment before initializing anything
    mimir_core_ai::config::inject_vault_secrets().await;

    let db_url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = sqlx::MySqlPool::connect(&db_url).await.expect("Failed to connect to DB");
    
    let qdrant = Arc::new(QdrantService::new());
    
    let llm_router = Arc::new(LlmRouter::new(pool.clone(), "default").await.expect("Failed to init LlmRouter"));
    
    let memvid = Arc::new(memory::memvid_manager::MemvidManager::new("data/agents"));
    
    let overseer = Arc::new(swarm_engine::overseer::OverseerManager::new(
        pool.clone(),
        qdrant,
        llm_router,
        memvid,
    ));

    let state = AppState { overseer, pool };

    // Build auth state from env (YGGDRASIL_ISSUER + JWT_AUDIENCE). If unset,
    // /v1/agents* accepts X-Tenant-Id header only and logs a WARN per
    // request — see `middleware::AuthState::from_env`.
    let auth_state = middleware::AuthState::from_env();

    // /v1/agents* sub-router: JWT + rate-limit (60 req/min/IP) applied
    // inside `agents::build_router`. Same builder is used by integration
    // tests so the test surface matches prod.
    let agents_router = agents::build_router(state.pool.clone(), auth_state, 60);

    let app = Router::new()
        .route("/healthz", get(|| async { "OK" }))
        .route("/v1/agents/{agent_id}/run", post(run_agent))
        .with_state(state)
        .merge(agents_router);

    let addr = "0.0.0.0:8100";
    tracing::info!("Listening on {}", addr);
    let listener = TcpListener::bind(addr).await?;

    // tower-governor's SmartIpKeyExtractor (used on /v1/agents*) falls back
    // to the peer IP from ConnectInfo when no `X-Forwarded-For` / `X-Real-IP`
    // header is present. Without `into_make_service_with_connect_info` axum
    // never populates ConnectInfo and the extractor errors with
    // "Unable To Extract Key!". Direct-NodePort callers (no ingress) need this.
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .await?;
    
    Ok(())
}
