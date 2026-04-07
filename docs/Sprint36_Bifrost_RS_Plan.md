# Bifrost-RS: Sprint 36 Planning (Rust & Memvid Integration)

> **Objective:** Transition Bifrost from a Python/FastAPI codebase to a fully native Rust/Axum architecture, utilizing `memvid-core` for persistent, serverless long-term agent memory.

## 🎯 1. Overview & Goals

1. **Unify the Tech Stack:** Bring Bifrost into the identical Rust ecosystem as `Heimdall` and Mimir's core, removing the massive overhead of managing parallel Python virtual environments.
2. **Infinite Multi-Agent Throughput:** Leverage Tokio's high-performance concurrency instead of Python's GIL to allow Bifrost to orchestrate Swarm agents flawlessly.
3. **Capsule Memory (Memvid):** Equip each active Agent with a `.mv2` file. Agents handle their own specific knowledge retrieval out of their dedicated `.mv2` files using `memvid-core`'s 0.025ms vector search capabilities.

---

## 🏃 2. Sprint Backlog & Task Breakdown

### 🟢 Epic 1: Scaffold & Server Initialization (Sprint 36 - Week 1)
*   **Task 1.1:** Setup workspace dependencies (`axum`, `tokio`, `rig-core`, `memvid-core`). *(✅ Done)*
*   **Task 1.2:** Initialize the Axum router and core middlewares (CORS, payload limits).
*   **Task 1.3:** Port the `mimir-core-ai` LLM Client & DB pooling configurations so Bifrost can speak to Heimdall right out of the box.

### 🔵 Epic 2: Memvid Cognitive Layer (Sprint 36 - Week 1/2)
*   **Task 2.1: Capsule Factory:** Write `src/memory/memvid_manager.rs` to automatically instantiate and open `data/agents/{agent_id}.mv2` when an agent session begins.
*   **Task 2.2: Memory Commit (Smart Frames):** Hook into the end of every agent cycle to commit the conversation context into the `Memvid` instance as an immutable chronological frame.
*   **Task 2.3: `MemvidSearchTool`:** Create a `rig-core` compatible Tool `#[derive(Tool)]` that an Agent can invoke natively to query its *own* past memories via Full-Text (Tantivy/Lex) and Vector search.

### 🟣 Epic 3: Swarm Engine Porting (Sprint 36 - Week 2)
*   **Task 3.1:** Migrate `overseer.rs`, `souls.rs`, and `skills.rs` from `Mimir/ro-ai-bridge` over into `Bifrost-RS/src/swarm_engine`.
*   **Task 3.2:** Refactor the Database interface. Currently, Mimir writes checkpoints to MariaDB. Bifrost will intercept these and direct long-term data straight into Memvid instead.
*   **Task 3.3:** Ensure the Overseer agent (Meta-orchestrator) can dynamically access the `MemvidSearchTool` to summarize its own historic workflow.

### 🔴 Epic 4: Mimir Integration & Testing (Sprint 36 - Week 2)
*   **Task 4.1:** Build the POST `/v1/agents/{agent_id}/run` generic runner endpoint.
*   **Task 4.2:** On Mimir's end (`ro-ai-dashboard`), repoint the Agent Studio "Execution" logic to trigger a REST API call directly to Bifrost-RS (`http://localhost:8100`).
*   **Task 4.3:** End-to-End Test: Run a 20-hop complex conversation and verify the `.mv2` file scales properly while Agent recall remains instant.

---

## 📅 3. Resource & Timeline Strategy

- **Repository:** `megacare-dev/Bifrost`
- **Dependencies:** `mimir-core-ai` (Local path resolution)
- **Review Checkpoints:** 
  1. Once `MemvidSearchTool` is fully implemented and tested.
  2. Once the Axum server successfully executes its first `rig-core` conversational ping.
