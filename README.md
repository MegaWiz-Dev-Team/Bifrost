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

```
                         ┌─────────────────────────┐
                         │      Bifrost Server      │
                         │      (FastAPI/Uvicorn)    │
                         └────────────┬────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
     ┌────────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
     │  Agent Executor  │    │  Tool Registry   │    │ Session Manager │
     │                  │    │                  │    │                 │
     │ • ReAct loop     │    │ • Built-in tools │    │ • Short-term    │
     │ • Plan-Execute   │    │ • MCP tools      │    │   (conversation)│
     │ • Max iterations │    │ • Custom tools   │    │ • Long-term     │
     │ • Error recovery │    │ • JSON Schema    │    │   (memory bank) │
     └─────────────────┘    └─────────────────┘    └─────────────────┘
              │                       │
     ┌────────▼────────┐    ┌────────▼────────┐
     │  Agent Router    │    │  Event Logger    │
     │  • Multi-agent   │    │  • Execution     │
     │  • Handoff       │    │    trace         │
     └─────────────────┘    └─────────────────┘
```

---

## Core Features

### 1. Agent Executor (ReAct Loop)

```
User Input → Build Context → Call LLM (via Heimdall)
                               ├─ tool_call? → Execute Tool → Loop back
                               └─ final answer? → Return to user
```

- **OpenAI-compatible function calling** format
- Configurable `max_iterations` (default: 10) and `max_execution_time` (120s)
- Streaming via SSE
- Graceful error recovery

### 2. Tool Registry (MCP + Custom)

Tools exposed via **MCP protocol** — Bifrost acts as MCP client calling MCP servers:

| MCP Server | Tools |
|:--|:--|
| **mimir-mcp** | `search_knowledge`, `list_sources`, `get_document` |
| **fenrir-mcp** | `browser_navigate`, `fill_form`, `screenshot`, `run_shell` |
| **Built-in** | `get_current_time`, `calculate`, `http_request` |

### 3. Session Manager

| Type | Scope | Storage | TTL |
|:--|:--|:--|:--|
| **Short-term** | Per conversation | SQLite | Session lifetime |
| **Long-term** | Per user/agent | SQLite | Configurable (30d) |

### 4. Skills System *(Sprint 35)*

DeerFlow-compatible `SKILL.md` format with progressive loading — agents only receive skills relevant to the current task.

```
Agent receives: "scan code for security vulnerabilities"
  → Skills loader matches: security-audit
  → Injects <skills> block into system prompt
  → Other skills (medical, deployment, etc.) are NOT loaded
```

5 built-in skills: `medical-research`, `patient-summary`, `iso-doc-generator`, `security-audit`, `deployment`

### 5. Long-Term Memory *(Sprint 35)*

Per-tenant persistent memory across sessions. LLM extracts facts from conversations, deduplicates, and stores in SQLite.

| Category | Example |
|:--|:--|
| `fact` | "User is a cardiologist." |
| `context` | "Works at Siriraj Hospital." |
| `medical` | "Patient has diabetes type 2." |
| `preference` | "Prefers Thai language responses." |

Top 15 facts injected as `<memory>` block in system prompt.

### 6. Context Engineering *(Sprint 35)*

Automatic context window management with configurable triggers:

| Trigger | Default | Action |
|:--|:--|:--|
| Message count | > 20 messages | Summarize older messages |
| Token estimate | > 6,000 tokens | Summarize older messages |

Recent messages kept verbatim, older ones summarized via LLM.

### 7. Agent Router — Multi-agent delegation and handoff

### 8. Execution Tracing — Structured trace logs for every agent run

---

## Tech Stack

| Layer | Technology | Rationale |
|:--|:--|:--|
| **Runtime** | Python 3.11+ | Rich AI/agent ecosystem |
| **Framework** | FastAPI + Uvicorn | Async, fast, OpenAPI docs |
| **Database** | SQLite (aiosqlite) | Consistent with Mimir |
| **LLM Client** | httpx (async) | Calls Heimdall API |
| **MCP Client** | mcp SDK | Connects to MCP tool servers |
| **Serialization** | Pydantic v2 | Type safety |

---

## Project Structure

```
bifrost/
├── README.md
├── pyproject.toml
├── .env.example
├── Dockerfile
├── bifrost/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Settings (incl. skills_dir)
│   ├── api/                    # Routes: agents, sessions, tools, health
│   ├── core/                   # Executor (ReAct + skills + memory injection)
│   ├── tools/                  # Registry, base class, built-in tools
│   ├── skills/                 # SKILL.md parser + progressive loader
│   ├── memory/                 # Session + long-term facts (per-tenant)
│   ├── context/                # Summarizer + compression middleware
│   ├── clients/                # Heimdall + Mimir clients
│   └── db/                     # SQLite connection + schema
├── tests/                      # 146 tests (TDD)
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
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn bifrost.main:app --host 0.0.0.0 --port 8100 --reload
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
