"""
Execution Management & Debugging MCP Tools
Deep execution log analysis, error extraction, performance metrics.
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


def register_execution_tools(mcp: FastMCP) -> None:
    settings = get_settings()

    @mcp.tool(
        description=(
            "List recent workflow executions. Filter by workflow ID, status "
            "(success/error/running/waiting), and limit. Returns execution "
            "summaries with timing and status information."
        )
    )
    async def list_executions(
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        include_data: bool = False,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        cache_key = f"executions:list:{workflow_id}:{status}:{limit}"
        result = await cached(
            cache_key,
            lambda: client.list_executions(
                workflow_id=workflow_id,
                status=status,
                limit=limit,
                include_data=include_data,
            ),
            ttl=settings.cache_ttl_executions,
            enabled=settings.cache_enabled,
        )

        executions = result.get("data", [])
        summary = []
        for ex in executions:
            duration_ms = None
            if ex.get("startedAt") and ex.get("stoppedAt"):
                try:
                    from datetime import datetime
                    start = datetime.fromisoformat(ex["startedAt"].replace("Z", "+00:00"))
                    stop = datetime.fromisoformat(ex["stoppedAt"].replace("Z", "+00:00"))
                    duration_ms = round((stop - start).total_seconds() * 1000)
                except Exception:
                    pass

            summary.append({
                "id": ex.get("id"),
                "workflow_id": ex.get("workflowId"),
                "workflow_name": ex.get("workflowData", {}).get("name") if include_data else None,
                "status": ex.get("status"),
                "mode": ex.get("mode"),
                "started_at": ex.get("startedAt"),
                "stopped_at": ex.get("stoppedAt"),
                "duration_ms": duration_ms,
                "finished": ex.get("finished"),
            })

        ctx.record_action("list_executions", {"workflow_id": workflow_id, "status": status}, f"Found {len(summary)} executions")

        return json.dumps({
            "total": len(summary),
            "executions": summary,
            "next_cursor": result.get("nextCursor"),
        }, indent=2)

    @mcp.tool(
        description=(
            "Get full details of a specific execution including all node "
            "outputs, error messages, and execution data. Essential for "
            "debugging failed workflows. Returns node-by-node results."
        )
    )
    async def get_execution_details(
        execution_id: str,
        include_full_data: bool = True,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        result = await client.get_execution(execution_id, include_data=include_full_data)

        # Extract error information
        error_info = _extract_errors(result)
        node_results = _extract_node_results(result)

        ctx.record_action("get_execution_details", {"id": execution_id}, f"Status: {result.get('status')}")

        return json.dumps({
            "execution_id": execution_id,
            "status": result.get("status"),
            "mode": result.get("mode"),
            "started_at": result.get("startedAt"),
            "stopped_at": result.get("stoppedAt"),
            "finished": result.get("finished"),
            "errors": error_info,
            "node_results": node_results,
            "raw_data": result if include_full_data else None,
        }, indent=2)

    @mcp.tool(
        description=(
            "Analyze failed executions for a workflow and provide detailed "
            "error analysis with root cause identification and fix suggestions. "
            "This is the primary debugging tool — use it when workflows fail."
        )
    )
    async def analyze_workflow_errors(
        workflow_id: str,
        last_n: int = 5,
    ) -> str:
        client = get_n8n_client()
        ctx = await get_context_manager().get_default()

        # Get failed executions
        result = await client.list_executions(
            workflow_id=workflow_id,
            status="error",
            limit=last_n,
            include_data=True,
        )

        executions = result.get("data", [])
        if not executions:
            return json.dumps({
                "message": "No failed executions found for this workflow.",
                "workflow_id": workflow_id,
            }, indent=2)

        analyses = []
        for ex in executions:
            errors = _extract_errors(ex)
            node_results = _extract_node_results(ex)
            failed_nodes = [n for n in node_results if n.get("error")]

            analysis = {
                "execution_id": ex.get("id"),
                "started_at": ex.get("startedAt"),
                "errors": errors,
                "failed_nodes": failed_nodes,
                "fix_suggestions": _generate_fix_suggestions(errors, failed_nodes),
            }
            analyses.append(analysis)

        ctx.record_action("analyze_errors", {"workflow_id": workflow_id}, f"Analyzed {len(analyses)} failures")

        return json.dumps({
            "workflow_id": workflow_id,
            "total_failures_analyzed": len(analyses),
            "analyses": analyses,
            "recommended_action": _recommend_action(analyses),
        }, indent=2)

    @mcp.tool(
        description=(
            "Get execution performance metrics for a workflow. "
            "Returns average duration, success rate, peak times, "
            "and performance trends for optimization."
        )
    )
    async def get_execution_metrics(
        workflow_id: str,
        limit: int = 50,
    ) -> str:
        client = get_n8n_client()

        result = await client.list_executions(
            workflow_id=workflow_id,
            limit=limit,
            include_data=False,
        )

        executions = result.get("data", [])
        if not executions:
            return json.dumps({"message": "No executions found", "workflow_id": workflow_id}, indent=2)

        durations = []
        statuses: Dict[str, int] = {}
        from datetime import datetime

        for ex in executions:
            status = ex.get("status", "unknown")
            statuses[status] = statuses.get(status, 0) + 1

            if ex.get("startedAt") and ex.get("stoppedAt"):
                try:
                    start = datetime.fromisoformat(ex["startedAt"].replace("Z", "+00:00"))
                    stop = datetime.fromisoformat(ex["stoppedAt"].replace("Z", "+00:00"))
                    durations.append((stop - start).total_seconds() * 1000)
                except Exception:
                    pass

        total = len(executions)
        success_count = statuses.get("success", 0)

        metrics = {
            "workflow_id": workflow_id,
            "total_executions": total,
            "status_breakdown": statuses,
            "success_rate_pct": round(success_count / total * 100, 2) if total > 0 else 0,
        }

        if durations:
            metrics["performance"] = {
                "avg_duration_ms": round(sum(durations) / len(durations)),
                "min_duration_ms": round(min(durations)),
                "max_duration_ms": round(max(durations)),
                "p95_duration_ms": round(sorted(durations)[int(len(durations) * 0.95)]),
            }

        return json.dumps(metrics, indent=2)

    @mcp.tool(
        description=(
            "Get the most recent execution of any workflow and return "
            "a detailed summary. Useful for quick status checks."
        )
    )
    async def get_latest_execution(workflow_id: str) -> str:
        client = get_n8n_client()

        result = await client.list_executions(
            workflow_id=workflow_id,
            limit=1,
            include_data=True,
        )

        executions = result.get("data", [])
        if not executions:
            return json.dumps({"message": "No executions found", "workflow_id": workflow_id}, indent=2)

        ex = executions[0]
        errors = _extract_errors(ex)
        node_results = _extract_node_results(ex)

        return json.dumps({
            "execution_id": ex.get("id"),
            "status": ex.get("status"),
            "started_at": ex.get("startedAt"),
            "stopped_at": ex.get("stoppedAt"),
            "errors": errors,
            "node_results": node_results,
        }, indent=2)

    logger.info("execution_tools_registered", count=5)


def _extract_errors(execution: Dict) -> List[Dict]:
    errors = []
    data = execution.get("data", {})
    if not data:
        return errors

    result_data = data.get("resultData", {})
    run_data = result_data.get("runData", {})

    for node_name, node_runs in run_data.items():
        for run in (node_runs or []):
            error = run.get("error")
            if error:
                errors.append({
                    "node": node_name,
                    "error_message": error.get("message", str(error)),
                    "error_type": error.get("name", "UnknownError"),
                    "stack": error.get("stack", "")[:500],
                })

    return errors


def _extract_node_results(execution: Dict) -> List[Dict]:
    results = []
    data = execution.get("data", {})
    if not data:
        return results

    result_data = data.get("resultData", {})
    run_data = result_data.get("runData", {})

    for node_name, node_runs in run_data.items():
        for run in (node_runs or []):
            error = run.get("error")
            output_data = run.get("data", {})
            item_count = 0

            if output_data and isinstance(output_data, dict):
                main = output_data.get("main", [[]])
                if main and main[0]:
                    item_count = len(main[0])

            results.append({
                "node": node_name,
                "status": "error" if error else "success",
                "output_items": item_count,
                "execution_time_ms": run.get("executionTime"),
                "error": error.get("message") if error else None,
            })

    return results


def _generate_fix_suggestions(errors: List[Dict], failed_nodes: List[Dict]) -> List[str]:
    suggestions = []

    for error in errors:
        msg = (error.get("error_message") or "").lower()
        node = error.get("node", "")

        if "authentication" in msg or "401" in msg or "unauthorized" in msg:
            suggestions.append(f"🔑 Node '{node}': Check credentials — re-authenticate in n8n Settings > Credentials")
        elif "timeout" in msg:
            suggestions.append(f"⏱️ Node '{node}': Increase timeout in node settings or check external service availability")
        elif "not found" in msg or "404" in msg:
            suggestions.append(f"🔍 Node '{node}': Verify the resource URL/ID exists and is accessible")
        elif "rate limit" in msg or "429" in msg:
            suggestions.append(f"🚦 Node '{node}': Add Wait node before this node to respect rate limits")
        elif "json" in msg or "parse" in msg:
            suggestions.append(f"📄 Node '{node}': Check that previous node output is valid JSON format")
        elif "connection" in msg or "econnrefused" in msg:
            suggestions.append(f"🔌 Node '{node}': Service is unreachable — check URL and network connectivity")
        elif "expression" in msg:
            suggestions.append(f"💻 Node '{node}': Fix expression syntax — use {{ $json.fieldName }} format")
        else:
            suggestions.append(f"⚠️ Node '{node}': Review error: {error.get('error_message', '')[:100]}")

    if not suggestions:
        suggestions.append("Check n8n logs for more details: Settings > Log Streaming")

    return suggestions


def _recommend_action(analyses: List[Dict]) -> str:
    all_errors = []
    for a in analyses:
        all_errors.extend(a.get("errors", []))

    if not all_errors:
        return "No specific recommendation — review workflow logic manually."

    error_types: Dict[str, int] = {}
    for e in all_errors:
        t = e.get("error_type", "Unknown")
        error_types[t] = error_types.get(t, 0) + 1

    most_common = max(error_types, key=lambda k: error_types[k])

    recommendations = {
        "NodeOperationError": "Fix node configuration — likely missing required fields or wrong settings",
        "AuthenticationError": "Update credentials in n8n Settings → Credentials",
        "WorkflowOperationError": "Check workflow structure and node connections",
        "ExpressionError": "Fix expression syntax — review all {{ }} expressions",
    }

    return recommendations.get(most_common, f"Most common error: {most_common} — check node configuration")
