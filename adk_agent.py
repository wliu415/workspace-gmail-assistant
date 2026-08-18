#!/usr/bin/env python3
"""Google ADK (Agent Development Kit) implementation for Gmail Assistant.

Demonstrates configuring an ADK LlmAgent with GcpAuthProvider and AuthenticatedFunctionTool
to automatically retrieve and inject credentials from Agent Identity Auth Manager.
"""

import os
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Check ADK availability
try:
    from google.adk.agents.llm_agent import LlmAgent
    from google.adk.auth.credential_manager import CredentialManager
    from google.adk.integrations.agent_identity import GcpAuthProvider, GcpAuthProviderScheme
    from google.adk.auth.auth_credential import AuthCredential
    from google.adk.auth.auth_tool import AuthConfig
    from google.adk.tools.authenticated_function_tool import AuthenticatedFunctionTool
    from google.adk.apps import App
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False


def setup_adk_agent(
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    auth_provider_name: Optional[str] = None,
    model_name: str = "gemini-2.5-flash",
) -> Tuple[Any, Any]:
    """Initialize an ADK LlmAgent wired to Google Cloud Agent Identity Auth Manager.

    Args:
        project_id: Optional GCP project ID override.
        location: Optional GCP region override (default: 'us-central1').
        auth_provider_name: Optional Auth Provider name override.
        model_name: Foundation model name (default: 'gemini-2.5-flash').

    Returns:
        Tuple[App, LlmAgent]: Configured ADK App and root Agent instances.

    Raises:
        ImportError: If google-adk is not installed in the Python environment.
    """
    if not ADK_AVAILABLE:
        raise ImportError(
            "google-adk is not installed. Install with:\n"
            "pip install google-cloud-aiplatform[agent_engines,adk] google-adk[agent-identity]"
        )

    project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    auth_provider_name = auth_provider_name or os.getenv("AGENT_AUTH_PROVIDER_NAME", "gmail-agent-auth-provider")

    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable or project_id parameter is required.")

    # 1. Register GCP Auth Provider with ADK CredentialManager
    CredentialManager.register_auth_provider(GcpAuthProvider())

    # 2. Configure Auth Scheme pointing to GCP Auth Provider resource
    auth_resource = f"projects/{project_id}/locations/{location}/authProviders/{auth_provider_name}"
    gmail_auth_config = AuthConfig(
        auth_scheme=GcpAuthProviderScheme(name=auth_resource)
    )

    # 3. Define Authenticated Function Tools
    async def send_email_tool(
        credential: AuthCredential,
        to: str,
        subject: str,
        body: str,
    ) -> str:
        """Send an email using credentials injected dynamically by Auth Manager."""
        token = credential.http.credentials.token if (credential.http and credential.http.credentials) else None
        if not token:
            return "Error: No authorization token provided by Auth Manager."

        from auth_manager import AgentIdentityAuthManager
        from gmail_client import GmailClient

        auth_mgr = AgentIdentityAuthManager(project_id=project_id, location=location, auth_provider_name=auth_provider_name)
        auth_mgr._cached_token = token
        client = GmailClient(auth_manager=auth_mgr)

        res = client.send_email(to=to, subject=subject, body_text=body)
        return f"Email sent successfully! Message ID: {res.get('id')}"

    async def get_token_tool(credential: AuthCredential) -> str:
        """Retrieve and return the bearer token from Auth Manager."""
        token = credential.http.credentials.token if (credential.http and credential.http.credentials) else None
        if not token:
            return "Error: No token available."
        return f"Active Bearer Token: {token}"

    auth_send_tool = AuthenticatedFunctionTool(func=send_email_tool, auth_config=gmail_auth_config)
    auth_token_tool = AuthenticatedFunctionTool(func=get_token_tool, auth_config=gmail_auth_config)

    # 4. Instantiate LLM Agent with System Instructions and Auth Tools
    agent = LlmAgent(
        name="workspace_gmail_agent",
        model=model_name,
        instruction=(
            "You are an automated Workspace Gmail Assistant. "
            "You have access to authenticated Gmail tools backed by Google Cloud Agent Identity Auth Manager. "
            "You can fetch access tokens, search emails, compose drafts, and send emails on behalf of authorized accounts."
        ),
        tools=[auth_send_tool, auth_token_tool],
    )

    app = App(name="workspace_gmail_app", root_agent=agent)
    return app, agent


if __name__ == "__main__":
    print("[*] ADK Agent configuration module.")
    if ADK_AVAILABLE:
        print("[✔] Google ADK and Agent Identity extensions detected.")
    else:
        print("[i] ADK not installed in current environment; use standalone auth_manager / cli.")

