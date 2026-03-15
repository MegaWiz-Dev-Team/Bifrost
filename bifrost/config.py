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
    mimir_tenant_id: str = Field(default="default", description="Mimir tenant ID")

    # Eir Gateway connection
    eir_url: str = Field(default="http://localhost:8300", description="Eir Gateway URL")
    eir_api_key: str = Field(default="", description="Eir Gateway API key")

    # Fenrir MCP connection
    fenrir_url: str = Field(default="http://localhost:8200", description="Fenrir MCP Server URL")
    fenrir_enabled: bool = Field(default=True, description="Enable Fenrir MCP connection")

    # Agent Execution Limits
    max_iterations: int = Field(default=10, description="Max ReAct loop iterations")
    max_execution_time: int = Field(default=120, description="Max execution time in seconds")

    # Default LLM Model
    default_model: str = Field(default="qwen3.5", description="Default model name via Heimdall")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton
settings = Settings()
