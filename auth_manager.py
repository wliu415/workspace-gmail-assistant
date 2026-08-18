#!/usr/bin/env python3
"""Google Cloud Agent Identity Auth Manager.

Integrates with Google Cloud IAM Agent Identity Auth Manager
(https://docs.cloud.google.com/iam/docs/auth-manager-overview).
Acts as a centralized credentials vault & authentication broker for AI agents.
"""

import datetime
import os
import time
from typing import Any, Dict, List, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import webbrowser
import requests

import google.auth
from google.auth.credentials import Credentials as BaseCredentials
from google.auth.transport.requests import Request
from google.cloud.agentidentitycredentials_v1 import (
    AuthProviderCredentialsServiceClient,
    RetrieveCredentialsRequest,
    FinalizeCredentialsRequest,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Default OAuth 2.0 Scopes required for Gmail operations
DEFAULT_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class AuthManagerCredentials(BaseCredentials):
    """Google Auth Credentials adapter for Agent Identity Auth Manager.

    Allows google-api-python-client (googleapiclient) to seamlessly use tokens
    managed and dynamically refreshed by Google Cloud Agent Identity Auth Manager.
    """

    def __init__(self, auth_manager: "AgentIdentityAuthManager"):
        """Initialize the credentials wrapper.

        Args:
            auth_manager: The AgentIdentityAuthManager instance supplying tokens.
        """
        super().__init__()
        self.auth_manager = auth_manager
        self.token: Optional[str] = None
        self.expiry: Optional[datetime.datetime] = None

    def refresh(self, request=None):
        """Fetch/refresh token from Google Cloud Agent Identity Auth Manager.

        Args:
            request: Unused, kept for compatibility with google.auth.credentials.Credentials interface.
        """
        self.token = self.auth_manager.get_access_token(force_refresh=True)
        # Set naive UTC expiry (55 mins) for google-auth compatibility
        self.expiry = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(minutes=55)

    @property
    def valid(self) -> bool:
        """Check if the current access token is valid and not expired."""
        return bool(self.token) and not self.expired

    @property
    def expired(self) -> bool:
        """Check if the token has expired."""
        if not self.token or not self.expiry:
            return True
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        return now >= self.expiry

    def before_request(self, request, method, url, headers):
        """Apply the Bearer authorization header to outgoing HTTP requests.

        Args:
            request: The transport request.
            method: HTTP method.
            url: Target request URL.
            headers: Mutable dictionary of request headers.
        """
        if not self.token or self.expired:
            self.refresh(request)
        headers["authorization"] = f"Bearer {self.token}"


class AgentIdentityAuthManager:
    """Manages authentication tokens via Google Cloud IAM Agent Identity Auth Manager."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        auth_provider_name: Optional[str] = None,
        user_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ):
        """Initialize AgentIdentityAuthManager.

        Args:
            project_id: GCP project ID. Defaults to GOOGLE_CLOUD_PROJECT env var.
            location: GCP location/region. Defaults to GOOGLE_CLOUD_LOCATION env var (default: 'us-central1').
            auth_provider_name: Auth Provider name or ID. Defaults to AGENT_AUTH_PROVIDER_NAME env var.
            user_id: Target user email. Defaults to TARGET_USER_EMAIL env var.
            scopes: OAuth scopes list. Defaults to DEFAULT_GMAIL_SCOPES.
        """
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.auth_provider_name = auth_provider_name or os.getenv("AGENT_AUTH_PROVIDER_NAME", "gmail-agent-auth-provider")
        self.user_id = user_id or os.getenv("TARGET_USER_EMAIL")
        self.scopes = scopes or DEFAULT_GMAIL_SCOPES
        self._cached_token: Optional[str] = None
        self._client: Optional[AuthProviderCredentialsServiceClient] = None

    @property
    def full_resource_name(self) -> str:
        """Return the fully qualified resource name for the Auth Provider."""
        if not self.project_id:
            raise ValueError(
                "Google Cloud Project ID is not set. Please set GOOGLE_CLOUD_PROJECT "
                "in your .env file or pass project_id to the constructor."
            )
        if self.auth_provider_name.startswith("projects/"):
            return self.auth_provider_name
        return f"projects/{self.project_id}/locations/{self.location}/authProviders/{self.auth_provider_name}"

    @property
    def client(self) -> AuthProviderCredentialsServiceClient:
        """Lazily initialize the REST transport client for Agent Identity Credentials."""
        if self._client is None:
            self._client = AuthProviderCredentialsServiceClient(transport="rest")
        return self._client

    def retrieve_credentials(
        self,
        force_refresh: bool = False,
        user_id: Optional[str] = None,
        continue_uri: Optional[str] = None,
    ) -> Any:
        """Call the Google Cloud Agent Identity Credentials API to request access credentials.

        Args:
            force_refresh: If True, forces Google Cloud to mint a new token from the vault.
            user_id: Target user email. Defaults to self.user_id.
            continue_uri: Redirect URI after user consent. Defaults to CONTINUE_URI or localhost:8501.

        Returns:
            RetrieveCredentialsResponse from Agent Identity Credentials API.
        """
        uid = user_id or self.user_id
        if not uid:
            raise ValueError(
                "Target user ID (email) is not set. Please set TARGET_USER_EMAIL "
                "in your .env file or pass user_id to the method."
            )

        target_continue_uri = continue_uri or os.getenv("CONTINUE_URI", "http://localhost:8501")
        
        kwargs = {
            "auth_provider": self.full_resource_name,
            "user_id": uid,
            "scopes": list(self.scopes),
            "continue_uri": target_continue_uri,
        }
        if force_refresh:
            kwargs["force_refresh_token"] = "true"

        req = RetrieveCredentialsRequest(**kwargs)
        return self.client.retrieve_credentials(request=req)

    def get_access_token(self, force_refresh: bool = False, user_id: Optional[str] = None) -> str:
        """Retrieve an OAuth 2.0 Bearer access token from Agent Identity Auth Manager.

        Args:
            force_refresh: Force minting a fresh token.
            user_id: Target user email.

        Returns:
            str: OAuth 2.0 Bearer access token (e.g. 'ya29...').

        Raises:
            RuntimeError: If consent is required, rejected, or token retrieval fails.
        """
        if self._cached_token and not force_refresh:
            return self._cached_token

        uid = user_id or self.user_id
        resp = self.retrieve_credentials(force_refresh=force_refresh, user_id=uid)

        # 1. Success with resp.success (protobuf field)
        if getattr(resp, "success", None) and getattr(resp.success, "token", None):
            self._cached_token = resp.success.token
            return self._cached_token

        # 2. Success with direct HTTP token
        if getattr(resp, "http", None) and resp.http.credentials and resp.http.credentials.token:
            self._cached_token = resp.http.credentials.token
            return self._cached_token

        # 3. Token field directly populated
        if getattr(resp, "token", None):
            self._cached_token = resp.token
            return self._cached_token

        # 4. User Consent Required (returns authorization_uri with signed state)
        if getattr(resp, "uri_consent_required", None):
            raise RuntimeError(
                f"User consent is required for '{uid}'.\n\n"
                f"👉 Run 'python3 cli.py authorize' to complete one-time authorization.\n"
            )

        if getattr(resp, "consent_rejected", None):
            raise RuntimeError("User consent was rejected.")

        raise RuntimeError(f"Unexpected response from Agent Identity Auth Manager: {resp}")

    def finalize_user_credentials(self, validation_state: str, consent_nonce: str, user_id: Optional[str] = None) -> Any:
        """Finalize credentials with Google Cloud Agent Identity after user consent redirect.

        Args:
            validation_state: The user_id_validation_state query param received from GCP callback.
            consent_nonce: The consent_nonce received from RetrieveCredentialsResponse.
            user_id: Target user email.

        Returns:
            FinalizeCredentialsResponse from Google Cloud.
        """
        uid = user_id or self.user_id
        req = FinalizeCredentialsRequest(
            auth_provider=self.full_resource_name,
            user_id=uid,
            user_id_validation_state=validation_state,
            consent_nonce=consent_nonce,
        )
        return self.client.finalize_credentials(request=req)

    def start_interactive_authorization(self, port: int = 8501) -> str:
        """Run an automated local server to capture consent redirect and finalize credentials in GCP.

        Args:
            port: Local port for the redirect server (default: 8501).

        Returns:
            str: Success message upon completing authorization.
        """
        continue_uri = f"http://localhost:{port}"
        resp = self.retrieve_credentials(continue_uri=continue_uri)

        # If credentials are already vaulted and active, no consent needed
        if not getattr(resp, "uri_consent_required", None):
            return "Auth Provider already has active credentials for this user!"

        auth_uri = resp.uri_consent_required.authorization_uri
        consent_nonce = getattr(resp.uri_consent_required, "consent_nonce", "")

        # Attach login_hint so user account is preselected in Google OAuth screen
        if self.user_id and "login_hint=" not in auth_uri:
            auth_uri += f"&login_hint={self.user_id}"

        state_captured = {}
        server_error = []

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)

                val_state = params.get("user_id_validation_state", [""])[0]
                if val_state:
                    state_captured["val_state"] = val_state
                    try:
                        self.server.auth_mgr.finalize_user_credentials(
                            validation_state=val_state,
                            consent_nonce=consent_nonce,
                        )
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(b"""
                        <html>
                        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                            <h1 style="color: #0f9d58;">&#10004; Authorization Successful!</h1>
                            <p>Your Google Workspace credentials have been stored in <b>Google Cloud Agent Identity Auth Manager</b>.</p>
                            <p>You may close this window and return to your terminal.</p>
                        </body>
                        </html>
                        """)
                    except Exception as e:
                        server_error.append(str(e))
                        self.send_response(500)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(f"<html><body><h2>Error finalizing credentials: {e}</h2></body></html>".encode("utf-8"))
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing user_id_validation_state parameter.")

            def log_message(self, format, *args):
                # Silence default HTTP server logging to keep terminal output clean
                pass

        server = HTTPServer(("127.0.0.1", port), CallbackHandler)
        server.auth_mgr = self
        server.timeout = 120

        print("=" * 75)
        print("🔐 One-Time Google Workspace User Authorization")
        print("=" * 75)
        print(f"[*] Account to authorize: {self.user_id}")
        print("\nOpening browser for one-time consent. If it does not open automatically, click:\n")
        print(auth_uri)
        print("\n" + "=" * 75)
        print(f"[*] Listening on http://localhost:{port} for authorization completion...")

        try:
            webbrowser.open(auth_uri)
        except Exception:
            pass

        start_time = time.time()
        while not state_captured and not server_error and (time.time() - start_time < 120):
            server.handle_request()

        server.server_close()

        if server_error:
            raise RuntimeError(f"Failed to finalize credentials: {server_error[0]}")
        if not state_captured:
            raise TimeoutError("Authorization timed out after 120 seconds.")

        # Invalidate token cache to fetch fresh token
        self._cached_token = None
        return "🎉 Authorization completed and credentials successfully vaulted in Google Cloud Auth Manager!"

    def revoke_credentials(self, user_id: Optional[str] = None) -> bool:
        """Revoke user authorization credentials stored in Agent Identity Auth Manager.

        Args:
            user_id: Target user email. Defaults to configured user_id.

        Returns:
            bool: True if revocation succeeded.
        """
        uid = user_id or self.user_id
        if not uid:
            raise ValueError("Target user email must be specified.")

        adc_creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not adc_creds.valid:
            adc_creds.refresh(Request())

        url = f"https://agentidentity.googleapis.com/v1alpha/{self.full_resource_name}:revokeAuthorization"
        headers = {
            "Authorization": f"Bearer {adc_creds.token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": self.project_id,
        }
        body = {"userId": uid}
        resp = requests.post(url, json=body, headers=headers, timeout=15)

        # Clear cached token
        self._cached_token = None

        if resp.status_code == 200:
            return True
        elif resp.status_code == 404:
            raise RuntimeError(f"Auth Provider or User Authorization not found: {self.full_resource_name}")
        else:
            raise RuntimeError(f"Failed to revoke credentials (Status {resp.status_code}): {resp.text}")

    def get_google_credentials(self, force_refresh: bool = False) -> AuthManagerCredentials:
        """Return a google.auth.credentials.Credentials instance wrapping the Auth Manager token.

        Args:
            force_refresh: Force token refresh upon initialization.

        Returns:
            AuthManagerCredentials adapter instance.
        """
        creds = AuthManagerCredentials(self)
        if force_refresh or not creds.valid:
            creds.refresh()
        return creds

    def get_token_details(self) -> Dict[str, Any]:
        """Return token information and Auth Provider metadata.

        Returns:
            Dict containing access_token, token_type, auth_provider, project_id, location, and user_id.
        """
        token = self.get_access_token()
        return {
            "access_token": token,
            "token_type": "Bearer",
            "auth_provider": self.full_resource_name,
            "project_id": self.project_id,
            "location": self.location,
            "user_id": self.user_id,
        }

