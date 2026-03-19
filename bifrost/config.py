"""Bifrost configuration via environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Heimdall LLM Gateway
    heimdall_url: str = Field(default="http://localhost:8080", description="Heimdall LLM Gateway URL")
    heimdall_api_key: str = Field(default="", description="Heimdall API key (optional)")

    # Bifrost Server
    bifrost_host: str = Field(default="0.0.0.0", description="Server bind host")
    bifrost_port: int = Field(default=8100, description="Server bind port")

    # Database
    database_path: str = Field(default="data/bifrost.db", description="SQLite database file path")

    # Mimir connection
    mimir_url: str = Field(default="http://localhost:3000", description="Mimir API URL")
    mimir_api_key: str = Field(default="", description="Mimir API key")
    mimir_tenant_id: str = Field(default="default", description="Mimir tenant ID (legacy, prefer dynamic injection)")
    mimir_mcp_url: str = Field(default="http://localhost:3000/mcp/sse", description="Mimir MCP SSE endpoint for tool discovery")
    mimir_sync_enabled: bool = Field(default=False, description="Enable periodic agent sync from Mimir")
    mimir_sync_interval: int = Field(default=300, description="Agent sync interval in seconds")

    # Eir Gateway connection
    eir_url: str = Field(default="http://localhost:8300", description="Eir Gateway URL")
    eir_api_key: str = Field(default="", description="Eir Gateway API key")

    # Fenrir MCP connection
    fenrir_url: str = Field(default="http://localhost:8200", description="Fenrir MCP Server URL")
    fenrir_enabled: bool = Field(default=True, description="Enable Fenrir MCP connection")

    # Authentication (Yggdrasil)
    auth_enabled: bool = Field(default=True, description="Enable JWT authentication")
    yggdrasil_issuer: str = Field(default="http://localhost:8085", description="Yggdrasil issuer URL for JWKS")
    jwt_audience: str = Field(default="", description="Expected JWT audience (optional)")

    # Guardrails
    guardrails_enabled: bool = Field(default=True, description="Enable AI guardrails")
    pii_filter_enabled: bool = Field(default=True, description="Enable PII detection/masking")
    content_filter_enabled: bool = Field(default=True, description="Enable content category filter")
    hallucination_threshold: float = Field(default=0.5, description="Grounding score threshold")

    # Agent Execution Limits
    max_iterations: int = Field(default=10, description="Max ReAct loop iterations")
    max_execution_time: int = Field(default=120, description="Max execution time in seconds")

    # Default LLM Model (must match Heimdall backend model ID)
    default_model: str = Field(default="mlx-community/Qwen3.5-9B-MLX-4bit", description="Default model name via Heimdall")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton
settings = Settings()
