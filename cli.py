#!/usr/bin/env python3
"""CLI interface for Workspace Gmail Assistant with Agent Identity Auth Manager.

Provides commands for one-time interactive OAuth consent, token inspection,
mailbox profile retrieval, sending emails, creating drafts, listing/searching messages,
reading messages, and revoking user credentials from the Google Cloud IAM Auth Manager vault.
"""

import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def build_client(args: argparse.Namespace):
    """Instantiate a GmailClient based on CLI arguments and .env configuration."""
    from auth_manager import AgentIdentityAuthManager
    from gmail_client import GmailClient
    
    project_id = getattr(args, "project", None) or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = getattr(args, "location", None) or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    auth_provider_name = getattr(args, "auth_provider", None) or os.getenv("AGENT_AUTH_PROVIDER_NAME", "gmail-agent-auth-provider")

    auth_manager = AgentIdentityAuthManager(
        project_id=project_id,
        location=location,
        auth_provider_name=auth_provider_name,
    )
    return GmailClient(auth_manager=auth_manager)


def cmd_token(args: argparse.Namespace):
    """Retrieve and display the active OAuth2 Access Token from Agent Identity Auth Manager."""
    client = build_client(args)
    details = client.auth_manager.get_token_details()

    if args.raw:
        print(details["access_token"])
        return

    print("=" * 65)
    print("🔑 Google Cloud Agent Identity Auth Manager Token")
    print("=" * 65)
    print(f"[*] Project ID:      {details['project_id']}")
    print(f"[*] Location:        {details['location']}")
    print(f"[*] Auth Provider:   {details['auth_provider']}")
    print("\n[+] Access Token (Bearer):")
    print(details["access_token"])
    print("=" * 65)


def cmd_authorize(args: argparse.Namespace):
    """Run automated local authorization server and open consent in browser."""
    client = build_client(args)
    port = getattr(args, "port", 8501)
    res = client.auth_manager.start_interactive_authorization(port=port)
    print(f"\n[✔] {res}")


