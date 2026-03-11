# PM-01: Project Plan (แผนโครงการ)
**Project Name:** Bifrost — Agent Runtime Engine
**Document Version:** 1.0
**Date:** 2026-03-11
**Standard:** ISO/IEC 29110 — PM Process

---

## 1. Project Scope & Objectives (ขอบเขตและวัตถุประสงค์)

### เป้าหมาย
พัฒนา Agent Runtime Engine สำหรับ Asgard AI Platform ที่สามารถรัน AI Agents ด้วย ReAct loop, tool calling ผ่าน MCP, และ multi-agent collaboration โดยเชื่อมต่อกับ Heimdall (LLM Gateway) และ Mimir (RAG + Agent Builder)

### ขอบเขต
| Feature | Description |
|:--|:--|
| Agent Executor | ReAct loop (think → tool_call → observe → loop) |
| Tool Registry | MCP-based tool system + built-in tools |
| Session Manager | Short/long-term memory (SQLite) |
| Heimdall Client | OpenAI-compatible LLM inference via Gateway |
| Agent Router | Multi-agent delegation and handoff |
| REST API | FastAPI endpoints with SSE streaming |
| PSO Optimizer | Auto-generate agent configs (Phase 4) |

### Tech Stack
| Layer | Technology |
|:--|:--|
| Runtime | Python 3.11+ |
| Framework | FastAPI + Uvicorn |
| Database | SQLite (aiosqlite) |
| LLM Client | httpx (async) → Heimdall |
| MCP Client | mcp SDK |
| Serialization | Pydantic v2 |

---

## 2. Project Organization & Resources (โครงสร้างทีมและทรัพยากร)

| Role | Person/Team | Responsibility |
|:--|:--|:--|
| **Founder / CTO** | Paripol (MegaWiz) | Architecture, strategy |
| **Developer** | AI-assisted (Antigravity) | Code, testing, documentation |

---

## 3. Project Schedule & Milestones (ตารางเวลาและจุดส่งมอบ)

### Sprint 1: Foundation & Tools (Mar 11, 2026) — ✅ COMPLETED
| Deliverable | Status |
|:--|:--|
| Project scaffolding (pyproject.toml, Dockerfile, .env) | ✅ Done |
| Config module (Pydantic Settings) | ✅ Done |
| Database layer (SQLite + aiosqlite) | ✅ Done |
| Heimdall client (httpx async) | ✅ Done |
| Tool system (base + registry + 3 built-in tools) | ✅ Done |
| Agent Executor (ReAct loop) | ✅ Done |
| Session Manager | ✅ Done |
| API routes + FastAPI entry point | ✅ Done |
| Unit & integration tests (TDD) | ✅ Done (27 tests) |

### Sprint 2: MCP & Mimir Integration (Mar 11, 2026) — ✅ COMPLETED
| Deliverable | Status |
|:--|:--|
| MCP client (stdio + SSE transport) | ✅ Done |
| MCP tool discovery + execution | ✅ Done |
| Mimir RAG tools (search, sources, documents) | ✅ Done |
| Agent config sync from Mimir API | ✅ Done |
| Webhook tools (custom HTTP tools) | ✅ Done |
| Tests (TDD) | ✅ Done (52 total, 25 new) |

### Sprint 3: Multi-Agent & Routing (Mar 11, 2026) — ✅ COMPLETED
| Deliverable | Status |
|:--|:--|
| Agent Router (regex + priority routing) | ✅ Done |
| Delegate tool (agent-to-agent) | ✅ Done |
| Execution tracing (SQLite + API) | ✅ Done |
| A2A protocol (Agent Card + Tasks) | ✅ Done |
| Tests (TDD) | ✅ Done (77 total, 25 new) |

### Sprint 4: Self-Optimization (Mar 11, 2026) — ✅ COMPLETED
| Deliverable | Status |
|:--|:--|
| Plan-and-Execute strategy | ✅ Done |
| Self-Reflection loop | ✅ Done |
| PSO Agent Auto-Generate | ✅ Done |
| Tests (TDD) | ✅ Done (99 total, 22 new) |

---

## 4. Risk Management (การจัดการความเสี่ยง)

| Risk | Impact | Mitigation |
|:--|:--|:--|
| **Heimdall unavailable** | High | Graceful degradation, health check retry |
| **LLM generates invalid tool calls** | Medium | JSON schema validation, error recovery, max retries |
| **Infinite ReAct loop** | High | max_iterations (10) + max_execution_time (120s) guards |
| **Memory leak in long sessions** | Medium | Session TTL, auto-cleanup, connection pooling |
| **SQLite concurrency** | Medium | WAL mode, connection pool, async locks |
| **Tool execution timeout** | Medium | Per-tool timeout (30s), graceful abort |

---

## 5. Quality Assurance (การประกันคุณภาพ)

### Methodology
- **TDD** (Test-Driven Development) — เขียน test ก่อน code
- **Agile Scrum** — 2-week sprints
- **ISO 29110** — PM + SI processes

### Test Strategy
| Level | Tool | Coverage Target |
|:--|:--|:--|
| Unit Tests | pytest + pytest-asyncio | ≥ 80% |
| Integration Tests | FastAPI TestClient | All API endpoints |
| E2E Tests | curl + Heimdall | Happy path + error cases |

---

*บันทึกโดย: AI Assistant (ตามมาตรฐาน ISO/IEC 29110 หมวด PM-01)*
