"""
Workflow Management MCP Tools
Covers: list, get, create, update, delete, activate, deactivate, run
All tools are context-aware and cache-optimized.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from config import get_settings
from core.cache import cached, get_cache
from core.context import get_context_manager
from core.logger import get_logger
from core.n8n_client import get_n8n_client

logger = get_logger(__name__)


def register_workflow_tools(mcp: FastMCP) -> None:
    settings = get_settings()

    @mcp.tool(
        description=(
            "List all n8n workflows. Returns workflow IDs, names, status, "
            "node count, and last update time. Use this first to discover "
            "what workflows exist before operating on them."
        )
    )
    async def list_workflows(
        active_only: bool = False,
        tag: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        cache_key = f"workflows:list:{active_only}:{tag}:{limit}"
        result = await cached(
            cache_key,
            lambda: client.list_workflows(
                active=True if active_only else None,
                tags=tag,
                limit=limit,
            ),
            ttl=settings.cache_ttl_workflows,
            enabled=settings.cache_enabled,
        )

        workflows = result.get("data", [])
        summary = []
        for w in workflows:
            nodes = w.get("nodes", [])
            summary.append({
                "id": w.get("id"),
                "name": w.get("name"),
                "active": w.get("active", False),
                "node_count": len(nodes),
                "tags": [t.get("name") for t in w.get("tags", [])],
                "updated_at": w.get("updatedAt"),
                "created_at": w.get("createdAt"),
            })

        ctx.record_action("list_workflows", {"active_only": active_only}, f"Found {len(summary)} workflows")
        return json.dumps({
            "total": len(summary),
            "workflows": summary,
            "next_cursor": result.get("nextCursor"),
        }, indent=2)

    @mcp.tool(
        description=(
            "Get complete details of a specific n8n workflow by ID. "
            "Returns full workflow JSON including all nodes, connections, "
            "settings, and credentials. Always call this before modifying "
            "a workflow to get the current state."
        )
    )
    async def get_workflow(workflow_id: str) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        cache_key = f"workflow:{workflow_id}"
        result = await cached(
            cache_key,
            lambda: client.get_workflow(workflow_id),
            ttl=settings.cache_ttl_workflows,
            enabled=settings.cache_enabled,
        )

        ctx.set_current_workflow(workflow_id, result)
        ctx.record_action("get_workflow", {"id": workflow_id}, f"Fetched: {result.get('name')}")

        return json.dumps(result, indent=2)

    @mcp.tool(
        description=(
            "Create a new n8n workflow from a JSON definition. "
            "The workflow_json must be a valid n8n workflow structure "
            "with 'name', 'nodes', 'connections', and 'settings' fields. "
            "Returns the created workflow with its assigned ID."
        )
    )
    async def create_workflow(
        name: str,
        workflow_json: str,
        activate_immediately: bool = False,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()
        cache = get_cache()

        try:
            payload = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}", "success": False})

        payload["name"] = name

        # Ensure required fields
        if "nodes" not in payload:
            payload["nodes"] = []
        if "connections" not in payload:
            payload["connections"] = {}
        if "settings" not in payload:
            payload["settings"] = {"executionOrder": "v1"}

        result = await client.create_workflow(payload)
        workflow_id = result.get("id")

        # Optionally activate
        if activate_immediately and workflow_id:
            try:
                await client.activate_workflow(workflow_id)
                result["active"] = True
            except Exception as e:
                result["activation_warning"] = str(e)

        # Invalidate workflow list cache
        await cache.delete_pattern("workflows:list:")
        if workflow_id:
            ctx.set_current_workflow(workflow_id, result)

        ctx.record_action("create_workflow", {"name": name}, f"Created ID: {workflow_id}")
        logger.info("workflow_created", name=name, id=workflow_id)

        return json.dumps({
            "success": True,
            "workflow_id": workflow_id,
            "name": result.get("name"),
            "active": result.get("active", False),
            "node_count": len(result.get("nodes", [])),
            "workflow": result,
        }, indent=2)

    @mcp.tool(
        description=(
            "Update an existing n8n workflow. Provide the workflow_id and "
            "the complete updated workflow JSON. Always fetch the current "
            "workflow with get_workflow first, modify it, then call this. "
            "Replaces the entire workflow definition."
        )
    )
    async def update_workflow(
        workflow_id: str,
        workflow_json: str,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()
        cache = get_cache()

        try:
            payload = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}", "success": False})

        result = await client.update_workflow(workflow_id, payload)

        # Invalidate caches
        await cache.delete(f"workflow:{workflow_id}")
        await cache.delete_pattern("workflows:list:")

        ctx.set_current_workflow(workflow_id, result)
        ctx.record_action("update_workflow", {"id": workflow_id}, f"Updated: {result.get('name')}")
        logger.info("workflow_updated", id=workflow_id)

        return json.dumps({
            "success": True,
            "workflow_id": workflow_id,
            "name": result.get("name"),
            "active": result.get("active", False),
            "node_count": len(result.get("nodes", [])),
        }, indent=2)

    @mcp.tool(
        description=(
            "Add or modify a single node in an existing workflow. "
            "Fetches the current workflow, adds/updates the node, "
            "and saves. Much safer than replacing the entire workflow. "
            "node_config must be a valid n8n node JSON object."
        )
    )
    async def upsert_node_in_workflow(
        workflow_id: str,
        node_config: str,
        node_name: Optional[str] = None,
    ) -> str:
        client = get_n8n_client()
        cache = get_cache()
        ctx = await get_context_manager().get_default()

        # Fetch current
        workflow = await client.get_workflow(workflow_id)

        try:
            new_node = json.loads(node_config)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid node JSON: {e}", "success": False})

        nodes: List[Dict] = workflow.get("nodes", [])
        target_name = node_name or new_node.get("name")

        # Replace if exists, else append
        replaced = False
        for i, node in enumerate(nodes):
            if node.get("name") == target_name:
                nodes[i] = new_node
                replaced = True
                break

        if not replaced:
            nodes.append(new_node)

        workflow["nodes"] = nodes
        result = await client.update_workflow(workflow_id, workflow)

        await cache.delete(f"workflow:{workflow_id}")
        await cache.delete_pattern("workflows:list:")

        action = "replaced" if replaced else "added"
        ctx.record_action("upsert_node", {"workflow_id": workflow_id, "node": target_name}, f"Node {action}")

        return json.dumps({
            "success": True,
            "action": action,
            "node_name": target_name,
            "total_nodes": len(result.get("nodes", [])),
        }, indent=2)

    @mcp.tool(
        description=(
            "Delete an n8n workflow permanently by ID. "
            "This action is irreversible. Confirm the workflow ID "
            "is correct before calling this tool."
        )
    )
    async def delete_workflow(workflow_id: str, confirm: bool = False) -> str:
        if not confirm:
            return json.dumps({
                "error": "Set confirm=True to permanently delete this workflow.",
                "success": False,
            })

        client = get_n8n_client()
        cache = get_cache()
        ctx = await get_context_manager().get_default()

        result = await client.delete_workflow(workflow_id)

        await cache.delete(f"workflow:{workflow_id}")
        await cache.delete_pattern("workflows:list:")

        ctx.record_action("delete_workflow", {"id": workflow_id}, "Deleted")
        logger.warning("workflow_deleted", id=workflow_id)

        return json.dumps({"success": True, "deleted_id": workflow_id}, indent=2)

    @mcp.tool(
        description="Activate an n8n workflow so it responds to triggers and runs on schedule."
    )
    async def activate_workflow(workflow_id: str) -> str:
        client = get_n8n_client()
        cache = get_cache()
        ctx = await get_context_manager().get_default()

        result = await client.activate_workflow(workflow_id)
        await cache.delete(f"workflow:{workflow_id}")
        await cache.delete_pattern("workflows:list:")

        ctx.record_action("activate_workflow", {"id": workflow_id}, "Activated")
        return json.dumps({"success": True, "active": True, "workflow_id": workflow_id}, indent=2)

    @mcp.tool(
        description="Deactivate an n8n workflow to stop it from running automatically."
    )
    async def deactivate_workflow(workflow_id: str) -> str:
        client = get_n8n_client()
        cache = get_cache()
        ctx = await get_context_manager().get_default()

        result = await client.deactivate_workflow(workflow_id)
        await cache.delete(f"workflow:{workflow_id}")
        await cache.delete_pattern("workflows:list:")

        ctx.record_action("deactivate_workflow", {"id": workflow_id}, "Deactivated")
        return json.dumps({"success": True, "active": False, "workflow_id": workflow_id}, indent=2)

    @mcp.tool(
        description=(
            "Manually trigger/execute an n8n workflow. "
            "Optionally pass input data as JSON string. "
            "Returns the execution ID for tracking."
        )
    )
    async def execute_workflow(
        workflow_id: str,
        input_data: Optional[str] = None,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        run_data: Dict[str, Any] = {}
        if input_data:
            try:
                run_data = json.loads(input_data)
            except json.JSONDecodeError:
                run_data = {"input": input_data}

        result = await client.run_workflow(workflow_id, run_data)
        ctx.record_action("execute_workflow", {"id": workflow_id}, f"Execution: {result.get('executionId')}")

        return json.dumps({
            "success": True,
            "execution_id": result.get("executionId"),
            "workflow_id": workflow_id,
            "status": result.get("waitTill", "running"),
        }, indent=2)

    @mcp.tool(
        description=(
            "Duplicate an existing workflow with a new name. "
            "Fetches the source workflow, removes the ID, "
            "renames it, and creates a copy."
        )
    )
    async def duplicate_workflow(
        source_workflow_id: str,
        new_name: str,
        activate: bool = False,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        # Fetch original
        original = await client.get_workflow(source_workflow_id)

        # Remove identity fields
        for field in ["id", "createdAt", "updatedAt", "versionId"]:
            original.pop(field, None)

        original["name"] = new_name
        original["active"] = False  # Start inactive

        result = await client.create_workflow(original)
        new_id = result.get("id")

        if activate and new_id:
            await client.activate_workflow(new_id)
            result["active"] = True

        ctx.record_action("duplicate_workflow", {"source": source_workflow_id, "new_name": new_name}, f"Created: {new_id}")

        return json.dumps({
            "success": True,
            "new_workflow_id": new_id,
            "new_name": new_name,
            "source_id": source_workflow_id,
            "active": result.get("active", False),
        }, indent=2)

    logger.info("workflow_tools_registered", count=7)
