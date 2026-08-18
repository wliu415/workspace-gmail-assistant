#!/usr/bin/env python3
"""Deploy Workspace Gmail Agent to Google Cloud Vertex AI Agent Engines / Reasoning Engines.

Deploys the ADK LlmAgent with Agent Identity enabled (identity_type=AGENT_IDENTITY),
allowing the remote cloud agent to securely access the Auth Manager without storing keys.
"""

import os
import argparse
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def deploy_agent(
    project_id: Optional[str] = None,
    location: str = "us-central1",
    auth_provider_name: str = "gmail-agent-auth-provider",
    staging_bucket: Optional[str] = None,
):
    """Deploy the agent to Vertex AI Agent Engines.

    Args:
        project_id: Target GCP project ID.
        location: Target GCP region (default: 'us-central1').
        auth_provider_name: Auth Provider name or ID.
        staging_bucket: Optional Cloud Storage staging bucket for artifacts.
    """
    project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError(
            "GCP Project ID is required. Please set GOOGLE_CLOUD_PROJECT in your .env "
            "or provide --project on the command line."
        )

    print("=" * 70)
    print("🚀 Deploying Gmail Assistant to Google Cloud Vertex AI Agent Engines")
    print("=" * 70)
    print(f"[*] Project ID:      {project_id}")
    print(f"[*] Location:        {location}")
    print(f"[*] Auth Provider:   {auth_provider_name}")

    try:
        import vertexai
        from vertexai import types
        from vertexai.agent_engines import AdkApp
        from adk_agent import setup_adk_agent
    except ImportError:
        print("\n[!] Required deployment packages missing. Please install:")
        print("    pip install google-cloud-aiplatform[agent_engines,adk] google-adk[agent-identity]")
        return

    # 1. Initialize Vertex AI client with v1beta1 API
    client = vertexai.Client(
        project=project_id,
        location=location,
        http_options=dict(api_version="v1beta1"),
    )

    # 2. Build ADK App
    print("\n[*] Initializing ADK Agent with GcpAuthProvider...")
    app, agent = setup_adk_agent(
        project_id=project_id,
        location=location,
        auth_provider_name=auth_provider_name,
    )
    adk_wrapper = AdkApp(app_name=app)

    # 3. Deploy to Agent Engines with AGENT_IDENTITY
    print("[*] Packaging and deploying to Vertex AI Agent Engines...")
    deployment_requirements = [
        "google-cloud-aiplatform[agent_engines,adk]>=1.70.0",
        "google-adk[agent-identity]>=0.1.0",
        "google-api-python-client>=2.115.0",
        "google-auth>=2.27.0",
        "httpx>=0.27.0",
        "requests>=2.31.0",
    ]

    config_dict = {
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "requirements": deployment_requirements,
    }
    if staging_bucket:
        config_dict["staging_bucket"] = staging_bucket

    remote_app = client.agent_engines.create(
        agent=adk_wrapper,
        config=config_dict,
    )

    print("\n" + "=" * 70)
    print("🎉 Agent successfully deployed!")
    print(f"[✔] Resource Name: {remote_app.resource_name}")
    print("=" * 70)
    print("\n💡 Next Step: Grant Agent Identity User role to the deployed Agent's SPIFFE ID:")
    print(f"   gcloud alpha agent-identity auth-providers add-iam-policy-binding {auth_provider_name} \\")
    print(f"       --project=\"{project_id}\" \\")
    print(f"       --location=\"{location}\" \\")
    print('       --role="roles/agentidentity.user" \\')
    print('       --member="<AGENT_SPIFFE_PRINCIPAL_ID>"')
    return remote_app


def main():
    parser = argparse.ArgumentParser(description="Deploy Workspace Gmail Assistant to Vertex AI Agent Engines")
    parser.add_argument("--project", "-p", default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="GCP Project ID")
    parser.add_argument("--location", "-l", default=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"), help="GCP Location (default: us-central1)")
    parser.add_argument("--auth-provider", "-a", default=os.getenv("AGENT_AUTH_PROVIDER_NAME", "gmail-agent-auth-provider"), help="Auth Provider Name")
    parser.add_argument("--bucket", "-b", help="Optional GCS staging bucket")
    args = parser.parse_args()

    deploy_agent(
        project_id=args.project,
        location=args.location,
        auth_provider_name=args.auth_provider,
        staging_bucket=args.bucket,
    )


if __name__ == "__main__":
    main()

