#!/usr/bin/env python3
"""Gmail API Client powered by Google Cloud Agent Identity Auth Manager.

Provides a clean, object-oriented interface for interacting with the Gmail REST API (v1),
authenticating dynamically via tokens minted by Google Cloud IAM Agent Identity Auth Manager.
"""

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Union

from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from auth_manager import AgentIdentityAuthManager


class GmailClient:
    """Client for interacting with Gmail API using credentials from Agent Identity Auth Manager."""

    def __init__(self, auth_manager: Optional[AgentIdentityAuthManager] = None):
        """Initialize GmailClient.

        Args:
            auth_manager: Optional AgentIdentityAuthManager instance. If omitted,
                          a new manager is initialized from environment variables.
        """
        self.auth_manager = auth_manager or AgentIdentityAuthManager()
        self._service: Optional[Resource] = None

    @property
    def service(self) -> Resource:
        """Lazily initialize and return the authenticated Gmail API Resource (v1)."""
        if self._service is None:
            credentials = self.auth_manager.get_google_credentials()
            self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return self._service

    @staticmethod
    def _create_message_payload(
        to: Union[str, List[str]],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build and base64url-encode an RFC 2822 email message.

        Args:
            to: Single recipient email or list of emails.
            subject: Email subject line.
            body_text: Plain text content of the message.
            body_html: Optional HTML version of the message.
            cc: Optional CC recipient(s).
            bcc: Optional BCC recipient(s).
            reply_to: Optional Reply-To email address.

        Returns:
            Dict[str, str]: Dictionary containing the 'raw' URL-safe base64 encoded message string.
        """
        if body_html:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body_text, "plain", "utf-8"))
            message.attach(MIMEText(body_html, "html", "utf-8"))
        else:
            message = MIMEText(body_text, "plain", "utf-8")

        to_str = ", ".join(to) if isinstance(to, list) else to
        message["to"] = to_str
        message["subject"] = subject

        if cc:
            message["cc"] = ", ".join(cc) if isinstance(cc, list) else cc
        if bcc:
            message["bcc"] = ", ".join(bcc) if isinstance(bcc, list) else bcc
        if reply_to:
            message["reply-to"] = reply_to

        raw_bytes = message.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
        return {"raw": raw_b64}

    def get_profile(self, user_id: str = "me") -> Dict[str, Any]:
        """Retrieve profile information and message statistics for the authenticated user.

        Args:
            user_id: Target user ID or 'me' for authenticated account.

        Returns:
            Dict containing emailAddress, messagesTotal, threadsTotal, historyId.
        """
        return self.service.users().getProfile(userId=user_id).execute()

    def list_labels(self, user_id: str = "me") -> List[Dict[str, Any]]:
        """List all system and user labels in the mailbox.

        Args:
            user_id: Target user ID or 'me'.

        Returns:
            List of label dictionaries (id, name, type, messageListVisibility, etc.).
        """
        results = self.service.users().labels().list(userId=user_id).execute()
        return results.get("labels", [])

    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
        user_id: str = "me",
    ) -> Dict[str, Any]:
        """Send an email message via Gmail API.

        Args:
            to: Recipient email address(es).
            subject: Subject line.
            body_text: Plain text body.
            body_html: Optional HTML body.
            cc: Optional CC recipient(s).
            bcc: Optional BCC recipient(s).
            reply_to: Optional Reply-To address.
            user_id: Target user ID or 'me'.

        Returns:
            Dict containing 'id', 'threadId', and 'labelIds'.
        """
        payload = self._create_message_payload(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
        )
        return self.service.users().messages().send(userId=user_id, body=payload).execute()

    def create_draft(
        self,
        to: Union[str, List[str]],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        user_id: str = "me",
    ) -> Dict[str, Any]:
        """Create an email draft in the user's mailbox without sending.

        Args:
            to: Recipient email address(es).
            subject: Draft subject.
            body_text: Plain text content.
            body_html: Optional HTML content.
            cc: Optional CC recipient(s).
            bcc: Optional BCC recipient(s).
            user_id: Target user ID or 'me'.

        Returns:
            Dict containing draft metadata (id, message metadata).
        """
        payload = self._create_message_payload(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
        )
        draft_body = {"message": payload}
        return self.service.users().drafts().create(userId=user_id, body=draft_body).execute()

    def list_messages(
        self,
        query: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
        max_results: int = 10,
        user_id: str = "me",
    ) -> List[Dict[str, Any]]:
        """List or search messages in the mailbox with header metadata.

        Args:
            query: Gmail search filter syntax (e.g. 'is:unread', 'from:alerts@example.com').
            label_ids: Optional list of label IDs to filter by (e.g. ['INBOX', 'UNREAD']).
            max_results: Maximum messages to retrieve (1-100).
            user_id: Target user ID or 'me'.

        Returns:
            List of dictionaries with id, threadId, subject, from, to, date, snippet, labelIds.
        """
        request_params: Dict[str, Any] = {
            "userId": user_id,
            "maxResults": max(1, min(max_results, 100)),
        }
        if query:
            request_params["q"] = query
        if label_ids:
            request_params["labelIds"] = label_ids

        response = self.service.users().messages().list(**request_params).execute()
        message_summaries = response.get("messages", [])

        detailed_messages = []
        for msg in message_summaries:
            msg_id = msg.get("id")
            if not msg_id:
                continue
            try:
                detail = self.service.users().messages().get(
                    userId=user_id,
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Date"],
                ).execute()

                headers = {
                    h.get("name"): h.get("value")
                    for h in detail.get("payload", {}).get("headers", [])
                }

                detailed_messages.append({
                    "id": msg_id,
                    "threadId": detail.get("threadId"),
                    "snippet": detail.get("snippet", ""),
                    "subject": headers.get("Subject", "(No Subject)"),
                    "from": headers.get("From", "(Unknown)"),
                    "to": headers.get("To", "(Unknown)"),
                    "date": headers.get("Date", ""),
                    "labelIds": detail.get("labelIds", []),
                })
            except HttpError:
                detailed_messages.append({
                    "id": msg_id,
                    "threadId": msg.get("threadId"),
                    "snippet": "",
                    "subject": "(Error fetching details)",
                    "from": "",
                    "to": "",
                    "date": "",
                    "labelIds": [],
                })

        return detailed_messages

    def get_message_content(self, message_id: str, user_id: str = "me") -> Dict[str, Any]:
        """Fetch complete content, MIME structure, and parsed bodies of a single message.

        Args:
            message_id: Unique message ID.
            user_id: Target user ID or 'me'.

        Returns:
            Dict containing id, threadId, subject, from, to, date, snippet,
            body_text, body_html, and labelIds.
        """
        message = self.service.users().messages().get(userId=user_id, id=message_id, format="full").execute()

        payload = message.get("payload", {})
        headers = {h.get("name"): h.get("value") for h in payload.get("headers", [])}

        body_text = ""
        body_html = ""

        def extract_parts(part_node):
            """Recursively extract plain text and HTML payloads from MIME part nodes."""
            nonlocal body_text, body_html
            mime_type = part_node.get("mimeType", "")
            data = part_node.get("body", {}).get("data")
            if data:
                decoded = base64.urlsafe_b64decode(data.encode("ASCII")).decode("utf-8", errors="replace")
                if mime_type == "text/plain" and not body_text:
                    body_text = decoded
                elif mime_type == "text/html" and not body_html:
                    body_html = decoded

            for subpart in part_node.get("parts", []):
                extract_parts(subpart)

        extract_parts(payload)

        return {
            "id": message_id,
            "threadId": message.get("threadId"),
            "subject": headers.get("Subject", "(No Subject)"),
            "from": headers.get("From", "(Unknown)"),
            "to": headers.get("To", "(Unknown)"),
            "date": headers.get("Date", ""),
            "snippet": message.get("snippet", ""),
            "body_text": body_text,
            "body_html": body_html,
            "labelIds": message.get("labelIds", []),
        }

