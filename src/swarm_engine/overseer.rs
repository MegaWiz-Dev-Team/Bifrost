use anyhow::{Result, anyhow};
use mimir_core_ai::services::db::DbPool;
use mimir_core_ai::services::llm_router::LlmRouter;
use mimir_core_ai::services::qdrant::QdrantService;
use std::sync::Arc;
use rig::completion::Prompt;
use tracing::{info, instrument, Instrument};
use serde::{Deserialize, Serialize};

use serde_json::json;

use super::souls::OVERSEER_SYSTEM_PROMPT;
use super::privacy::MedicalPrivacyShield;

#[derive(Debug, sqlx::FromRow)]
struct AgentConfigRow {
    system_prompt: String,
    model_id: String,
    provider: String,
    use_rag: Option<bool>,
    use_knowledge_graph: Option<bool>,
    use_pageindex: Option<bool>,
    temperature: Option<f64>,
    rag_params: Option<serde_json::Value>,
    tools: Option<serde_json::Value>,
}
use crate::memory::memvid_manager::MemvidManager;
use crate::memory::tool::MemvidSearchTool;

#[derive(Debug, Serialize, Deserialize, Clone, schemars::JsonSchema)]
pub struct ActionApproval {
    pub action_type: String,
    pub description: String,
}

/// A single reasoning step tracked during the ReAct loop.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ReasoningStep {
    pub step_type: String,   // "reasoning" | "tool_call" | "self_correction"
    pub content: String,
    pub tool_name: Option<String>,
    pub duration_ms: u64,
}

/// Internal struct used by the LLM for structured output (what the model returns).
#[derive(Debug, Serialize, Deserialize, schemars::JsonSchema)]
struct LlmStructuredOutput {
    #[serde(default)]
    pub reasoning: String,
    pub final_answer: String,
    #[serde(default)]
    pub action_required: Option<ActionApproval>,
}

/// The full response returned to callers, enriched with telemetry.
#[derive(Serialize, Deserialize)]
pub struct SwarmResponse {
    pub reasoning: String,
    pub final_answer: String,
    pub action_required: Option<ActionApproval>,
    pub trace_id: Option<String>,
    pub steps: Vec<ReasoningStep>,
}

pub struct OverseerManager {
    db_pool: DbPool,
    qdrant: Arc<QdrantService>,
    router: Arc<LlmRouter>,
    memvid: Arc<MemvidManager>,
}

impl OverseerManager {
    pub fn new(
        db_pool: DbPool,
        qdrant: Arc<QdrantService>,
        router: Arc<LlmRouter>,
        memvid: Arc<MemvidManager>,
    ) -> Self {
        Self {
            db_pool,
            qdrant,
            router,
            memvid,
        }
    }

