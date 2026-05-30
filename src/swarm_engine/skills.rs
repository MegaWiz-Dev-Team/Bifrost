use mimir_core_ai::services::db::DbPool;
use mimir_core_ai::services::llm_router::LlmRouter;
use mimir_core_ai::services::qdrant::QdrantService;
use rig::tool::Tool;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::retrieval::{
    graph::SqlGraphRetriever,
    qdrant::{QdrantRetriever, VectorRetriever},
    tree::{NativeTreeRetriever, TreeRetriever},
};

#[derive(Deserialize, Serialize)]
pub struct ExtractorArgs {
    pub query: String,
    pub tenant_id: String,
}

// -----------------------------------------------------------------------------
// 1. Vector Search Tool
// -----------------------------------------------------------------------------
pub struct VectorSearchTool {
    #[allow(dead_code)]
    db_pool: DbPool,
    qdrant: Arc<QdrantService>,
    #[allow(dead_code)]
    router: Arc<LlmRouter>,
    embedding_model: String,
    collections: Vec<String>,
    limit: usize,
    alpha: f64,
    patient_source_ids: Option<Vec<i64>>,
}

impl VectorSearchTool {
    pub fn new(
        db_pool: DbPool,
        qdrant: Arc<QdrantService>,
        router: Arc<LlmRouter>,
        embedding_model: String,
        collections: Vec<String>,
        limit: usize,
        alpha: f64,
        patient_source_ids: Option<Vec<i64>>,
    ) -> Self {
        Self {
            db_pool,
            qdrant,
            router,
            embedding_model,
            collections,
            limit,
            alpha,
            patient_source_ids,
        }
    }
}

