"""
Production-Grade Async n8n API Client
- Connection pooling
- Automatic retries with exponential backoff
- Full API coverage
- Comprehensive error handling
- Request/response logging
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)


class N8NAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class N8NClient:
    """
    Async HTTP client for n8n REST API v1.
    Thread-safe, connection-pooled, retry-capable.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=f"{self.settings.n8n_base_url}/api/v1",
                    headers={
                        "X-N8N-API-KEY": self.settings.n8n_api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": f"{self.settings.server_name}/{self.settings.server_version}",
                    },
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=self.settings.n8n_api_timeout,
                        write=15.0,
                        pool=5.0,
                    ),
                    limits=httpx.Limits(
                        max_connections=self.settings.n8n_max_connections,
                        max_keepalive_connections=10,
                        keepalive_expiry=30,
                    ),
                    follow_redirects=True,
                )
        return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict] = None,
        json: Optional[Any] = None,
    ) -> Any:
        client = await self._get_client()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.n8n_api_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await client.request(
                        method=method,
                        url=path,
                        params=params,
                        json=json,
                    )
                    logger.debug(
                        "n8n_api_request",
                        method=method,
                        path=path,
                        status=response.status_code,
                    )
                    if response.status_code == 404:
                        raise N8NAPIError(
                            f"Resource not found: {path}",
                            status_code=404,
                        )
                    if response.status_code == 401:
                        raise N8NAPIError(
                            "Authentication failed — check N8N_API_KEY",
                            status_code=401,
                        )
                    if response.status_code == 429:
                        raise N8NAPIError(
                            "n8n rate limit exceeded — slow down requests",
                            status_code=429,
                        )
                    response.raise_for_status()

                    if response.content:
                        return response.json()
                    return {}

                except httpx.HTTPStatusError as e:
                    detail = ""
                    try:
                        detail = e.response.json().get("message", str(e))
                    except Exception:
                        detail = str(e)
                    raise N8NAPIError(
                        f"n8n API error {e.response.status_code}: {detail}",
                        status_code=e.response.status_code,
                        detail=detail,
                    )

    # ── Workflow Operations ──────────────────────────────────────────────────

    async def list_workflows(
        self,
        active: Optional[bool] = None,
        tags: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict:
        params: Dict[str, Any] = {"limit": limit}
        if active is not None:
            params["active"] = str(active).lower()
        if tags:
            params["tags"] = tags
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/workflows", params=params)

    async def get_workflow(self, workflow_id: str) -> Dict:
        return await self._request("GET", f"/workflows/{workflow_id}")

    async def create_workflow(self, payload: Dict) -> Dict:
        return await self._request("POST", "/workflows", json=payload)

    async def update_workflow(self, workflow_id: str, payload: Dict) -> Dict:
        return await self._request("PUT", f"/workflows/{workflow_id}", json=payload)

    async def delete_workflow(self, workflow_id: str) -> Dict:
        return await self._request("DELETE", f"/workflows/{workflow_id}")

    async def activate_workflow(self, workflow_id: str) -> Dict:
        return await self._request("POST", f"/workflows/{workflow_id}/activate")

    async def deactivate_workflow(self, workflow_id: str) -> Dict:
        return await self._request("POST", f"/workflows/{workflow_id}/deactivate")

    async def run_workflow(
        self,
        workflow_id: str,
        run_data: Optional[Dict] = None,
    ) -> Dict:
        payload = run_data or {}
        return await self._request(
            "POST", f"/workflows/{workflow_id}/run", json=payload
        )

    async def get_workflow_tags(self, workflow_id: str) -> List:
        result = await self._request("GET", f"/workflows/{workflow_id}/tags")
        return result if isinstance(result, list) else []

    async def update_workflow_tags(self, workflow_id: str, tag_ids: List[str]) -> List:
        return await self._request(
            "PUT",
            f"/workflows/{workflow_id}/tags",
            json=[{"id": t} for t in tag_ids],
        )

    # ── Execution Operations ─────────────────────────────────────────────────

    async def list_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
        include_data: bool = False,
    ) -> Dict:
        params: Dict[str, Any] = {
            "limit": limit,
            "includeData": str(include_data).lower(),
        }
        if workflow_id:
            params["workflowId"] = workflow_id
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/executions", params=params)

    async def get_execution(
        self,
        execution_id: str,
        include_data: bool = True,
    ) -> Dict:
        params = {"includeData": str(include_data).lower()}
        return await self._request(
            "GET", f"/executions/{execution_id}", params=params
        )

    async def delete_execution(self, execution_id: str) -> Dict:
        return await self._request("DELETE", f"/executions/{execution_id}")

    # ── Credential Operations ────────────────────────────────────────────────

    async def list_credentials(self, type_filter: Optional[str] = None) -> Dict:
        params = {}
        if type_filter:
            params["type"] = type_filter
        return await self._request("GET", "/credentials", params=params)

    async def get_credential_schema(self, credential_type: str) -> Dict:
        return await self._request(
            "GET", f"/credentials/schema/{credential_type}"
        )

    async def create_credential(self, payload: Dict) -> Dict:
        return await self._request("POST", "/credentials", json=payload)

    async def delete_credential(self, credential_id: str) -> Dict:
        return await self._request("DELETE", f"/credentials/{credential_id}")

    # ── Tags Operations ──────────────────────────────────────────────────────

    async def list_tags(self) -> Dict:
        return await self._request("GET", "/tags")

    async def create_tag(self, name: str) -> Dict:
        return await self._request("POST", "/tags", json={"name": name})

    # ── Variable Operations ──────────────────────────────────────────────────

    async def list_variables(self) -> Dict:
        return await self._request("GET", "/variables")

    # ── Audit ────────────────────────────────────────────────────────────────

    async def generate_audit(self) -> Dict:
        return await self._request("POST", "/audit")

    # ── Source Control ───────────────────────────────────────────────────────

    async def pull_from_source_control(self) -> Dict:
        return await self._request("POST", "/source-control/pull")

    # ── Health Check ─────────────────────────────────────────────────────────

    async def health_check(self) -> Dict:
        try:
            result = await self._request("GET", "/workflows", params={"limit": 1})
            return {"status": "healthy", "n8n_reachable": True}
        except Exception as e:
            return {"status": "unhealthy", "n8n_reachable": False, "error": str(e)}


# Global singleton client
_client_instance: Optional[N8NClient] = None


def get_n8n_client() -> N8NClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = N8NClient()
    return _client_instance
