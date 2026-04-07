use anyhow::Result;
use rig::tool::Tool;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use crate::memory::memvid_manager::MemvidManager;
use tracing::info;

#[derive(Serialize, Deserialize, schemars::JsonSchema)]
pub struct MemvidSearchArgs {
    pub query: String,
}

pub struct MemvidSearchTool {
    manager: Arc<MemvidManager>,
    agent_id: String,
}

impl MemvidSearchTool {
    pub fn new(manager: Arc<MemvidManager>, agent_id: String) -> Self {
        Self { manager, agent_id }
    }
}

impl Tool for MemvidSearchTool {
    const NAME: &'static str = "memvid_agent_memory_search";

    type Error = std::io::Error;
    type Args = MemvidSearchArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> rig::completion::ToolDefinition {
        rig::completion::ToolDefinition {
            name: Self::NAME.to_string(),
            description: "Search your absolute long-term memory for past conversations, facts, or context you have stored using this tool. Input a search query.".to_string(),
            parameters: serde_json::to_value(&schemars::schema_for!(MemvidSearchArgs))
                .unwrap_or(serde_json::json!({})),
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        info!("Memvid tool invoked by agent {} with query: {}", self.agent_id, args.query);
        
        let resp = self.manager.search_memory(&self.agent_id, &args.query, 5)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))?;
        
        if resp.hits.is_empty() {
            return Ok("No relevant long-term memories found for this query.".to_string());
        }

        let mut output = String::from("Found the following memories:\n");
        for (i, hit) in resp.hits.iter().enumerate() {
            output.push_str(&format!("{}. [{}] {}\n", i+1, hit.title.as_deref().unwrap_or("Memory"), hit.text));
        }

        Ok(output)
    }
}