impl Tool for VectorSearchTool {
    const NAME: &'static str = "vector_search";
    type Error = std::io::Error;
    type Args = ExtractorArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> rig::completion::ToolDefinition {
        rig::completion::ToolDefinition {
            name: Self::NAME.to_string(),
            description: "Search the dense and sparse embeddings vector database. Excellent for finding broad, semantic knowledge or matching general concepts. Use this as your primary search tool.".to_string(),
            parameters: serde_json::json!({
                "type": "object",
                "properties": {
                    "tenant_id": { "type": "string" },
                    "query": { "type": "string" }
                },
                "required": ["tenant_id", "query"]
            })
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let _db_pool = self.db_pool.clone();
        let qdrant = self.qdrant.clone();
        let embedding_model = self.embedding_model.clone();
        let collections = self.collections.clone();
        let tenant_id = args.tenant_id.clone();
        let query = args.query.clone();

        let mut all_results = Vec::new();
        let mut handles = Vec::new();

        let limit = self.limit;
        let alpha = self.alpha;
        let patient_source_ids = self.patient_source_ids.clone();

        for collection in collections {
            let qdrant_clone = qdrant.clone();
            let embed_clone = embedding_model.clone();
            let tenant_clone = tenant_id.clone();
            let query_clone = query.clone();
            let source_ids = patient_source_ids.clone();

            let handle = tokio::spawn(async move {
                let retriever = QdrantRetriever::new(
                    (*qdrant_clone).clone(),
                    embed_clone,
                    collection,
                );
                retriever.search_filtered(&query_clone, &tenant_clone, limit, source_ids.as_deref(), alpha).await
            });
            handles.push(handle);
        }

        for handle in handles {
            if let Ok(Ok(results)) = handle.await {
                all_results.extend(results);
            }
        }

        all_results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
        // Truncate based on total requested limit across all collections
        all_results.truncate(limit);

        let mut output = String::new();
        for res in all_results {
            output.push_str(&format!("- [{}] {}\n", res.title, res.content));
        }
        
        if output.is_empty() {
            Ok("No semantic vector results found.".to_string())
        } else {
            Ok(output)
        }
    }
}

// -----------------------------------------------------------------------------
// 2. Graph Search Tool
// -----------------------------------------------------------------------------
pub struct GraphSearchTool {
    db_pool: DbPool,
}

impl GraphSearchTool {
    pub fn new(db_pool: DbPool) -> Self {
        Self {
            db_pool,
        }
    }
}

impl Tool for GraphSearchTool {
    const NAME: &'static str = "graph_search";
    type Error = std::io::Error;
    type Args = ExtractorArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> rig::completion::ToolDefinition {
        rig::completion::ToolDefinition {
            name: Self::NAME.to_string(),
            description: "Search the knowledge graph database for interconnected entities and relationships. Use this when the query asks about how multiple things relate to each other, or complex entity maps.".to_string(),
            parameters: serde_json::json!({
                "type": "object",
                "properties": {
                    "tenant_id": { "type": "string" },
                    "query": { "type": "string" }
                },
                "required": ["tenant_id", "query"]
            })
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let db_pool = self.db_pool.clone();
        let tenant_id = args.tenant_id.clone();
        let query = args.query.clone();

        let results = tokio::spawn(async move {
            let retriever = SqlGraphRetriever::new(db_pool);
            crate::retrieval::graph::GraphRetriever::search(&retriever, &query, &tenant_id, 3).await
        })
        .await
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?
        .map_err(|e: String| std::io::Error::new(std::io::ErrorKind::Other, e))?;

        let retrieval_results = crate::retrieval::graph::graph_to_retrieval_results(&results);

        let mut output = String::new();
        for res in retrieval_results {
            output.push_str(&format!("- [{}] {}\n", res.title, res.content));
        }

        if output.is_empty() {
            Ok("No graph relational results found.".to_string())
        } else {
            Ok(output)
        }
    }
}

// -----------------------------------------------------------------------------
// 3. Tree Search Tool
// -----------------------------------------------------------------------------
pub struct TreeSearchTool {
    db_pool: DbPool,
    router: Arc<LlmRouter>,
}

impl TreeSearchTool {
    pub fn new(db_pool: DbPool, router: Arc<LlmRouter>) -> Self {
        Self { db_pool, router }
    }
}

impl Tool for TreeSearchTool {
    const NAME: &'static str = "tree_search";
    type Error = std::io::Error;
    type Args = ExtractorArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> rig::completion::ToolDefinition {
        rig::completion::ToolDefinition {
            name: Self::NAME.to_string(),
            description: "Search the hierarchical tree index. Use this tool when the query requires extracting information from highly structured documents with parent-child heading relationships.".to_string(),
            parameters: serde_json::json!({
                "type": "object",
                "properties": {
                    "tenant_id": { "type": "string" },
                    "query": { "type": "string" }
                },
                "required": ["tenant_id", "query"]
            })
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        let db_pool = self.db_pool.clone();
        let router = self.router.clone();
        let tenant_id = args.tenant_id.clone();
        let query = args.query.clone();

        let results = tokio::spawn(async move {
            let retriever = NativeTreeRetriever::new();

            // Load data sources with tree indexes
            let docs: Vec<(i64, String, Option<String>, Option<String>)> = sqlx::query_as(
                "SELECT id, name, CAST(raw_markdown AS CHAR), CAST(pageindex_tree AS CHAR) \
                 FROM data_sources WHERE tenant_id = ?",
            )
            .bind(&tenant_id)
            .fetch_all(&db_pool)
            .await
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))?;

            let mut tree_docs = Vec::new();
            for (_, title, content_opt, tree_opt) in docs {
                if let (Some(content), Some(tree)) = (content_opt, tree_opt) {
                    tree_docs.push((title, content, tree));
                }
            }

            let res = retriever
                .search_parallel(&router, &tree_docs, &query)
                .await;
            Ok::<Vec<crate::retrieval::tree::TreeSearchResult>, std::io::Error>(res)
        })
        .await
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?
        .map_err(|e: std::io::Error| e)?;

        let mut output = String::new();
        // Convert to text response
        for res in results {
            output.push_str(&format!(
                "- [{}]\nMatched section: {}\nRelevant context: {}\n---\n",
                res.document_title, res.relevant_sections.join(" > "), res.answer.unwrap_or_default()
            ));
        }