    /// Run the full swarm simulation and return the final synthesized answer.
    #[instrument(skip(self), fields(tenant_id = %tenant_id, agent_id = %agent_id))]
    pub async fn run_swarm(&self, tenant_id: &str, agent_id: &str, query: &str, session_id: Option<&str>) -> Result<SwarmResponse> {
        let generation_slot = self.router.config.resolve_slot("generation", None, None);
        let api_key = self.router.config.openai_api_key.clone()
            .filter(|k| !k.trim().is_empty())
            .unwrap_or_else(|| std::env::var("HEIMDALL_API_KEY").unwrap_or_default());
        let endpoint = std::env::var("HEIMDALL_URL").unwrap_or_else(|_| "http://host.docker.internal:8081/v1".to_string());
        
        let start_time = std::time::Instant::now();

        // 1. Fetch Agent Config from Database
        let agent_row: Option<AgentConfigRow> = sqlx::query_as(
            "SELECT system_prompt, model_id, provider, use_rag, use_knowledge_graph, use_pageindex, CAST(temperature AS DOUBLE) as temperature, rag_params, tools FROM agent_configs WHERE id = ? AND tenant_id = ?"
        )
        .bind(agent_id)
        .bind(tenant_id)
        .fetch_optional(&self.db_pool)
        .await?;

        // Fallback to Overseer generic values if agent not found
        let (system_prompt, model_name, provider, use_rag, use_kg, use_tree, rag_params, agent_tools) = match agent_row {
            Some(agent) => {
                // Parse tools JSON array into Vec<String>
                let tools_list: Vec<String> = agent.tools
                    .as_ref()
                    .and_then(|v| serde_json::from_value(v.clone()).ok())
                    .unwrap_or_default();

                // If tools column is populated, use it for dynamic mounting
                // Otherwise fall back to boolean flags
                let (r, k, t) = if !tools_list.is_empty() {
                    (
                        tools_list.iter().any(|t| t == "vector_search"),
                        tools_list.iter().any(|t| t == "graph_search"),
                        tools_list.iter().any(|t| t == "tree_search"),
                    )
                } else {
                    (
                        agent.use_rag.unwrap_or(false),
                        agent.use_knowledge_graph.unwrap_or(false),
                        agent.use_pageindex.unwrap_or(false),
                    )
                };

                (
                    agent.system_prompt,
                    agent.model_id,
                    agent.provider,
                    r, k, t,
                    agent.rag_params,
                    tools_list,
                )
            },
            None => {
                tracing::warn!("Agent config for id={} tenant={} not found. Falling back to default overseer settings.", agent_id, tenant_id);
                (
                    super::souls::OVERSEER_SYSTEM_PROMPT.to_string(),
                    std::env::var("DEFAULT_MODEL").unwrap_or_else(|_| generation_slot.model.clone()),
                    "heimdall".to_string(),
                    true, true, true, None, vec![]
                )
            }
        };
        // Sprint 51 — wire agent_configs.tools allowlist (set by
        // sprint50_eir_ocr_allowlist.sql for the clinical Eir variants)
        // into Bifrost's Rig tool registry. vector/graph/tree are already
        // surfaced via the booleans above; ocr_extract is the first
        // dynamic per-agent tool. New tools added here as they ship.
        let has_ocr_extract = agent_tools.iter().any(|t| t == "ocr_extract");

        let mut limit = 5_usize;
        let mut alpha = 0.7_f64;
        let mut output_format_constraint = String::from("auto");

        if let Some(params) = rag_params {
            if let Some(l) = params.get("limit").and_then(|v| v.as_u64()) {
                limit = l as usize;
            }
            if let Some(a) = params.get("alpha").and_then(|v| v.as_f64()) {
                alpha = a;
            }
            if let Some(format) = params.get("output_format").and_then(|v| v.as_str()) {
                output_format_constraint = format.to_string();
            }
        }

        // rig-core expects a Client
        let client = rig::providers::openai::Client::from_url(&api_key, &endpoint);
        
        let provider_lower = provider.to_lowercase();
        let generation_model_name = match provider_lower.as_str() {
            "gemini" => {
                let bare_model = model_name.strip_prefix("google/")
                    .or_else(|| model_name.strip_prefix("gemini/"))
                    .unwrap_or(&model_name);
                format!("gemini/{}", bare_model)
            },
            "openai" => {
                let bare_model = model_name.strip_prefix("openai/")
                    .unwrap_or(&model_name);
                format!("openai/{}", bare_model)
            },
            "openrouter" => {
                let bare_model = model_name.strip_prefix("openrouter/")
                    .unwrap_or(&model_name);
                format!("openrouter/{}", bare_model)
            },
            _ => {
                // If it's heimdall, we still need to give Heimdall's smart router the right prefix.
                // If the user typed "google/gemini...", rewrite it to "gemini/" so Heimdall routes to Google API.
                if model_name.starts_with("google/gemini") || model_name.starts_with("gemini") {
                    let bare_model = model_name.strip_prefix("google/")
                        .or_else(|| model_name.strip_prefix("gemini/"))
                        .unwrap_or(&model_name);
                    format!("gemini/{}", bare_model)
                } else if provider_lower == "heimdall" || model_name.contains('/') {
                    model_name.clone()
                } else {
                    format!("{}/{}", provider_lower, model_name)
                }
            }
        };
        
        tracing::info!(provider = %provider, model = %generation_model_name, endpoint = %endpoint, "Routing request via Heimdall gateway");

        let embedding_model = self.router.config.resolve_slot("embedding", None, None).model.clone();

        let mut builder = client
            .agent(generation_model_name.as_str());

        let final_system_prompt = match output_format_constraint.as_str() {
            "markdown_table" => format!("{}\n\nCRITICAL INSTRUCTION: You MUST format all data, lists, or comparisons as beautiful Markdown Tables. Do not use plain text lists.", system_prompt),
            "json_chart" => format!("{}\n\nCRITICAL INSTRUCTION: You MUST output ONLY a valid JSON block enclosed in ```json representing a 'line' or 'bar' chart. Use this schema: {{\"chart\": {{\"type\": \"line\", \"title\": \"...\", \"x_key\": \"...\", \"series\": [{{\"dataKey\": \"...\", \"color\": \"#...\"}}], \"data\": [...]}}}}", system_prompt),
            _ => system_prompt.to_string(), // "auto" uses default formatting
        };

        // Rig-Guard: Structured Output Preamble (uses LlmStructuredOutput, not SwarmResponse which has extra telemetry fields)
        let structural_prompt = format!(
            "{}\n\nCRITICAL SYSTEM INSTRUCTION: You are communicating with an API that ONLY accepts JSON objects. You MUST wrap your entire response inside a JSON object EXACTLY matching this schema: \n{}\n\nDO NOT output raw markdown strings directly. DO NOT regurgitate tool results. You MUST ALWAYS synthesize your answer and place it inside the `final_answer` field of the JSON object, and place your thoughts in the `reasoning` field. FAILURE TO USE A JSON OBJECT WILL CRASH THE SYSTEM.",
            final_system_prompt,
            serde_json::to_string_pretty(&schemars::schema_for!(LlmStructuredOutput)).unwrap()
        );
        
        builder = builder.preamble(&structural_prompt);

        use rig::tool::Tool;
        let bypass_tools = provider_lower == "gemini" || provider_lower == "heimdall" || model_name.contains("gemini");
        let mut manual_context = String::new();

        if use_rag {
            let vector_tool = super::skills::VectorSearchTool::new(
                self.db_pool.clone(),
                self.qdrant.clone(),
                self.router.clone(),
                embedding_model.clone(),
                vec!["golden_qa".to_string(), "source_chunks".to_string()],
                limit,
                alpha,
            );
            if bypass_tools {
                let args = crate::swarm_engine::skills::ExtractorArgs { tenant_id: tenant_id.to_string(), query: query.to_string() };
                if let Ok(res) = vector_tool.call(args).await {
                    manual_context.push_str(&format!("\n[Semantic Search Results]:\n{}\n", res));
                }
            } else {
                builder = builder.tool(vector_tool);
            }
        }

        if use_kg {
            let graph_tool = super::skills::GraphSearchTool::new(
                self.db_pool.clone(),
            );
            if bypass_tools {
                let args = crate::swarm_engine::skills::ExtractorArgs { tenant_id: tenant_id.to_string(), query: query.to_string() };
                if let Ok(res) = graph_tool.call(args).await {
                    manual_context.push_str(&format!("\n[Graph Search Results]:\n{}\n", res));
                }
            } else {
                builder = builder.tool(graph_tool);
            }
        }

        if use_tree {
            let tree_tool = super::skills::TreeSearchTool::new(
                self.db_pool.clone(),
                self.router.clone(),
            );
            if bypass_tools {
                let args = crate::swarm_engine::skills::ExtractorArgs { tenant_id: tenant_id.to_string(), query: query.to_string() };
                if let Ok(res) = tree_tool.call(args).await {
                    manual_context.push_str(&format!("\n[Tree Search Results]:\n{}\n", res));
                }
            } else {
                builder = builder.tool(tree_tool);
            }
        }

        let memvid_tool = crate::memory::tool::MemvidSearchTool::new(
            self.memvid.clone(),
            tenant_id.to_string(),
            session_id.unwrap_or("anon").to_string(),
        );

        if bypass_tools {
            let args = crate::memory::tool::MemvidSearchArgs { query: query.to_string() };
            if let Ok(res) = memvid_tool.call(args).await {
                manual_context.push_str(&format!("\n[Memory Bank context]:\n{}\n", res));
            }
        } else {
            builder = builder.tool(memvid_tool);
        }

        // Sprint 51 — mount ocr_extract when the agent's allowlist includes
        // it. Backed by hermodr-syn (Syn/deploy/k8s/hermodr-syn.yaml); not
        // pre-called here because the image arg only exists when the agent
        // reasons toward it — unlike RAG tools which run on every turn.
        // bypass_tools (gemini/heimdall path) skips tool surfacing entirely;
        // those providers get OCR through the transparent path in
        // `ocr_preprocess.rs` instead.
        if has_ocr_extract && !bypass_tools {
            let hermodr_url = std::env::var("HERMODR_SYN_URL")
                .unwrap_or_else(|_| "http://hermodr-syn.asgard.svc:8090/rpc".to_string());
            let ocr_tool = crate::swarm_engine::skills::OcrExtractTool::new(
                hermodr_url,
                tenant_id.to_string(),
            );
            builder = builder.tool(ocr_tool);
        }

        let overseer_agent = builder.build();

        // Rig-Guard: Medical Privacy Shield
        let safe_query = crate::swarm_engine::privacy::MedicalPrivacyShield::scrub(query);

        let mut history_text = String::new();
        let mut new_history = vec![];

        if let Some(sid) = session_id {
            let row: Option<(serde_json::Value,)> = sqlx::query_as(
                "SELECT state_json FROM swarm_checkpoints WHERE session_id = ? AND tenant_id = ?"
            )
            .bind(sid)
            .bind(tenant_id)
            .fetch_optional(&self.db_pool)
            .await?;

            if let Some((state_json,)) = row {
                if let Some(history) = state_json.get("history").and_then(|h| h.as_array()) {
                    for msg in history {
                        if let (Some(r), Some(c)) = (msg.get("role").and_then(|r| r.as_str()), msg.get("content").and_then(|c| c.as_str())) {
                            history_text.push_str(&format!("{}: {}\n", r, c));
                            new_history.push(msg.clone());
                        }
                    }
                }
            }
        }

        let augmented_query = if history_text.is_empty() {
            format!("Tenant ID: {}\nQuery: {}\n{}", tenant_id, safe_query, manual_context)
        } else {
            format!("Tenant ID: {}\nPrevious Context:\n{}\n\nNew Query: {}\n{}", tenant_id, history_text, safe_query, manual_context)
        };

        // Auto-correction Context Constraint Loop
        let mut final_answer = None;
        let mut current_query = augmented_query.clone();
        let mut steps: Vec<ReasoningStep> = Vec::new();

        let mut _total_input_tokens = 0_usize;
        let mut _total_output_tokens = 0_usize;
        let mut _loop_count = 0;
        let mut last_raw_response = String::new();

        info!("Starting Rig-Orchestrator Swarm with {}", generation_model_name);

        for iteration in 1..=3 {
            _loop_count += 1;
            _total_input_tokens += current_query.len() / 3;

            let step_start = std::time::Instant::now();
            let input_tokens = current_query.len() / 3;

            let reasoning_span = tracing::info_span!(
                "agent.reasoning_step",
                iteration = iteration,
                "lmnr.span.type" = "LLM",
                "lmnr.span.input" = current_query.as_str(),
                "lmnr.span.output" = tracing::field::Empty,
                "gen_ai.request.model" = generation_model_name.as_str(),
                "gen_ai.usage.input_tokens" = input_tokens,
                "gen_ai.usage.output_tokens" = tracing::field::Empty
            );

            let raw_response = overseer_agent.prompt(current_query.clone())
                .instrument(reasoning_span.clone())
                .await?;

            let output_tokens = raw_response.len() / 3;
            reasoning_span.record("gen_ai.usage.output_tokens", &output_tokens);
            reasoning_span.record("lmnr.span.output", &raw_response.as_str());

            let step_duration = step_start.elapsed().as_millis() as u64;
            _total_output_tokens += raw_response.len() / 3;
            
            tracing::debug!("Rig raw response (iteration {}, len={}): {:?}", iteration, raw_response.len(), &raw_response[..raw_response.len().min(200)]);
            
            // Handle empty responses from models that choke on tool calls
            if raw_response.trim().is_empty() {
                steps.push(ReasoningStep {
                    step_type: "self_correction".to_string(),
                    content: format!("Iteration {}: Model returned empty response — retrying with simplified prompt", iteration),
                    tool_name: None,
                    duration_ms: step_duration,
                });
                info!("Rig-Guard: Empty response on iteration {}. Model may struggle with tools + structured output.", iteration);
                
                // On iteration 2+, try a direct non-tool query via raw HTTP to bypass rig agent framework
                if iteration >= 2 {
                    tracing::info!("Rig-Guard: Attempting direct HTTP fallback to bypass agent tool framework.");
                    match direct_llm_query(&endpoint, &api_key, &generation_model_name, &structural_prompt, query).await {
                        Ok(direct_text) if !direct_text.trim().is_empty() => {
                            last_raw_response = direct_text.clone();
                            // Try to parse the direct response
                            let json_part = direct_text.trim().trim_start_matches("```json").trim_end_matches("```").trim();
                            
                            if let Ok(response) = serde_json::from_str::<LlmStructuredOutput>(json_part) {
                                steps.push(ReasoningStep {
                                    step_type: "reasoning".to_string(),
                                    content: format!("Iteration {}: Direct HTTP fallback — parsed OK", iteration),
                                    tool_name: None,
                                    duration_ms: step_start.elapsed().as_millis() as u64,
                                });
                                final_answer = Some(response);
                                break;
                            }
                            
                            if let Some(extracted) = extract_json_object(json_part) {
                                if let Ok(response) = serde_json::from_str::<LlmStructuredOutput>(&extracted) {
                                    steps.push(ReasoningStep {
                                        step_type: "reasoning".to_string(),
                                        content: format!("Iteration {}: Direct HTTP fallback — extracted JSON OK", iteration),
                                        tool_name: None,
                                        duration_ms: step_start.elapsed().as_millis() as u64,
                                    });
                                    final_answer = Some(response);
                                    break;
                                }
                            }
                            
                            if let Some(answer) = extract_final_answer_field(json_part) {
                                let reasoning = extract_reasoning_field(json_part).unwrap_or_default();
                                steps.push(ReasoningStep {
                                    step_type: "reasoning".to_string(),
                                    content: format!("Iteration {}: Direct HTTP fallback — extracted final_answer field", iteration),
                                    tool_name: None,
                                    duration_ms: step_start.elapsed().as_millis() as u64,
                                });
                                final_answer = Some(LlmStructuredOutput {
                                    reasoning,
                                    final_answer: answer,
                                    action_required: None,
                                });
                                break;
                            }
                            
                            // Use raw direct response as final answer
                            steps.push(ReasoningStep {
                                step_type: "reasoning".to_string(),
                                content: format!("Iteration {}: Direct HTTP fallback — using raw text response", iteration),
                                tool_name: None,
                                duration_ms: step_start.elapsed().as_millis() as u64,
                            });
                            final_answer = Some(LlmStructuredOutput {
                                reasoning: "Rig-Guard: Used direct HTTP fallback (model incompatible with agent tool framework).".to_string(),
                                final_answer: smart_clean_raw_response(&direct_text),
                                action_required: None,
                            });
                            break;
                        }
                        Ok(_) => {
                            tracing::warn!("Direct HTTP fallback also returned empty.");
                        }
                        Err(e) => {
                            tracing::error!("Direct HTTP fallback failed: {}", e);
                        }
                    }
                }
                
                // For self-correction retry, ask without tool requirements
                current_query = format!(
                    "You are a helpful medical assistant. Answer this question directly without using any tools.\n\nQuestion: {}\n\nRespond ONLY with a JSON object:\n{{\"reasoning\": \"your thought process\", \"final_answer\": \"your answer here\", \"action_required\": null}}",
                    query
                );
                continue;
            }

            last_raw_response = raw_response.clone();

            // Try to parse out potential JSON blocks
            let json_part = raw_response
                .trim()
                .trim_start_matches("```json")
                .trim_end_matches("```")
                .trim();

            // Strategy 1: Direct JSON parse
            if let Ok(response) = serde_json::from_str::<LlmStructuredOutput>(json_part) {
                steps.push(ReasoningStep {
                    step_type: "reasoning".to_string(),
                    content: format!("Iteration {}: Generated structured answer", iteration),
                    tool_name: None,
                    duration_ms: step_duration,
                });
                let response = if response.final_answer.trim().is_empty() && !response.reasoning.trim().is_empty() {
                    LlmStructuredOutput { reasoning: String::new(), final_answer: response.reasoning, action_required: response.action_required }
                } else { response };
                final_answer = Some(response);
                break;
            }

            // Strategy 2: Find embedded JSON object containing "final_answer"
            if let Some(extracted) = extract_json_object(json_part) {
                if let Ok(response) = serde_json::from_str::<LlmStructuredOutput>(&extracted) {
                    steps.push(ReasoningStep {
                        step_type: "reasoning".to_string(),
                        content: format!("Iteration {}: Extracted embedded JSON — parsed OK", iteration),
                        tool_name: None,
                        duration_ms: step_duration,
                    });
                    let response = if response.final_answer.trim().is_empty() && !response.reasoning.trim().is_empty() {
                        LlmStructuredOutput { reasoning: String::new(), final_answer: response.reasoning, action_required: response.action_required }
                    } else { response };
                    final_answer = Some(response);
                    break;
                }
            }

            // Strategy 3: Try to extract "final_answer" value from a partial/nested JSON
            if let Some(answer) = extract_final_answer_field(json_part) {
                let reasoning = extract_reasoning_field(json_part).unwrap_or_default();
                steps.push(ReasoningStep {
                    step_type: "reasoning".to_string(),
                    content: format!("Iteration {}: Extracted final_answer from partial JSON", iteration),
                    tool_name: None,
                    duration_ms: step_duration,
                });
                final_answer = Some(LlmStructuredOutput {
                    reasoning,
                    final_answer: answer,
                    action_required: None,
                });
                break;
            }

            // Strategy 4: Universal Catch-All Fallback
            // If all specific structural parsers failed, the model generated something completely unparseable
            // or incorrectly named fields. Do NOT retry, as it causes massive UX delays.
            if json_part.len() > 10 {
                let mut clean_text = json_part.to_string();
                
                // If the LLM quoted the entire markdown response
                if clean_text.starts_with('"') && clean_text.ends_with('"') {
                    if let Ok(serde_json::Value::String(s)) = serde_json::from_str(&clean_text) {
                        clean_text = s;
                    }
                } else if clean_text.starts_with('{') {
                    // It's a JSON block but fields might be named incorrectly or schema is wrong
                    if let Ok(serde_json::Value::Object(map)) = serde_json::from_str::<serde_json::Value>(&clean_text) {
                        let potential = map.get("answer").or(map.get("response")).or(map.get("content")).or(map.get("message"));
                        if let Some(v) = potential {
                            if let serde_json::Value::String(s) = v {
                                clean_text = s.to_string();
                            } else {
                                clean_text = serde_json::to_string_pretty(v).unwrap_or(clean_text);
                            }
                        } else {
                            // No obvious answer field found, just stringify the whole thing so user isn't blanked
                            clean_text = serde_json::to_string_pretty(&map).unwrap_or(clean_text);
                        }
                    }
                }
                
                // Fix escaped newlines if any
                clean_text = clean_text.replace("\\n", "\n").replace("\\t", "\t");
                
                steps.push(ReasoningStep {
                    step_type: "reasoning".to_string(),
                    content: format!("Iteration {}: Universal Extraction Fallback", iteration),
                    tool_name: None,
                    duration_ms: step_duration,
                });
                
                final_answer = Some(LlmStructuredOutput {
                    reasoning: "Rig-Guard: Complete structural parsing failure. Applied universal fallback.".to_string(),
                    final_answer: clean_text,
                    action_required: None,
                });
                break;
            }

            // All strategies failed for this non-empty response
            let e_msg = serde_json::from_str::<LlmStructuredOutput>(json_part).unwrap_err().to_string();
            // Truncate error for readable UI display (keep first 120 chars)
            let short_err = if e_msg.chars().count() > 120 { 
                format!("{}…", e_msg.chars().take(120).collect::<String>()) 
            } else { 
                e_msg.clone() 
            };
            steps.push(ReasoningStep {
                step_type: "self_correction".to_string(),
                content: format!("Iteration {}: JSON parse failed — {}", iteration, short_err),
                tool_name: None,
                duration_ms: step_duration,
            });
            info!("Rig-Guard: Overseer JSON Parse error on iteration {}. Error: {}", iteration, short_err);
            
            // After 2 failed attempts with non-empty garbage, go straight to Direct HTTP fallback
            if iteration >= 2 {
                tracing::info!("Rig-Guard: 2+ non-empty parse failures. Attempting direct HTTP fallback.");
                match direct_llm_query(&endpoint, &api_key, &generation_model_name, &structural_prompt, query).await {
                    Ok(direct_text) if !direct_text.trim().is_empty() => {
                        last_raw_response = direct_text.clone();
                        let dj = direct_text.trim().trim_start_matches("```json").trim_end_matches("```").trim();
                        
                        if let Ok(response) = serde_json::from_str::<LlmStructuredOutput>(dj) {
                            steps.push(ReasoningStep {
                                step_type: "reasoning".to_string(),
                                content: format!("Iteration {}: Direct HTTP fallback — parsed OK", iteration),
                                tool_name: None,
                                duration_ms: step_start.elapsed().as_millis() as u64,
                            });
                            // If final_answer is empty but reasoning has the actual answer, swap them
                            let response = if response.final_answer.trim().is_empty() && !response.reasoning.trim().is_empty() {
                                LlmStructuredOutput {
                                    reasoning: String::new(),
                                    final_answer: response.reasoning,
                                    action_required: response.action_required,
                                }
                            } else { response };
                            final_answer = Some(response);
                            break;
                        }
                        
                        if let Some(extracted) = extract_json_object(dj) {
                            if let Ok(response) = serde_json::from_str::<LlmStructuredOutput>(&extracted) {
                                steps.push(ReasoningStep {
                                    step_type: "reasoning".to_string(),
                                    content: format!("Iteration {}: Direct HTTP fallback — extracted JSON OK", iteration),
                                    tool_name: None,
                                    duration_ms: step_start.elapsed().as_millis() as u64,
                                });
                                final_answer = Some(response);
                                break;
                            }
                        }
                        
                        if let Some(answer) = extract_final_answer_field(dj) {
                            let reasoning = extract_reasoning_field(dj).unwrap_or_default();
                            steps.push(ReasoningStep {
                                step_type: "reasoning".to_string(),
                                content: format!("Iteration {}: Direct HTTP fallback — extracted answer", iteration),
                                tool_name: None,
                                duration_ms: step_start.elapsed().as_millis() as u64,
                            });
                            final_answer = Some(LlmStructuredOutput { reasoning, final_answer: answer, action_required: None });
                            break;
                        }
                        
                        // Use raw direct response as final answer
                        steps.push(ReasoningStep {
                            step_type: "reasoning".to_string(),
                            content: format!("Iteration {}: Direct HTTP fallback — using cleaned text", iteration),
                            tool_name: None,
                            duration_ms: step_start.elapsed().as_millis() as u64,
                        });
                        final_answer = Some(LlmStructuredOutput {
                            reasoning: "Rig-Guard: Used direct HTTP fallback (model incompatible with agent tool framework).".to_string(),
                            final_answer: smart_clean_raw_response(&direct_text),
                            action_required: None,
                        });
                        break;
                    }
                    Ok(_) => { tracing::warn!("Direct HTTP fallback returned empty."); }
                    Err(e) => { tracing::error!("Direct HTTP fallback failed: {}", e); }
                }
            }
            
            current_query = format!(
                "{}\n\nCRITICAL: Your previous response was NOT valid JSON. You MUST respond with ONLY a JSON object, nothing else. No markdown, no explanation, no schema definitions. Example:\n{{\"reasoning\": \"your thought process\", \"final_answer\": \"your answer here\", \"action_required\": null}}\n\nPrevious error: {}",
                augmented_query, short_err
            );
        }

        let llm_output = final_answer.unwrap_or_else(|| {
            tracing::warn!("Rig-Guard: All strategies exhausted. Applying smart fallback.");
            let cleaned = smart_clean_raw_response(&last_raw_response);
            LlmStructuredOutput {
                reasoning: "Rig-Guard: Structured parsing failed. Applied smart text extraction fallback.".to_string(),
                final_answer: if cleaned.is_empty() {
                    "ขออภัย ระบบไม่สามารถประมวลผลคำตอบได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง".to_string()
                } else {
                    cleaned
                },
                action_required: None,
            }
        });

        // Extract trace_id from current OpenTelemetry span
        let trace_id = {
            use tracing::Span;
            use tracing_opentelemetry::OpenTelemetrySpanExt;
            use opentelemetry::trace::TraceContextExt;
            let span = Span::current();
            let otel_ctx = span.context();
            let span_ref = otel_ctx.span();
            let ctx = span_ref.span_context();
            if ctx.is_valid() {
                Some(format!("{:032x}", ctx.trace_id()))
            } else {
                None
            }
        };

        // Rig-Flow: Checkpoint Upsert
        if let Some(sid) = session_id {
            new_history.push(json!({"role": "User", "content": safe_query}));
            new_history.push(json!({"role": "Assistant", "content": llm_output.final_answer}));
            let new_state_json = json!({
                "history": new_history,
                "action_pending": llm_output.action_required.is_some()
            });

            if let Err(e) = sqlx::query(
                r#"
                INSERT INTO swarm_checkpoints (session_id, tenant_id, state_json)
                VALUES (?, ?, ?)
                ON DUPLICATE KEY UPDATE 
                state_json = VALUES(state_json), updated_at = NOW()
                "#
            )
            .bind(sid)
            .bind(tenant_id)
            .bind(&new_state_json)
            .execute(&self.db_pool)
            .await 
            {
                tracing::error!("Failed to checkpoint Swarm State to database: {}", e);
            }
        }
        
        let final_latency = start_time.elapsed().as_millis() as i32;
        info!("Swarm orchestration complete in {}ms.", final_latency);

        // Commit to long-term memory via Memvid
        let frame_content = format!("User Query: {}\nAgent Response: {}", query, llm_output.final_answer);
        let title = format!("Conversation {} at {}", session_id.unwrap_or("anon"), chrono::Utc::now().to_rfc3339());
        
        if let Err(e) = self.memvid.commit_memory(tenant_id, session_id.unwrap_or("anon"), &frame_content, Some(&title)) {
            tracing::error!("Memvid failed to commit frame to deep memory: {}", e);
        }

        // Build enriched response with telemetry
        let answer = SwarmResponse {
            reasoning: llm_output.reasoning,
            final_answer: llm_output.final_answer,
            action_required: llm_output.action_required,
            trace_id,
            steps,
        };

        Ok(answer)
    }
}

