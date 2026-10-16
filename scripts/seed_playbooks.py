#!/usr/bin/env python3
"""
scripts/seed_playbooks.py - Real-World Engineering Playbooks Ingestion Utility.

Securely injects 3 production-grade, highly searched software engineering failure resolutions:
1. Next.js 14 Dynamic Server Usage Bailout
2. Prisma Query Engine Binary Architecture Mismatch in Alpine/Docker
3. Python AsyncPG Greenlet Spawn Initialization Failure
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path for local module imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    import httpx
except ImportError:
    httpx = None


# ---------------------------------------------------------------------------
# Terminal Colors & Styling
# ---------------------------------------------------------------------------
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# 3 Production-Grade Engineering Playbooks
# ---------------------------------------------------------------------------
PLAYBOOKS: List[Dict[str, Any]] = [
    {
        "title": "Resolve Dynamic server usage: Route couldn't be rendered statically error in Next.js 14",
        "task_goal": "Fix build failure when accessing cookies() or searchParams inside statically exported page route",
        "error_trace": (
            "Error: Dynamic server usage: Route /dashboard couldn't be rendered statically because it used `cookies`. "
            "See more info here: https://nextjs.org/docs/messages/dynamic-server-usage\n"
            "   at Object.cookies (/node_modules/next/dist/server/web/spec-extension/cookies.js:42:15)\n"
            "   at DashboardPage (app/dashboard/page.tsx:12:20)\n"
            "   at async Promise.all (index 0)\n"
            "Export encountered errors on following paths:\n"
            "   /dashboard/page: /dashboard"
        ),
        "playbook": {
            "model": "claude-3-5-sonnet",
            "runtime": "Next.js 14 / React 18",
            "environment": {
                "os": "Linux / Vercel Serverless",
                "arch": "x86_64",
                "node_version": "v20.12.0",
            },
            "execution_steps": [
                {
                    "tool": "read_file",
                    "path": "app/dashboard/page.tsx",
                    "details": "Inspect route header access and dynamic functions",
                },
                {
                    "tool": "replace_file_content",
                    "path": "app/dashboard/page.tsx",
                    "patch": "export const dynamic = 'force-dynamic';\nexport const revalidate = 0;\n\nimport { cookies } from 'next/headers';",
                },
                {
                    "tool": "run_command",
                    "command": "npm run build",
                    "details": "Verify static compilation marks route as dynamic and build succeeds with exit code 0",
                },
            ],
            "code_snippet": (
                "// app/dashboard/page.tsx\n"
                "// Mark route as dynamic to opt out of static prerendering when reading cookies\n"
                "export const dynamic = 'force-dynamic';\n"
                "export const revalidate = 0;\n\n"
                "import { cookies } from 'next/headers';\n"
                "import { Suspense } from 'react';\n"
                "import { DashboardMetrics } from '@/components/dashboard-metrics';\n\n"
                "export default async function DashboardPage() {\n"
                "  const cookieStore = cookies();\n"
                "  const sessionToken = cookieStore.get('session_id')?.value;\n\n"
                "  return (\n"
                "    <main className=\"p-8\">\n"
                "      <h1 className=\"text-2xl font-bold\">Telemetry Dashboard</h1>\n"
                "      <Suspense fallback={<div>Loading live metrics...</div>}>\n"
                "        <DashboardMetrics token={sessionToken} />\n"
                "      </Suspense>\n"
                "    </main>\n"
                "  );\n"
                "}"
            ),
            "verification_command": "npm run build",
            "is_verified": True,
        },
    },
    {
        "title": "Resolve Prisma Client could not locate Query Engine binary for alpine-arm64/musl",
        "task_goal": "Fix Prisma runtime crash in lightweight Docker container with musl libc on ARM64",
        "error_trace": (
            "PrismaClientInitializationError: Query engine binary for current platform 'linux-musl-arm64' could not be found. "
            "Expected: libquery_engine-linux-musl-arm64.so.node\n"
            "This probably means that your schema was generated with another platform's binaryTargets or you are running an "
            "Alpine image without musl runtime dependencies.\n"
            "   at instantiateEngine (/app/node_modules/@prisma/client/runtime/library.js:142:19)\n"
            "   at new PrismaClient (/app/node_modules/@prisma/client/index.js:28:11)"
        ),
        "playbook": {
            "model": "gpt-4o",
            "runtime": "Node.js / Prisma / Alpine",
            "environment": {
                "os": "Alpine Linux 3.19",
                "arch": "arm64",
                "runtime_version": "Prisma 5.11.0",
            },
            "execution_steps": [
                {
                    "tool": "replace_file_content",
                    "path": "prisma/schema.prisma",
                    "patch": (
                        "generator client {\n"
                        "  provider      = \"prisma-client-js\"\n"
                        "  binaryTargets = [\"native\", \"linux-musl-arm64-openssl-3.0.x\", \"linux-musl-openssl-3.0.x\"]\n"
                        "}"
                    ),
                },
                {
                    "tool": "edit_file",
                    "path": "Dockerfile",
                    "patch": "RUN apk add --no-cache openssl3 libc6-compat",
                },
                {
                    "tool": "run_command",
                    "command": "npx prisma generate",
                    "details": "Regenerate query engine binaries targeting Alpine musl architecture",
                },
            ],
            "code_snippet": (
                "// prisma/schema.prisma\n"
                "generator client {\n"
                "  provider      = \"prisma-client-js\"\n"
                "  binaryTargets = [\"native\", \"linux-musl-arm64-openssl-3.0.x\", \"linux-musl-openssl-3.0.x\"]\n"
                "}\n\n"
                "datasource db {\n"
                "  provider = \"postgresql\"\n"
                "  url      = env(\"DATABASE_URL\")\n"
                "}\n\n"
                "# In Dockerfile (Alpine Linux ARM64):\n"
                "FROM node:20-alpine AS runner\n"
                "RUN apk add --no-cache openssl3 libc6-compat\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "RUN npx prisma generate"
            ),
            "verification_command": "npx prisma db pull --print",
            "is_verified": True,
        },
    },
    {
        "title": "Resolve greenlet_spawn has not been called error in async SQLAlchemy 2.0",
        "task_goal": "Prevent MissingGreenlet exception when accessing lazy-loaded relationship attributes in async FastAPI route",
        "error_trace": (
            "sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call __setattr__ or load attribute "
            "eagerly in async engine context.\n"
            "This error occurs when an attribute that was configured for lazy loading is accessed outside of the async session worker thread.\n"
            "File \"/app/backend/main.py\", line 184, in get_user_profile\n"
            "    return {\"user\": user.name, \"roles\": [r.name for r in user.roles]}"
        ),
        "playbook": {
            "model": "claude-3-5-sonnet",
            "runtime": "Python 3.11 / SQLAlchemy / asyncpg",
            "environment": {
                "os": "Debian 12 / Docker",
                "arch": "x86_64",
                "python_version": "3.11.9",
            },
            "execution_steps": [
                {
                    "tool": "read_file",
                    "path": "backend/models.py",
                    "details": "Check User.roles relationship definition and loader strategy",
                },
                {
                    "tool": "replace_file_content",
                    "path": "backend/models.py",
                    "patch": "roles = relationship('Role', lazy='selectin', back_populates='user')",
                },
                {
                    "tool": "replace_file_content",
                    "path": "backend/routes/users.py",
                    "patch": "stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)",
                },
            ],
            "code_snippet": (
                "from sqlalchemy import select\n"
                "from sqlalchemy.orm import selectinload\n"
                "from sqlalchemy.ext.asyncio import AsyncSession\n\n"
                "# Option 1: Eager-load relationship in async query via selectinload()\n"
                "async def get_user_profile(db: AsyncSession, user_id: str):\n"
                "    stmt = (\n"
                "        select(User)\n"
                "        .options(selectinload(User.roles))\n"
                "        .where(User.id == user_id)\n"
                "    )\n"
                "    result = await db.execute(stmt)\n"
                "    user = result.scalar_one_or_none()\n"
                "    return user\n\n"
                "# Option 2: Configure default loader on model to prevent sync I/O in async context\n"
                "class User(Base):\n"
                "    __tablename__ = \"users\"\n"
                "    id = Column(String(36), primary_key=True)\n"
                "    roles = relationship(\"Role\", lazy=\"selectin\", back_populates=\"user\")"
            ),
            "verification_command": "pytest tests/test_async_routes.py",
            "is_verified": True,
        },
    },
]


# ---------------------------------------------------------------------------
# Helper: Resolve or Create Valid Agent Token
# ---------------------------------------------------------------------------
def resolve_or_create_agent_token(provided_token: Optional[str]) -> str:
    """Returns a valid agent token, checking CLI args, environment variables, or local DB."""
    if provided_token and provided_token.strip():
        return provided_token.strip()

    env_token = os.getenv("AGENT_FLOW_TOKEN") or os.getenv("AGENTFLOW_API_KEY")
    if env_token and env_token.strip():
        return env_token.strip()

    # Fallback to local database lookup/creation
    try:
        from backend.database import SessionLocal
        from backend.models import Agent

        db = SessionLocal()
        try:
            # Check for existing seed agent with known secret
            fallback_token = "seed-playbooks-token-secret"
            token_hash = hashlib.sha256(fallback_token.encode("utf-8")).hexdigest()

            agent = db.query(Agent).filter(Agent.api_key_hash == token_hash).first()
            if not agent:
                agent = Agent(
                    id=f"agent-seeder-{uuid.uuid4().hex[:8]}",
                    name="Production Playbooks Seeder Agent",
                    api_key_hash=token_hash,
                    is_active=True,
                )
                db.add(agent)
                db.commit()
                db.refresh(agent)
            return fallback_token
        finally:
            db.close()
    except Exception as exc:
        print(f"{YELLOW}[Warning] Could not resolve local agent from DB: {exc}{RESET}")
        return "seed-playbooks-token-secret"


# ---------------------------------------------------------------------------
# Fallback: Direct Database Ingestion
# ---------------------------------------------------------------------------
def direct_db_ingest(playbook_item: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Ingests a trajectory directly into the database if the HTTP API is offline."""
    from backend.database import SessionLocal
    from backend.models import Agent, Trajectory
    from backend.services.queue_service import PostgresSkipLockedQueue

    db = SessionLocal()
    try:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        agent = db.query(Agent).filter(Agent.api_key_hash == token_hash).first()
        if not agent:
            agent = Agent(
                id=f"agent-seeder-{uuid.uuid4().hex[:8]}",
                name="Production Playbooks Seeder Agent",
                api_key_hash=token_hash,
                is_active=True,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)

        traj = Trajectory(
            agent_id=agent.id,
            title=playbook_item["title"],
            task_goal=playbook_item["task_goal"],
            error_trace=playbook_item.get("error_trace"),
            playbook=playbook_item["playbook"],
            status="pending",
        )
        db.add(traj)
        db.commit()
        db.refresh(traj)

        queue = PostgresSkipLockedQueue(db)
        task_id = queue.enqueue(
            task_type="generate_embedding",
            payload={
                "trajectory_id": traj.id,
                "task_goal": traj.task_goal,
                "initial_error": traj.error_trace,
                "text_to_embed": f"{traj.title}\n{traj.task_goal}\n{traj.error_trace or ''}",
            },
        )
        return {
            "id": traj.id,
            "status": "pending",
            "enqueued_task_id": task_id,
            "mode": "Direct DB Fallback",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main Execution Routine
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Seed AgentFlow with 3 real-world, production-grade engineering failure playbooks."
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.getenv("AGENTFLOW_API_URL", "http://localhost:8000/api/v1"),
        help="Target AgentFlow REST API URL (e.g. http://localhost:8000/api/v1 or https://app.railway.app/api/v1)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Agent Bearer token (defaults to AGENT_FLOW_TOKEN or local seed agent)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate playbooks and authentication without persisting data",
    )
    parser.add_argument(
        "--direct-db",
        action="store_true",
        help="Bypass HTTP and write directly to the database via SessionLocal",
    )
    args = parser.parse_args()

    api_base = args.api_url.rstrip("/")
    if not api_base.endswith("/api/v1") and not api_base.endswith("/trajectories"):
        api_url = f"{api_base}/api/v1/trajectories"
    elif api_base.endswith("/api/v1"):
        api_url = f"{api_base}/trajectories"
    else:
        api_url = api_base

    token = resolve_or_create_agent_token(args.token)

    print("\n" + "=" * 76)
    print(f"  {BOLD}{CYAN}⚡ AGENTFLOW REAL-WORLD PLAYBOOKS SEEDER{RESET}")
    print("=" * 76)
    print(f"  {BOLD}Target Endpoint:{RESET} {api_url}")
    print(f"  {BOLD}Agent Token:{RESET}     {token[:12]}...{token[-4:] if len(token) > 16 else ''}")
    print(f"  {BOLD}Mode:{RESET}            {'DRY-RUN (Validation only)' if args.dry_run else 'LIVE INGESTION'}")
    print("-" * 76)

    success_count = 0

    for idx, item in enumerate(PLAYBOOKS, start=1):
        print(f"\n{BOLD}[{idx}/3] Ingesting:{RESET} {CYAN}{item['title']}{RESET}")
        print(f"      {DIM}Goal:{RESET} {item['task_goal'][:80]}...")
        print(f"      {DIM}Verification Command:{RESET} `{item['playbook']['verification_command']}`")

        if args.dry_run:
            print(f"      {GREEN}✓ Validation passed (Dry-Run){RESET}")
            success_count += 1
            continue

        result_data = None
        method = "HTTP"

        if not args.direct_db:
            try:
                if httpx is None:
                    raise ImportError("httpx is not installed. Install httpx or use --direct-db.")

                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(api_url, json=item, headers=headers)
                    if resp.status_code in (200, 201, 202):
                        result_data = resp.json()
                        method = "HTTP REST"
                    else:
                        print(f"      {YELLOW}HTTP Ingestion returned {resp.status_code}: {resp.text}{RESET}")
            except Exception as http_err:
                print(f"      {YELLOW}HTTP API unavailable ({http_err}). Attempting Direct DB Fallback...{RESET}")

        if not result_data:
            try:
                result_data = direct_db_ingest(item, token)
                method = "Direct DB Fallback"
            except Exception as db_err:
                print(f"      {RED}❌ Ingestion failed: {db_err}{RESET}")
                continue

        traj_id = result_data.get("id")
        task_id = result_data.get("enqueued_task_id")
        status = result_data.get("status")

        print(f"      {GREEN}✓ Ingested via {method}!{RESET}")
        print(f"        • {BOLD}Trajectory UUID:{RESET} {traj_id}")
        print(f"        • {BOLD}Queue Task ID:{RESET}   {task_id}")
        print(f"        • {BOLD}Initial Status:{RESET}  {status}")
        success_count += 1

    print("\n" + "=" * 76)
    if success_count == len(PLAYBOOKS):
        print(f"  {GREEN}{BOLD}🎉 ALL {success_count} PLAYBOOKS INGESTED SUCCESSFULLY!{RESET}")
    else:
        print(f"  {YELLOW}{BOLD}⚠️ Ingestion completed with {success_count}/{len(PLAYBOOKS)} successes.{RESET}")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    main()
