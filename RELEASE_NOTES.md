# Release Notes — Bifrost

> Versioning note: 0.1.0 → 0.3.0 below tracks the **Rust rewrite** (the current production binary, `Cargo.toml`). The v0.4.0 – v0.8.0 entries further down are historical for the pre-rewrite Python codebase and are kept for archeological context only.

## v0.3.0 (Rust) — Sprint 50 Transparent OCR (2026-05-11)

> Image-bearing chat now does OCR before the agent ever sees the message. Path A (transparent) — the agent reads the extracted text inside the prompt and doesn't need to call `ocr_extract` explicitly.

### ✨ New
- **Transparent OCR preprocess** (B-50d, PR #13) — `RunAgentRequest` gains optional `image_base64` + `image_filename` + `doc_type`. When present, Bifrost POSTs to Syn's `/api/v1/syn/ocr/extract-json` before entering the swarm and prepends the extracted text in an explicit `[Attached Document — extracted via <engine> (audit_id=...)]` marker block. Backwards-compatible — text-only clients still work.
- **Policy mapping** — 402 → `{error: budget_exceeded}`, 403 → `{error: phi_strict}`, transport/engine_failed → 502 `{error: ocr_failed}`. Engine failures are **not** silently swallowed: if the user attached an image, they want OCR to work.
- **OTel span** — `preprocess_image` is `#[instrument]`-decorated; the OCR call appears as its own span under the swarm trace in Laminar (Sága), with tenant_id, audit_id, engine_used, cost_usd, latency_ms.

### ⚙️ Config
- `SYN_API_URL` — default `http://syn-api.asgard.svc:8080`.

### 🧪 Tests
- 3 unit tests pass: `format_block_includes_engine_and_audit`, `ocr_request_serializes_minimal_fields`, `ocr_request_serializes_full_fields`.

### 🗺️ Companion PRs
- Mimir #265 — Path A delegation (the receiving end of the smart-router)
- Mimir #270 — `/playground` upload UI (alternative to transparent path; gives the user an editable OCR preview before send)

## v0.2.0 (Rust) — Sprint 38 / Asgard v1.2-alpha (2026-04-22)

Initial public release of the Rust rewrite — swarm engine + RAG retrieval + memvid memory, integrated with Heimdall gateway + Mimir RAG. Bumped per Asgard umbrella to align with the 14-service Sprint 38 release.

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