/// Direct HTTP query to the LLM endpoint, bypassing rig-core's agent/tool framework entirely.
/// Used as a fallback when the model cannot handle tools + structured output simultaneously.
async fn direct_llm_query(
    endpoint: &str,
    api_key: &str,
    model: &str,
    system_prompt: &str,
    user_query: &str,
) -> Result<String> {
    let client = reqwest::Client::new();
    let url = format!("{}chat/completions", endpoint.trim_end_matches('/').to_string() + "/");
    
    // Use simplified system prompt without schema preamble (strip everything after "IMPORTANT:")
    let simple_system = system_prompt
        .find("\n\nIMPORTANT: You must return")
        .map(|pos| &system_prompt[..pos])
        .unwrap_or(system_prompt);

    let llm_span = tracing::info_span!(
        "agent.direct_llm_query",
        "lmnr.span.type" = "LLM",
        "lmnr.span.input" = user_query,
        "lmnr.span.output" = tracing::field::Empty,
        "gen_ai.request.model" = model,
        "gen_ai.usage.input_tokens" = (user_query.len() / 3) as u64,
        "gen_ai.usage.output_tokens" = tracing::field::Empty
    );
    
    let body = serde_json::json!({
        "model": model,
        "messages": [
            {"role": "system", "content": simple_system},
            {"role": "user", "content": format!(
                "{}\n\nIMPORTANT: Respond ONLY with a valid JSON object. Put your ACTUAL COMPLETE ANSWER to the user's question in \"final_answer\". Put a brief summary of your thought process in \"reasoning\". Do NOT describe what you would do — just answer the question directly.\n\nFormat:\n{{\"reasoning\": \"brief thought process\", \"final_answer\": \"YOUR ACTUAL COMPLETE ANSWER HERE — this is what the user will see\", \"action_required\": null}}",
                user_query
            )}
        ],
        "max_tokens": 2048,
        "temperature": 0.7
    });
    
    let response = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .instrument(llm_span.clone())
        .await
        .map_err(|e| anyhow!("Direct LLM HTTP error: {}", e))?;
    
    if !response.status().is_success() {
        let err_body = response.text().await.unwrap_or_default();
        return Err(anyhow!("Direct LLM error response: {}", err_body));
    }
    
    let resp_json: serde_json::Value = response.json().await
        .map_err(|e| anyhow!("Direct LLM parse error: {}", e))?;
    
    let content = resp_json["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("")
        .to_string();
    
    let output_tks: u64 = (content.len() / 3) as u64;
    llm_span.record("gen_ai.usage.output_tokens", &output_tks);
    llm_span.record("lmnr.span.output", &content.as_str());
    
    tracing::info!("Direct HTTP fallback response length: {}", content.len());
    Ok(content)
}

/// Attempt to find a balanced JSON object `{...}` containing `"final_answer"` 
/// within a larger string that may have leading/trailing noise.
fn extract_json_object(text: &str) -> Option<String> {
    // Find the first '{' that appears before "final_answer"
    let fa_pos = text.find("\"final_answer\"")?;
    
    // Walk backwards from "final_answer" to find the opening brace
    let before = &text[..fa_pos];
    let open_pos = before.rfind('{')?;
    
    // Walk forward from open_pos to find the matching closing brace
    let slice = &text[open_pos..];
    let mut depth = 0i32;
    let mut end_pos = None;
    for (i, ch) in slice.char_indices() {
        match ch {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    end_pos = Some(i + 1);
                    break;
                }
            }
            _ => {}
        }
    }
    
    let end = end_pos?;
    Some(slice[..end].to_string())
}

