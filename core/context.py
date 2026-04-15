"""
Context Memory System
Tracks workflow building context across tool calls within a session.
Enables AI agents to make smarter, context-aware decisions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WorkflowContext:
    """Tracks the current workflow being worked on."""
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    workflow_data: Optional[Dict] = None
    last_fetched: Optional[datetime] = None
    pending_changes: List[Dict] = field(default_factory=list)
    error_history: List[Dict] = field(default_factory=list)
    node_count: int = 0


@dataclass
class SessionContext:
    """Full session context for AI agent."""
    session_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)
    current_workflow: WorkflowContext = field(default_factory=WorkflowContext)
    action_history: List[Dict] = field(default_factory=list)
    workflow_ids_touched: List[str] = field(default_factory=list)
    total_actions: int = 0
    ai_suggestions: List[str] = field(default_factory=list)

    def record_action(self, tool: str, params: Dict, result_summary: str) -> None:
        self.action_history.append({
            "tool": tool,
            "params": params,
            "result": result_summary,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.total_actions += 1
        self.last_active = datetime.utcnow()
        # Keep last 50 actions
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]

    def set_current_workflow(self, workflow_id: str, workflow_data: Dict) -> None:
        self.current_workflow = WorkflowContext(
            workflow_id=workflow_id,
            workflow_name=workflow_data.get("name", "Unknown"),
            workflow_data=workflow_data,
            last_fetched=datetime.utcnow(),
            node_count=len(workflow_data.get("nodes", [])),
        )
        if workflow_id not in self.workflow_ids_touched:
            self.workflow_ids_touched.append(workflow_id)

    def add_error(self, error: str, context: str) -> None:
        self.current_workflow.error_history.append({
            "error": error,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_summary(self) -> Dict:
        return {
            "session_id": self.session_id,
            "total_actions": self.total_actions,
            "current_workflow": self.current_workflow.workflow_name,
            "current_workflow_id": self.current_workflow.workflow_id,
            "workflows_touched": self.workflow_ids_touched,
            "recent_actions": self.action_history[-5:],
            "ai_suggestions": self.ai_suggestions[-3:],
            "session_age_minutes": round(
                (datetime.utcnow() - self.created_at).total_seconds() / 60, 1
            ),
        }


class ContextManager:
    """
    In-memory session context manager.
    Supports multiple concurrent sessions (one per AI client).
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()
        self._default_session = SessionContext(session_id="default")

    async def get_session(self, session_id: str = "default") -> SessionContext:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionContext(session_id=session_id)
                logger.info("context_session_created", session_id=session_id)
            return self._sessions[session_id]

    async def clear_session(self, session_id: str = "default") -> None:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("context_session_cleared", session_id=session_id)

    async def get_default(self) -> SessionContext:
        return await self.get_session("default")

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)


# Global context manager singleton
_ctx_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    global _ctx_manager
    if _ctx_manager is None:
        _ctx_manager = ContextManager()
    return _ctx_manager