def cmd_revoke(args: argparse.Namespace):
    """Revoke user authorization credentials from Google Cloud Auth Manager."""
    client = build_client(args)
    target_user = args.user or client.auth_manager.user_id

    if not target_user:
        print("[X] Target user email is required. Pass --user or set TARGET_USER_EMAIL in .env.", file=sys.stderr)
        sys.exit(1)

    print("=" * 65)
    print("🗑️  Google Cloud Agent Identity Auth Manager - Revoke Access")
    print("=" * 65)
    print(f"[*] Project ID:      {client.auth_manager.project_id}")
    print(f"[*] Location:        {client.auth_manager.location}")
    print(f"[*] Auth Provider:   {client.auth_manager.full_resource_name}")
    print(f"[*] Target User:     {target_user}")
    print("=" * 65)

    if not getattr(args, "yes", False):
        confirm = input(f"\n⚠️  Are you sure you want to revoke credentials for '{target_user}'? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("[!] Revocation cancelled.")
            return

    print(f"\n[*] Revoking vaulted credentials for '{target_user}' in Google Cloud...")
    client.auth_manager.revoke_credentials(user_id=target_user)
    print(f"[✔] Successfully revoked credentials for '{target_user}' from Google Cloud Auth Manager.")
    print("    Future token requests will require running 'python3 cli.py authorize'.\n")


def cmd_profile(args: argparse.Namespace):
    """Retrieve user mailbox profile."""
    client = build_client(args)
    print(f"[*] Connecting to Gmail API via Auth Manager ({client.auth_manager.full_resource_name})...")
    profile = client.get_profile()

    print("\n" + "=" * 55)
    print("📬 Gmail Mailbox Profile")
    print("=" * 55)
    print(f"[*] Email Address:   {profile.get('emailAddress')}")
    print(f"[*] Total Messages:  {profile.get('messagesTotal')}")
    print(f"[*] Total Threads:   {profile.get('threadsTotal')}")
    print(f"[*] History ID:      {profile.get('historyId')}")
    print("=" * 55)


def cmd_send(args: argparse.Namespace):
    """Send an email."""
    client = build_client(args)
    print(f"[*] Sending email to {args.to} with subject '{args.subject}'...")
    res = client.send_email(
        to=args.to,
        subject=args.subject,
        body_text=args.body,
        body_html=args.html,
        cc=args.cc,
        bcc=args.bcc,
    )
    print(f"[✔] Email successfully sent!")
    print(f"    Message ID: {res.get('id')}")
    print(f"    Thread ID:  {res.get('threadId')}")


def cmd_draft(args: argparse.Namespace):
    """Create a draft email."""
    client = build_client(args)
    print(f"[*] Creating draft email to {args.to} with subject '{args.subject}'...")
    res = client.create_draft(
        to=args.to,
        subject=args.subject,
        body_text=args.body,
        body_html=args.html,
        cc=args.cc,
        bcc=args.bcc,
    )
    print(f"[✔] Draft successfully created!")
    print(f"    Draft ID:   {res.get('id')}")
    print(f"    Message ID: {res.get('message', {}).get('id')}")


def cmd_list(args: argparse.Namespace):
    """List recent messages."""
    client = build_client(args)
    print(f"[*] Fetching up to {args.max} messages...")
    messages = client.list_messages(query=args.query, max_results=args.max)

    if not messages:
        print("[-] No messages found matching criteria.")
        return

    print("\n" + "=" * 70)
    print(f"📧 Messages ({len(messages)} found)")
    print("=" * 70)
    for i, msg in enumerate(messages, 1):
        print(f"[{i}] Subject: {msg.get('subject')}")
        print(f"    From:    {msg.get('from')}")
        print(f"    Date:    {msg.get('date')}")
        print(f"    ID:      {msg.get('id')}")
        print(f"    Snippet: {msg.get('snippet')[:90]}...")
        print("-" * 70)


def cmd_search(args: argparse.Namespace):
    """Search messages using Gmail query syntax."""
    args.max = getattr(args, "max", 10)
    cmd_list(args)


def cmd_read(args: argparse.Namespace):
    """Read a specific message content."""
    client = build_client(args)
    print(f"[*] Fetching message {args.id}...")
    msg = client.get_message_content(args.id)

    print("\n" + "=" * 70)
    print(f"Subject: {msg.get('subject')}")
    print(f"From:    {msg.get('from')}")
    print(f"To:      {msg.get('to')}")
    print(f"Date:    {msg.get('date')}")
    print("=" * 70)
    print("\n--- BODY (PLAIN TEXT) ---")
    print(msg.get("body_text") or "(No plain text body found)")
    if msg.get("body_html"):
        print("\n--- BODY (HTML AVAILABLE) ---")
        print(f"HTML Length: {len(msg['body_html'])} chars")
    print("=" * 70)


def cmd_labels(args: argparse.Namespace):
    """List all mailbox labels."""
    client = build_client(args)
    labels = client.list_labels()
    print("\n" + "=" * 50)
    print(f"🏷️  Mailbox Labels ({len(labels)})")
    print("=" * 50)
    for label in labels:
        print(f"  - {label.get('name')} (ID: {label.get('id')}, Type: {label.get('type')})")
    print("=" * 50)


def cmd_setup_guide(args: argparse.Namespace):
    """Display gcloud setup commands to create the Auth Provider."""
    project = args.project or os.getenv("GOOGLE_CLOUD_PROJECT", "YOUR_PROJECT_ID")
    location = args.location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    name = args.auth_provider or os.getenv("AGENT_AUTH_PROVIDER_NAME", "gmail-agent-auth-provider")
    user_email = os.getenv("TARGET_USER_EMAIL", "user@yourdomain.com")

    print("=" * 75)
    print("🛠️  Google Cloud Agent Identity Auth Manager Setup Guide")
    print("=" * 75)
    print("\n1. Set Project & Enable Required APIs:")
    print(f"   gcloud config set project {project}")
    print("   gcloud services enable agentidentity.googleapis.com aiplatform.googleapis.com gmail.googleapis.com")
    print("\n2. Create the Auth Provider in Google Cloud:")
    print(f"   gcloud alpha agent-identity auth-providers create {name} \\")
    print(f"       --project=\"{project}\" \\")
    print(f"       --location=\"{location}\" \\")
    print('       --three-legged-oauth-client-id="<YOUR_CLIENT_ID>" \\')
    print('       --three-legged-oauth-client-secret="<YOUR_CLIENT_SECRET>" \\')
    print('       --three-legged-oauth-authorization-url="https://accounts.google.com/o/oauth2/v2/auth" \\')
    print('       --three-legged-oauth-token-url="https://oauth2.googleapis.com/token"')
    print(f"\n3. Grant Access to {user_email}:")
    print(f"   gcloud alpha agent-identity auth-providers add-iam-policy-binding {name} \\")
    print(f"       --project=\"{project}\" \\")
    print(f"       --location=\"{location}\" \\")
    print('       --role="roles/agentidentity.user" \\')
    print(f'       --member="user:{user_email}"')
    print("=" * 75)


def main():
    parser = argparse.ArgumentParser(
        description="Workspace Gmail Assistant CLI - Agent Identity Auth Manager Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", "-p", help="GCP Project ID (default: from .env / ADC)")
    parser.add_argument("--location", "-l", help="GCP Location/Region (default: us-central1)")
    parser.add_argument("--auth-provider", "-a", help="Auth Provider name/ID (default: from .env)")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available subcommands")

    # Command: authorize
    p_auth = subparsers.add_parser("authorize", help="Run automated one-time user authorization flow")
    p_auth.add_argument("--port", type=int, default=8501, help="Local port for callback redirect (default: 8501)")
    p_auth.set_defaults(func=cmd_authorize)

    # Command: revoke
    p_revoke = subparsers.add_parser("revoke", help="Revoke user authorization from Google Cloud Auth Manager")
    p_revoke.add_argument("--user", "-u", help="User email to revoke (default: from .env)")
    p_revoke.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p_revoke.set_defaults(func=cmd_revoke)

    # Command: token
    p_token = subparsers.add_parser("token", help="Retrieve OAuth2 Bearer Access Token from Auth Manager")
    p_token.add_argument("--raw", "-r", action="store_true", help="Print only raw token string")
    p_token.set_defaults(func=cmd_token)

    # Command: profile
    p_profile = subparsers.add_parser("profile", help="Get Gmail mailbox stats & profile")
    p_profile.set_defaults(func=cmd_profile)

    # Command: send
    p_send = subparsers.add_parser("send", help="Send an email via Gmail API")
    p_send.add_argument("--to", required=True, help="Recipient email address")
    p_send.add_argument("--subject", required=True, help="Email subject line")
    p_send.add_argument("--body", required=True, help="Plain text message body")
    p_send.add_argument("--html", help="Optional HTML message body")
    p_send.add_argument("--cc", help="Optional CC recipient")
    p_send.add_argument("--bcc", help="Optional BCC recipient")
    p_send.set_defaults(func=cmd_send)

    # Command: draft
    p_draft = subparsers.add_parser("draft", help="Create a draft email in Gmail")
    p_draft.add_argument("--to", required=True, help="Recipient email address")
    p_draft.add_argument("--subject", required=True, help="Draft subject line")
    p_draft.add_argument("--body", required=True, help="Plain text draft body")
    p_draft.add_argument("--html", help="Optional HTML draft body")
    p_draft.add_argument("--cc", help="Optional CC recipient")
    p_draft.add_argument("--bcc", help="Optional BCC recipient")
    p_draft.set_defaults(func=cmd_draft)

    # Command: list
    p_list = subparsers.add_parser("list", help="List recent messages")
    p_list.add_argument("--query", "-q", default="", help="Optional search query")
    p_list.add_argument("--max", "-m", type=int, default=10, help="Max messages to return (default: 10)")
    p_list.set_defaults(func=cmd_list)

    # Command: search
    p_search = subparsers.add_parser("search", help="Search messages with Gmail syntax")
    p_search.add_argument("query", help="Gmail query string (e.g. 'is:unread', 'label:SENT')")
    p_search.add_argument("--max", "-m", type=int, default=10, help="Max messages to return (default: 10)")
    p_search.set_defaults(func=cmd_search)

    # Command: read
    p_read = subparsers.add_parser("read", help="Read full message content by message ID")
    p_read.add_argument("id", help="Message ID to read")
    p_read.set_defaults(func=cmd_read)

    # Command: labels
    p_labels = subparsers.add_parser("labels", help="List all mailbox labels")
    p_labels.set_defaults(func=cmd_labels)

    # Command: setup-guide
    p_setup = subparsers.add_parser("setup-guide", help="Show gcloud commands to create Auth Provider")
    p_setup.set_defaults(func=cmd_setup_guide)

    args = parser.parse_args()

    try:
        args.func(args)
    except ModuleNotFoundError as e:
        print(f"\n[!] Missing dependency: {e.name}", file=sys.stderr)
        print("Please install requirements with: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if type(e).__name__ == "HttpError":
            print(f"\n[X] Google API Error: {e}", file=sys.stderr)
        else:
            print(f"\n[X] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