/// Try to extract just the `"final_answer": "..."` value from text that contains
/// valid JSON fragments but doesn't parse as a whole.
fn extract_final_answer_field(text: &str) -> Option<String> {
    let marker = "\"final_answer\"";
    let pos = text.find(marker)?;
    let after_key = &text[pos + marker.len()..];
    
    // Skip whitespace and colon
    let after_colon = after_key.trim_start().strip_prefix(':')?;
    let after_colon = after_colon.trim_start();
    
    // Check if it's a JSON string value
    if after_colon.starts_with('"') {
        // Parse the JSON string value properly (handles escapes)
        // Find the end of the string — scan for unescaped quote
        let content = &after_colon[1..];
        let mut escaped = false;
        let mut end = None;
        for (i, ch) in content.char_indices() {
            if escaped {
                escaped = false;
                continue;
            }
            if ch == '\\' {
                escaped = true;
                continue;
            }
            if ch == '"' {
                end = Some(i);
                break;
            }
        }
        let end_idx = end?;
        let value = &content[..end_idx];
        // Unescape basic JSON escapes
        let unescaped = value
            .replace("\\n", "\n")
            .replace("\\\"", "\"")
            .replace("\\\\", "\\")
            .replace("\\t", "\t");
        Some(unescaped)
    } else {
        None
    }
}

