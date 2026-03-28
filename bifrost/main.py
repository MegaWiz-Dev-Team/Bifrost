"""Bifrost — Agent Runtime Engine for Asgard AI Platform.

FastAPI application entry point.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bifrost.config import settings
from bifrost.db.connection import get_db, close_db
from bifrost.tools.builtin import register_builtin_tools
from bifrost.core.mcp_adapter import create_mcp_adk_tools
from bifrost.tools.eir import register_eir_tools
from bifrost.core.agents import agent_store, AgentConfig
from bifrost.core.router import router as agent_router
from bifrost.api import health, tools, agents, a2a, traces, guardrails, odin


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

    # Discover Mimir tools via MCP (replaces legacy static registration)
    if settings.mimir_mcp_url:
        try:
            mimir_tools = await create_mcp_adk_tools(settings.mimir_mcp_url, "mimir")
            logger.info(f"🧠 Mimir MCP: {len(mimir_tools)} tools discovered ({settings.mimir_mcp_url})")
        except Exception as e:
            logger.warning(f"🧠 Mimir MCP discovery failed (non-fatal): {e}")

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

    # Discover Yggdrasil MCP Sidecar tools (Go → validate_token, get_user_roles)
    yggdrasil_mcp_tools = []
    if settings.yggdrasil_mcp_enabled and settings.yggdrasil_mcp_url:
        try:
            yggdrasil_mcp_tools = await create_mcp_adk_tools(
                settings.yggdrasil_mcp_url, "yggdrasil-mcp"
            )
            logger.info(
                f"🌳 Yggdrasil MCP Sidecar: {len(yggdrasil_mcp_tools)} tools "
                f"discovered ({settings.yggdrasil_mcp_url})"
            )
        except Exception as e:
            logger.warning(f"🌳 Yggdrasil MCP Sidecar discovery failed (non-fatal): {e}")

    # Discover Eir MCP Sidecar tools (Go → get_patient_medical_history, book_appointment)
    eir_mcp_tools = []
    if settings.eir_mcp_enabled and settings.eir_mcp_url:
        try:
            eir_mcp_tools = await create_mcp_adk_tools(
                settings.eir_mcp_url, "eir-mcp"
            )
            logger.info(
                f"🏥 Eir MCP Sidecar: {len(eir_mcp_tools)} tools "
                f"discovered ({settings.eir_mcp_url})"
            )
        except Exception as e:
            logger.warning(f"🏥 Eir MCP Sidecar discovery failed (non-fatal): {e}")

    # Register discovered MCP tools into the Bifrost execution registry
    from bifrost.tools.registry import registry
    for tool in yggdrasil_mcp_tools:
        registry.register(tool)
    for tool in eir_mcp_tools:
        registry.register(tool)

    # Set up default agent
    agent_store.add(AgentConfig(
        id="default",
        name="Eir Medical Assistant",
        system_prompt=(
            "You are a helpful AI medical assistant for the Eir OpenEMR system powered by Bifrost. "
            "You have access to tools that you MUST use to search patient records and clinical summaries. "
            "IMPORTANT: NEVER say 'Please wait', 'I am searching', or output conversational filler BEFORE using a tool. "
            "You MUST call the tool IMMEDIATELY. "
            "Respond in Thai politely only AFTER you have the data."
        ),
        tools=["search_patients", "get_patient_medical_history", "get_patient_summary", "get_sleep_reports"]
    ))
    
    logger.info(f"🤖 {len(agent_store)} agent(s) configured in legacy store")

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

# CORS — restrict to trusted origins (fixes CWE-942 / Huginn finding #9)
_cors_origins = [
    os.getenv("CORS_ALLOWED_ORIGIN", "http://localhost:3000"),
    "http://localhost:8400",  # Huginn
    "http://localhost:8500",  # Muninn
    "http://localhost:8600",  # Forseti
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
app.include_router(odin.router)

# Asgard ADK orchestrator routes
try:
    from google.adk.cli.fast_api import get_fast_api_app
    AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")
    adk_app = get_fast_api_app(
        agents_dir=AGENT_DIR,
        web=True,
        a2a=False,
    )
    for middleware in adk_app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            adk_app.user_middleware.remove(middleware)
    app.mount("/v1/adk", adk_app)
    logger.info("mounted ADK app at /v1/adk")
except ImportError:
    logger.warning("google-adk not installed. Skipped ADK mount.")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "bifrost.main:app",
        host=settings.bifrost_host,
        port=settings.bifrost_port,
        reload=True,
    )