        if output.is_empty() {
            Ok("No structured tree results found.".to_string())
        } else {
            Ok(output)
        }
    }
}

// -----------------------------------------------------------------------------
// 4. OCR Extract Tool (Sprint 51 — wires agent_configs.tools allowlist to Syn)
// -----------------------------------------------------------------------------
//
// Surfaces Syn's `/api/v1/syn/ocr/extract-json` through Hermodr's MCP
// JSON-RPC. Calling path:
//
//   Agent (Bifrost) → OcrExtractTool::call → POST hermodr-syn /rpc
//   → hermodr-syn (UPSTREAM=syn-api) → syn-api /extract-json
//   → smart-router → engine (PaddleOCR / Typhoon / Gemini Flash / Pro)
//
// All policy enforcement (phi_strict, cloud-tier opt-in, budget) lives
// downstream in syn-api; this tool is pure transport. Audit row gets
// written by syn-api into `ocr_documents`.
//
// Activation: agent_configs.tools JSON array contains "ocr_extract".
// Sprint 50 B-50g seeded this for eir, eir-cardio, eir-sleep, eir-ent,
// eir-pediatrics via sprint50_eir_ocr_allowlist.sql.
//
// Sibling to the transparent OCR path in `ocr_preprocess.rs`. That path
// auto-runs on any image-bearing chat without the agent ever seeing the
// tool. This tool is for the explicit case — when the agent reasons
// about a document and decides on its own that it needs OCR.

#[derive(Deserialize, Serialize)]
pub struct OcrExtractArgs {
    pub image_base64: String,
    #[serde(default)]
    pub filename: Option<String>,
    #[serde(default)]
    pub doc_type: Option<String>,
    #[serde(default)]
    pub hint_lang: Option<String>,
    #[serde(default)]
    pub high_stakes: Option<bool>,
    #[serde(default)]
    pub engine: Option<String>,
}

pub struct OcrExtractTool {
    hermodr_url: String,
    tenant_id: String,
    client: reqwest::Client,
}

impl OcrExtractTool {
    pub fn new(hermodr_url: String, tenant_id: String) -> Self {
        Self {
            hermodr_url,
            tenant_id,
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(60))
                .build()
                .expect("reqwest client build"),
        }
    }
}

impl Tool for OcrExtractTool {
    const NAME: &'static str = "ocr_extract";
    type Error = std::io::Error;
    type Args = OcrExtractArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> rig::completion::ToolDefinition {
        rig::completion::ToolDefinition {
            name: Self::NAME.to_string(),
            description:
                "Extract text from a medical document image using Syn's hybrid OCR. \
                 The smart router picks PaddleOCR / Typhoon-OCR-local locally, or \
                 Gemini Flash/Pro on tenants with cloud tiers enabled (blocked on \
                 phi_strict). Image must be base64-encoded PNG/JPEG/PDF (≤20MB). \
                 Returns extracted_text plus audit_id."
                    .to_string(),
            parameters: serde_json::json!({
                "type": "object",
                "properties": {
                    "image_base64": {
                        "type": "string",
                        "description": "Base64-encoded image bytes (no data: URI prefix)."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Original filename — used for MIME detection.",
                        "default": "upload.png"
                    },
                    "doc_type": {
                        "type": "string",
                        "enum": ["handwriting", "printed_thai", "mixed"],
                        "description": "Optional document type hint for the smart router."
                    },
                    "hint_lang": {
                        "type": "string",
                        "description": "Language hint, e.g. 'th', 'en', 'th+en'."
                    },
                    "high_stakes": {
                        "type": "boolean",
                        "description": "Route to Gemini Pro if cloud Pro is enabled.",
                        "default": false
                    },
                    "engine": {
                        "type": "string",
                        "description": "Manual override of router (curator use only)."
                    }
                },
                "required": ["image_base64"]
            }),
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        // Build the Hermodr JSON-RPC envelope: tools/call with the
        // ocr_extract name. Hermodr forwards to syn-api /extract-json.
        let mut params = serde_json::json!({
            "name": "ocr_extract",
            "arguments": {
                "image_base64": args.image_base64,
            }
        });
        if let Some(v) = &args.filename {
            params["arguments"]["filename"] = serde_json::Value::String(v.clone());
        }
        if let Some(v) = &args.doc_type {
            params["arguments"]["doc_type"] = serde_json::Value::String(v.clone());
        }
        if let Some(v) = &args.hint_lang {
            params["arguments"]["hint_lang"] = serde_json::Value::String(v.clone());
        }
        if let Some(v) = args.high_stakes {
            params["arguments"]["high_stakes"] = serde_json::Value::Bool(v);
        }
        if let Some(v) = &args.engine {
            params["arguments"]["engine"] = serde_json::Value::String(v.clone());
        }
        let body = serde_json::json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": params,
        });

