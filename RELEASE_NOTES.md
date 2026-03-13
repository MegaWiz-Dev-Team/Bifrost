# Release Notes — Bifrost

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
