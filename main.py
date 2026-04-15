"""
n8n Unified MCP Server — Production Entry Point
================================================
A production-grade, unified MCP server for n8n automation development.
Compatible with: Gemini CLI, Claude Code CLI, Groq CLI, Codex CLI, Antigravity

Transport: Dual Architecture (stdio for CLI agents, SSE for HTTP/IDE clients)
Protocol:  MCP 2025-06-18
Auth:      Bearer Token
"""

from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from config import get_settings
from core.cache import get_cache
from core.context import get_context_manager
from core.logger import get_logger, setup_logging
from core.n8n_client import get_n8n_client
from tools import (
    register_credential_tools,
    register_execution_tools,
    register_intelligence_tools,
    register_node_tools,
    register_validation_tools,
    register_workflow_tools,
)

# ── Bootstrap ─────────────────────────────────────────────────────────────────
setup_logging()
logger = get_logger(__name__)
settings = get_settings()


# ── MCP Server Instance ───────────────────────────────────────────────────────
mcp = FastMCP(
    name=settings.server_name,
)

# ── Register All Tool Modules ─────────────────────────────────────────────────
register_workflow_tools(mcp)
register_execution_tools(mcp)
register_node_tools(mcp)
register_validation_tools(mcp)
register_intelligence_tools(mcp)
register_credential_tools(mcp)

logger.info("mcp_tools_registered", server=settings.server_name)


# ── FastAPI Application ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Manage application lifecycle — startup and shutdown."""
    logger.info(
        "server_starting",
        name=settings.server_name,
        version=settings.server_version,
        transport="sse (HTTP)",
        host=settings.mcp_host,
        port=settings.mcp_port,
    )

    # Warm up n8n connection
    client = get_n8n_client()
    health = await client.health_check()
    logger.info("n8n_health_check", **health)

    # Start background cache eviction task
    async def evict_cache_loop():
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            evicted = await get_cache().evict_expired()
            if evicted:
                logger.debug("cache_eviction", evicted_keys=evicted)

    eviction_task = asyncio.create_task(evict_cache_loop())

    logger.info("server_ready", endpoints=["/sse", "/health", "/metrics", "/docs"])

    yield

    # Shutdown
    eviction_task.cancel()
    await client.close()
    logger.info("server_shutdown")


app = FastAPI(
    title=settings.server_name,
    description=settings.server_description,
    version=settings.server_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware Stack ──────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Track request timing and add observability headers."""
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID", f"req_{int(time.time() * 1000)}")

    try:
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        response.headers["X-Server"] = settings.server_name

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        return response
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "http_error",
            method=request.method,
            path=request.url.path,
            error=str(e),
            duration_ms=duration_ms,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "request_id": request_id},
        )


@app.middleware("http")
async def bearer_auth_middleware(request: Request, call_next):
    """Bearer token authentication for MCP endpoints."""
    if not settings.mcp_bearer_token:
        return await call_next(request)

    # Skip auth for health check and docs
    if request.url.path in ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"error": "Missing or invalid Authorization header. Use: Bearer <token>"},
        )

    token = auth_header[7:]
    if token != settings.mcp_bearer_token:
        logger.warning("auth_failed", path=request.url.path)
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid bearer token"},
        )

    return await call_next(request)


# ── Health & Observability Routes ─────────────────────────────────────────────
@app.get("/health", tags=["Observability"])
async def health_check():
    """Health check — confirms server and n8n connectivity."""
    client = get_n8n_client()
    n8n_health = await client.health_check()
    cache = get_cache()
    ctx_mgr = get_context_manager()

    return {
        "status": "healthy" if n8n_health.get("n8n_reachable") else "degraded",
        "server": settings.server_name,
        "version": settings.server_version,
        "n8n": n8n_health,
        "cache": cache.stats,
        "active_sessions": ctx_mgr.active_sessions,
    }


@app.get("/metrics", tags=["Observability"])
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    cache = get_cache()
    stats = cache.stats
    ctx_mgr = get_context_manager()

    lines = [
        "# HELP n8n_mcp_cache_hits Total cache hits",
        "# TYPE n8n_mcp_cache_hits counter",
        f"n8n_mcp_cache_hits {stats['hits']}",
        "# HELP n8n_mcp_cache_misses Total cache misses",
        "# TYPE n8n_mcp_cache_misses counter",
        f"n8n_mcp_cache_misses {stats['misses']}",
        "# HELP n8n_mcp_cache_size Current cache size",
        "# TYPE n8n_mcp_cache_size gauge",
        f"n8n_mcp_cache_size {stats['size']}",
        "# HELP n8n_mcp_active_sessions Active context sessions",
        "# TYPE n8n_mcp_active_sessions gauge",
        f"n8n_mcp_active_sessions {ctx_mgr.active_sessions}",
    ]

    return Response(content="\n".join(lines), media_type="text/plain")


@app.get("/info", tags=["Observability"])
async def server_info():
    """Server configuration and capabilities."""
    return {
        "server_name": settings.server_name,
        "version": settings.server_version,
        "description": settings.server_description,
        "transport": "dual (stdio/sse)",
        "mcp_endpoint": "/sse",
        "compatible_clients": [
            "Gemini CLI", "Claude Code CLI", "Codex CLI", "Groq CLI", "Antigravity IDE",
            "Claude Desktop", "Any MCP-compatible client",
        ],
        "features": {
            "caching": settings.cache_enabled,
            "validation": settings.enable_workflow_validation,
            "auto_fix": settings.enable_auto_fix,
            "context_memory": settings.enable_context_memory,
            "template_search": settings.enable_template_search,
        },
    }


@app.post("/cache/clear", tags=["Admin"])
async def clear_cache():
    """Clear all cached data (admin operation)."""
    cache = get_cache()
    await cache.clear()
    return {"message": "Cache cleared successfully"}


# ── Mount MCP Server ──────────────────────────────────────────────────────────
# Mount the FastMCP Server-Sent Events (SSE) app natively.
# We mount it at "/mcp" so it doesn't overwrite your /health and /metrics endpoints!
app.mount("/mcp", mcp.app) 

logger.info("mcp_mounted", path="/mcp/sse")


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Check for CLI agent flag
    if "--stdio" in sys.argv:
        logger.info("Starting in stdio mode for CLI agents...")
        mcp.run(transport="stdio")
    else:
        # Run standard HTTP server for IDEs
        logger.info("Starting HTTP/SSE server for IDE clients...")
        uvicorn.run(
            "main:app",
            host=settings.mcp_host,
            port=settings.mcp_port,
            workers=1,  # Set >1 only via environment for production
            log_level=settings.log_level.lower(),
            access_log=False, 
            # Removed 'loop="uvloop"' to prevent Windows crashes
        )
