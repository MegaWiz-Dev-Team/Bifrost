# Release Notes — Bifrost

## v0.8.0 — MCP Orchestrator Upgrade (2026-03-19)

### ✨ New Features
- **MCP-ADK Adapter** (`bifrost/core/mcp_adapter.py`) — dynamic bridge that converts MCP JSON-RPC tool schemas into ADK-callable async functions at startup
- **Auto-discovery** — connects to Mimir MCP SSE endpoint, discovers tools via `tools/list`, no hardcoded tool definitions
- **Dynamic X-Tenant-ID** — per-request tenant isolation extracted from ADK `tool_context.state`, preventing cross-tenant data leakage
- New config: `MIMIR_MCP_URL` (default: `http://localhost:3000/mcp/sse`)

### 🗑️ Removed
- **Legacy `bifrost/tools/mimir.py`** (171 lines) — `SearchKnowledgeTool`, `ListSourcesTool`, `GetDocumentTool` class-based tools replaced by dynamic MCP discovery

### 📊 Stats
- **18 new TDD tests** (Red→Green), **216 total passing** (0.63s)
- Sprint 32 complete — Closes #4, #5, #6, #7
- ISO 29110 PM-02-32

## v0.7.0 — Mimir Agent Sync (2026-03-15)

### ✨ New Features
- **`MimirSyncClient`** — periodic agent config sync from Mimir API
- One-shot `sync_once()` and background `start_periodic()` modes
- Status tracking for health checks (`/api/messages/status` pattern)
- `create_sync_client()` factory from settings
- New config: `MIMIR_SYNC_ENABLED`, `MIMIR_SYNC_INTERVAL`

### 📊 Stats
- **133 tests**, all passing (0.32s)
- Sprint 7 complete (ISO 29110 PM-02-07)

---

## v0.6.0 — JWT Auth + E2E Integration (2026-03-15)

### 🔒 Security
- **JWT Auth Middleware** via Yggdrasil — Yggdrasil-issued token validation
- Public paths excluded: `/healthz`, `/readyz`, `/docs`, `/.well-known/agent.json`, `/a2a/*`
- `AUTH_ENABLED=false` dev bypass (reads settings at request time)
- Depends on: `yggdrasil>=0.1.0`, `PyJWT>=2.0`

### 🔗 E2E Integration
- **Eir Gateway tools** — 3 HTTP tools (patient_search, fhir_query, clinical_summary)
- **Fenrir MCP connection** — SSE transport, auto-discovery, graceful fallback
- Total tool registry: **9 tools** (3 built-in + 3 Mimir + 3 Eir)

### 📊 Stats
- **127 tests**, all passing (0.27s)
- Sprint 6 complete (ISO 29110 PM-02-06)

---

## v0.5.0 — Docker & Compose (2026-03-13)

### 🐳 Infrastructure
- Dockerfile rewritten: single-stage build, hatchling compatibility
- Healthcheck endpoint fixed: `/health` → `/healthz`
- `.dockerignore` added (includes README.md for hatchling)
- Integrated into Asgard unified Docker Compose (:8100)

### 📊 Stats
- **99 tests**, all passing
- Sprint 5 complete

---

## v0.4.0 — Self-Optimization (2026-03-11)

> Asgard เป็นของทุกคนแล้ว — Asgard belongs to everyone.

### ✨ New Features
- **Plan-and-Execute** strategy — multi-step planning before execution
- **Self-Reflection** loop — agent reviews own output quality
- **PSO Agent Auto-Generate** — Particle Swarm Optimization for agent config tuning

### 📊 Stats
- **99 tests**, all passing
- Sprint 4 complete

---

## v0.3.0 — Multi-Agent & Routing (2026-03-11)

### ✨ New Features
- Agent Router (regex + priority-based routing)
- Delegate tool (agent-to-agent handoff)
- Execution tracing (SQLite + API)
- A2A protocol (Agent Card + Tasks)

### 📊 Stats
- **77 tests** (+25 new)

---

## v0.2.0 — MCP & Mimir Integration (2026-03-11)

### ✨ New Features
- MCP client (stdio + SSE transport)
- MCP tool discovery + execution
- Mimir RAG tools (search, sources, documents)
- Agent config sync from Mimir API
- Webhook tools (custom HTTP tools)

### 📊 Stats
- **52 tests** (+25 new)

---

## v0.1.0 — Foundation (2026-03-11)

### ✨ New Features
- FastAPI + Uvicorn entry point
- Pydantic Settings config
- SQLite database layer (aiosqlite)
- Heimdall LLM client (httpx async)
- Tool system (base + registry + 3 built-in tools)
- Agent Executor (ReAct loop with max_iterations guard)
- Session Manager
- API routes

### 📊 Stats
- **27 tests**
