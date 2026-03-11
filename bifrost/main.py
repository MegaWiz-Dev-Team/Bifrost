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
from bifrost.api import health, tools, agents


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bifrost")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # Startup
    logger.info("⚡ Bifrost starting up...")
    await get_db()
    register_builtin_tools()
    logger.info(f"📦 Registered {len(tools.registry)} tools")
    logger.info(f"🛡️ Heimdall: {settings.heimdall_url}")
    logger.info(f"🗄️ Database: {settings.database_path}")
    logger.info("⚡ Bifrost ready!")

    yield

    # Shutdown
    logger.info("⚡ Bifrost shutting down...")
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

# Include routers
app.include_router(health.router)
app.include_router(tools.router)
app.include_router(agents.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "bifrost.main:app",
        host=settings.bifrost_host,
        port=settings.bifrost_port,
        reload=True,
    )
