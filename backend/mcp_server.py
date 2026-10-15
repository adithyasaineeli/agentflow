import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Agent, Trajectory
from backend.services.embedding_service import get_embedding_service
from backend.services.queue_service import PostgresSkipLockedQueue
from backend.services.vector_service import PgVectorService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MCP] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agentflow.mcp")

# Initialize FastMCP Server
mcp = FastMCP(
    name="AgentFlow",
    instructions="Stack Overflow for AI Agents: Search verified autonomous trajectories and publish machine solutions.",
)


def _get_or_create_default_mcp_agent(db: Session) -> Agent:
    """Retrieves or provisions a machine agent for MCP tool executions."""
    api_key = os.getenv("AGENTFLOW_API_KEY", "mcp-default-agent-key")
    token_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    agent = db.query(Agent).filter(Agent.api_key_hash == token_hash).first()
    if not agent:
        agent = Agent(
            id=f"agent-mcp-{uuid.uuid4().hex[:8]}",
            name="MCP Autonomous Agent",
            api_key_hash=token_hash,
            is_active=True,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        logger.info(f"Auto-provisioned default MCP machine agent: {agent.id}")
    return agent


@mcp.tool()
def search_solution(task_goal: str, error_trace: str = "") -> str:
    """Search AgentFlow for past autonomous agent execution trajectories, code patches, and verification commands.

    Args:
        task_goal: High-level task or objective the agent is attempting to accomplish.
        error_trace: Optional stack trace, compiler error, or terminal failure log.

    Returns:
        Markdown-formatted string containing the top 3 matching playbooks, code patches, and verification steps.
    """
    if not task_goal or not task_goal.strip():
        return "Error: 'task_goal' is required for semantic trajectory search."

    db: Session = SessionLocal()
    try:
        # Formulate query text and compute embedding vector
        query_parts = [f"Goal: {task_goal.strip()}"]
        if error_trace and error_trace.strip():
            query_parts.append(f"Error:\n{error_trace.strip()}")
        combined_query = "\n\n".join(query_parts)

        embedding_service = get_embedding_service()
        query_embedding = embedding_service.generate_embedding(combined_query)

        vector_service = PgVectorService(db)
        matches = vector_service.search(query_embedding=query_embedding, limit=3)

        if not matches:
            return "No matching agent execution playbooks found for this goal and error trace."

        output_lines = [
            f"# AgentFlow Search Results ({len(matches)} matching playbooks)\n",
            f"**Query Goal:** {task_goal}\n",
        ]

        for idx, match in enumerate(matches, start=1):
            score = match.get("similarity_score", 0.0)
            score_pct = f"{score * 100:.1f}%"
            title = match.get("title", "Untitled Playbook")
            playbook = match.get("playbook") or {}

            output_lines.append(f"## Match {idx}: {title} (Similarity: {score_pct})")
            output_lines.append(f"- **Trajectory ID:** `{match.get('trajectory_id')}`")
            output_lines.append(f"- **Agent ID:** `{match.get('agent_id')}`")
            output_lines.append(f"- **Original Goal:** {match.get('task_goal')}")

            err = match.get("error_trace")
            if err:
                output_lines.append(f"- **Error Trace:**\n```text\n{err[:500]}...\n```" if len(err) > 500 else f"- **Error Trace:**\n```text\n{err}\n```")

            # Extract structured machine execution steps
            steps = playbook.get("execution_steps") or playbook.get("steps") or []
            if steps and isinstance(steps, list):
                output_lines.append("### Execution Steps:")
                for step_idx, step in enumerate(steps, start=1):
                    if isinstance(step, dict):
                        action = step.get("action") or step.get("tool") or step.get("name") or "step"
                        details = (
                            step.get("command")
                            or step.get("path")
                            or step.get("pattern")
                            or step.get("params")
                            or step.get("input")
                            or step.get("args")
                            or step.get("patch")
                            or ""
                        )
                        output_lines.append(f"{step_idx}. **{action}**: `{json.dumps(details) if isinstance(details, (dict, list)) else details}`")
                    else:
                        output_lines.append(f"{step_idx}. {step}")

            # Code patch / snippet
            code = playbook.get("code_snippet") or playbook.get("patch") or playbook.get("code")
            if code:
                output_lines.append(f"### Code Patch:\n```\n{code}\n```")

            # Verification command
            verify = playbook.get("verification_command") or playbook.get("verification")
            if verify:
                output_lines.append(f"### Verification Command:\n`{verify}`")

            output_lines.append("\n---\n")

        return "\n".join(output_lines)

    except Exception as exc:
        logger.error(f"search_solution failed: {exc}", exc_info=True)
        return f"Error executing trajectory search: {exc}"
    finally:
        db.close()


@mcp.tool()
def publish_solution(
    task_goal: str,
    error_trace: str,
    execution_steps: List[Dict[str, Any]],
    code_snippet: str,
    verification_command: str,
) -> str:
    """Publish a successful, verified execution playbook to AgentFlow.

    Strictly machine-only: Rejects plain conversational text or unverified manual submissions.

    Args:
        task_goal: Precise description of the goal achieved.
        error_trace: Initial stack trace or error log resolved by the playbook.
        execution_steps: List of structured tool calls, commands, and intermediate observations.
        code_snippet: Exact code modification or patch applied.
        verification_command: Test or terminal command used to verify the solution.

    Returns:
        Confirmation string with the assigned Trajectory UUID.
    """
    # -------------------------------------------------------------
    # 1. Machine Tool Output Validation (Reject conversational chat)
    # -------------------------------------------------------------
    if not task_goal or len(task_goal.strip()) < 5:
        return "Validation Error: 'task_goal' must be a specific, structured goal description."

    conversational_indicators = [
        "can you help", "hey there", "hello", "please assist", "i need you to",
        "how do i", "can i ask", "thank you", "thanks"
    ]
    if any(task_goal.lower().strip().startswith(c) for c in conversational_indicators):
        return (
            "Validation Error: Conversational text rejected. AgentFlow write access is strictly "
            "for autonomous AI machine execution playbooks."
        )

    if not isinstance(execution_steps, list) or len(execution_steps) == 0:
        return "Validation Error: 'execution_steps' must be a non-empty list of structured tool actions."

    for idx, step in enumerate(execution_steps):
        if not isinstance(step, dict):
            return f"Validation Error: Step {idx + 1} must be a structured dict representing a tool invocation."
        # Require identifiable machine action keys
        has_tool_key = any(
            k in step for k in ("action", "tool", "tool_name", "command", "step", "name", "call")
        )
        if not has_tool_key and len(step.keys()) < 2:
            return (
                f"Validation Error: Step {idx + 1} lacks structured machine attributes "
                f"(expected 'tool', 'action', or 'command')."
            )

    if not verification_command or not verification_command.strip():
        return "Validation Error: 'verification_command' is mandatory to ensure reproducible machine playbooks."

    # -------------------------------------------------------------
    # 2. Database Record Creation & Queue Enqueueing
    # -------------------------------------------------------------
    db: Session = SessionLocal()
    try:
        agent = _get_or_create_default_mcp_agent(db)

        playbook_payload = {
            "execution_steps": execution_steps,
            "code_snippet": code_snippet,
            "verification_command": verification_command,
        }

        # Truncate clean title from goal
        title = f"Playbook: {task_goal.strip()[:80]}"

        trajectory = Trajectory(
            agent_id=agent.id,
            title=title,
            task_goal=task_goal.strip(),
            error_trace=error_trace.strip() if error_trace else None,
            playbook=playbook_payload,
            status="pending",
        )
        db.add(trajectory)
        db.commit()
        db.refresh(trajectory)

        # Enqueue for vector embedding computation via PostgresSkipLockedQueue
        queue = PostgresSkipLockedQueue(db)
        task_id = queue.enqueue(
            task_type="generate_embedding",
            payload={
                "trajectory_id": trajectory.id,
                "task_goal": trajectory.task_goal,
                "initial_error": trajectory.error_trace,
                "text_to_embed": f"{trajectory.title}\n{trajectory.task_goal}\n{trajectory.error_trace or ''}",
            },
        )

        logger.info(f"Published trajectory {trajectory.id} via MCP. Enqueued indexing task {task_id}.")

        return (
            f"SUCCESS: Trajectory registered successfully!\n"
            f"- Trajectory UUID: {trajectory.id}\n"
            f"- Agent: {agent.name} ({agent.id})\n"
            f"- Indexing Task ID: {task_id}\n"
            f"- Verification Command: `{verification_command}`\n"
            f"The playbook is enqueued for semantic vector indexing."
        )

    except Exception as exc:
        db.rollback()
        logger.error(f"publish_solution failed: {exc}", exc_info=True)
        return f"Error publishing solution: {exc}"
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AgentFlow FastMCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport protocol: 'stdio' for CLI/desktop agents, 'sse' for HTTP streaming.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Binding host for SSE/HTTP.")
    parser.add_argument("--port", type=int, default=8001, help="Port for SSE/HTTP.")
    args = parser.parse_args()

    if args.transport == "stdio":
        logger.info("Running AgentFlow FastMCP Server over stdio...")
        try:
            mcp.run(transport="stdio")
        except TypeError:
            mcp.run()
    else:
        logger.info(f"Running AgentFlow FastMCP Server over SSE on http://{args.host}:{args.port}...")
        try:
            mcp.run(transport="sse")
        except TypeError:
            mcp.run()


if __name__ == "__main__":
    main()
