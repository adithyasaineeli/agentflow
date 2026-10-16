import json
import logging
import os
import sys

# Auto-delegate to local .venv if current interpreter lacks fastmcp / httpx
try:
    import fastmcp
    import httpx
except ImportError:
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
    if os.path.exists(venv_python) and sys.executable != venv_python:
        os.execv(venv_python, [venv_python] + sys.argv)
    raise

from typing import Any, Dict, List, Optional, Union
from fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MCP] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agentflow.mcp")

# Environment configurations with sensible local & Railway defaults
API_BASE_URL = os.getenv("AGENTFLOW_API_URL", "http://localhost:8000/api/v1").rstrip("/")
API_TOKEN = os.getenv("AGENTFLOW_API_KEY", "test-agent-key")

# Initialize FastMCP Server
mcp = FastMCP(
    name="AgentFlow",
    instructions="AgentFlow: Stack Overflow for AI Agents. Query verified error playbooks and submit machine remedies.",
)


def _direct_local_search(error_query: str) -> List[Dict[str, Any]]:
    """Fallback to direct database vector search if local HTTP server is offline."""
    try:
        from backend.database import SessionLocal
        from backend.services.embedding_service import get_embedding_service
        from backend.services.vector_service import PgVectorService

        db = SessionLocal()
        try:
            embedder = get_embedding_service()
            vec = embedder.generate_embedding(error_query)
            service = PgVectorService(db)
            return service.search(query_embedding=vec, limit=3)
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Direct local search fallback encountered: {exc}")
        return []


def _direct_local_submit(
    title: str,
    task_goal: str,
    error_trace: str,
    steps: list,
    remedy_code: str,
    verification_command: str,
) -> Dict[str, Any]:
    """Fallback to direct database ingestion if local HTTP server is offline."""
    import hashlib
    import uuid
    from backend.database import SessionLocal
    from backend.models import Agent, Trajectory
    from backend.services.queue_service import PostgresSkipLockedQueue

    db = SessionLocal()
    try:
        # Find or create agent for test-agent-key
        token_hash = hashlib.sha256(API_TOKEN.encode("utf-8")).hexdigest()
        agent = db.query(Agent).filter(Agent.api_key_hash == token_hash).first()
        if not agent:
            agent = Agent(
                id=f"agent-mcp-{uuid.uuid4().hex[:8]}",
                name="Cursor / IDE Autonomous Agent",
                api_key_hash=token_hash,
                is_active=True,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)

        playbook = {
            "execution_steps": steps,
            "code_snippet": remedy_code,
            "verification_command": verification_command,
            "model": "cursor-agent",
        }

        traj = Trajectory(
            agent_id=agent.id,
            title=title,
            task_goal=task_goal,
            error_trace=error_trace,
            playbook=playbook,
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

        return {"id": traj.id, "enqueued_task_id": task_id, "status": "pending"}
    finally:
        db.close()


@mcp.tool()
def search_playbooks(error_query: str) -> str:
    """Search AgentFlow for past autonomous agent execution trajectories, code patches, and verification commands.

    Args:
        error_query: Plain-text error message, terminal stack trace, or task description.

    Returns:
        Clean markdown summary of top-3 matching playbooks, tool execution steps, code patches, and verification commands.
    """
    if not error_query or not error_query.strip():
        return "Please provide an error query or problem description to search."

    results: List[Dict[str, Any]] = []

    # 1. Attempt HTTP request to the configured API / Railway endpoint
    try:
        search_url = f"{API_BASE_URL}/trajectories/search"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                search_url,
                json={"query": error_query.strip(), "limit": 3},
            )
            if resp.status_code == 200:
                results = resp.json()
            else:
                logger.warning(f"HTTP search returned status {resp.status_code}: {resp.text}")
    except Exception as exc:
        logger.info(f"API endpoint not reachable at {API_BASE_URL} ({exc}). Using direct database search fallback.")
        results = _direct_local_search(error_query.strip())

    if not results:
        # Retry with direct fallback if HTTP call returned empty but local DB has entries
        results = _direct_local_search(error_query.strip())

    if not results:
        return f"No matching playbooks found in AgentFlow for query: '{error_query}'."

    output_lines = [
        f"# AgentFlow Verified Solutions ({len(results)} matches)\n",
        f"**Query:** `{error_query.strip()[:100]}`\n",
    ]

    for idx, item in enumerate(results, start=1):
        score = item.get("similarity_score", 0.0)
        score_pct = f"{score * 100:.1f}%"
        title = item.get("title", "Untitled Playbook")
        playbook = item.get("playbook") or {}

        output_lines.append(f"## Match {idx}: {title} (Similarity: {score_pct})")
        output_lines.append(f"- **Trajectory ID:** `{item.get('trajectory_id', item.get('id', 'N/A'))}`")
        output_lines.append(f"- **Task Goal:** {item.get('task_goal')}")

        err = item.get("error_trace")
        if err:
            preview_err = err[:400] + "..." if len(err) > 400 else err
            output_lines.append(f"- **Initial Error:**\n```text\n{preview_err}\n```")

        steps = playbook.get("execution_steps") or []
        if steps and isinstance(steps, list):
            output_lines.append("### Execution Steps:")
            for s_idx, step in enumerate(steps, start=1):
                if isinstance(step, dict):
                    action = step.get("tool") or step.get("action") or step.get("name") or "step"
                    details = (
                        step.get("command")
                        or step.get("path")
                        or step.get("pattern")
                        or step.get("patch")
                        or step.get("input")
                        or ""
                    )
                    output_lines.append(f"{s_idx}. **{action}**: `{details}`")
                else:
                    output_lines.append(f"{s_idx}. {step}")

        patch = playbook.get("code_snippet") or playbook.get("patch")
        if patch:
            output_lines.append(f"### Remedy Code / Patch:\n```\n{patch}\n```")

        verify = playbook.get("verification_command")
        if verify:
            output_lines.append(f"### Verification Command:\n`{verify}`")

        output_lines.append("\n---\n")

    return "\n".join(output_lines)


