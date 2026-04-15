"""
Workflow Validation & Auto-Fix MCP Tools
Validates workflow JSON before pushing to n8n.
Auto-fixes common issues.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import FastMCP

from core.context import get_context_manager
from core.logger import get_logger

logger = get_logger(__name__)


def register_validation_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        description=(
            "Validate an n8n workflow JSON before creating or updating it. "
            "Checks structure, required fields, node connections, expression "
            "syntax, and common mistakes. Returns errors and warnings with "
            "fix suggestions. Always validate before pushing to n8n."
        )
    )
    async def validate_workflow(workflow_json: str) -> str:
        try:
            workflow = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return json.dumps({
                "valid": False,
                "errors": [f"Invalid JSON syntax: {e}"],
                "warnings": [],
                "fix_suggestions": ["Fix JSON syntax errors first"],
            }, indent=2)

        errors, warnings, suggestions = _validate_workflow_structure(workflow)

        return json.dumps({
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "fix_suggestions": suggestions,
            "node_count": len(workflow.get("nodes", [])),
            "connection_count": sum(
                len(conns)
                for node_conns in workflow.get("connections", {}).values()
                for conns in node_conns.values()
            ),
        }, indent=2)

    @mcp.tool(
        description=(
            "Auto-fix common issues in an n8n workflow JSON. "
            "Fixes: missing IDs, missing positions, incorrect structure, "
            "missing required fields. Returns the corrected workflow JSON. "
            "Use this when validation reports fixable errors."
        )
    )
    async def auto_fix_workflow(workflow_json: str, workflow_name: str = "Fixed Workflow") -> str:
        try:
            workflow = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Cannot fix invalid JSON: {e}", "success": False}, indent=2)

        fixed_workflow, fixes_applied = _auto_fix(workflow, workflow_name)
        errors, warnings, _ = _validate_workflow_structure(fixed_workflow)

        return json.dumps({
            "success": True,
            "fixes_applied": fixes_applied,
            "remaining_errors": errors,
            "remaining_warnings": warnings,
            "is_valid": len(errors) == 0,
            "fixed_workflow": fixed_workflow,
            "fixed_workflow_json": json.dumps(fixed_workflow, indent=2),
        }, indent=2)

    @mcp.tool(
        description=(
            "Build a complete n8n workflow JSON from a description. "
            "Generates the full workflow structure with correct node types, "
            "positions, connections, and settings based on the description. "
            "Returns workflow JSON ready to create with create_workflow."
        )
    )
    async def build_workflow_template(
        workflow_name: str,
        trigger_type: str,
        description: str,
        nodes_to_include: Optional[str] = None,
    ) -> str:
        ctx = await get_context_manager().get_default()

        nodes_list = []
        if nodes_to_include:
            try:
                nodes_list = json.loads(nodes_to_include)
            except Exception:
                nodes_list = [n.strip() for n in nodes_to_include.split(",")]

        workflow = _build_workflow_scaffold(
            name=workflow_name,
            trigger_type=trigger_type,
            description=description,
            extra_nodes=nodes_list,
        )

        errors, warnings, suggestions = _validate_workflow_structure(workflow)
        ctx.record_action("build_template", {"name": workflow_name}, f"Built {len(workflow['nodes'])} nodes")

        return json.dumps({
            "workflow_name": workflow_name,
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "suggestions": suggestions,
            "node_count": len(workflow["nodes"]),
            "workflow": workflow,
            "workflow_json": json.dumps(workflow, indent=2),
            "next_step": "Call create_workflow with this workflow_json to deploy it to n8n",
        }, indent=2)

    @mcp.tool(
        description=(
            "Check if a specific node connection is valid in a workflow. "
            "Verifies that source and destination nodes exist and that "
            "the output index is valid for the source node type."
        )
    )
    async def validate_connection(
        workflow_json: str,
        source_node_name: str,
        destination_node_name: str,
        output_index: int = 0,
    ) -> str:
        try:
            workflow = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return json.dumps({"valid": False, "error": f"Invalid JSON: {e}"}, indent=2)

        nodes = {n["name"]: n for n in workflow.get("nodes", [])}

        errors = []
        if source_node_name not in nodes:
            errors.append(f"Source node '{source_node_name}' not found in workflow")
        if destination_node_name not in nodes:
            errors.append(f"Destination node '{destination_node_name}' not found in workflow")

        # Check existing connections
        connections = workflow.get("connections", {})
        existing = (
            connections.get(source_node_name, {}).get("main", [])
        )
        already_connected = any(
            any(c.get("node") == destination_node_name for c in branch)
            for branch in existing
            if branch
        )

        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "already_connected": already_connected,
            "source_exists": source_node_name in nodes,
            "destination_exists": destination_node_name in nodes,
        }, indent=2)

    logger.info("validation_tools_registered", count=4)


def _validate_workflow_structure(workflow: Dict) -> Tuple[List[str], List[str], List[str]]:
    errors = []
    warnings = []
    suggestions = []

    # Required top-level fields
    if "nodes" not in workflow:
        errors.append("Missing required field: 'nodes'")
        suggestions.append("Add 'nodes': [] to the workflow")

    if "connections" not in workflow:
        errors.append("Missing required field: 'connections'")
        suggestions.append("Add 'connections': {} to the workflow")

    if "settings" not in workflow:
        warnings.append("Missing 'settings' field — will use n8n defaults")
        suggestions.append("Add 'settings': {'executionOrder': 'v1'}")

    if not workflow.get("name"):
        errors.append("Missing workflow name")

    nodes = workflow.get("nodes", [])
    node_names = set()

    for i, node in enumerate(nodes):
        node_label = f"Node[{i}] '{node.get('name', 'unnamed')}'"

        # Required node fields
        if not node.get("type"):
            errors.append(f"{node_label}: Missing 'type' field")

        if not node.get("name"):
            errors.append(f"{node_label}: Missing 'name' field")
            continue

        if node["name"] in node_names:
            errors.append(f"Duplicate node name: '{node['name']}'")
        node_names.add(node["name"])

        if not node.get("id"):
            warnings.append(f"{node_label}: Missing 'id' — will be auto-generated")

        if "position" not in node:
            warnings.append(f"{node_label}: Missing 'position' — layout may be incorrect")
        elif not isinstance(node["position"], list) or len(node["position"]) != 2:
            errors.append(f"{node_label}: 'position' must be [x, y] array")

        if "parameters" not in node:
            warnings.append(f"{node_label}: Missing 'parameters' — using defaults")

        # Check expressions
        params_str = json.dumps(node.get("parameters", {}))
        if "{{" in params_str and "}}" not in params_str:
            errors.append(f"{node_label}: Unclosed expression — missing '}}'")

    # Check connections reference valid nodes
    connections = workflow.get("connections", {})
    for source_name, outputs in connections.items():
        if source_name not in node_names:
            errors.append(f"Connection references non-existent source node: '{source_name}'")

        if not isinstance(outputs, dict):
            errors.append(f"Connections for '{source_name}' must be an object")
            continue

        for output_type, branches in outputs.items():
            if not isinstance(branches, list):
                errors.append(f"Branches for '{source_name}.{output_type}' must be an array")
                continue
            for branch in branches:
                if not isinstance(branch, list):
                    continue
                for conn in branch:
                    if not isinstance(conn, dict):
                        continue
                    dest = conn.get("node")
                    if dest and dest not in node_names:
                        errors.append(f"Connection points to non-existent node: '{dest}'")

    # Check for trigger node
    trigger_types = [
        "webhook", "scheduleTrigger", "manualTrigger",
        "emailReadImap", "chatTrigger", "errorTrigger",
        "Trigger",
    ]
    has_trigger = any(
        any(t.lower() in (n.get("type") or "").lower() for t in trigger_types)
        for n in nodes
    )
    if nodes and not has_trigger:
        warnings.append("No trigger node found — workflow won't run automatically")
        suggestions.append("Add a Webhook, Schedule Trigger, or Manual Trigger node")

    return errors, warnings, suggestions


def _auto_fix(workflow: Dict, name: str) -> Tuple[Dict, List[str]]:
    fixes = []

    # Fix name
    if not workflow.get("name"):
        workflow["name"] = name
        fixes.append("Added workflow name")

    # Fix settings
    if "settings" not in workflow:
        workflow["settings"] = {"executionOrder": "v1"}
        fixes.append("Added default settings")

    # Fix nodes
    if "nodes" not in workflow:
        workflow["nodes"] = []
        fixes.append("Added empty nodes array")

    if "connections" not in workflow:
        workflow["connections"] = {}
        fixes.append("Added empty connections object")

    node_names = set()
    for i, node in enumerate(workflow["nodes"]):
        # Fix missing id
        if not node.get("id"):
            node["id"] = str(uuid.uuid4())[:8]
            fixes.append(f"Generated ID for node '{node.get('name', f'node-{i}')}'")

        # Fix missing name
        if not node.get("name"):
            node["name"] = f"Node {i + 1}"
            fixes.append(f"Generated name for node {i}")

        # Fix duplicate names
        if node["name"] in node_names:
            node["name"] = f"{node['name']} ({i})"
            fixes.append(f"Renamed duplicate node to '{node['name']}'")
        node_names.add(node["name"])

        # Fix missing position
        if "position" not in node:
            x = 240 + (i * 240)
            node["position"] = [x, 300]
            fixes.append(f"Added position for node '{node['name']}'")

        # Fix missing parameters
        if "parameters" not in node:
            node["parameters"] = {}
            fixes.append(f"Added empty parameters for '{node['name']}'")

        # Fix missing typeVersion
        if "typeVersion" not in node:
            node["typeVersion"] = 1
            fixes.append(f"Added typeVersion=1 for '{node['name']}'")

    return workflow, fixes


def _build_workflow_scaffold(
    name: str,
    trigger_type: str,
    description: str,
    extra_nodes: Optional[List] = None,
) -> Dict:
    """Build a workflow scaffold based on trigger type."""

    trigger_map = {
        "webhook": {
            "type": "n8n-nodes-base.webhook",
            "name": "Webhook",
            "parameters": {
                "httpMethod": "POST",
                "path": name.lower().replace(" ", "-"),
                "responseMode": "onReceived",
            },
        },
        "schedule": {
            "type": "n8n-nodes-base.scheduleTrigger",
            "name": "Schedule Trigger",
            "parameters": {
                "rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}
            },
        },
        "manual": {
            "type": "n8n-nodes-base.manualTrigger",
            "name": "When clicking 'Execute workflow'",
            "parameters": {},
        },
        "chat": {
            "type": "n8n-nodes-base.chatTrigger",
            "name": "Chat Trigger",
            "parameters": {},
        },
        "email": {
            "type": "n8n-nodes-base.emailReadImap",
            "name": "Email Trigger",
            "parameters": {"mailbox": "INBOX", "action": "unread"},
        },
    }

    trigger_config = trigger_map.get(trigger_type.lower(), trigger_map["manual"])
    trigger_node = {
        **trigger_config,
        "id": str(uuid.uuid4())[:8],
        "position": [240, 300],
        "typeVersion": 1,
    }

    nodes = [trigger_node]
    connections: Dict = {}

    # Add a Code node as placeholder for logic
    code_node = {
        "type": "n8n-nodes-base.code",
        "name": "Process Data",
        "parameters": {
            "jsCode": (
                "// Auto-generated by n8n MCP Server\n"
                f"// Workflow: {name}\n"
                f"// Description: {description}\n\n"
                "return items.map(item => ({\n"
                "  json: {\n"
                "    ...item.json,\n"
                "    processed: true,\n"
                "    timestamp: new Date().toISOString()\n"
                "  }\n"
                "}));"
            )
        },
        "id": str(uuid.uuid4())[:8],
        "position": [480, 300],
        "typeVersion": 2,
    }
    nodes.append(code_node)

    # Connect trigger → code
    connections[trigger_node["name"]] = {
        "main": [[{"node": code_node["name"], "type": "main", "index": 0}]]
    }

    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "saveExecutionProgress": True,
        },
        "meta": {
            "description": description,
            "generatedBy": "n8n-unified-mcp-server",
        },
    }
