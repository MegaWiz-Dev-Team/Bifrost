//! Reinforcement Learning Feedback Collection System
//!
//! Every A2A dispatch is automatically scored on:
//! - Quality (0-1.0)
//! - Relevance (0-1.0)
//! - Latency (0-1.0)
//! - Confidence (0-1.0)
//!
//! Scores stored in mimir.agent_feedback_logs for downstream RL analysis

use serde::{Deserialize, Serialize};
use sqlx::MySqlPool;
use uuid::Uuid;

/// Feedback for a single A2A dispatch
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DispatchFeedback {
    pub dispatch_id: String,
    pub tenant_id: String,
    pub agent_id: i64,
    pub session_id: String,

    // Quality metrics (0.0-1.0)
    pub quality_score: f32,      // Overall response quality
    pub relevance_score: f32,    // How well matched to question
    pub latency_score: f32,      // Response time score
    pub confidence_score: f32,   // Model's self-confidence

    // Explicit feedback
    pub user_satisfaction: Option<bool>,
    pub follow_up_needed: Option<bool>,

    // Context
    pub feedback_domain: Option<String>,
    pub source_context: Option<String>,
}

/// Compute feedback scores from dispatch response
pub fn compute_feedback_scores(
    query: &str,
    response: &str,
    latency_ms: i32,
    model_confidence: f32,
) -> DispatchFeedback {
    // Quality score: based on response length and coherence
    let quality_score = compute_quality_score(response);

    // Relevance score: based on semantic similarity between query and response
    let relevance_score = compute_relevance_score(query, response);

    // Latency score: penalize slow responses
    // < 500ms = 1.0, > 5000ms = 0.0, linear scale
    let latency_score = if latency_ms < 500 {
        1.0
    } else if latency_ms > 5000 {
        0.0
    } else {
        1.0 - ((latency_ms - 500) as f32 / 4500.0)
    };

    // Confidence score: use model's self-confidence
    let confidence_score = model_confidence.min(1.0).max(0.0);

    DispatchFeedback {
        dispatch_id: Uuid::new_v4().to_string(),
        tenant_id: String::new(),
        agent_id: 0,
        session_id: String::new(),
        quality_score,
        relevance_score,
        latency_score,
        confidence_score,
        user_satisfaction: None,
        follow_up_needed: None,
        feedback_domain: None,
        source_context: None,
    }
}

/// Compute quality score based on response characteristics
fn compute_quality_score(response: &str) -> f32 {
    let len = response.len();

    // Empty response = 0.0
    if len == 0 {
        return 0.0;
    }

    // Too short (<50 chars) = low quality
    if len < 50 {
        return 0.3;
    }

    // Reasonable length (50-500 chars) = high quality
    if len >= 50 && len <= 500 {
        return 0.95;
    }

    // Very long (>500 chars) = good but slightly lower (verbosity penalty)
    if len > 500 && len <= 2000 {
        return 0.90;
    }

    // Extremely long (>2000 chars) = might be too verbose
    0.80
}

/// Compute relevance score via simple keyword matching
/// In production, use semantic similarity (embeddings)
fn compute_relevance_score(query: &str, response: &str) -> f32 {
    let query_words: Vec<&str> = query.split_whitespace().collect();
    let response_lower = response.to_lowercase();

    if query_words.is_empty() {
        return 0.5;
    }

    // Count how many query words appear in response
    let matches = query_words
        .iter()
        .filter(|word| response_lower.contains(&word.to_lowercase()))
        .count();

    let relevance = (matches as f32) / (query_words.len() as f32);

    // Relevance should be between 0.5-1.0 (never 0, assume some relevance)
    0.5 + (relevance * 0.5)
}

