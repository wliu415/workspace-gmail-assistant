#!/usr/bin/env python3
"""Standalone script to revoke user credentials in Google Cloud Agent Identity Auth Manager.

Allows administrators or automated workflows to immediately disconnect and invalidate
a user's vaulted authorization credentials in Google Cloud IAM without running the full CLI.
"""

import argparse
import sys
from auth_manager import AgentIdentityAuthManager


def main():
    parser = argparse.ArgumentParser(
        description="Revoke user authorization from Google Cloud Agent Identity Auth Manager.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--user", "-u", help="User email to revoke (default: from .env or TARGET_USER_EMAIL)")
    parser.add_argument("--project", "-p", help="GCP Project ID (default: from .env)")
    parser.add_argument("--location", "-l", default="us-central1", help="GCP Location (default: us-central1)")
    parser.add_argument("--auth-provider", "-a", help="Auth Provider name/ID (default: from .env)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    auth_mgr = AgentIdentityAuthManager(
        project_id=args.project,
        location=args.location,
        auth_provider_name=args.auth_provider,
        user_id=args.user,
    )

    target_user = args.user or auth_mgr.user_id
    if not target_user:
        print("[X] Error: Target user email is required. Provide --user or set TARGET_USER_EMAIL in .env.", file=sys.stderr)
        sys.exit(1)

    print("=" * 65)
    print("🗑️  Google Cloud Agent Identity Auth Manager - Revoke Access")
    print("=" * 65)
    print(f"[*] Project ID:      {auth_mgr.project_id}")
    print(f"[*] Location:        {auth_mgr.location}")
    print(f"[*] Auth Provider:   {auth_mgr.full_resource_name}")
    print(f"[*] Target User:     {target_user}")
    print("=" * 65)

    if not args.yes:
        confirm = input(f"\n⚠️  Are you sure you want to revoke credentials for '{target_user}'? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("[!] Revocation cancelled.")
            sys.exit(0)

    try:
        print(f"\n[*] Revoking vaulted credentials for '{target_user}' in Google Cloud...")
        auth_mgr.revoke_credentials(user_id=target_user)
        print(f"[✔] Successfully revoked credentials for '{target_user}' from Google Cloud Auth Manager.")
        print("    Future token requests will require running 'python3 cli.py authorize'.\n")
    except Exception as e:
        print(f"\n[X] Error revoking credentials: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

