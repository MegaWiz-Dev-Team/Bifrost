use axum::{
    extract::{Path, State, Json},
    routing::{get, post},
    response::IntoResponse,
    Router,
};
use mimir_core_ai::services::{db::DbPool, llm_router::LlmRouter, qdrant::QdrantService};
use std::sync::Arc;
use tokio::net::TcpListener;
use serde::Deserialize;

// Import the swarm engine modules
pub mod swarm_engine;
pub mod memory;
pub mod retrieval;

#[derive(Clone)]
struct AppState {
    overseer: Arc<swarm_engine::overseer::OverseerManager>,
}

#[derive(Deserialize)]
struct RunAgentRequest {
    query: String,
    session_id: Option<String>,
}

async fn run_agent(
    Path(agent_id): Path<String>,
    State(state): State<AppState>,
    Json(payload): Json<RunAgentRequest>,
) -> impl IntoResponse {
    match state.overseer.run_swarm(&agent_id, &payload.query, payload.session_id.as_deref()).await {
        Ok(response) => (axum::http::StatusCode::OK, axum::Json(response)).into_response(),
        Err(e) => (
            axum::http::StatusCode::INTERNAL_SERVER_ERROR,
            axum::Json(serde_json::json!({"error": e.to_string()}))
        ).into_response(),
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt::init();

    tracing::info!("Starting Bifrost-RS (Standalone Agent Engine)");

    // Initialize dependencies
    dotenvy::dotenv().ok();
    
    let db_url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = sqlx::MySqlPool::connect(&db_url).await.expect("Failed to connect to DB");
    
    let qdrant = Arc::new(QdrantService::new());
    
    let llm_router = Arc::new(LlmRouter::new(pool.clone(), "default").await.expect("Failed to init LlmRouter"));
    
    let memvid = Arc::new(memory::memvid_manager::MemvidManager::new("data/agents"));
    
    let overseer = Arc::new(swarm_engine::overseer::OverseerManager::new(
        pool,
        qdrant,
        llm_router,
        memvid,
    ));

    let state = AppState { overseer };

    let app = Router::new()
        .route("/healthz", get(|| async { "OK" }))
        .route("/v1/agents/:agent_id/run", post(run_agent))
        .with_state(state);

    let addr = "0.0.0.0:8100";
    tracing::info!("Listening on {}", addr);
    let listener = TcpListener::bind(addr).await?;
    
    axum::serve(listener, app).await?;
    
    Ok(())
}
