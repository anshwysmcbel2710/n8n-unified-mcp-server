"""
Credential Management MCP Tools
List, inspect, and manage n8n credentials securely.
"""

from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.cache import cached
from config import get_settings
from core.logger import get_logger
from core.n8n_client import get_n8n_client

logger = get_logger(__name__)


def register_credential_tools(mcp: FastMCP) -> None:
    settings = get_settings()

    @mcp.tool(
        description=(
            "List all credentials configured in n8n. Returns credential names, "
            "types, and IDs (never actual secrets). Use this to see what "
            "credentials are available to reference in workflow nodes."
        )
    )
    async def list_credentials(type_filter: Optional[str] = None) -> str:
        client = get_n8n_client()

        result = await cached(
            f"credentials:list:{type_filter}",
            lambda: client.list_credentials(type_filter),
            ttl=120,
            enabled=settings.cache_enabled,
        )

        creds = result.get("data", [])
        safe_creds = []
        for c in creds:
            safe_creds.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "type": c.get("type"),
                "created_at": c.get("createdAt"),
                "updated_at": c.get("updatedAt"),
            })

        return json.dumps({
            "total": len(safe_creds),
            "credentials": safe_creds,
            "note": "Credential values are never exposed — only names and types",
        }, indent=2)

    @mcp.tool(
        description=(
            "Get the schema/required fields for a specific credential type. "
            "Use this to understand what fields are needed to configure "
            "a particular credential (e.g., 'gmailOAuth2', 'slackApi', 'openAiApi')."
        )
    )
    async def get_credential_schema(credential_type: str) -> str:
        client = get_n8n_client()

        result = await cached(
            f"credential:schema:{credential_type}",
            lambda: client.get_credential_schema(credential_type),
            ttl=3600,
            enabled=settings.cache_enabled,
        )

        return json.dumps({
            "credential_type": credential_type,
            "schema": result,
        }, indent=2)

    @mcp.tool(
        description=(
            "Get the common credential type names used in n8n node configurations. "
            "Returns a reference map of node types to their credential type strings."
        )
    )
    async def get_credential_types_reference() -> str:
        reference = {
            "Gmail": "gmailOAuth2",
            "Google Sheets": "googleSheetsOAuth2Api",
            "Google Drive": "googleDriveOAuth2Api",
            "Google Calendar": "googleCalendarOAuth2Api",
            "Slack": "slackApi OR slackOAuth2Api",
            "Telegram": "telegramApi",
            "OpenAI": "openAiApi",
            "Anthropic/Claude": "anthropicApi",
            "HubSpot": "hubspotApi OR hubspotOAuth2Api",
            "Salesforce": "salesforceOAuth2Api",
            "Notion": "notionApi",
            "Airtable": "airtableTokenApi",
            "GitHub": "githubApi",
            "Stripe": "stripeApi",
            "PostgreSQL": "postgres",
            "MongoDB": "mongoDb",
            "Redis": "redis",
            "HTTP Request (Basic Auth)": "httpBasicAuth",
            "HTTP Request (Header Auth)": "httpHeaderAuth",
            "HTTP Request (Bearer Token)": "httpBearerAuth",
            "SMTP Email": "smtp",
            "IMAP Email": "imap",
        }

        return json.dumps({
            "credential_type_reference": reference,
            "usage_note": (
                "Reference credentials in node config as: "
                "'credentials': {'credentialType': {'id': 'CREDENTIAL_ID', 'name': 'My Credential'}}"
            ),
        }, indent=2)

    logger.info("credential_tools_registered", count=3)
