use bifrost::rl_orchestrator::run_daily_rl_cycle;
use sqlx::MySqlPool;
use std::time::Duration;
use tokio::task;
use tracing::info;

pub fn spawn_rl_cycle_scheduler(pool: MySqlPool) {
    task::spawn(async move {
        loop {
            let sleep_duration = calculate_sleep_until_02_utc();
            info!("RL cycle will run in {}s", sleep_duration.as_secs());

            tokio::time::sleep(sleep_duration).await;

            // Run for each tenant
            for tenant_id in &["asgard_medical", "asgard_insurance", "asgard_platform"] {
                match run_daily_rl_cycle(&pool, tenant_id).await {
                    Ok(_) => info!("✓ RL cycle completed: {}", tenant_id),
                    Err(e) => info!("✗ RL cycle failed: {}: {:?}", tenant_id, e),
                }
            }
        }
    });
}

fn calculate_sleep_until_02_utc() -> Duration {
    use chrono::{Local, Timelike};

    let now = Local::now();
    let target = now
        .with_hour(2)
        .unwrap()
        .with_minute(0)
        .unwrap()
        .with_second(0)
        .unwrap();

    let duration = if now < target {
        target - now
    } else {
        (target + chrono::Duration::days(1)) - now
    };

    duration.to_std().unwrap_or(Duration::from_secs(3600))
}
