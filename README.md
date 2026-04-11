# ⚡ Bifrost — Agent Runtime Engine

> *"The burning rainbow bridge that connects the realms"*
>
> Bifrost is a self-hosted Agent Runtime Engine for deploying, executing, and managing AI agents with tool-use capabilities. Part of the [🏰 Asgard AI Platform](https://github.com/MegaWiz-Dev-Team/Asgard).

| Component | Link |
|:--|:--|
| 🏰 Asgard | [Ecosystem Overview](https://github.com/MegaWiz-Dev-Team/Asgard) |
| 🧠 Mimir | [RAG + Agent Builder](https://github.com/MegaWiz-Dev-Team/Mimir) |
| 🛡️ Heimdall | [LLM Gateway](https://github.com/MegaWiz-Dev-Team/Heimdall) |
| ⚡ Bifrost | **This repo** |
| 🐺 Fenrir | [Computer Use Agent](https://github.com/MegaWiz-Dev-Team/Fenrir) |

### 🏥 Role in Multi-Agent Ecosystem

> **Orchestrator (หัวหน้าทีม)** — Bifrost รับคำถามจากแพทย์ วิเคราะห์เจตนา มอบหมายงานให้ Agent เฉพาะทาง แล้วประกอบคำตอบส่งกลับ
>
> **Guardrails:** G3 (Scope Guard, Tool Allowlist) • G5 (Citation Check, Confidence Gate, Disclaimer)
>
> 📖 [Full Architecture →](https://github.com/MegaWiz-Dev-Team/Asgard/blob/main/docs/roadmap/MultiAgent_Architecture_Plan.md) | [Sprint Plan →](https://github.com/MegaWiz-Dev-Team/Asgard/blob/main/docs/roadmap/MultiAgent_Sprint_Plan.md)

---

## Overview

### Problem

Mimir's Agent Builder lets users create agents (system prompt, model, temperature), but execution is limited to **single-turn LLM calls**. Agents cannot:

- Call external tools or APIs
- Execute multi-step reasoning (ReAct loop)
- Search the RAG knowledge base autonomously
- Maintain long-term memory across sessions
- Learn and apply specialized skills
- Delegate to other agents

### Solution

Bifrost provides a **managed runtime** that takes agent configs from Mimir and executes them as autonomous agents with full tool-use capabilities.

```
Mimir (Agent Builder) → deploys to → Bifrost (Agent Runtime) → calls → Heimdall (LLM Gateway)
                                          ↕ MCP Protocol
                                    Fenrir / mimir-mcp / custom tools
```

---

## Architecture

Bifrost is now built entirely on **Rust** and **Axum** for high concurrency and deterministic memory management, replacing the legacy Python/FastAPI architecture.

```mermaid
graph TB
    subgraph Bifrost["⚡ Bifrost Runtime (Rust/Axum)"]
        direction TB
        
        API["REST API (Port 8100)"]
        
        subgraph Engine["Rig-Core Engine"]
            Overseer["Overseer (Router Agent)"]
            Tools["Tool Registry"]
            MemoryManager["MemvidManager (Souls)"]
        end
        
        API --> Engine
        Overseer --> Tools
        Overseer --> MemoryManager
    end

    subgraph Mimir["🧠 Mimir App Layer"]
        Dashboard["Agent Studio UI"]
        Pipeline["RAG Pipeline"]
    end

    subgraph Storage["Persistent Layer"]
        Qdrant["Qdrant (Vector)"]
        Neo4j["Neo4j (Graph)"]
        Memvid["🚀 Memvid (.mv2 Files)"]
    end

    Dashboard -->|POST /v1/agents/{id}/run| API
    Tools --> Qdrant
    Tools --> Neo4j
    MemoryManager --> Memvid
```

---

## Core Operational Flow

### 1. Request Intake & Initiation
When a user interacts with an Agent via Mimir's Agent Studio, the request is proxied to Bifrost on port `8100`. Bifrost receives the input query, tenant context, and session ID.

### 2. Context Loading (The Soul)
Instead of relying on centralized MariaDB schemas for agent memory, Bifrost integrates **memvid-core**. Each agent is assigned an independent, flat-file database (`.mv2` format) inside `data/agents/`. The `MemvidManager` unlocks this file instantly, scanning for previous interactions, preferences, or factual memories specific to the session.

### 3. Execution Engine (ReAct / Swarm)
Using `rig-core`, Bifrost encapsulates the LLM interaction loop. The Overseer Agent builds a ReAct (Reason + Act) loop. If it determines a query requires external context, it will halt generation and invoke one of its registered tools:
- `VectorSearchTool`: Runs semantic + BM25 hybrid search over Qdrant.
- `GraphSearchTool`: Pulls structured entity paths from Neo4j.
- `MemvidSearchTool`: Retrieves personal agent lore from its `.mv2` capsule.

### 4. Synthesis & Response
After satisfying the query context, the LLM generates a final response natively typed through Rust's `serde` validation to guarantee conformity to the `SwarmResponse` schema. The memory layer then commits the new "Smart Frame" to disk, and the result is returned to the user instantly.

---

## Why Rust?
Bifrost migrated from Python to Rust alongside `mimir-core-ai` to unify the ecosystem. Rust provides:
- **Zero-Cost Abstractions**: Allowing high concurrency loops (thousands of agents) without the Python GIL.
- **Microsecond Memory Queries**: Integrating `memvid` directly allows sub-millisecond memory fetches.
- **Memory Safety**: Ensuring complex agent recursive behavior does not leak or OOM out Kubernetes pods.

### 8. Execution Tracing — Structured trace logs for every agent run

---

## Tech Stack

| Layer | Technology | Rationale |
|:--|:--|:--|
| **Runtime** | Rust 1.85+ | High performance, memory safety, no GIL |
| **Framework** | Axum + Tokio | Native Async, low-latency API |
| **Database** | Memvid (`.mv2`) + SQLite | Portable agent memory, ultra-fast local retrieval |
| **LLM Client** | rig-core | Leading Rust agentic orchestration framework |
| **MCP Client** | mcp SDK (Rust) | Connects to MCP tool servers |
| **Serialization** | Serde | Type safety and speed |

---

## Project Structure

```
bifrost/
├── README.md
├── Cargo.toml                  # Rust dependencies
├── .env.example
├── Dockerfile
├── src/
│   ├── main.rs                 # Axum entry point
│   ├── api/                    # Routes: agents, sessions, tools, health
│   ├── swarm_engine/           # Executor (rig-core + skills + memory injection)
│   ├── memory/                 # Memvid (.mv2) integration + SQLite
│   ├── context/                # Summarizer + compression middleware
│   └── clients/                # Heimdall + Mimir (mimir-core-ai)
├── tests/                      # Rust integration tests
└── scripts/
```

---

## API Reference

### `POST /v1/agents/{agent_id}/run` — Execute agent
### `POST /v1/agents/{agent_id}/stream` — Execute with SSE stream
### `GET /v1/sessions` — List sessions
### `GET /v1/tools` — List registered tools
### `POST /v1/tools` — Register custom tool
### `GET /healthz` — Liveness probe

---

## Quick Start

```bash
git clone https://github.com/MegaWiz-Dev-Team/Bifrost.git
cd Bifrost
cp .env.example .env
cargo build --release
cargo run --bin bifrost-rs
```

---

## Roadmap

- [x] Project structure & setup
- [x] **Phase 1**: Agent Executor, built-in tools, session management
- [x] **Phase 2**: MCP integration, guardrails, A2A protocol
- [x] **Phase 3**: Skills system, long-term memory, context engineering *(Sprint 35)*
- [ ] **Phase 4**: Multi-agent orchestration (Odin), sandbox execution *(Sprint 36)*
- [ ] **Phase 5**: K3s deployment, CI/CD, observability *(Sprint 37)*

---

<p align="center">
  <strong>⚡ Bifrost</strong> — Part of the <a href="https://github.com/MegaWiz-Dev-Team/Asgard">🏰 Asgard AI Platform</a>
</p>
