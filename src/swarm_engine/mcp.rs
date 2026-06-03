//! Per-agent MCP tool wiring — Hermodr-scoped.
//!
//! An agent's `agent_configs.mcp_servers` list is wired into execution here.
//! For safety on a medical platform, this is gated to **Hermodr** (the internal
//! MCP/JSON-RPC bridge) only — arbitrary external MCP URLs are rejected, so an
//! agent can never be pointed at an untrusted external tool server.
//!
//! Flow: resolve each `mcp_servers` entry → a trusted Hermodr `/rpc` URL
//! (`resolve_hermodr_url`), discover its tools via MCP `tools/list`
//! (`hermodr_list_tools`), and register each as a `HermodrMcpTool` (a rig `Tool`
//! whose name is set at runtime so a single type backs every discovered tool).
//! `tools/call` is proxied to Hermodr exactly like `OcrExtractTool`.

use rig::tool::Tool;
use serde_json::{json, Value};

/// Resolve an `mcp_servers` entry to a trusted Hermodr `/rpc` URL, or `None` if
/// it isn't a Hermodr target (the security gate — only `hermodr-*` allowed).
///
/// - bare name `hermodr-mimir` → env `HERMODR_MIMIR_URL` or
///   `http://hermodr-mimir.asgard.svc:8090/rpc`
/// - full URL → accepted only if its host begins with `hermodr`
/// - anything else → `None` (rejected)
pub fn resolve_hermodr_url(entry: &str) -> Option<String> {
    let e = entry.trim();
    if e.is_empty() {
        return None;
    }
    if e.starts_with("http://") || e.starts_with("https://") {
        // Full URL: require the host to be a Hermodr service.
        let after_scheme = e.split("://").nth(1).unwrap_or("");
        let host = after_scheme
            .split('/')
            .next()
            .unwrap_or("")
            .split(':')
            .next()
            .unwrap_or("");
        if host == "hermodr" || host.starts_with("hermodr-") {
            return Some(e.to_string());
        }
        return None;
    }
    // Bare service name: must be `hermodr` or `hermodr-<suffix>`.
    let is_name = e == "hermodr"
        || (e.starts_with("hermodr-")
            && e.len() > "hermodr-".len()
            && e.chars().all(|c| c.is_ascii_alphanumeric() || c == '-'));
    if !is_name {
        return None;
    }
    let env_key = format!("{}_URL", e.to_uppercase().replace('-', "_"));
    if let Ok(url) = std::env::var(&env_key) {
        if !url.trim().is_empty() {
            return Some(url);
        }
    }
    Some(format!("http://{e}.asgard.svc:8090/rpc"))
}

/// A tool discovered from a Hermodr server via `tools/list`.
#[derive(Debug, Clone)]
pub struct DiscoveredTool {
    pub name: String,
    pub description: String,
    pub schema: Value,
}

/// Call MCP `tools/list` on a Hermodr `/rpc` endpoint and return its tools.
pub async fn hermodr_list_tools(
    client: &reqwest::Client,
    hermodr_url: &str,
    tenant_id: &str,
) -> Result<Vec<DiscoveredTool>, String> {
    let body = json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}});
    let resp = client
        .post(hermodr_url)
        .header("Content-Type", "application/json")
        .header("X-Tenant-Id", tenant_id)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("hermodr tools/list post: {e}"))?;
    let envelope: Value = resp
        .json()
        .await
        .map_err(|e| format!("hermodr tools/list json: {e}"))?;
    if let Some(err) = envelope.get("error") {
        return Err(format!("hermodr tools/list rpc error: {err}"));
    }
    let tools = envelope
        .pointer("/result/tools")
        .and_then(|v| v.as_array())
        .ok_or_else(|| "hermodr tools/list: no result.tools array".to_string())?;
    Ok(tools
        .iter()
        .filter_map(|t| {
            let name = t.get("name").and_then(|v| v.as_str())?.to_string();
            let description = t
                .get("description")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let schema = t
                .get("inputSchema")
                .cloned()
                .unwrap_or_else(|| json!({"type": "object"}));
            Some(DiscoveredTool {
                name,
                description,
                schema,
            })
        })
        .collect())
}

