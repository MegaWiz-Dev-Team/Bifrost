use anyhow::Result;
use memvid_core::{Memvid, PutOptions, SearchRequest, SearchResponse};
use std::path::{Path, PathBuf};
use tracing::info;

pub struct MemvidManager {
    base_path: PathBuf,
}

impl MemvidManager {
    pub fn new(base_path: impl AsRef<Path>) -> Self {
        let path = base_path.as_ref().to_path_buf();
        if !path.exists() {
            std::fs::create_dir_all(&path).expect("Failed to create memvid data directory");
        }
        Self { base_path: path }
    }

    fn get_agent_path(&self, agent_id: &str, session_id: &str) -> PathBuf {
        self.base_path.join(format!("agent_{}_session_{}.mv2", agent_id, session_id))
    }

    /// Appends a new conversation frame or fact into the agent's memory
    pub fn commit_memory(&self, agent_id: &str, session_id: &str, content: &str, title: Option<&str>) -> Result<()> {
        let path = self.get_agent_path(agent_id, session_id);
        let path_str = path.to_string_lossy().to_string();
        
        let mut mem = if path.exists() {
            Memvid::open(&path_str)?
        } else {
            Memvid::create(&path_str)?
        };

        let mut opts_builder = PutOptions::builder();
        if let Some(t) = title {
            opts_builder = opts_builder.title(t);
        }
        let opts = opts_builder.build();

        mem.put_bytes_with_options(content.as_bytes(), opts)?;
        mem.commit()?;

        info!("Committed memory frame to agent {} session {} (.mv2)", agent_id, session_id);
        Ok(())
    }

    /// Searches the agent's memory for context
    pub fn search_memory(&self, agent_id: &str, session_id: &str, query: &str, top_k: usize) -> Result<SearchResponse> {
        let path = self.get_agent_path(agent_id, session_id);
        if !path.exists() {
            // Return empty response if no memory file
            return Ok(SearchResponse {
                hits: vec![],
                total_hits: 0,
                elapsed_ms: 0,
                query: String::new(),
                params: memvid_core::SearchParams {
                    top_k: 0,
                    snippet_chars: 0,
                    cursor: None,
                },
                context: String::new(),
                next_cursor: None,
                engine: memvid_core::SearchEngineKind::LexFallback,
                stale_index_skips: 0,
            });
        }
        
        let path_str = path.to_string_lossy().to_string();
        let mut mem = Memvid::open(&path_str)?;

        let response = mem.search(SearchRequest {
            query: query.into(),
            top_k,
            snippet_chars: 200,
            uri: None,
            scope: None,
            cursor: None,
            as_of_frame: None,
            as_of_ts: None,
            no_sketch: false,
            acl_context: None,
            acl_enforcement_mode: memvid_core::AclEnforcementMode::Audit,
        })?;

        Ok(response)
    }
}
