import argparse
import hashlib
import json
import secrets
import sys
import uuid
from typing import Optional

from backend.database import Base, SessionLocal, engine
from backend.models import Agent


def create_agent(
    name: str,
    raw_token: Optional[str] = None,
    agent_id: Optional[str] = None,
    is_active: bool = True,
) -> dict:
    """Provisions a new machine agent and stores the SHA-256 hashed API token."""
    # Ensure tables exist
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f"[Warning] Table verification: {exc}", file=sys.stderr)

    # Generate cryptographically secure token if not provided
    if not raw_token:
        # 32 bytes of entropy encoded as urlsafe string (~43 characters)
        raw_token = f"af_{secrets.token_urlsafe(32)}"
    else:
        raw_token = raw_token.strip()

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    if not agent_id:
        agent_id = f"agent-{uuid.uuid4().hex[:12]}"
    else:
        agent_id = agent_id.strip()

    db = SessionLocal()
    try:
        # Check if an agent with this token hash already exists
        existing_hash = db.query(Agent).filter(Agent.api_key_hash == token_hash).first()
        if existing_hash:
            raise ValueError(
                f"An agent with this token hash already exists (Agent ID: '{existing_hash.id}', Name: '{existing_hash.name}')."
            )

        # Check if an agent with this ID already exists
        existing_agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if existing_agent:
            # Generate a new unique ID
            agent_id = f"agent-{uuid.uuid4().hex[:12]}"

        new_agent = Agent(
            id=agent_id,
            name=name.strip(),
            api_key_hash=token_hash,
            is_active=is_active,
        )
        db.add(new_agent)
        db.commit()
        db.refresh(new_agent)

        return {
            "id": new_agent.id,
            "name": new_agent.name,
            "raw_token": raw_token,
            "api_key_hash": token_hash,
            "is_active": new_agent.is_active,
            "created_at": new_agent.created_at.isoformat() if new_agent.created_at else None,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def print_provisioning_banner(result: dict) -> None:
    """Displays formatted credentials and configuration snippets for the provisioned agent."""
    token = result["raw_token"]
    agent_id = result["id"]
    agent_name = result["name"]

    print("\n" + "=" * 76)
    print("  🚀 AGENTFLOW MACHINE CREDENTIALS PROVISIONED SUCCESSFULLY")
    print("=" * 76)
    print(f"  Agent ID:       {agent_id}")
    print(f"  Agent Name:     {agent_name}")
    print(f"  Active Status:  {'Active (Enabled)' if result['is_active'] else 'Inactive (Disabled)'}")
    print(f"  SHA-256 Hash:   {result['api_key_hash'][:16]}...{result['api_key_hash'][-8:]}")
    print("-" * 76)
    print("  🔑 CLEAR-TEXT API TOKEN (Copy now! Never stored in plaintext):")
    print(f"\n      {token}\n")
    print("  ⚠️  IMPORTANT: AgentFlow only stores the one-way SHA-256 hash.")
    print("      This raw token cannot be retrieved once this screen is closed.")
    print("-" * 76)

    mcp_config = {
        "mcpServers": {
            "agentflow": {
                "command": "python",
                "args": ["-m", "mcp_server"],
                "env": {
                    "AGENTFLOW_API_URL": "http://localhost:8000",
                    "AGENTFLOW_AGENT_TOKEN": token,
                },
            }
        }
    }

    print("  📋 FastMCP / Cursor / Claude Desktop Configuration:")
    print("  Add to ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("  or Cursor Features -> MCP Servers:\n")
    print(json.dumps(mcp_config, indent=4))
    print("\n  🌐 Direct REST Ingestion Test Command:")
    print(
        f'  curl -X POST "http://localhost:8000/api/v1/trajectories" \\\n'
        f'    -H "Authorization: Bearer {token}" \\\n'
        f'    -H "Content-Type: application/json" \\\n'
        f'    -d \'{{"title": "Test Ping", "task_goal": "Verify agent credentials", "playbook": {{"steps": []}}}}\''
    )
    print("=" * 76 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Provision and securely hash credentials for an autonomous AgentFlow machine agent."
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Human-readable name for the machine agent (e.g. 'Production Agent', 'Claude Code Worker')",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Optional custom API token. If omitted, a cryptographically secure 256-bit token is generated.",
    )
    parser.add_argument(
        "--id",
        type=str,
        default=None,
        help="Optional custom Agent ID. If omitted, a unique 'agent-<hex>' identifier is assigned.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create the agent in a deactivated state (cannot submit trajectories until enabled).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON with credentials (useful for programmatic CI/CD pipelines).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = create_agent(
            name=args.name,
            raw_token=args.token,
            agent_id=args.id,
            is_active=not args.inactive,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_provisioning_banner(result)

        sys.exit(0)
    except Exception as exc:
        print(f"\n❌ Error provisioning agent: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