/// A rig `Tool` backed by a Hermodr MCP tool. One type backs every discovered
/// tool — the name/description/schema are runtime values, and `name()` is
/// overridden so rig registers and dispatches by the discovered name.
pub struct HermodrMcpTool {
    hermodr_url: String,
    tenant_id: String,
    tool_name: String,
    description: String,
    schema: Value,
    client: reqwest::Client,
}

impl HermodrMcpTool {
    pub fn new(
        hermodr_url: String,
        tenant_id: String,
        tool_name: String,
        description: String,
        schema: Value,
    ) -> Self {
        Self {
            hermodr_url,
            tenant_id,
            tool_name,
            description,
            schema,
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(60))
                .build()
                .expect("reqwest client build"),
        }
    }
}

impl Tool for HermodrMcpTool {
    // Placeholder const — rig registers/dispatches via the runtime `name()`
    // override below, so multiple instances coexist under distinct names.
    const NAME: &'static str = "hermodr_mcp";
    type Error = std::io::Error;
    type Args = Value;
    type Output = String;

    fn name(&self) -> String {
        self.tool_name.clone()
    }

    async fn definition(&self, _prompt: String) -> rig::completion::ToolDefinition {
        rig::completion::ToolDefinition {
            name: self.tool_name.clone(),
            description: self.description.clone(),
            parameters: self.schema.clone(),
        }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        // Inject tenant_id into the arguments object — most Hermodr tools require
        // it and the LLM shouldn't have to supply it.
        let mut arguments = match args {
            Value::Object(m) => Value::Object(m),
            other => json!({ "input": other }),
        };
        if arguments.get("tenant_id").is_none() {
            arguments["tenant_id"] = Value::String(self.tenant_id.clone());
        }
        let body = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": { "name": self.tool_name, "arguments": arguments },
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
        let envelope: Value = resp.json().await.map_err(|e| {
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
        // Hermodr wraps upstream JSON as {result:{content:[{type:"text",text}]}}.
        let inner = envelope
            .pointer("/result/content/0/text")
            .and_then(|v| v.as_str());
        Ok(inner.map(|s| s.to_string()).unwrap_or_else(|| envelope.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bare_hermodr_name_resolves_to_svc_url() {
        // (env not set in test → default svc URL)
        let url = resolve_hermodr_url("hermodr-mimir").unwrap();
        assert_eq!(url, "http://hermodr-mimir.asgard.svc:8090/rpc");
    }

    #[test]
    fn hermodr_syn_and_eir_allowed() {
        assert!(resolve_hermodr_url("hermodr-syn").is_some());
        assert!(resolve_hermodr_url("hermodr-eir").is_some());
        assert!(resolve_hermodr_url("hermodr").is_some());
    }

    #[test]
    fn non_hermodr_name_rejected() {
        assert!(resolve_hermodr_url("evil-server").is_none());
        assert!(resolve_hermodr_url("mimir").is_none());
        assert!(resolve_hermodr_url("").is_none());
        assert!(resolve_hermodr_url("hermodr-").is_none()); // empty suffix
    }

    #[test]
    fn external_url_rejected_hermodr_url_allowed() {
        assert!(resolve_hermodr_url("http://evil.com/rpc").is_none());
        assert!(resolve_hermodr_url("https://attacker.example/mcp").is_none());
        assert_eq!(
            resolve_hermodr_url("http://hermodr-mimir.asgard.svc:8090/rpc").as_deref(),
            Some("http://hermodr-mimir.asgard.svc:8090/rpc")
        );
    }

    #[test]
    fn name_with_path_traversal_or_junk_rejected() {
        assert!(resolve_hermodr_url("hermodr-mimir/../../etc").is_none());
        assert!(resolve_hermodr_url("hermodr mimir").is_none());
    }
}
