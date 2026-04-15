"""
AI Intelligence & Context-Aware Assistance Tools
Smart recommendations, next-step suggestions, workflow analysis,
and decision support for advanced AI automation development.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from config import get_settings
from core.cache import cached
from core.context import get_context_manager
from core.logger import get_logger
from core.n8n_client import get_n8n_client

logger = get_logger(__name__)


def register_intelligence_tools(mcp: FastMCP) -> None:
    settings = get_settings()

    @mcp.tool(
        description=(
            "Get the current session context — what workflows have been "
            "accessed, what actions were taken, current workflow being worked on. "
            "Use this to understand the state of the current development session "
            "and make context-aware decisions."
        )
    )
    async def get_session_context() -> str:
        ctx = await get_context_manager().get_default()
        return json.dumps(ctx.get_summary(), indent=2)

    @mcp.tool(
        description=(
            "Get intelligent recommendations for what to do next based on "
            "the current workflow state and session history. Returns prioritized "
            "action suggestions to guide development decisions."
        )
    )
    async def get_next_step_recommendations(
        workflow_id: Optional[str] = None,
        current_goal: Optional[str] = None,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        recommendations = []
        context_notes = []

        # Use current workflow from context if not specified
        if not workflow_id and ctx.current_workflow.workflow_id:
            workflow_id = ctx.current_workflow.workflow_id
            context_notes.append(f"Using current workflow: {ctx.current_workflow.workflow_name}")

        if workflow_id:
            try:
                workflow = await client.get_workflow(workflow_id)
                nodes = workflow.get("nodes", [])
                active = workflow.get("active", False)

                # Analyze workflow
                has_error_handling = any(
                    "errorTrigger" in (n.get("type") or "") or
                    "try" in (n.get("name") or "").lower()
                    for n in nodes
                )
                has_wait_node = any("wait" in (n.get("type") or "").lower() for n in nodes)
                node_count = len(nodes)

                if not active:
                    recommendations.append({
                        "priority": "HIGH",
                        "action": "Test and activate workflow",
                        "reason": "Workflow is currently inactive",
                        "command": f"Call execute_workflow('{workflow_id}') to test, then activate_workflow('{workflow_id}')",
                    })

                if not has_error_handling and node_count > 3:
                    recommendations.append({
                        "priority": "MEDIUM",
                        "action": "Add error handling",
                        "reason": "Complex workflows should handle failures gracefully",
                        "command": "Add a try-catch in Code node or create error handler workflow",
                    })

                if node_count > 10 and not has_wait_node:
                    recommendations.append({
                        "priority": "LOW",
                        "action": "Consider rate limiting",
                        "reason": "Large workflow may hit API rate limits",
                        "command": "Add Wait node between API calls",
                    })

                # Check recent errors
                try:
                    exec_result = await client.list_executions(
                        workflow_id=workflow_id,
                        status="error",
                        limit=3,
                    )
                    if exec_result.get("data"):
                        recommendations.append({
                            "priority": "HIGH",
                            "action": "Debug recent failures",
                            "reason": f"{len(exec_result['data'])} recent execution failures",
                            "command": f"Call analyze_workflow_errors('{workflow_id}') for root cause",
                        })
                except Exception:
                    pass

            except Exception as e:
                context_notes.append(f"Could not analyze workflow: {e}")
        else:
            # No specific workflow — general recommendations
            recommendations.append({
                "priority": "HIGH",
                "action": "List existing workflows",
                "reason": "Start by understanding what already exists",
                "command": "Call list_workflows() to see all workflows",
            })
            recommendations.append({
                "priority": "MEDIUM",
                "action": "Search node documentation",
                "reason": "Find the right nodes for your use case",
                "command": "Call search_nodes(query='your use case') to find relevant nodes",
            })

        # Goal-based recommendations
        if current_goal:
            goal_lower = current_goal.lower()
            if "email" in goal_lower:
                recommendations.append({
                    "priority": "HIGH",
                    "action": "Use Gmail or IMAP node",
                    "reason": "Email workflows use Gmail or Email Trigger nodes",
                    "command": "Call get_node_documentation('n8n-nodes-base.gmail') for config",
                })
            if "ai" in goal_lower or "agent" in goal_lower:
                recommendations.append({
                    "priority": "HIGH",
                    "action": "Use AI Agent node",
                    "reason": "AI agent workflows require AI Agent + LLM + Tool nodes",
                    "command": "Call get_node_documentation('@n8n/n8n-nodes-langchain.agent')",
                })
            if "schedule" in goal_lower or "cron" in goal_lower or "daily" in goal_lower:
                recommendations.append({
                    "priority": "HIGH",
                    "action": "Use Schedule Trigger",
                    "reason": "Scheduled workflows use Schedule Trigger node",
                    "command": "Call get_node_documentation('n8n-nodes-base.scheduleTrigger')",
                })
            if "webhook" in goal_lower or "api" in goal_lower:
                recommendations.append({
                    "priority": "HIGH",
                    "action": "Use Webhook Trigger",
                    "reason": "API-triggered workflows start with Webhook node",
                    "command": "Call get_node_documentation('n8n-nodes-base.webhook')",
                })

        ctx.record_action("get_recommendations", {"workflow_id": workflow_id}, f"{len(recommendations)} recommendations")

        return json.dumps({
            "context": context_notes,
            "current_goal": current_goal,
            "recommendation_count": len(recommendations),
            "recommendations": sorted(recommendations, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x["priority"], 3)),
        }, indent=2)

    @mcp.tool(
        description=(
            "Analyze an existing workflow and provide a comprehensive report: "
            "what it does, potential improvements, missing error handling, "
            "performance issues, and optimization suggestions."
        )
    )
    async def analyze_workflow(workflow_id: str) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        workflow = await client.get_workflow(workflow_id)
        nodes = workflow.get("nodes", [])
        connections = workflow.get("connections", {})

        # Categorize nodes
        node_categories: Dict[str, List[str]] = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            cat = _categorize_node(node_type)
            if cat not in node_categories:
                node_categories[cat] = []
            node_categories[cat].append(node.get("name", "unnamed"))

        # Find issues
        issues = []
        improvements = []

        # Check for disconnected nodes
        connected_nodes = set()
        for source, outputs in connections.items():
            connected_nodes.add(source)
            for branches in outputs.values():
                for branch in branches:
                    for conn in (branch or []):
                        if isinstance(conn, dict):
                            connected_nodes.add(conn.get("node", ""))

        all_node_names = {n.get("name") for n in nodes}
        disconnected = all_node_names - connected_nodes
        if disconnected:
            issues.append(f"Disconnected nodes (not wired): {', '.join(disconnected)}")

        # Check for error handling
        has_error_handling = any("error" in (n.get("type") or "").lower() for n in nodes)
        if not has_error_handling and len(nodes) > 3:
            improvements.append("Add error handling — use Error Trigger or IF node to handle failures")

        # Check for hardcoded credentials
        for node in nodes:
            params_str = json.dumps(node.get("parameters", {}))
            for keyword in ["password", "secret", "token", "apikey"]:
                if keyword in params_str.lower() and "$env" not in params_str:
                    issues.append(f"Possible hardcoded credential in '{node.get('name')}' — use $env.VARIABLE instead")

        # Check for missing wait nodes near API calls
        http_nodes = [n for n in nodes if "http" in (n.get("type") or "").lower()]
        if len(http_nodes) > 3:
            has_wait = any("wait" in (n.get("type") or "").lower() for n in nodes)
            if not has_wait:
                improvements.append("Consider adding Wait nodes between API calls to prevent rate limiting")

        ctx.record_action("analyze_workflow", {"id": workflow_id}, "Analysis complete")

        return json.dumps({
            "workflow_id": workflow_id,
            "workflow_name": workflow.get("name"),
            "active": workflow.get("active", False),
            "total_nodes": len(nodes),
            "node_categories": node_categories,
            "issues_found": len(issues),
            "issues": issues,
            "improvement_suggestions": improvements,
            "complexity": "Simple" if len(nodes) < 5 else "Medium" if len(nodes) < 15 else "Complex",
            "last_updated": workflow.get("updatedAt"),
        }, indent=2)

    @mcp.tool(
        description=(
            "Get a comprehensive n8n workflow building guide for a specific "
            "use case. Returns step-by-step instructions, required nodes, "
            "connections map, and example JSON. Covers common automation patterns."
        )
    )
    async def get_workflow_guide(use_case: str) -> str:
        guides = _get_use_case_guides()
        use_case_lower = use_case.lower()

        matched_guide = None
        best_score = 0
        for key, guide in guides.items():
            score = sum(1 for word in key.split() if word in use_case_lower)
            if score > best_score:
                best_score = score
                matched_guide = guide

        if not matched_guide:
            matched_guide = {
                "title": "Custom Workflow",
                "description": f"Building: {use_case}",
                "steps": [
                    "1. Call list_node_categories() to explore available nodes",
                    f"2. Call search_nodes(query='{use_case}') to find relevant nodes",
                    "3. Call get_node_documentation() for required nodes",
                    "4. Call build_workflow_template() to scaffold the workflow",
                    "5. Call validate_workflow() to check correctness",
                    "6. Call create_workflow() to deploy to n8n",
                    "7. Call execute_workflow() to test",
                    "8. Call activate_workflow() for production",
                ],
                "recommended_nodes": ["Webhook/Manual Trigger", "Code", "HTTP Request"],
                "tips": ["Always validate before creating", "Start simple, then add complexity"],
            }

        return json.dumps(matched_guide, indent=2)

    @mcp.tool(
        description=(
            "Search n8n workflow templates from the template library. "
            "Returns matching templates with descriptions and node counts. "
            "Templates provide ready-made workflow patterns you can adapt."
        )
    )
    async def search_workflow_templates(
        query: str,
        category: Optional[str] = None,
    ) -> str:
        # Built-in template catalog
        templates = _get_template_catalog()

        query_lower = query.lower()
        results = []

        for t in templates:
            score = 0
            if query_lower in t["name"].lower():
                score += 10
            if query_lower in t["description"].lower():
                score += 5
            if category and category.lower() in t.get("category", "").lower():
                score += 3
            if score > 0 or not category:
                if score > 0:
                    results.append({**t, "relevance_score": score})
                elif query_lower in " ".join(t.get("tags", [])).lower():
                    results.append({**t, "relevance_score": 2})

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        return json.dumps({
            "query": query,
            "total_found": len(results),
            "templates": results[:10],
        }, indent=2)

    logger.info("intelligence_tools_registered", count=5)


def _categorize_node(node_type: str) -> str:
    type_lower = node_type.lower()
    if "trigger" in type_lower or "webhook" in type_lower:
        return "Triggers"
    if "gmail" in type_lower or "slack" in type_lower or "telegram" in type_lower:
        return "Communication"
    if "http" in type_lower or "graphql" in type_lower:
        return "HTTP/API"
    if "sheets" in type_lower or "airtable" in type_lower or "postgres" in type_lower:
        return "Data Storage"
    if "if" in type_lower or "switch" in type_lower or "merge" in type_lower:
        return "Logic"
    if "code" in type_lower or "function" in type_lower:
        return "Code"
    if "langchain" in type_lower or "openai" in type_lower or "agent" in type_lower:
        return "AI/LLM"
    if "set" in type_lower or "filter" in type_lower or "sort" in type_lower:
        return "Data Transform"
    return "Other"


def _get_use_case_guides() -> Dict:
    return {
        "email notification alert": {
            "title": "Email Notification Workflow",
            "description": "Trigger → Process → Send Gmail Notification",
            "steps": [
                "1. Add Webhook trigger or Schedule Trigger",
                "2. Add IF node to filter relevant data",
                "3. Add Gmail node with 'send' operation",
                "4. Configure Gmail OAuth2 credentials",
                "5. Test with execute_workflow()",
            ],
            "required_nodes": ["n8n-nodes-base.webhook OR scheduleTrigger", "n8n-nodes-base.if", "n8n-nodes-base.gmail"],
            "tips": ["Use IF node to avoid sending unnecessary emails", "Store email templates in Code node"],
        },
        "ai agent chatbot": {
            "title": "AI Agent Workflow",
            "description": "Chat Trigger → AI Agent → LLM + Tools → Response",
            "steps": [
                "1. Add Chat Trigger node",
                "2. Add AI Agent node (LangChain)",
                "3. Connect Gemini or OpenAI Chat Model as LLM",
                "4. Add Tool nodes (HTTP Request, Google Sheets, etc.)",
                "5. Add Window Buffer Memory for conversation history",
                "6. Test via Chat interface",
            ],
            "required_nodes": [
                "@n8n/n8n-nodes-langchain.chatTrigger",
                "@n8n/n8n-nodes-langchain.agent",
                "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
                "@n8n/n8n-nodes-langchain.memoryBufferWindow",
            ],
            "tips": ["Set clear system prompt in AI Agent", "Add tools relevant to your use case"],
        },
        "data sync integration": {
            "title": "Data Sync Workflow",
            "description": "Source → Transform → Destination",
            "steps": [
                "1. Add Schedule Trigger (e.g., every hour)",
                "2. Add HTTP Request to fetch source data",
                "3. Add Code node to transform/map data",
                "4. Add IF node to filter duplicates",
                "5. Add destination node (Google Sheets, Database, etc.)",
            ],
            "required_nodes": ["scheduleTrigger", "httpRequest", "code", "if", "googleSheets OR postgres"],
            "tips": ["Store last sync timestamp in n8n variables", "Use Split in Batches for large datasets"],
        },
        "webhook api": {
            "title": "Webhook API Endpoint",
            "description": "Webhook → Validate → Process → Respond",
            "steps": [
                "1. Add Webhook trigger (POST method)",
                "2. Add IF node to validate incoming data",
                "3. Add Code node to process the request",
                "4. Add Respond to Webhook node with response",
            ],
            "required_nodes": ["webhook", "if", "code", "respondToWebhook"],
            "tips": ["Set responseMode='lastNode' for custom responses", "Validate required fields in IF node"],
        },
    }


def _get_template_catalog() -> List[Dict]:
    return [
        {"name": "Send email on webhook", "description": "Webhook → Gmail notification", "category": "Email", "tags": ["email", "webhook", "gmail"], "nodes": 3},
        {"name": "Daily Slack digest", "description": "Schedule → Aggregate data → Post to Slack", "category": "Communication", "tags": ["slack", "schedule", "daily"], "nodes": 4},
        {"name": "AI customer support", "description": "Chat trigger → AI Agent → Knowledge base", "category": "AI", "tags": ["ai", "chatbot", "support"], "nodes": 5},
        {"name": "Lead capture to CRM", "description": "Webhook → Validate → HubSpot", "category": "CRM", "tags": ["lead", "hubspot", "webhook"], "nodes": 4},
        {"name": "Google Sheets sync", "description": "Schedule → API fetch → Update Sheets", "category": "Data", "tags": ["sheets", "sync", "api"], "nodes": 4},
        {"name": "Error monitoring alert", "description": "Error trigger → Slack alert", "category": "Monitoring", "tags": ["error", "monitoring", "alert"], "nodes": 3},
        {"name": "PDF to data extraction", "description": "Webhook → AI extract → Database", "category": "AI", "tags": ["pdf", "ai", "extraction"], "nodes": 5},
        {"name": "Multi-step approval", "description": "Form → Email approval → Action", "category": "Process", "tags": ["approval", "email", "form"], "nodes": 6},
        {"name": "Social media scheduler", "description": "Schedule → Content → Post to platforms", "category": "Marketing", "tags": ["social", "schedule", "post"], "nodes": 5},
        {"name": "Database backup", "description": "Schedule → Export → Google Drive", "category": "DevOps", "tags": ["backup", "database", "schedule"], "nodes": 4},
    ]
