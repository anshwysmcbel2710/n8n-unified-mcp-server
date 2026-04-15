# n8n Unified MCP Server

A **production-grade, unified MCP server** for n8n automation development.  
Connect Gemini CLI, Claude Code CLI, Groq CLI, Codex CLI, and Antigravity IDE  
to your n8n instance via a single, high-performance server.

---

## Features

- **30 MCP tools** covering every n8n operation
- **Context-aware AI assistance** with session memory
- **Workflow validation** before pushing to n8n
- **Auto-fix** for common workflow issues
- **Full node documentation** (40+ nodes built-in)
- **Deep execution debugging** with root cause analysis
- **Smart recommendations** for next development steps
- **Production-ready** with auth, caching, retries, structured logging
- **Streamable HTTP transport** (MCP 2025-06-18 spec)
- **Compatible with ALL MCP clients**

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your n8n details
```

Minimum required in `.env`:
```env
N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=your_n8n_api_key_here
MCP_BEARER_TOKEN=your_secure_token_here
```

**Get your n8n API key:**  
Go to `localhost:5678` → Settings → n8n API → Create API Key

**Get your n8n MCP Access Token:**  
Go to `localhost:5678/settings/mcp` → Access token tab → Copy token

### 3. Start the Server

```bash
python main.py
```

Server starts at: `http://localhost:8000`  
MCP endpoint: `http://localhost:8000/mcp`  
Health check: `http://localhost:8000/health`

---

## Connecting AI Clients

### Gemini CLI — `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "n8n": {
      "httpUrl": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_BEARER_TOKEN"
      }
    }
  }
}
```

### Claude Code CLI — `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "n8n": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_BEARER_TOKEN"
      }
    }
  }
}
```

### Groq CLI — `~/.groq/config.json`

```json
{
  "mcpServers": {
    "n8n": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8000/mcp",
        "--header", "Authorization: Bearer YOUR_MCP_BEARER_TOKEN"
      ]
    }
  }
}
```

### Codex CLI — `~/.codex/config.toml`

```toml
[mcp_servers.n8n]
command = "npx"
args = [
  "-y", "mcp-remote",
  "http://localhost:8000/mcp",
  "--header", "Authorization: Bearer YOUR_MCP_BEARER_TOKEN"
]
```

### Antigravity — `mcp_config.json`

```json
{
  "mcpServers": {
    "n8n": {
      "serverUrl": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_BEARER_TOKEN",
        "Content-Type": "application/json"
      }
    }
  }
}
```

---

## Available MCP Tools (30 Total)

### Workflow Management (9 tools)
| Tool | Description |
|------|-------------|
| `list_workflows` | List all workflows with status |
| `get_workflow` | Get complete workflow JSON |
| `create_workflow` | Create workflow from JSON |
| `update_workflow` | Update existing workflow |
| `delete_workflow` | Delete a workflow |
| `activate_workflow` | Activate a workflow |
| `deactivate_workflow` | Deactivate a workflow |
| `execute_workflow` | Manually run a workflow |
| `duplicate_workflow` | Copy workflow with new name |
| `upsert_node_in_workflow` | Add/replace single node |

### Execution & Debugging (5 tools)
| Tool | Description |
|------|-------------|
| `list_executions` | List recent executions |
| `get_execution_details` | Full execution with node outputs |
| `analyze_workflow_errors` | Root cause analysis of failures |
| `get_execution_metrics` | Performance metrics & success rate |
| `get_latest_execution` | Quick status of last run |

### Node Documentation (5 tools)
| Tool | Description |
|------|-------------|
| `search_nodes` | Find nodes by keyword/category |
| `get_node_documentation` | Full node params & examples |
| `list_node_categories` | Browse all node categories |
| `get_node_example` | Ready-to-use node JSON |
| `get_expression_guide` | n8n expression syntax reference |

### Validation & Building (4 tools)
| Tool | Description |
|------|-------------|
| `validate_workflow` | Check workflow before deploying |
| `auto_fix_workflow` | Fix common issues automatically |
| `build_workflow_template` | Scaffold workflow from description |
| `validate_connection` | Verify node connections |

### AI Intelligence (5 tools)
| Tool | Description |
|------|-------------|
| `get_session_context` | Current session state |
| `get_next_step_recommendations` | Smart AI suggestions |
| `analyze_workflow` | Deep workflow analysis |
| `get_workflow_guide` | Step-by-step use case guide |
| `search_workflow_templates` | Find template patterns |

### Credentials (3 tools)
| Tool | Description |
|------|-------------|
| `list_credentials` | See available credentials |
| `get_credential_schema` | Fields for credential type |
| `get_credential_types_reference` | Node→credential type map |

---

## Production Deployment

### Fly.io (Recommended — Free Tier)

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Launch (first time)
fly launch --no-deploy

# Set secrets
fly secrets set N8N_API_KEY=your_key
fly secrets set MCP_BEARER_TOKEN=your_token
fly secrets set N8N_BASE_URL=https://your-n8n-instance.com

# Deploy
fly deploy

# Check status
fly status
fly logs
```

Your server will be at: `https://n8n-unified-mcp-server.fly.dev/mcp`

### Docker

```bash
# Build
docker build -t n8n-mcp-server .

# Run
docker run -d \
  -p 8000:8000 \
  -e N8N_API_KEY=your_key \
  -e N8N_BASE_URL=http://your-n8n:5678 \
  -e MCP_BEARER_TOKEN=your_token \
  n8n-mcp-server
```

### Docker Compose

```bash
# Set env vars in .env then:
docker-compose up -d
```

---

## Example Prompts That Work

Once connected, use natural language in any AI client:

```
"List all my n8n workflows"
"Create a webhook workflow that monitors form submissions and sends Gmail alerts"
"Show me all failed executions in the last hour"
"Debug why my Invoice Processor workflow keeps failing"
"Get the node documentation for Gmail"
"Validate this workflow JSON before I create it: {...}"
"Build a workflow template for an AI agent chatbot"
"What should I do next to improve my current workflow?"
"Show me the n8n expression syntax for mapping arrays"
"Analyze my AI Outreach Engine workflow for issues"
```

---

## Architecture

```
AI Client (Gemini/Claude/Groq/Codex/Antigravity)
                    │
              Bearer Token Auth
                    │
         FastAPI + MCP Server (:8000)
                    │
         ┌──────────┼──────────┐
         │          │          │
      Cache      Context    Logger
      (TTL)      Memory    (JSON)
         │          │          │
         └──────────┼──────────┘
                    │
           n8n REST API v1
           (localhost:5678)
```

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp` | POST | MCP Streamable HTTP endpoint |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |
| `/info` | GET | Server info & capabilities |
| `/cache/clear` | POST | Clear cache (admin) |
| `/docs` | GET | Swagger API docs |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `N8N_API_KEY` | ✅ Yes | — | n8n REST API key |
| `N8N_BASE_URL` | ✅ Yes | `http://localhost:5678` | n8n instance URL |
| `MCP_BEARER_TOKEN` | Recommended | — | Auth token for MCP clients |
| `MCP_PORT` | No | `8000` | Server port |
| `LOG_LEVEL` | No | `INFO` | Log verbosity |
| `LOG_FORMAT` | No | `json` | `json` or `console` |
| `CACHE_ENABLED` | No | `true` | Enable response caching |
| `CACHE_TTL_WORKFLOWS` | No | `30` | Workflow cache TTL (sec) |
| `WORKERS` | No | `4` | Uvicorn worker count |

See `.env.example` for full list.
