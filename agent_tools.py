#!/usr/bin/env python3
"""AI Agent Tools for Google Workspace Gmail API via Agent Identity Auth Manager.

Defines standardized tool functions and schema declarations compatible with Google GenAI SDK,
Gemini function calling, LangChain, and Vertex AI Agent Engines.
"""

from typing import Any, Dict, List, Optional
from auth_manager import AgentIdentityAuthManager
from gmail_client import GmailClient


# Module-level singleton caches for agent execution
_auth_manager: Optional[AgentIdentityAuthManager] = None
_gmail_client: Optional[GmailClient] = None


def get_clients(
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    auth_provider_name: Optional[str] = None,
) -> GmailClient:
    """Retrieve or initialize the active Gmail client with Agent Identity Auth Manager.

    Args:
        project_id: Optional GCP project ID override.
        location: Optional GCP region override.
        auth_provider_name: Optional Auth Provider name override.

    Returns:
        GmailClient: Authenticated Gmail client instance.
    """
    global _auth_manager, _gmail_client
    if _gmail_client is None:
        _auth_manager = AgentIdentityAuthManager(
            project_id=project_id,
            location=location,
            auth_provider_name=auth_provider_name,
        )
        _gmail_client = GmailClient(auth_manager=_auth_manager)
    return _gmail_client


# ============================================================================
# Agent Callable Functions
# ============================================================================

def get_workspace_access_token(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve the OAuth 2.0 Bearer Access Token from GCP Agent Identity Auth Manager.

    Use this tool when the user or agent needs the active bearer access token
    from the Google Cloud Auth Provider vault.

    Args:
        user_id: Optional target user email.

    Returns:
        Dict containing access_token and metadata.
    """
    client = get_clients()
    return client.auth_manager.get_token_details()


def revoke_workspace_access(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Revoke user authorization credentials from Google Cloud Agent Identity Auth Manager.

    Use this tool when the user requests to disconnect or revoke access.

    Args:
        user_id: Optional target user email to revoke.

    Returns:
        Dict with status and confirmation message.
    """
    client = get_clients()
    target_user = user_id or client.auth_manager.user_id
    client.auth_manager.revoke_credentials(user_id=target_user)
    return {
        "status": "revoked",
        "user_id": target_user,
        "message": f"Successfully revoked Google Workspace credentials for {target_user}."
    }


def get_gmail_profile() -> Dict[str, Any]:
    """Fetch the authenticated Gmail account profile (email address, message/thread count).

    Returns:
        Dict containing mailbox profile and message statistics.
    """
    client = get_clients()
    return client.get_profile()


def send_gmail_message(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an email using the Gmail API with credentials from Agent Identity Auth Manager.

    Args:
        to: Recipient email address (e.g. 'recipient@example.com').
        subject: Email subject.
        body_text: Plain text content of the email.
        body_html: Optional HTML version of the email.
        cc: Optional CC email address.

    Returns:
        Dict with status, message_id, and thread_id.
    """
    client = get_clients()
    res = client.send_email(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        cc=cc,
    )
    return {
        "status": "success",
        "message_id": res.get("id"),
        "thread_id": res.get("threadId"),
        "recipient": to,
        "subject": subject,
    }


def create_gmail_draft(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a draft email in the Gmail mailbox for user review without sending immediately.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body_text: Plain text content.
        body_html: Optional HTML content.

    Returns:
        Dict with status, draft_id, and message metadata.
    """
    client = get_clients()
    res = client.create_draft(to=to, subject=subject, body_text=body_text, body_html=body_html)
    return {
        "status": "success",
        "draft_id": res.get("id"),
        "message_id": res.get("message", {}).get("id"),
    }


def search_gmail_messages(query: str = "is:unread", max_results: int = 5) -> Dict[str, Any]:
    """Search for messages in Gmail matching a standard Gmail search query.

    Args:
        query: Search query (e.g. 'is:unread', 'from:alerts@example.com', 'subject:Report').
        max_results: Max messages to return (default: 5).

    Returns:
        Dict containing list of matching messages and count.
    """
    client = get_clients()
    messages = client.list_messages(query=query, max_results=max_results)
    return {
        "count": len(messages),
        "messages": messages,
    }


# ============================================================================
# Tool Declarations / Schemas for AI Agents (Gemini & OpenAPI Formats)
# ============================================================================

AGENT_TOOL_DEFINITIONS = [
    {
        "name": "get_workspace_access_token",
        "description": "Mint and return the OAuth2 Bearer Access Token from Agent Identity Auth Manager.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Optional target user ID"},
            },
        },
    },
    {
        "name": "revoke_workspace_access",
        "description": "Revoke and disconnect user credentials stored in Agent Identity Auth Manager.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Optional target user ID to revoke"},
            },
        },
    },
    {
        "name": "get_gmail_profile",
        "description": "Retrieve profile information and stats for the authenticated Gmail user.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "send_gmail_message",
        "description": "Send an email via Gmail API using the Auth Manager token.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Subject line"},
                "body_text": {"type": "string", "description": "Plain text message body"},
                "body_html": {"type": "string", "description": "Optional HTML message body"},
                "cc": {"type": "string", "description": "Optional CC recipient"},
            },
            "required": ["to", "subject", "body_text"],
        },
    },
    {
        "name": "create_gmail_draft",
        "description": "Create a draft email in the Gmail mailbox for user review.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Subject line"},
                "body_text": {"type": "string", "description": "Plain text message body"},
                "body_html": {"type": "string", "description": "Optional HTML body"},
            },
            "required": ["to", "subject", "body_text"],
        },
    },
    {
        "name": "search_gmail_messages",
        "description": "Search messages in the Gmail inbox using Gmail query syntax.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query syntax (e.g. 'is:unread')"},
                "max_results": {"type": "integer", "description": "Maximum number of messages to return"},
            },
            "required": ["query"],
        },
    },
]


def get_agent_tools() -> List[Dict[str, Any]]:
    """Return all AI agent tool definitions.

    Returns:
        List[Dict[str, Any]]: Array of tool schema definitions.
    """
    return AGENT_TOOL_DEFINITIONS

