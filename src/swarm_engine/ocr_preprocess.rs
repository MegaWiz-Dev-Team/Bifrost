//! B-50d — Transparent OCR preprocessing for image-bearing chat requests.
//!
//! Flow: if a chat request includes `image_base64`, Bifrost POSTs to Syn's
//! `/api/v1/syn/ocr/extract-json` BEFORE entering the swarm. The extracted
//! text is prepended to the user's text query so the LLM sees both. The
//! agent never has to call `ocr_extract` explicitly — the document content
//! is already in context.
//!
//! Policy enforcement (cost guard, PHI strict, smart-router engine choice)
//! happens server-side in Syn/Mimir per B-50e/B-50m. Bifrost just calls and
//! surfaces errors:
//!
//!   - 402 (budget exceeded)   → OcrPreprocessError::BudgetExceeded
//!   - 403 (PHI strict block)  → OcrPreprocessError::PhiStrict
//!   - other HTTP error / OCR engine_failed → log + return error
//!
//! The caller decides how to map errors to user-visible responses. Engine
//! failures are NOT silently swallowed — if a user sent an image, they
//! probably want OCR to work; better to surface the failure than process
//! the text query as if the image didn't exist.

use serde::{Deserialize, Serialize};
use tracing::{info, instrument, warn};

#[derive(Debug, Serialize)]
struct SynOcrRequest<'a> {
    image_base64: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    filename: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    doc_type: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    hint_lang: Option<&'a str>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    high_stakes: bool,
}

#[derive(Debug, Deserialize)]
pub struct SynOcrResponse {
    pub audit_id: String,
    pub engine_used: String,
    pub status: String,
    #[serde(default)]
    pub extracted_text: Option<String>,
    #[serde(default)]
    pub confidence: Option<f64>,
    #[serde(default)]
    pub cost_usd: f64,
    #[serde(default)]
    pub latency_ms: u64,
}

#[derive(Debug)]
pub enum OcrPreprocessError {
    /// Tenant is PHI-strict — cloud OCR forbidden. Caller should bubble up
    /// to the user (the image isn't going anywhere).
    PhiStrict { detail: String },
    /// Monthly budget exceeded. Caller should surface a clear "budget cap
    /// hit" message rather than silently degrading.
    BudgetExceeded { detail: String },
    /// OCR ran but the engine failed (engine_failed status). Caller may
    /// choose to ask the user to re-upload or continue text-only.
    EngineFailed { detail: String },
    /// HTTP transport or unexpected server error.
    Transport(String),
}

impl std::fmt::Display for OcrPreprocessError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::PhiStrict { detail } => write!(f, "OCR blocked (PHI strict): {}", detail),
            Self::BudgetExceeded { detail } => write!(f, "OCR blocked (budget exceeded): {}", detail),
            Self::EngineFailed { detail } => write!(f, "OCR engine failed: {}", detail),
            Self::Transport(detail) => write!(f, "OCR transport error: {}", detail),
        }
    }
}

impl std::error::Error for OcrPreprocessError {}

/// Options forwarded as router hints to Syn. All optional; sensible defaults
/// when the caller doesn't know yet (the smart router picks the engine).
#[derive(Debug, Default, Clone)]
pub struct OcrPreprocessOpts {
    pub filename: Option<String>,
    pub doc_type: Option<String>,
    pub hint_lang: Option<String>,
    pub high_stakes: bool,
}

/// Format an extracted-text block to prepend to the user's query. The marker
/// is explicit so the LLM (and human-in-the-loop) can tell document text
/// apart from the user's typed words.
pub fn format_ocr_block(text: &str, engine_used: &str, audit_id: &str) -> String {
    format!(
        "[Attached Document — extracted via {} (audit_id={})]\n{}\n[End of document]\n\n",
        engine_used, audit_id, text.trim()
    )
}

