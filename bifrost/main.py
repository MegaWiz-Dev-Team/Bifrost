"""Bifrost — Agent Runtime Engine for Asgard AI Platform.

FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bifrost.config import settings
from bifrost.db.connection import get_db, close_db
from bifrost.tools.builtin import register_builtin_tools
from bifrost.tools.mimir import register_mimir_tools
from bifrost.tools.eir import register_eir_tools
from bifrost.core.agents import agent_store, AgentConfig
from bifrost.core.router import router as agent_router
from bifrost.api import health, tools, agents, a2a, traces, guardrails


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bifrost")

# MCP manager for external tool servers
_mcp_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    global _mcp_manager

    # Startup
    logger.info("⚡ Bifrost starting up...")
    await get_db()
    register_builtin_tools()
    logger.info(f"📦 Registered {len(tools.registry)} built-in tools")

    # Register Mimir RAG tools
    if settings.mimir_url:
        register_mimir_tools(settings.mimir_url, settings.mimir_api_key, settings.mimir_tenant_id)
        logger.info(f"🧠 Mimir tools registered ({settings.mimir_url})")

    # Register Eir Gateway tools
    if settings.eir_url:
        register_eir_tools(settings.eir_url, settings.eir_api_key)
        logger.info(f"🏥 Eir tools registered ({settings.eir_url})")

    # Connect Fenrir via MCP (SSE transport)
    if settings.fenrir_enabled and settings.fenrir_url:
        try:
            from bifrost.clients.mcp import MCPManager, MCPServerConfig
            _mcp_manager = MCPManager()
            fenrir_config = MCPServerConfig(
                name="fenrir",
                transport="sse",
                url=settings.fenrir_url,
            )
            client = await _mcp_manager.add_server(fenrir_config)
            from bifrost.tools.registry import registry
            count = await client.discover_and_register(registry)
            logger.info(f"🐺 Fenrir MCP connected — {count} tools discovered ({settings.fenrir_url})")
        except Exception as e:
            logger.warning(f"🐺 Fenrir MCP connection failed (non-fatal): {e}")
            _mcp_manager = None

    # Set up default agent
    agent_store.add(AgentConfig(
        id="default",
        name="Default Assistant",
        system_prompt=(
            "You are a helpful AI assistant powered by Bifrost. "
            "You have access to tools that you can use to help answer questions. "
            "Always think step by step. Use tools when appropriate. "
            "Respond in the same language as the user."
        ),
    ))
    logger.info(f"🤖 {len(agent_store)} agent(s) configured")

    logger.info(f"🛡️ Heimdall: {settings.heimdall_url}")
    logger.info(f"🗄️ Database: {settings.database_path}")
    logger.info("⚡ Bifrost ready!")

    yield

    # Shutdown
    logger.info("⚡ Bifrost shutting down...")
    if _mcp_manager:
        await _mcp_manager.disconnect_all()
    await close_db()


app = FastAPI(
    title="Bifrost — Agent Runtime Engine",
    description="Self-hosted Agent Runtime for the Asgard AI Platform. "
                "Execute AI agents with ReAct loop, tool calling, and session management.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT Auth (Yggdrasil)
from bifrost.middleware.auth import JWTAuthMiddleware
app.add_middleware(JWTAuthMiddleware)

# Include routers
app.include_router(health.router)
app.include_router(tools.router)
app.include_router(agents.router)
app.include_router(a2a.router)
app.include_router(traces.router)
app.include_router(guardrails.router)

# Odin orchestrator routes
from bifrost.api.odin import router as odin_router
app.include_router(odin_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "bifrost.main:app",
        host=settings.bifrost_host,
        port=settings.bifrost_port,
        reload=True,
    )
