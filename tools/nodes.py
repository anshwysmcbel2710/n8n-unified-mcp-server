"""
n8n Node Documentation & Schema MCP Tools
Provides AI agents with comprehensive n8n node knowledge.
This is what separates a basic MCP from a production-grade one.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from config import get_settings
from core.cache import cached
from core.logger import get_logger

logger = get_logger(__name__)

# ── Built-in n8n Node Reference Database ─────────────────────────────────────
# Comprehensive node catalog for offline documentation access
NODE_CATALOG: Dict[str, Dict] = {
    # ── Triggers ──────────────────────────────────────────────────────────────
    "n8n-nodes-base.webhook": {
        "name": "Webhook",
        "category": "Trigger",
        "description": "Starts workflow on HTTP webhook call",
        "required_params": ["httpMethod", "path", "responseMode"],
        "optional_params": ["authentication", "responseData", "responseCode"],
        "outputs": ["main"],
        "example": {
            "type": "n8n-nodes-base.webhook",
            "name": "Webhook",
            "parameters": {
                "httpMethod": "POST",
                "path": "my-webhook",
                "responseMode": "onReceived",
                "responseData": "allEntries",
            },
            "position": [240, 300],
            "id": "webhook-001",
        },
    },
    "n8n-nodes-base.scheduleTrigger": {
        "name": "Schedule Trigger",
        "category": "Trigger",
        "description": "Triggers workflow on a schedule (cron)",
        "required_params": ["rule"],
        "example": {
            "type": "n8n-nodes-base.scheduleTrigger",
            "name": "Schedule Trigger",
            "parameters": {
                "rule": {"interval": [{"field": "hours", "hoursInterval": 1}]},
            },
            "position": [240, 300],
            "id": "schedule-001",
        },
    },
    "n8n-nodes-base.emailReadImap": {
        "name": "Email Trigger (IMAP)",
        "category": "Trigger",
        "description": "Triggers when new email arrives",
        "required_params": ["mailbox"],
    },
    "n8n-nodes-base.manualTrigger": {
        "name": "Manual Trigger",
        "category": "Trigger",
        "description": "Triggers workflow manually from UI",
        "required_params": [],
    },
    "n8n-nodes-base.chatTrigger": {
        "name": "Chat Trigger",
        "category": "Trigger",
        "description": "Opens chat interface for the workflow",
        "required_params": [],
    },
    # ── Communication ─────────────────────────────────────────────────────────
    "n8n-nodes-base.gmail": {
        "name": "Gmail",
        "category": "Communication",
        "description": "Send, receive, label Gmail emails",
        "operations": ["send", "getAll", "get", "delete", "reply", "addLabel"],
        "required_params": ["operation", "sendTo", "subject", "message"],
        "credentials": "gmailOAuth2",
        "example": {
            "type": "n8n-nodes-base.gmail",
            "name": "Send Email",
            "parameters": {
                "operation": "send",
                "sendTo": "={{ $json.email }}",
                "subject": "Hello from n8n",
                "message": "={{ $json.body }}",
            },
            "position": [480, 300],
            "id": "gmail-001",
            "credentials": {"gmailOAuth2": {"id": "1", "name": "Gmail account"}},
        },
    },
    "n8n-nodes-base.slack": {
        "name": "Slack",
        "category": "Communication",
        "description": "Send messages to Slack channels or DMs",
        "operations": ["message:post", "message:update", "channel:get"],
        "required_params": ["operation", "channel", "text"],
        "credentials": "slackApi",
    },
    "n8n-nodes-base.telegram": {
        "name": "Telegram",
        "category": "Communication",
        "description": "Send Telegram messages via bot",
        "operations": ["message:sendMessage", "message:sendPhoto"],
        "required_params": ["operation", "chatId", "text"],
        "credentials": "telegramApi",
    },
    # ── Data & Storage ────────────────────────────────────────────────────────
    "n8n-nodes-base.googleSheets": {
        "name": "Google Sheets",
        "category": "Data",
        "description": "Read/write Google Sheets data",
        "operations": ["append", "read", "update", "delete", "clear"],
        "required_params": ["operation", "documentId", "sheetName"],
        "credentials": "googleSheetsOAuth2Api",
    },
    "n8n-nodes-base.airtable": {
        "name": "Airtable",
        "category": "Data",
        "description": "CRUD operations on Airtable bases",
        "operations": ["list", "get", "create", "update", "delete"],
        "credentials": "airtableTokenApi",
    },
    "n8n-nodes-base.postgres": {
        "name": "Postgres",
        "category": "Database",
        "description": "Execute SQL queries on PostgreSQL",
        "operations": ["execute", "insert", "update", "delete", "select"],
        "credentials": "postgres",
    },
    "n8n-nodes-base.mongodb": {
        "name": "MongoDB",
        "category": "Database",
        "description": "CRUD operations on MongoDB collections",
        "credentials": "mongoDb",
    },
    "n8n-nodes-base.redis": {
        "name": "Redis",
        "category": "Database",
        "description": "Get/set Redis key-value data",
        "operations": ["get", "set", "delete", "incr", "publish"],
        "credentials": "redis",
    },
    # ── HTTP & APIs ───────────────────────────────────────────────────────────
    "n8n-nodes-base.httpRequest": {
        "name": "HTTP Request",
        "category": "Core",
        "description": "Make any HTTP/REST API request",
        "required_params": ["method", "url"],
        "optional_params": ["authentication", "headers", "queryParameters", "body", "responseFormat"],
        "example": {
            "type": "n8n-nodes-base.httpRequest",
            "name": "HTTP Request",
            "parameters": {
                "method": "POST",
                "url": "https://api.example.com/endpoint",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "Bearer {{ $env.API_KEY }}"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "bodyParameters": {
                    "parameters": [{"name": "data", "value": "={{ $json.data }}"}]
                },
            },
            "position": [480, 300],
            "id": "http-001",
        },
    },
    "n8n-nodes-base.graphql": {
        "name": "GraphQL",
        "category": "Core",
        "description": "Execute GraphQL queries and mutations",
    },
    # ── Logic & Flow ──────────────────────────────────────────────────────────
    "n8n-nodes-base.if": {
        "name": "IF",
        "category": "Logic",
        "description": "Route data based on conditions. Has true/false outputs.",
        "outputs": ["true", "false"],
        "example": {
            "type": "n8n-nodes-base.if",
            "name": "IF",
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True},
                    "conditions": [{
                        "leftValue": "={{ $json.status }}",
                        "rightValue": "active",
                        "operator": {"type": "string", "operation": "equals"},
                    }],
                    "combinator": "and",
                },
            },
            "position": [480, 300],
            "id": "if-001",
        },
    },
    "n8n-nodes-base.switch": {
        "name": "Switch",
        "category": "Logic",
        "description": "Route data to multiple outputs based on conditions",
        "outputs": ["multiple"],
    },
    "n8n-nodes-base.splitInBatches": {
        "name": "Split in Batches",
        "category": "Logic",
        "description": "Process items in chunks to avoid overwhelming APIs",
        "required_params": ["batchSize"],
    },
    "n8n-nodes-base.merge": {
        "name": "Merge",
        "category": "Logic",
        "description": "Merge data from multiple workflow branches",
        "operations": ["append", "combine", "chooseBranch"],
    },
    "n8n-nodes-base.wait": {
        "name": "Wait",
        "category": "Logic",
        "description": "Pause workflow for a time or until webhook",
        "required_params": ["resume", "time", "timeUnit"],
    },
    "n8n-nodes-base.code": {
        "name": "Code",
        "category": "Core",
        "description": "Execute custom JavaScript or Python code",
        "required_params": ["jsCode"],
        "example": {
            "type": "n8n-nodes-base.code",
            "name": "Code",
            "parameters": {
                "jsCode": "return items.map(item => ({\n  json: {\n    ...item.json,\n    processed: true,\n    timestamp: new Date().toISOString()\n  }\n}));",
            },
            "position": [480, 300],
            "id": "code-001",
        },
    },
    "n8n-nodes-base.functionItem": {
        "name": "Function Item",
        "category": "Core",
        "description": "Run JavaScript on each item individually",
    },
    "n8n-nodes-base.errorTrigger": {
        "name": "Error Trigger",
        "category": "Trigger",
        "description": "Triggers when another workflow fails — for error handling",
    },
    # ── AI & LLM ──────────────────────────────────────────────────────────────
    "@n8n/n8n-nodes-langchain.openAi": {
        "name": "OpenAI",
        "category": "AI",
        "description": "Chat completions, embeddings, image generation with OpenAI",
        "credentials": "openAiApi",
    },
    "@n8n/n8n-nodes-langchain.lmChatGoogleGemini": {
        "name": "Google Gemini Chat Model",
        "category": "AI",
        "description": "Gemini models for AI Agent workflows",
        "credentials": "googlePalmApi",
    },
    "@n8n/n8n-nodes-langchain.agent": {
        "name": "AI Agent",
        "category": "AI",
        "description": "Autonomous AI agent with tools and memory",
        "required_params": ["agent", "promptType"],
    },
    "@n8n/n8n-nodes-langchain.chainLlm": {
        "name": "Basic LLM Chain",
        "category": "AI",
        "description": "Simple LLM chain with prompt template",
    },
    "@n8n/n8n-nodes-langchain.memoryBufferWindow": {
        "name": "Window Buffer Memory",
        "category": "AI",
        "description": "Keeps last N messages in agent memory",
    },
    # ── Data Transformation ───────────────────────────────────────────────────
    "n8n-nodes-base.set": {
        "name": "Set",
        "category": "Data Transformation",
        "description": "Set, rename, or remove fields from items",
        "example": {
            "type": "n8n-nodes-base.set",
            "name": "Set Fields",
            "parameters": {
                "mode": "manual",
                "assignments": {
                    "assignments": [
                        {"id": "1", "name": "fullName", "value": "={{ $json.firstName + ' ' + $json.lastName }}", "type": "string"},
                        {"id": "2", "name": "timestamp", "value": "={{ $now }}", "type": "string"},
                    ]
                },
            },
            "position": [480, 300],
            "id": "set-001",
        },
    },
    "n8n-nodes-base.filter": {
        "name": "Filter",
        "category": "Data Transformation",
        "description": "Filter items based on conditions",
    },
    "n8n-nodes-base.removeDuplicates": {
        "name": "Remove Duplicates",
        "category": "Data Transformation",
        "description": "Remove duplicate items based on field values",
    },
    "n8n-nodes-base.sort": {
        "name": "Sort",
        "category": "Data Transformation",
        "description": "Sort items by field values",
    },
    "n8n-nodes-base.limit": {
        "name": "Limit",
        "category": "Data Transformation",
        "description": "Limit the number of items passed through",
    },
    "n8n-nodes-base.aggregate": {
        "name": "Aggregate",
        "category": "Data Transformation",
        "description": "Aggregate multiple items into one",
    },
    "n8n-nodes-base.spreadsheetFile": {
        "name": "Spreadsheet File",
        "category": "Files",
        "description": "Read/write CSV and Excel files",
    },
    # ── CRM & Business ────────────────────────────────────────────────────────
    "n8n-nodes-base.hubspot": {
        "name": "HubSpot",
        "category": "CRM",
        "description": "Manage HubSpot contacts, deals, companies",
        "credentials": "hubspotApi",
    },
    "n8n-nodes-base.salesforce": {
        "name": "Salesforce",
        "category": "CRM",
        "description": "CRUD on Salesforce objects",
        "credentials": "salesforceOAuth2Api",
    },
    "n8n-nodes-base.notion": {
        "name": "Notion",
        "category": "Productivity",
        "description": "Read/write Notion databases and pages",
        "credentials": "notionApi",
    },
    "n8n-nodes-base.googleDrive": {
        "name": "Google Drive",
        "category": "Files",
        "description": "Upload, download, manage Google Drive files",
        "credentials": "googleDriveOAuth2Api",
    },
    "n8n-nodes-base.github": {
        "name": "GitHub",
        "category": "Developer",
        "description": "Manage GitHub repos, issues, PRs",
        "credentials": "githubApi",
    },
    "n8n-nodes-base.stripe": {
        "name": "Stripe",
        "category": "Finance",
        "description": "Manage Stripe payments, customers, subscriptions",
        "credentials": "stripeApi",
    },
}


def register_node_tools(mcp: FastMCP) -> None:
    settings = get_settings()

    @mcp.tool(
        description=(
            "Search n8n node documentation by keyword, category, or use case. "
            "Returns matching nodes with descriptions, required parameters, "
            "and configuration examples. Use this before creating workflows "
            "to find the correct node types."
        )
    )
    async def search_nodes(
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        query_lower = query.lower()
        results = []

        for node_type, info in NODE_CATALOG.items():
            score = 0
            name_lower = info["name"].lower()
            desc_lower = info["description"].lower()
            cat_lower = info.get("category", "").lower()

            if query_lower in name_lower:
                score += 10
            if query_lower in desc_lower:
                score += 5
            if query_lower in cat_lower:
                score += 3
            if query_lower in node_type.lower():
                score += 7

            # Category filter
            if category and category.lower() not in cat_lower:
                continue

            if score > 0:
                results.append({
                    "node_type": node_type,
                    "name": info["name"],
                    "category": info.get("category"),
                    "description": info["description"],
                    "score": score,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:limit]

        return json.dumps({
            "query": query,
            "total_found": len(results),
            "nodes": results,
        }, indent=2)

    @mcp.tool(
        description=(
            "Get complete documentation for a specific n8n node type including "
            "all parameters, required fields, credential types, and a working "
            "configuration example. Use this to get exact node config before "
            "building workflows."
        )
    )
    async def get_node_documentation(node_type: str) -> str:
        # Try exact match first
        info = NODE_CATALOG.get(node_type)

        # Try case-insensitive partial match
        if not info:
            for k, v in NODE_CATALOG.items():
                if node_type.lower() in k.lower() or node_type.lower() in v["name"].lower():
                    info = v
                    node_type = k
                    break

        if not info:
            return json.dumps({
                "error": f"Node type '{node_type}' not found in documentation",
                "suggestion": "Use search_nodes to find the correct node type string",
                "available_categories": list(set(v.get("category", "") for v in NODE_CATALOG.values())),
            }, indent=2)

        return json.dumps({
            "node_type": node_type,
            "documentation": info,
        }, indent=2)

    @mcp.tool(
        description=(
            "List all available n8n node categories and the nodes in each. "
            "Use this to explore what's available for building workflows."
        )
    )
    async def list_node_categories() -> str:
        categories: Dict[str, List[str]] = {}
        for node_type, info in NODE_CATALOG.items():
            cat = info.get("category", "Other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(info["name"])

        for cat in categories:
            categories[cat].sort()

        return json.dumps({
            "total_nodes": len(NODE_CATALOG),
            "categories": categories,
        }, indent=2)

    @mcp.tool(
        description=(
            "Get a working example configuration for a specific node type. "
            "Returns ready-to-use JSON that can be inserted directly into "
            "a workflow's nodes array."
        )
    )
    async def get_node_example(node_type: str) -> str:
        info = NODE_CATALOG.get(node_type)
        if not info:
            return json.dumps({
                "error": f"No example found for '{node_type}'",
                "tip": "Use search_nodes to find exact node type strings",
            }, indent=2)

        example = info.get("example")
        if not example:
            # Generate minimal example
            example = {
                "type": node_type,
                "name": info["name"],
                "parameters": {},
                "position": [480, 300],
                "id": f"{node_type.split('.')[-1]}-001",
            }

        return json.dumps({
            "node_type": node_type,
            "example": example,
            "required_params": info.get("required_params", []),
            "credentials": info.get("credentials"),
        }, indent=2)

    @mcp.tool(
        description=(
            "Get n8n expression syntax guide and common patterns. "
            "Covers $json, $item, $node, $env, $workflow variables, "
            "date functions, and common transformations. Essential for "
            "writing correct n8n expressions."
        )
    )
    async def get_expression_guide() -> str:
        guide = {
            "overview": "n8n uses a JavaScript-based expression language wrapped in {{ }}",
            "basic_variables": {
                "$json": "Current item's JSON data — e.g. {{ $json.email }}",
                "$json.fieldName": "Access a specific field — e.g. {{ $json.name }}",
                "$json['field-name']": "Access fields with special characters",
                "$item()": "Access a specific item — {{ $item(0).$node['NodeName'].json }}",
                "$node": "Access data from a specific node — {{ $node['NodeName'].json.field }}",
                "$items()": "All items from a node — {{ $items('NodeName').length }}",
                "$env": "Environment variables — {{ $env.MY_API_KEY }}",
                "$workflow.id": "Current workflow ID",
                "$workflow.name": "Current workflow name",
                "$executionId": "Current execution ID",
                "$now": "Current datetime ISO string",
                "$today": "Today's date",
            },
            "common_patterns": {
                "String concatenation": "{{ $json.firstName + ' ' + $json.lastName }}",
                "Conditional value": "{{ $json.status === 'active' ? 'Yes' : 'No' }}",
                "Number formatting": "{{ $json.price.toFixed(2) }}",
                "Array join": "{{ $json.tags.join(', ') }}",
                "Date formatting": "{{ new Date($json.timestamp).toLocaleDateString() }}",
                "JSON stringify": "{{ JSON.stringify($json.data) }}",
                "Object spread": "{{ {...$json, newField: 'value'} }}",
                "Filter array": "{{ $json.items.filter(i => i.active) }}",
                "Map array": "{{ $json.items.map(i => i.name) }}",
                "Default value": "{{ $json.name ?? 'Anonymous' }}",
                "String template": "`Hello ${$json.name}, you have ${$json.count} items`",
                "Math": "{{ Math.round($json.score * 100) / 100 }}",
            },
            "code_node_patterns": {
                "return_items": "return items.map(item => ({ json: { ...item.json, processed: true } }));",
                "create_items": "return [{ json: { result: 'value' } }];",
                "filter_items": "return items.filter(item => item.json.active === true);",
                "aggregate": "return [{ json: { count: items.length, total: items.reduce((s, i) => s + i.json.amount, 0) } }];",
            },
            "tips": [
                "Always wrap expressions in {{ }} inside parameter fields",
                "Use $json for current item, $node['name'].json for specific node",
                "Code node returns array of { json: {...} } objects",
                "Use optional chaining: {{ $json.user?.email ?? 'no-email' }}",
                "DateTime: {{ $now.toISO() }}, {{ $today.toFormat('yyyy-MM-dd') }}",
            ],
        }
        return json.dumps(guide, indent=2)

    logger.info("node_tools_registered", count=5)