/// Log feedback to database
pub async fn log_dispatch_feedback(
    pool: &MySqlPool,
    mut feedback: DispatchFeedback,
    tenant_id: &str,
    agent_id: i64,
    session_id: &str,
) -> Result<(), sqlx::Error> {
    feedback.tenant_id = tenant_id.to_string();
    feedback.agent_id = agent_id;
    feedback.session_id = session_id.to_string();

    // Insert feedback into database
    sqlx::query(
        r#"
        INSERT INTO agent_feedback_logs (
            tenant_id, agent_id, session_id, dispatch_id,
            quality_score, relevance_score, latency_score, confidence_score,
            user_satisfaction, follow_up_needed,
            feedback_domain, source_context, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        "#,
    )
    .bind(feedback.tenant_id)
    .bind(feedback.agent_id)
    .bind(feedback.session_id)
    .bind(feedback.dispatch_id)
    .bind(feedback.quality_score)
    .bind(feedback.relevance_score)
    .bind(feedback.latency_score)
    .bind(feedback.confidence_score)
    .bind(feedback.user_satisfaction)
    .bind(feedback.follow_up_needed)
    .bind(feedback.feedback_domain)
    .bind(feedback.source_context)
    .execute(pool)
    .await?;

    tracing::info!(
        "Feedback logged: agent={}, quality={:.2}, relevance={:.2}, latency={:.2}",
        feedback.agent_id,
        feedback.quality_score,
        feedback.relevance_score,
        feedback.latency_score
    );

    Ok(())
}

/// Compute daily metrics for an agent
pub async fn compute_daily_metrics(
    pool: &MySqlPool,
    tenant_id: &str,
    agent_id: i64,
) -> Result<(), sqlx::Error> {
    // Aggregate last 24h feedback
    let metrics = sqlx::query!(
        r#"
        SELECT
            COUNT(*) as conversation_count,
            AVG(quality_score) as avg_quality,
            AVG(CAST(latency_score AS DECIMAL(3,2))) as avg_latency_score,
            MIN(quality_score) as min_quality,
            COUNT(DISTINCT feedback_domain) as domain_count
        FROM agent_feedback_logs
        WHERE agent_id = ?
          AND tenant_id = ?
          AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        "#,
        agent_id,
        tenant_id
    )
    .fetch_one(pool)
    .await?;

    // Find weakest domain
    let weak_domain = sqlx::query!(
        r#"
        SELECT
            feedback_domain,
            AVG(quality_score) as avg_quality
        FROM agent_feedback_logs
        WHERE agent_id = ?
          AND tenant_id = ?
          AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
          AND feedback_domain IS NOT NULL
        GROUP BY feedback_domain
        ORDER BY avg_quality ASC
        LIMIT 1
        "#,
        agent_id,
        tenant_id
    )
    .fetch_optional(pool)
    .await?;

    // Calculate improvement opportunity score
    // Higher variance in quality = more opportunity to improve
    let improvement_opp = sqlx::query!(
        r#"
        SELECT
            AVG(quality_score) as avg_quality,
            STDDEV_POP(quality_score) as quality_stddev
        FROM agent_feedback_logs
        WHERE agent_id = ?
          AND tenant_id = ?
          AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        "#,
        agent_id,
        tenant_id
    )
    .fetch_one(pool)
    .await?;

    // Improvement opportunity = 1.0 - (avg_quality / 1.0) + stddev (domains vary)
    let avg_qual = improvement_opp.avg_quality.unwrap_or(0.5) as f32;
    let stddev = improvement_opp.quality_stddev.unwrap_or(0.0) as f32;
    let improvement_score = (1.0 - avg_qual) + (stddev * 0.5);

    // Upsert daily metrics
    sqlx::query(
        r#"
        INSERT INTO agent_rl_daily_metrics (
            tenant_id, agent_id, metric_date,
            conversation_count, avg_quality_score, avg_latency_ms,
            lowest_quality_domain, lowest_quality_score,
            improvement_opportunity_score, created_at
        ) VALUES (?, ?, CURDATE(), ?, ?, 0, ?, ?, ?, NOW())
        ON DUPLICATE KEY UPDATE
            conversation_count = VALUES(conversation_count),
            avg_quality_score = VALUES(avg_quality_score),
            lowest_quality_domain = VALUES(lowest_quality_domain),
            lowest_quality_score = VALUES(lowest_quality_score),
            improvement_opportunity_score = VALUES(improvement_opportunity_score)
        "#,
    )
    .bind(tenant_id)
    .bind(agent_id)
    .bind(metrics.conversation_count)
    .bind(avg_qual)
    .bind(weak_domain.as_ref().map(|w| w.feedback_domain.as_ref()))
    .bind(weak_domain.as_ref().map(|w| w.avg_quality))
    .bind(improvement_score)
    .execute(pool)
    .await?;

    tracing::info!(
        "Daily metrics computed: agent={}, conversations={}, avg_quality={:.2}, improvement_score={:.2}",
        agent_id,
        metrics.conversation_count.unwrap_or(0),
        avg_qual,
        improvement_score
    );

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quality_score_empty() {
        assert_eq!(compute_quality_score(""), 0.0);
    }

    #[test]
    fn test_quality_score_short() {
        assert_eq!(compute_quality_score("hi"), 0.3);
    }

    #[test]
    fn test_quality_score_good() {
        let response = "This is a comprehensive response that provides good information.";
        assert!(compute_quality_score(response) > 0.9);
    }

    #[test]
    fn test_relevance_score() {
        let query = "What is SRE?";
        let response = "SRE stands for Site Reliability Engineering";
        let score = compute_relevance_score(query, response);
        assert!(score > 0.7);
    }

    #[test]
    fn test_latency_score() {
        assert_eq!(compute_feedback_scores("test", "test", 100, 0.8).latency_score, 1.0);
        assert_eq!(compute_feedback_scores("test", "test", 5000, 0.8).latency_score, 0.0);
        assert!(compute_feedback_scores("test", "test", 1000, 0.8).latency_score > 0.8);
    }
}
