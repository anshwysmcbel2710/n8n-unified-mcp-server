"""
Production-Grade Configuration for n8n MCP Server
Uses Pydantic Settings for type-safe environment variable management
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Pydantic V2 Configuration ────────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Note: Pydantic automatically maps these to uppercase env vars 
    # (e.g., server_name maps to SERVER_NAME)

    # ── Server Identity ──────────────────────────────────────────────────────
    server_name: str = Field(default="n8n-unified-mcp-server")
    server_version: str = Field(default="1.0.0")
    server_description: str = Field(
        default="Production-grade unified MCP server for n8n automation development"
    )

    # ── n8n Connection ───────────────────────────────────────────────────────
    n8n_base_url: str = Field(default="http://localhost:5678")
    n8n_api_key: str = Field(...)
    n8n_api_timeout: int = Field(default=30)
    n8n_api_retries: int = Field(default=3)
    n8n_max_connections: int = Field(default=20)

    # ── MCP Server Auth ──────────────────────────────────────────────────────
    mcp_bearer_token: Optional[str] = Field(default=None)
    mcp_host: str = Field(default="0.0.0.0")
    mcp_port: int = Field(default=8000)

    # ── Transport ────────────────────────────────────────────────────────────
    # Default set to 'sse' for HTTP IDE clients. 
    # CLI clients will override this via the --stdio flag in main.py
    transport: str = Field(default="sse")
    stateless_http: bool = Field(default=True)
    json_response: bool = Field(default=True)

    # ── Cache ────────────────────────────────────────────────────────────────
    cache_enabled: bool = Field(default=True)
    cache_ttl_workflows: int = Field(default=30)
    cache_ttl_nodes: int = Field(default=3600)
    cache_ttl_templates: int = Field(default=1800)
    cache_ttl_executions: int = Field(default=10)
    redis_url: Optional[str] = Field(default=None)

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests: int = Field(default=200)
    rate_limit_window: int = Field(default=60)

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="console") # Set to console for local dev testing

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: List[str] = Field(default=["*"])

    # ── Performance ──────────────────────────────────────────────────────────
    workers: int = Field(default=4)
    max_workflow_size_kb: int = Field(default=512)

    # ── Feature Flags ────────────────────────────────────────────────────────
    enable_workflow_validation: bool = Field(default=True)
    enable_auto_fix: bool = Field(default=True)
    enable_context_memory: bool = Field(default=True)
    enable_template_search: bool = Field(default=True)

    @field_validator("n8n_base_url")
    @classmethod
    def clean_base_url(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — loaded once, reused everywhere."""
    return Settings()