// E2E Tests for Odin Agent Command Center
// Tests all agent interactions and chat functionality

#[cfg(test)]
mod odin_e2e_tests {
    use reqwest::Client;
    use serde_json::json;

    const ODIN_BASE_URL: &str = "https://odin.asgard.internal";
    const TENANT_ID: &str = "asgard_platform";

    struct OdinTestClient {
        client: Client,
    }

    impl OdinTestClient {
        fn new() -> Self {
            let client = Client::builder()
                .danger_accept_invalid_certs(true) // Allow self-signed certs for testing
                .build()
                .expect("Failed to create HTTP client");
            OdinTestClient { client }
        }

        async fn chat(&self, message: &str) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
            let response = self
                .client
                .post(&format!("{}/api/v1/odin/chat", ODIN_BASE_URL))
                .header("Content-Type", "application/json")
                .header("X-Tenant-Id", TENANT_ID)
                .json(&json!({ "message": message }))
                .send()
                .await?;

            let body = response.json::<serde_json::Value>().await?;
            Ok(body)
        }

        async fn list_agents(&self) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
            let response = self
                .client
                .get(&format!(
                    "{}/api/v1/rl/agent-status?tenant_id={}",
                    ODIN_BASE_URL, TENANT_ID
                ))
                .header("X-Tenant-Id", TENANT_ID)
                .send()
                .await?;