/// Call Syn OCR for a single image. The full Bifrost telemetry span wraps
/// this call so the OCR step shows up as its own span in Laminar (Sága).
#[instrument(skip(image_base64), fields(tenant_id = %tenant_id, image_bytes = image_base64.len()))]
pub async fn preprocess_image(
    syn_base: &str,
    tenant_id: &str,
    image_base64: &str,
    opts: &OcrPreprocessOpts,
) -> Result<SynOcrResponse, OcrPreprocessError> {
    let url = format!(
        "{}/api/v1/syn/ocr/extract-json",
        syn_base.trim_end_matches('/')
    );

    let body = SynOcrRequest {
        image_base64,
        filename: opts.filename.as_deref(),
        doc_type: opts.doc_type.as_deref(),
        hint_lang: opts.hint_lang.as_deref(),
        high_stakes: opts.high_stakes,
    };

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .map_err(|e| OcrPreprocessError::Transport(e.to_string()))?;

    let resp = client
        .post(&url)
        .header("X-Tenant-Id", tenant_id)
        .json(&body)
        .send()
        .await
        .map_err(|e| OcrPreprocessError::Transport(e.to_string()))?;

    let status = resp.status();

    // Map known policy responses before deserializing — the bodies may not
    // match SynOcrResponse on 402/403 paths.
    if status.as_u16() == 402 {
        let detail = resp.text().await.unwrap_or_else(|_| "budget exceeded".into());
        warn!(tenant_id = %tenant_id, "OCR blocked: budget exceeded — {}", detail);
        return Err(OcrPreprocessError::BudgetExceeded { detail });
    }
    if status.as_u16() == 403 {
        let detail = resp.text().await.unwrap_or_else(|_| "PHI strict block".into());
        warn!(tenant_id = %tenant_id, "OCR blocked: PHI strict — {}", detail);
        return Err(OcrPreprocessError::PhiStrict { detail });
    }
    if !status.is_success() {
        let detail = resp.text().await.unwrap_or_else(|_| status.to_string());
        return Err(OcrPreprocessError::Transport(format!(
            "Syn returned {}: {}",
            status, detail
        )));
    }

    let parsed: SynOcrResponse = resp
        .json()
        .await
        .map_err(|e| OcrPreprocessError::Transport(format!("decode failed: {}", e)))?;

    if parsed.status == "engine_failed" {
        return Err(OcrPreprocessError::EngineFailed {
            detail: format!(
                "engine={} audit_id={}",
                parsed.engine_used, parsed.audit_id
            ),
        });
    }

    info!(
        audit_id = %parsed.audit_id,
        engine = %parsed.engine_used,
        cost_usd = parsed.cost_usd,
        latency_ms = parsed.latency_ms,
        "OCR preprocess complete"
    );
    Ok(parsed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_block_includes_engine_and_audit() {
        let s = format_ocr_block("Hello world", "paddleocr-local", "abc-123");
        assert!(s.contains("paddleocr-local"));
        assert!(s.contains("abc-123"));
        assert!(s.contains("Hello world"));
        assert!(s.contains("[End of document]"));
    }

    #[test]
    fn ocr_request_serializes_minimal_fields() {
        let body = SynOcrRequest {
            image_base64: "AAAA",
            filename: None,
            doc_type: None,
            hint_lang: None,
            high_stakes: false,
        };
        let j = serde_json::to_value(&body).unwrap();
        assert_eq!(j.get("image_base64").and_then(|v| v.as_str()), Some("AAAA"));
        // Optional fields should be omitted when None / default
        assert!(j.get("filename").is_none());
        assert!(j.get("doc_type").is_none());
        assert!(j.get("hint_lang").is_none());
        assert!(j.get("high_stakes").is_none());
    }

    #[test]
    fn ocr_request_serializes_full_fields() {
        let body = SynOcrRequest {
            image_base64: "AAAA",
            filename: Some("lab.png"),
            doc_type: Some("printed_thai"),
            hint_lang: Some("th"),
            high_stakes: true,
        };
        let j = serde_json::to_value(&body).unwrap();
        assert_eq!(j.get("filename").and_then(|v| v.as_str()), Some("lab.png"));
        assert_eq!(j.get("doc_type").and_then(|v| v.as_str()), Some("printed_thai"));
        assert_eq!(j.get("hint_lang").and_then(|v| v.as_str()), Some("th"));
        assert_eq!(j.get("high_stakes").and_then(|v| v.as_bool()), Some(true));
    }
}