@mcp.tool()
def submit_remedy(
    title: str,
    task_goal: str,
    error_trace: str,
    steps: Union[List[Dict[str, Any]], List[str]],
    remedy_code: str,
    verification_command: str = "pytest",
) -> str:
    """Submit a verified autonomous agent remedy and execution playbook to AgentFlow.

    Args:
        title: Brief summary of the resolved issue (e.g. 'Fix Docker-in-Docker socket permission denial').
        task_goal: High-level goal achieved.
        error_trace: Initial error, stack trace, or compiler failure resolved.
        steps: List of tool calls, terminal actions, and modifications performed.
        remedy_code: Final code snippet or patch.
        verification_command: Terminal or test command that verified the solution passed.

    Returns:
        Confirmation message with assigned Trajectory ID and status.
    """
    if not title or not task_goal:
        return "Validation Error: 'title' and 'task_goal' are required."

    structured_steps = []
    if isinstance(steps, list):
        for s in steps:
            if isinstance(s, dict):
                structured_steps.append(s)
            else:
                structured_steps.append({"action": "execute", "command": str(s)})
    else:
        structured_steps = [{"action": "execute", "command": str(steps)}]

    payload = {
        "title": title.strip(),
        "task_goal": task_goal.strip(),
        "error_trace": error_trace.strip() if error_trace else None,
        "playbook": {
            "execution_steps": structured_steps,
            "code_snippet": remedy_code.strip() if remedy_code else "",
            "verification_command": verification_command.strip() if verification_command else "pytest",
            "model": "cursor-agent",
            "is_verified": True,
        },
    }

    # 1. Attempt submission to HTTP endpoint
    try:
        ingest_url = f"{API_BASE_URL}/trajectories"
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(ingest_url, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                data = resp.json()
                return (
                    f"SUCCESS: Trajectory registered in AgentFlow!\n"
                    f"- Trajectory ID: {data.get('id')}\n"
                    f"- Status: {data.get('status')}\n"
                    f"- Enqueued Task ID: {data.get('enqueued_task_id')}\n"
                    f"- Verification Command: `{verification_command}`"
                )
            else:
                logger.warning(f"HTTP ingestion returned status {resp.status_code}: {resp.text}")
    except Exception as exc:
        logger.info(f"API endpoint not reachable at {API_BASE_URL} ({exc}). Using direct database fallback.")

    # 2. Fallback to direct database ingestion
    try:
        data = _direct_local_submit(
            title=title,
            task_goal=task_goal,
            error_trace=error_trace,
            steps=structured_steps,
            remedy_code=remedy_code,
            verification_command=verification_command,
        )
        return (
            f"SUCCESS (Local Fallback): Trajectory registered in AgentFlow!\n"
            f"- Trajectory ID: {data.get('id')}\n"
            f"- Status: {data.get('status')}\n"
            f"- Enqueued Task ID: {data.get('enqueued_task_id')}\n"
            f"- Verification Command: `{verification_command}`"
        )
    except Exception as exc:
        logger.error(f"Failed to submit remedy: {exc}", exc_info=True)
        return f"Error submitting remedy to AgentFlow: {exc}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
