/// Batch embed texts via Heimdall /v1/embeddings (OpenAI-compatible)
pub async fn embed_texts(texts: &[String], model: &str) -> Result<Vec<Vec<f32>>, String> {
    let embed_base_url = std::env::var("EMBEDDING_API_URL")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| {
            std::env::var("HEIMDALL_API_URL")
                .ok()
                .filter(|s| !s.is_empty())
        })
        .or_else(|| {
            std::env::var("OLLAMA_URL")
                .ok()
                .filter(|s| !s.is_empty())
                .map(|u| format!("{}/v1", u))
        })
        .unwrap_or_else(|| "http://localhost:11434/v1".to_string());
    let embed_url = format!("{}/embeddings", embed_base_url.trim_end_matches('/'));
    let api_key = std::env::var("HEIMDALL_API_KEY").unwrap_or_default();
    let client = reqwest::Client::new();

    let resp = client
        .post(&embed_url)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&serde_json::json!({
            "model": model,
            "input": texts,
        }))
        .send()
        .await
        .map_err(|e| format!("Embedding HTTP error: {}", e))?;

    if !resp.status().is_success() {
        let err = resp.text().await.unwrap_or_default();
        return Err(format!("Embedding API error: {}", err));
    }

    let body: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse embedding response: {}", e))?;

    let data = body["data"]
        .as_array()
        .ok_or("No 'data' array in response")?;
    let mut vectors = Vec::with_capacity(data.len());
    for item in data {
        let vec: Vec<f32> = item["embedding"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_f64().map(|f| f as f32))
                    .collect()
            })
            .unwrap_or_default();
        vectors.push(vec);
    }
    Ok(vectors)
}