        let resp = self
            .client
            .post(&self.hermodr_url)
            .header("Content-Type", "application/json")
            .header("X-Tenant-Id", &self.tenant_id)
            .json(&body)
            .send()
            .await
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, format!("hermodr post: {e}")))?;

        let status = resp.status();
        let envelope: serde_json::Value = resp.json().await.map_err(|e| {
            std::io::Error::new(std::io::ErrorKind::InvalidData, format!("hermodr json: {e}"))
        })?;
        if !status.is_success() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("hermodr {}: {}", status, envelope),
            ));
        }
        if let Some(err) = envelope.get("error") {
            return Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("hermodr rpc error: {err}"),
            ));
        }
        // Hermodr wraps the upstream JSON as {result:{content:[{type:"text",text:"<json>"}]}}.
        // Unwrap one level so the agent sees the syn-api payload directly.
        let inner_text = envelope
            .pointer("/result/content/0/text")
            .and_then(|v| v.as_str());
        match inner_text {
            Some(s) => Ok(s.to_string()),
            None => Ok(envelope.to_string()),
        }
    }
}

// ─────────────────────────── HermodrKbTool ────────────────────────────────
// Generic medical knowledge-base tool. Calls a query-based Hermodr MCP tool
// (served by hermodr-mimir → Mimir Neo4j/Qdrant/mariadb masters) and returns
// its text payload. One struct covers R2 (code/text resolvers) + R3 (PrimeKG
// graph) because every such tool takes a single `query` argument and Hermodr
// wraps the reply the same way. Heimdall agents (bypass_tools) call this in
// the manual-context path; the result is injected before generation.
//
//   PrimeKG (R3, Neo4j-backed):  search_primekg, primekg_disease_relations
//   Resolvers (R2):              search_clinical_kb, snomed_search, ...
pub struct HermodrKbTool {
    hermodr_url: String,
    tenant_id: String,
    tool_name: String,
    client: reqwest::Client,
}

impl HermodrKbTool {
    pub fn new(hermodr_url: String, tenant_id: String, tool_name: String) -> Self {
        Self {
            hermodr_url,
            tenant_id,
            tool_name,
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(45))
                .build()
                .expect("reqwest client build"),
        }
    }

    pub async fn call(&self, args: ExtractorArgs) -> Result<String, std::io::Error> {
        let body = serde_json::json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": self.tool_name,
                "arguments": { "query": args.query }
            },
        });
        let resp = self
            .client
            .post(&self.hermodr_url)
            .header("Content-Type", "application/json")
            .header("X-Tenant-Id", &self.tenant_id)
            .json(&body)
            .send()
            .await
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, format!("hermodr-kb post: {e}")))?;
        let status = resp.status();
        let envelope: serde_json::Value = resp.json().await.map_err(|e| {
            std::io::Error::new(std::io::ErrorKind::InvalidData, format!("hermodr-kb json: {e}"))
        })?;
        if !status.is_success() || envelope.get("error").is_some() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("hermodr-kb {} err: {}", self.tool_name, envelope),
            ));
        }
        let inner = envelope
            .pointer("/result/content/0/text")
            .and_then(|v| v.as_str());
        Ok(inner.map(|s| s.to_string()).unwrap_or_else(|| envelope.to_string()))
    }
}

/// Query-based KB tools that can be auto-injected from a user query (no
/// structured args needed). Maps agent_configs.tools name → human label.
pub fn kb_tool_label(name: &str) -> Option<&'static str> {
    match name {
        "search_primekg" => Some("PrimeKG Knowledge Graph"),
        "primekg_disease_relations" => Some("PrimeKG Disease Relations"),
        "search_clinical_kb" => Some("Clinical Knowledge Base"),
        "snomed_search" | "resolve_snomed" => Some("SNOMED CT"),
        "pubmed_search" => Some("PubMed"),
        _ => None,
    }
}