/// Try to extract the `"reasoning": "..."` value similarly.
fn extract_reasoning_field(text: &str) -> Option<String> {
    let marker = "\"reasoning\"";
    let pos = text.find(marker)?;
    let after_key = &text[pos + marker.len()..];
    let after_colon = after_key.trim_start().strip_prefix(':')?;
    let after_colon = after_colon.trim_start();
    
    if after_colon.starts_with('"') {
        let content = &after_colon[1..];
        let mut escaped = false;
        let mut end = None;
        for (i, ch) in content.char_indices() {
            if escaped { escaped = false; continue; }
            if ch == '\\' { escaped = true; continue; }
            if ch == '"' { end = Some(i); break; }
        }
        let end_idx = end?;
        let value = &content[..end_idx];
        let unescaped = value
            .replace("\\n", "\n")
            .replace("\\\"", "\"")
            .replace("\\\\", "\\")
            .replace("\\t", "\t");
        Some(unescaped)
    } else {
        None
    }
}

/// Last-resort cleanup: strip JSON schema noise, markdown fences, and extract
/// the most human-readable portion of a raw LLM response.
fn smart_clean_raw_response(raw: &str) -> String {
    let mut text = raw.to_string();
    
    // Remove leading/trailing whitespace and markdown fences
    text = text.trim().to_string();
    if text.starts_with("```") {
        if let Some(end) = text.rfind("```") {
            let start = text.find('\n').map(|i| i + 1).unwrap_or(3);
            if end > start {
                text = text[start..end].to_string();
            }
        }
    }
    
    // Strategy 1: Try to find "final_answer" value directly
    if let Some(answer) = extract_final_answer_field(&text) {
        if !answer.trim().is_empty() {
            return answer;
        }
    }
    
    // Strategy 2: Try to parse any embedded JSON object with final_answer
    if let Some(extracted) = extract_json_object(&text) {
        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&extracted) {
            if let Some(fa) = parsed.get("final_answer").and_then(|v| v.as_str()) {
                if !fa.trim().is_empty() {
                    return fa.to_string();
                }
            }
            // If final_answer is empty but reasoning has content, use reasoning
            if let Some(r) = parsed.get("reasoning").and_then(|v| v.as_str()) {
                if !r.trim().is_empty() && r.len() > 20 {
                    return r.to_string();
                }
            }
        }
    }
    
    // Strategy 3: Try extracting reasoning field as fallback content
    if let Some(reasoning) = extract_reasoning_field(&text) {
        if !reasoning.trim().is_empty() && reasoning.len() > 20 {
            return reasoning;
        }
    }
    
    // Strategy 4: If text has schema noise, strip it and look for readable content
    let noise_patterns = [
        "\"$schema\"", "\"definitions\":", "\"http://json-schema.org",
        "\"LlmStructuredOutput\"",
    ];
    let has_noise = noise_patterns.iter().any(|p| text.contains(p));
    
    if has_noise {
        // Try to find readable text blocks between the noise
        // Look for lines that are actual natural language (Thai or English sentences)
        let readable_lines: Vec<&str> = text.lines()
            .filter(|line| {
                let trimmed = line.trim();
                // Skip JSON-like lines
                if trimmed.starts_with('{') || trimmed.starts_with('}') 
                    || trimmed.starts_with('"') || trimmed.starts_with('[')
                    || trimmed.starts_with(']') || trimmed.is_empty() {
                    return false;
                }
                // Keep lines that look like natural language
                trimmed.len() > 10 && !trimmed.contains("\"type\"") && !trimmed.contains("\"required\"")
            })
            .collect();
        
        if !readable_lines.is_empty() {
            return readable_lines.join("\n");
        }
    }
    
    // Strategy 5: If text doesn't have noise, return it as-is (plain text response)
    if !has_noise && !text.is_empty() {
        return text;
    }
    
    // Absolute last resort
    String::new()
}
