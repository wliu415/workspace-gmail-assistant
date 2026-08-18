#!/usr/bin/env python3
"""Unit tests for workspace-gmail-assistant using Agent Identity Auth Manager.

Validates message payload construction, token retrieval flows, credential revocation,
Gmail client API interactions, and AI agent tool definitions.
"""

import unittest
from unittest.mock import MagicMock, patch
import base64
import email

from auth_manager import AgentIdentityAuthManager, AuthManagerCredentials
from gmail_client import GmailClient
import agent_tools


class TestAgentIdentityGmailAssistant(unittest.TestCase):
    """Test suite for Agent Identity Auth Manager, Gmail Client, and Agent Tools."""

    def test_message_payload_encoding(self):
        """Verify RFC 2822 MIME message encoding (plain text + CC)."""
        payload = GmailClient._create_message_payload(
            to="recipient@example.com",
            subject="Test Subject",
            body_text="Hello World",
            cc=["cc1@example.com", "cc2@example.com"],
        )
        self.assertIn("raw", payload)
        raw_b64 = payload["raw"]
        decoded_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        
        parsed_msg = email.message_from_bytes(decoded_bytes)
        self.assertEqual(parsed_msg["to"], "recipient@example.com")
        self.assertEqual(parsed_msg["subject"], "Test Subject")
        self.assertEqual(parsed_msg["cc"], "cc1@example.com, cc2@example.com")
        
        payload_body = parsed_msg.get_payload(decode=True).decode("utf-8")
        self.assertEqual(payload_body, "Hello World")

    def test_message_payload_multipart_html(self):
        """Verify RFC 2822 multipart/alternative MIME encoding for HTML messages."""
        payload = GmailClient._create_message_payload(
            to="recipient@example.com",
            subject="HTML Subject",
            body_text="Plain body",
            body_html="<p>HTML body</p>",
        )
        raw_b64 = payload["raw"]
        decoded_bytes = base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        parsed_msg = email.message_from_bytes(decoded_bytes)

        self.assertTrue(parsed_msg.is_multipart())
        self.assertEqual(parsed_msg["to"], "recipient@example.com")
        self.assertEqual(parsed_msg["subject"], "HTML Subject")

    @patch("auth_manager.AuthProviderCredentialsServiceClient")
    def test_agent_identity_token_retrieval(self, mock_client_cls):
        """Verify token retrieval from Agent Identity Auth Manager endpoint."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success.token = "ya29.mock-agent-identity-auth-manager-token"
        mock_client.retrieve_credentials.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        manager = AgentIdentityAuthManager(
            project_id="test-project",
            location="us-central1",
            auth_provider_name="gmail-test-provider",
            user_id="user@example.com"
        )
        token = manager.get_access_token()

        self.assertEqual(token, "ya29.mock-agent-identity-auth-manager-token")
        self.assertEqual(
            manager.full_resource_name,
            "projects/test-project/locations/us-central1/authProviders/gmail-test-provider"
        )

    @patch("auth_manager.google.auth.default")
    @patch("requests.post")
    def test_agent_identity_revoke_credentials(self, mock_post, mock_adc):
        """Verify revocation endpoint call in Agent Identity Auth Manager."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.token = "mock-adc-token"
        mock_adc.return_value = (mock_creds, "test-project")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp

        manager = AgentIdentityAuthManager(
            project_id="test-project",
            location="us-central1",
            auth_provider_name="gmail-test-provider",
            user_id="user@example.com"
        )
        result = manager.revoke_credentials()
        self.assertTrue(result)
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        self.assertIn("revokeAuthorization", call_url)

    def test_auth_manager_credentials_adapter(self):
        """Verify AuthManagerCredentials adapter refreshes and populates Bearer headers."""
        mock_mgr = MagicMock(spec=AgentIdentityAuthManager)
        mock_mgr.get_access_token.return_value = "ya29.test-adapter-token"

        creds = AuthManagerCredentials(mock_mgr)
        self.assertFalse(creds.valid)

        creds.refresh()
        self.assertTrue(creds.valid)
        self.assertEqual(creds.token, "ya29.test-adapter-token")

        headers = {}
        creds.before_request(None, "GET", "https://gmail.googleapis.com", headers)
        self.assertEqual(headers.get("authorization"), "Bearer ya29.test-adapter-token")

    def test_agent_tool_schemas(self):
        """Verify tool schemas are properly structured and export all expected functions."""
        tools = agent_tools.get_agent_tools()
        tool_names = [t["name"] for t in tools]
        self.assertIn("send_gmail_message", tool_names)
        self.assertIn("create_gmail_draft", tool_names)
        self.assertIn("search_gmail_messages", tool_names)
        self.assertIn("get_gmail_profile", tool_names)
        self.assertIn("get_workspace_access_token", tool_names)
        self.assertIn("revoke_workspace_access", tool_names)


if __name__ == "__main__":
    unittest.main()