            let body = response.json::<serde_json::Value>().await?;
            Ok(body)
        }

        async fn check_health(&self) -> Result<bool, Box<dyn std::error::Error>> {
            let response = self
                .client
                .get(&format!("{}/healthz", ODIN_BASE_URL))
                .send()
                .await?;

            Ok(response.status().is_success())
        }
    }

    #[tokio::test]
    async fn test_odin_health() {
        let client = OdinTestClient::new();
        match client.check_health().await {
            Ok(healthy) => assert!(healthy, "Odin service should be healthy"),
            Err(e) => panic!("Failed to check health: {}", e),
        }
    }

    #[tokio::test]
    async fn test_list_agents() {
        let client = OdinTestClient::new();
        match client.list_agents().await {
            Ok(response) => {
                let agents = response["agents"].as_array().expect("agents should be array");
                assert!(!agents.is_empty(), "Should have agents in asgard_platform");

                // Verify agent structure
                for agent in agents {
                    assert!(agent["id"].is_number(), "Agent should have id");
                    assert!(agent["name"].is_string(), "Agent should have name");
                    assert!(agent["status"].is_string(), "Agent should have status");
                }

                println!("✓ Found {} agents in asgard_platform", agents.len());
            }
            Err(e) => panic!("Failed to list agents: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_hello() {
        let client = OdinTestClient::new();
        match client.chat("hello").await {
            Ok(response) => {
                assert!(response["reply"].is_string(), "Should have reply");
                let reply = response["reply"].as_str().unwrap();
                assert!(reply.contains("Odin"), "Odin should respond");
                println!("✓ Odin responds: {}", reply);
            }
            Err(e) => panic!("Failed to chat with Odin: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_help_command() {
        let client = OdinTestClient::new();
        match client.chat("help").await {
            Ok(response) => {
                let reply = response["reply"].as_str().expect("Should have reply");
                assert!(reply.contains("help") || reply.contains("command"), "Help should list commands");
                println!("✓ Help command: {}", reply);
            }
            Err(e) => panic!("Failed to get help: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_list_agents_command() {
        let client = OdinTestClient::new();
        match client.chat("list agents").await {
            Ok(response) => {
                assert!(response["reply"].is_string(), "Should have reply");
                assert!(response["tables"].is_array(), "Should have table data");

                let tables = response["tables"].as_array().unwrap();
                assert!(!tables.is_empty(), "Should have table with agents");

                let table = &tables[0];
                assert_eq!(table["type"].as_str().unwrap(), "table", "Should be table type");
                assert!(table["headers"].is_array(), "Should have headers");
                assert!(table["rows"].is_array(), "Should have rows");

                println!("✓ Agent list table with {} rows", table["rows"].as_array().unwrap().len());
            }
            Err(e) => panic!("Failed to list agents: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_show_agents_command() {
        let client = OdinTestClient::new();
        match client.chat("show agents").await {
            Ok(response) => {
                assert!(response["reply"].is_string(), "Should have reply");
                assert!(response["tables"].is_array(), "Should return table");
                println!("✓ Show agents command works with table display");
            }
            Err(e) => panic!("Failed show agents: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_agent_status_command() {
        let client = OdinTestClient::new();
        match client.chat("agent status").await {
            Ok(response) => {
                assert!(response["reply"].is_string(), "Should have reply");
                let reply = response["reply"].as_str().unwrap();
                assert!(reply.contains("agents"), "Should mention agents count");
                println!("✓ Agent status: {}", reply);
            }
            Err(e) => panic!("Failed to get agent status: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_laminar_report_invokes_agent() {
        let client = OdinTestClient::new();
        match client.chat("ขอรายงานจาก laminar").await {
            Ok(response) => {
                assert!(response["executed"].is_boolean(), "Should have executed flag");
                assert!(response["executed"].as_bool().unwrap(), "Should mark as executed");
                let reply = response["reply"].as_str().unwrap();
                assert!(reply.contains("summoned") || reply.contains("agents"), "Should indicate agent invocation");
                println!("✓ Laminar report invokes agent: executed={}", response["executed"]);
            }
            Err(e) => panic!("Failed laminar report: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_report_request_invokes_agent() {
        let client = OdinTestClient::new();
        match client.chat("show system report").await {
            Ok(response) => {
                assert_eq!(response["executed"].as_bool().unwrap(), true, "Should execute agent");
                println!("✓ Report request invokes agent");
            }
            Err(e) => panic!("Failed report request: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_trace_request_invokes_agent() {
        let client = OdinTestClient::new();
        match client.chat("show trace information").await {
            Ok(response) => {
                assert_eq!(response["executed"].as_bool().unwrap(), true, "Should execute agent");
                println!("✓ Trace request invokes agent");
            }
            Err(e) => panic!("Failed trace request: {}", e),
        }
    }

    #[tokio::test]
    async fn test_odin_unknown_command_graceful() {
        let client = OdinTestClient::new();
        match client.chat("unknown random command").await {
            Ok(response) => {
                assert!(response["reply"].is_string(), "Should still respond");
                let reply = response["reply"].as_str().unwrap();
                assert!(reply.contains("Odin"), "Should be from Odin");
                println!("✓ Unknown command handled gracefully");
            }
            Err(e) => panic!("Failed to handle unknown command: {}", e),
        }
    }

    #[tokio::test]
    async fn test_all_divine_agents_available() {
        let client = OdinTestClient::new();
        match client.list_agents().await {
            Ok(response) => {
                let agents = response["agents"].as_array().unwrap();

                // Expected divine agents
                let expected_agents = vec![
                    "mimir-platform",
                    "tyr-platform",
                    "syn-platform",
                    "eir-platform",
                    "yggdrasil-platform",
                    "heimdall-platform",
                    "bifrost-platform",
                    "huginn-platform",
                    "muninn-platform",
                    "odin-platform",
                ];

                for agent_name in expected_agents {
                    let found = agents.iter().any(|a| {
                        a["name"].as_str().unwrap() == agent_name
                    });
                    assert!(found, "Agent {} should be available", agent_name);
                    println!("✓ {} is available", agent_name);
                }

                println!("✓ All {} expected agents found", agents.len());
            }
            Err(e) => panic!("Failed to list agents: {}", e),
        }
    }

    #[tokio::test]
    async fn test_agent_response_structure() {
        let client = OdinTestClient::new();
        match client.chat("show agents").await {
            Ok(response) => {
                // Verify ChatResponse structure
                assert!(response.get("reply").is_some(), "Should have reply field");
                assert!(response.get("executed").is_some(), "Should have executed field");

                // Optional fields should exist if present
                if response.get("tables").is_some() {
                    assert!(response["tables"].is_array(), "tables should be array");
                }
                if response.get("charts").is_some() {
                    assert!(response["charts"].is_array(), "charts should be array");
                }
                if response.get("result").is_some() {
                    assert!(response["result"].is_string(), "result should be string");
                }

                println!("✓ Agent response structure is valid");
            }
            Err(e) => panic!("Failed response structure test: {}", e),
        }
    }

    #[tokio::test]
    async fn test_concurrent_agent_requests() {
        let client = OdinTestClient::new();

        let mut tasks = vec![];

        for i in 0..5 {
            let client = OdinTestClient::new();
            let task = tokio::spawn(async move {
                let message = format!("list agents request {}", i);
                match client.chat(&message).await {
                    Ok(v) => Ok(v),
                    Err(e) => Err(e.to_string()),
                }
            });
            tasks.push(task);
        }

        let mut success_count = 0;
        for task in tasks {
            match task.await {
                Ok(Ok(_)) => success_count += 1,
                _ => {}
            }
        }

        assert_eq!(success_count, 5, "All concurrent requests should succeed");
        println!("✓ All {} concurrent requests succeeded", success_count);
    }

    #[tokio::test]
    async fn test_thai_language_support() {
        let client = OdinTestClient::new();
        let thai_messages = vec![
            "ช่วยแสดงตัวแทนหน่อย",
            "เอาสถานะของเอเจนต์หน่อย",
            "ขอรายงานจาก laminar",
            "แสดงข้อมูลระบบ",
        ];

        for message in thai_messages {
            match client.chat(message).await {
                Ok(response) => {
                    assert!(response["reply"].is_string(), "Should respond to Thai");
                    println!("✓ Thai message handled: {}", message);
                }
                Err(e) => panic!("Failed to handle Thai: {}: {}", message, e),
            }
        }
    }
}
