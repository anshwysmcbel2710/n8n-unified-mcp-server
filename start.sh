#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# n8n Unified MCP Server — Quick Start Script
# ══════════════════════════════════════════════════════════════════════════════

set -e

echo "══════════════════════════════════════"
echo "  n8n Unified MCP Server — Starting"
echo "══════════════════════════════════════"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python: $PYTHON_VERSION"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Copying .env.example..."
    cp .env.example .env
    echo "📝 Edit .env with your n8n API key and settings, then re-run this script."
    exit 1
fi

# Check required env vars
source .env
if [ -z "$N8N_API_KEY" ] || [ "$N8N_API_KEY" = "your_n8n_api_key_here" ]; then
    echo "❌ ERROR: N8N_API_KEY is not set in .env"
    echo "   Get your API key from: localhost:5678 → Settings → n8n API"
    exit 1
fi

echo "✅ N8N_BASE_URL: ${N8N_BASE_URL:-http://localhost:5678}"
echo "✅ MCP_PORT: ${MCP_PORT:-8000}"

# Install dependencies if needed
if [ ! -d "venv" ] && [ -z "$VIRTUAL_ENV" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo "✅ Dependencies installed"
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start server
echo ""
echo "🚀 Starting MCP Server on port ${MCP_PORT:-8000}..."
echo "   MCP endpoint: http://localhost:${MCP_PORT:-8000}/mcp"
echo "   Health check: http://localhost:${MCP_PORT:-8000}/health"
echo "   API docs:     http://localhost:${MCP_PORT:-8000}/docs"
echo ""

python main.py
