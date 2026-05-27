use bifrost::rl_orchestrator::monitor_deployments;
use sqlx::MySqlPool;
use std::time::Duration;
use tokio::task;
use tracing::info;

pub fn spawn_deployment_monitor(pool: MySqlPool) {
    task::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(30)).await;

            match monitor_deployments(&pool).await {
                Ok(_) => {
                    tracing::debug!("✓ Deployment monitor check completed");
                }
                Err(e) => {
                    tracing::warn!("✗ Deployment monitor error: {:?}", e);
                }
            }
        }
    });
}
