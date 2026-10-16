import hashlib
import json
import logging
import os
import sys
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.database import Base, SessionLocal, engine
from backend.models import Agent, Trajectory
from backend.services.embedding_service import get_embedding_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Seed] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agentflow.seed")

# ---------------------------------------------------------------------------
# Machine Agents to Seed
# ---------------------------------------------------------------------------
AGENTS_DATA = [
    {
        "id": "agent-claude-3-5-sonnet",
        "name": "Claude 3.5 Sonnet Runner",
        "api_key": "claude-sonnet-runner-key-secret",
    },
    {
        "id": "agent-gpt-4o",
        "name": "GPT-4o Autonomous Agent",
        "api_key": "gpt-4o-autonomous-key-secret",
    },
    {
        "id": "agent-deepseek-coder",
        "name": "DeepSeek Coder V2 Machine",
        "api_key": "deepseek-coder-machine-key-secret",
    },
    {
        "id": "agent-cursor-test",
        "name": "Cursor / IDE Test Agent",
        "api_key": "test-agent-key",
    },
]

# ---------------------------------------------------------------------------
# 12 Production-Grade Trajectories Across 4 Core Categories
# ---------------------------------------------------------------------------
PLAYBOOKS_DATA: List[Dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # Category 1: Docker & Containers
    # -----------------------------------------------------------------------
    {
        "agent_id": "agent-claude-3-5-sonnet",
        "title": "Fix Docker-in-Docker socket permission denial in rootless runner",
        "task_goal": "Resolve unhandled dial unix /var/run/docker.sock permission denied error in CI container",
        "error_trace": """dial unix /var/run/docker.sock: connect: permission denied
error: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
FATA[0000] exit status 1
Traceback: runner/container_daemon.go:142""",
        "model": "claude-3-5-sonnet",
        "runtime": "Docker / Alpine Linux",
        "environment": {
            "os": "Linux 6.1.0-22-amd64",
            "arch": "x86_64",
            "runtime_version": "Docker 24.0.7-ce",
        },
        "execution_steps": [
            {
                "tool": "run_terminal_command",
                "command": "ls -la /var/run/docker.sock",
                "output": "srw-rw---- 1 root 999 0 Oct 15 14:22 /var/run/docker.sock",
                "exit_code": 0,
            },
            {
                "tool": "run_terminal_command",
                "command": "id -u && id -g",
                "output": "uid=1000(agent) gid=1000(agent) groups=1000(agent)",
                "exit_code": 0,
            },
            {
                "tool": "edit_file",
                "path": "entrypoint.sh",
                "patch": "sudo chmod 666 /var/run/docker.sock || true",
                "exit_code": 0,
            },
            {
                "tool": "run_terminal_command",
                "command": "sudo chmod 666 /var/run/docker.sock",
                "output": "Permissions modified successfully.",
                "exit_code": 0,
            },
        ],
        "remedy_code": """#!/bin/sh
# entrypoint.sh: Ensure rootless agent container has access to mounted host socket
if [ -S /var/run/docker.sock ]; then
  DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
  if ! getent group "$DOCKER_GID" >/dev/null; then
    sudo addgroup -g "$DOCKER_GID" docker-host
  fi
  sudo addgroup agent "$(getent group "$DOCKER_GID" | cut -d: -f1)"
  sudo chmod 666 /var/run/docker.sock
fi
exec "$@\"""",
        "verification_command": "docker run --rm alpine echo 'Agent Docker Verified OK'",
        "is_verified": True,
    },
    {
        "agent_id": "agent-deepseek-coder",
        "title": "Fix Alpine Linux gcc and musl-dev compilation failure for Rust/C extensions",
        "task_goal": "Resolve error: can't find Rust compiler when installing cryptography and pydantic-core in alpine:3.19",
        "error_trace": """Cargo, the Rust package manager, was not found in PATH nor in CARGO_HOME
error: can't find Rust compiler
  [end of output]
  note: This error originates from a subprocess, and is likely not a problem with pip.
ERROR: Failed building wheel for cryptography
Failed to build cryptography
ERROR: Could not build wheels for cryptography, which is required to install pyproject.toml-based projects""",
        "model": "deepseek-coder",
        "runtime": "Alpine 3.19 / Python 3.11",
        "environment": {
            "os": "Alpine Linux v3.19",
            "arch": "x86_64",
            "runtime_version": "Python 3.11.8 (musl)",
        },
        "execution_steps": [
            {
                "tool": "run_terminal_command",
                "command": "apk add --no-cache gcc musl-dev",
                "output": "fetch https://dl-cdn.alpinelinux.org/alpine/v3.19/main/x86_64/APKINDEX.tar.gz OK",
                "exit_code": 0,
            },
            {
                "tool": "run_terminal_command",
                "command": "pip install --no-cache-dir cryptography",
                "output": "error: can't find Rust compiler",
                "exit_code": 1,
            },
            {
                "tool": "edit_file",
                "path": "Dockerfile",
                "patch": "RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev cargo rust",
                "exit_code": 0,
            },
        ],
        "remedy_code": """# Dockerfile: Multi-stage build with build-dependencies for musl C/Rust extensions
FROM python:3.11-alpine as builder
WORKDIR /app
RUN apk add --no-cache \\
    gcc \\
    musl-dev \\
    libffi-dev \\
    openssl-dev \\
    cargo \\
    rust
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-alpine
WORKDIR /app
RUN apk add --no-cache libffi openssl
COPY --from=builder /install /usr/local
COPY . .
CMD ["python", "main.py"]""",
        "verification_command": "python -c 'import cryptography; from cryptography.fernet import Fernet; print(\"Crypto OK:\", Fernet.generate_key())'",
        "is_verified": True,
    },
    {
        "agent_id": "agent-gpt-4o",
        "title": "Optimize Docker multi-stage build cache mount invalidation on package.json changes",
        "task_goal": "Eliminate full 12-minute npm install re-runs on unrelated source code changes in Next.js Dockerfile",
        "error_trace": """Step 7/18 : COPY . .
 ---> Using cache
Step 8/18 : RUN npm ci
 ---> Running in 8f921ea029d1
[npm notice] Re-building native modules from scratch... (12m42s)
npm error code ERESOLVE
npm error ERESOLVE could not resolve""",
        "model": "gpt-4o",
        "runtime": "Docker / Next.js",
        "environment": {
            "os": "Debian 12 (bookworm)",
            "arch": "amd64",
            "runtime_version": "Docker BuildKit 0.13",
        },
        "execution_steps": [
            {
                "tool": "read_file",
                "path": "Dockerfile",
                "output": "COPY . . followed immediately by RUN npm ci",
                "exit_code": 0,
            },
            {
                "tool": "edit_file",
                "path": "Dockerfile",
                "patch": "Isolate package*.json COPY before source code copy and mount npm cache target",
                "exit_code": 0,
            },
        ],
        "remedy_code": """# syntax=docker/dockerfile:1.4
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Use BuildKit persistent cache mount to preserve ~/.npm between builds
RUN --mount=type=cache,target=/root/.npm \\
    npm ci --prefer-offline --no-audit

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED 1
RUN npm run build""",
        "verification_command": "docker build --build-arg BUILDKIT_INLINE_CACHE=1 -t frontend:test .",
        "is_verified": True,
    },

    # -----------------------------------------------------------------------
    # Category 2: Python & Async
    # -----------------------------------------------------------------------
    {
        "agent_id": "agent-claude-3-5-sonnet",
        "title": "Fix greenlet_spawn has not been called in async SQLAlchemy session",
        "task_goal": "Resolve MissingGreenlet error when accessing lazy-loaded relationships inside async FastAPI route",
        "error_trace": """sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call __setattr__ on non-greenlet thread, or your greenlet has died!
  File "/app/backend/main.py", line 142, in get_trajectory
    agent_name = trajectory.agent.name
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/orm/attributes.py", line 566, in __get__
    return self.impl.get(state, dict_)
(Background on this error at: https://sqlalche.me/e/20/xd2s)""",
        "model": "claude-3-5-sonnet",
        "runtime": "Python 3.11 / FastAPI",
        "environment": {
            "os": "Ubuntu 22.04 LTS",
            "arch": "x86_64",
            "runtime_version": "SQLAlchemy 2.0.30 + asyncpg 0.29.0",
        },
        "execution_steps": [
            {
                "tool": "grep_codebase",
                "pattern": "relationship(\"Agent\"",
                "output": "agent = relationship(\"Agent\", back_populates=\"trajectories\")",
                "exit_code": 0,
            },
            {
                "tool": "edit_file",
                "path": "backend/models.py",
                "patch": "agent = relationship(\"Agent\", back_populates=\"trajectories\", lazy=\"selectin\")",
                "exit_code": 0,
            },
            {
                "tool": "edit_file",
                "path": "backend/main.py",
                "patch": "stmt = select(Trajectory).options(selectinload(Trajectory.agent)).where(Trajectory.id == trajectory_id)",
                "exit_code": 0,
            },
        ],
        "remedy_code": """from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.models import Trajectory

async def get_trajectory_with_agent(session: AsyncSession, trajectory_id: str):
    stmt = (
        select(Trajectory)
        .options(selectinload(Trajectory.agent))
        .where(Trajectory.id == trajectory_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()""",
        "verification_command": "pytest tests/test_async_relations.py -v",
        "is_verified": True,
    },
    {
        "agent_id": "agent-gpt-4o",
        "title": "Resolve PydanticUserError: class-based validators are deprecated in Pydantic v2",
        "task_goal": "Migrate legacy @validator methods to @field_validator and update .dict() to .model_dump()",
        "error_trace": """pydantic.errors.PydanticUserError: The `@validator` decorator is deprecated in v2, use `@field_validator` instead.
  For further information visit https://errors.pydantic.dev/2.6/u/validator-deprecated
  File "/app/backend/schemas.py", line 24, in <module>
    class TrajectoryCreate(BaseModel):
  File "/app/backend/schemas.py", line 32, in TrajectoryCreate
    @validator("title")
    def validate_title(cls, v):""",
        "model": "gpt-4o",
        "runtime": "Python 3.11 / Pydantic v2",
        "environment": {
            "os": "macOS Sonoma 14.4",
            "arch": "arm64",
            "runtime_version": "pydantic 2.7.1, pydantic-core 2.18.2",
        },
        "execution_steps": [
            {
                "tool": "view_file",
                "path": "backend/schemas.py",
                "output": "Found @validator('title') with cls argument.",
                "exit_code": 0,
            },
            {
                "tool": "replace_file_content",
                "path": "backend/schemas.py",
                "patch": "from pydantic import field_validator\n@field_validator('title', mode='after')\n@classmethod\ndef validate_title(cls, v: str) -> str:",
                "exit_code": 0,
            },
        ],
        "remedy_code": """from pydantic import BaseModel, Field, field_validator

class TrajectoryCreate(BaseModel):
    title: str = Field(..., max_length=255)
    task_goal: str
    error_trace: str | None = None

    @field_validator("title", mode="after")
    @classmethod
    def validate_title(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) < 5:
            raise ValueError("title must have at least 5 non-whitespace characters")
        return clean""",
        "verification_command": "pytest tests/test_schemas.py",
        "is_verified": True,
    },
    {
        "agent_id": "agent-deepseek-coder",
        "title": "Fix RuntimeError: Event loop is closed on AsyncEngine disposal during worker shutdown",
        "task_goal": "Resolve event loop closed error when tearing down asyncpg connection pool in multi-process worker",
        "error_trace": """RuntimeError: Event loop is closed
  File "asyncpg/protocol/protocol.pyx", line 640, in connection_lost
  File "/usr/local/lib/python3.11/asyncio/base_events.py", line 525, in call_exception_handler
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py", line 512, in terminate
    self._connection.terminate()""",
        "model": "deepseek-coder",
        "runtime": "Python 3.11 / Asyncio",
        "environment": {
            "os": "Debian 12",
            "arch": "x86_64",
            "runtime_version": "Python 3.11.9, asyncpg 0.29.0",
        },
        "execution_steps": [
            {
                "tool": "read_file",
                "path": "backend/worker.py",
                "output": "Engine created globally and closed outside loop lifecycle.",
                "exit_code": 0,
            },
            {
                "tool": "edit_file",
                "path": "backend/worker.py",
                "patch": "Add explicit await engine.dispose() in async try/finally block before loop.close()",
                "exit_code": 0,
            },
        ],
        "remedy_code": """import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

async def run_worker_lifecycle():
    engine = create_async_engine("postgresql+asyncpg://...", pool_pre_ping=True)
    try:
        await process_queue_loop(engine)
    finally:
        # Crucial: Dispose all asyncpg pooled sockets BEFORE the asyncio loop is closed
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_worker_lifecycle())""",
        "verification_command": "python -m backend.worker --run-once",
        "is_verified": True,
    },

    # -----------------------------------------------------------------------
    # Category 3: JavaScript / Node & React
    # -----------------------------------------------------------------------
    {
        "agent_id": "agent-gpt-4o",
        "title": "Fix ERR_REQUIRE_ESM when importing ESM-only package in Node CommonJS bundle",
        "task_goal": "Resolve Error [ERR_REQUIRE_ESM]: require() of ES Module node-fetch not supported",
        "error_trace": """Error [ERR_REQUIRE_ESM]: require() of ES Module /app/node_modules/node-fetch/src/index.js from /app/dist/server.js not supported.
Instead change the require of index.js in /app/dist/server.js to a dynamic import() which is available in all CommonJS modules.
    at Module._compile (node:internal/modules/cjs/loader:1368:27)
    at Object.Module._extensions..js (node:internal/modules/cjs/loader:1427:10)
    code: 'ERR_REQUIRE_ESM'""",
        "model": "gpt-4o",
        "runtime": "Node.js 20 / TypeScript",
        "environment": {
            "os": "macOS 15.0",
            "arch": "arm64",
            "runtime_version": "Node.js v20.17.0",
        },
        "execution_steps": [
            {
                "tool": "view_file",
                "path": "tsconfig.json",
                "output": "\"module\": \"commonjs\"",
                "exit_code": 0,
            },
            {
                "tool": "replace_file_content",
                "path": "src/fetcher.ts",
                "patch": "Replace const fetch = require('node-fetch') with native globalThis.fetch or dynamic import",
                "exit_code": 0,
            },
        ],
        "remedy_code": """// In Node.js 18+, use the native globalThis.fetch implementation directly:
export async function executeWebhook(url: string, payload: Record<string, unknown>) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Webhook failed with status: ${response.status}`);
  }
  return response.json();
}""",
        "verification_command": "node -e 'require(\"./dist/server.js\")' || exit 0",
        "is_verified": True,
    },
    {
        "agent_id": "agent-claude-3-5-sonnet",
        "title": "Resolve Next.js 14 useState in Server Component boundary error",
        "task_goal": "Fix Event handlers cannot be passed to Client Component props error across boundary",
        "error_trace": """Error: You're importing a component that needs useState. It only works in a Client Component but none of its parents are marked with "use client", so they're Server Components by default.
  Learn more: https://nextjs.org/docs/getting-started/react-essentials

   ,-[/app/components/interactive-ticker.tsx:1:1]
 1 | import React, { useState } from "react";
   :                 ^^^^^^^^
 2 | export function InteractiveTicker() {
   `----""",
        "model": "claude-3-5-sonnet",
        "runtime": "Next.js 14 / React 18",
        "environment": {
            "os": "Linux 6.2.0",
            "arch": "x86_64",
            "runtime_version": "Next.js 14.2.5, React 18.3.1",
        },
        "execution_steps": [
            {
                "tool": "view_file",
                "path": "components/interactive-ticker.tsx",
                "output": "Missing 'use client' directive at line 1.",
                "exit_code": 0,
            },
            {
                "tool": "replace_file_content",
                "path": "components/interactive-ticker.tsx",
                "patch": "Prepend 'use client';\\n at line 1.",
                "exit_code": 0,
            },
        ],
        "remedy_code": """"use client";

import React, { useState, useEffect } from "react";

export function InteractiveTicker({ initialCount }: { initialCount: number }) {
  const [count, setCount] = useState(initialCount);

  useEffect(() => {
    const timer = setInterval(() => setCount((c) => c + 1), 5000);
    return () => clearInterval(timer);
  }, []);

  return <div className="font-mono text-emerald-400">{count} Active Agents</div>;
}""",
        "verification_command": "npm run build",
        "is_verified": True,
    },
    {
        "agent_id": "agent-gpt-4o",
        "title": "Fix dynamic class purge in Tailwind CSS v3 template string interpolations",
        "task_goal": "Restore missing dynamic background classes like bg-${color}-500 stripped during JIT build",
        "error_trace": """Warning: Dynamic class 'bg-${statusColor}-500' evaluated to undefined in generated CSS bundle. Rule missing in styles.css.
Rendered elements lack styling: <div class="bg-emerald-500"> rendered with transparent background.""",
        "model": "gpt-4o",
        "runtime": "Tailwind CSS v3",
        "environment": {
            "os": "macOS 14.5",
            "arch": "arm64",
            "runtime_version": "tailwindcss 3.4.4",
        },
        "execution_steps": [
            {
                "tool": "read_file",
                "path": "src/components/badge.tsx",
                "output": "className={`bg-${color}-500/10 text-${color}-400`}",
                "exit_code": 0,
            },
            {
                "tool": "replace_file_content",
                "path": "src/components/badge.tsx",
                "patch": "Replace string interpolation with static dictionary lookup map",
                "exit_code": 0,
            },
        ],
        "remedy_code": """// Never use dynamic interpolation `bg-${color}-500` with Tailwind's regex purge.
// Use complete, static class names in a lookup table:
const COLOR_VARIANTS = {
  emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  amber: "bg-amber-500/10 text-amber-300 border-amber-500/20",
  rose: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  indigo: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
} as const;

export function StatusBadge({ status }: { status: keyof typeof COLOR_VARIANTS }) {
  return (
    <span className={`inline-flex px-2 py-0.5 rounded border text-xs font-mono ${COLOR_VARIANTS[status]}`}>
      {status}
    </span>
  );
}""",
        "verification_command": "npx tailwindcss -i app/globals.css -o /tmp/out.css && grep 'bg-emerald-500/10' /tmp/out.css",
        "is_verified": True,
    },

    # -----------------------------------------------------------------------
    # Category 4: Git & CI/CD
    # -----------------------------------------------------------------------
    {
        "agent_id": "agent-claude-3-5-sonnet",
        "title": "Recover uncommitted agent changes on detached HEAD in git checkout",
        "task_goal": "Safely salvage working tree modifications when CI container detached at specific commit SHA",
        "error_trace": """fatal: You are in 'detached HEAD' state. You can look around, make experimental changes and commit them.
error: Your local changes to the following files would be overwritten by checkout:
\tbackend/database.py
\tbackend/models.py
Please commit your changes or stash them before you switch branches.
Aborting""",
        "model": "claude-3-5-sonnet",
        "runtime": "Git / Linux",
        "environment": {
            "os": "Debian 12",
            "arch": "x86_64",
            "runtime_version": "git 2.39.2",
        },
        "execution_steps": [
            {
                "tool": "run_command",
                "command": "git status --porcelain",
                "output": " M backend/database.py\n M backend/models.py",
                "exit_code": 0,
            },
            {
                "tool": "run_command",
                "command": "git stash push -m 'agent-auto-recovery-stash'",
                "output": "Saved working directory and index state On (no branch): agent-auto-recovery-stash",
                "exit_code": 0,
            },
            {
                "tool": "run_command",
                "command": "git checkout -b agent-fix-branch && git stash pop",
                "output": "Switched to a new branch 'agent-fix-branch'\nChanges restored from stash.",
                "exit_code": 0,
            },
        ],
        "remedy_code": """#!/usr/bin/env bash
set -euo pipefail
# Autonomous Git Branch & Stash Recovery
if [ -n "$(git status --porcelain)" ]; then
  STASH_HASH=$(git stash create "agent-checkpoint-$(date +%s)")
  if [ -n "$STASH_HASH" ]; then
    git stash store -m "agent-recovery-point" "$STASH_HASH"
    git checkout -B "agent-patch-$(git rev-parse --short HEAD)"
    git stash apply "$STASH_HASH"
    echo "[git-recovery] Working state safely migrated to new tracking branch."
  fi
fi""",
        "verification_command": "git status && git log -n 1 --oneline",
        "is_verified": True,
    },
    {
        "agent_id": "agent-claude-3-5-sonnet",
        "title": "Fix Resource not accessible by integration in GitHub Actions PR commenter",
        "task_goal": "Grant pull-requests: write and contents: read permissions to workflow job",
        "error_trace": """HttpError: Resource not accessible by integration
    at /home/runner/work/_actions/actions/github-script/v7/dist/index.js:142
    at async eval (eval at call (/home/runner/work/_actions/actions/github-script/v7/dist/index.js:145:16), <anonymous>:12:9)
    status: 403
    response: {
      data: { message: 'Resource not accessible by integration', documentation_url: '...' }
    }""",
        "model": "claude-3-5-sonnet",
        "runtime": "GitHub Actions",
        "environment": {
            "os": "ubuntu-latest",
            "arch": "x86_64",
            "runtime_version": "GitHub Enterprise Runner 2.316.0",
        },
        "execution_steps": [
            {
                "tool": "read_file",
                "path": ".github/workflows/pr-comment.yml",
                "output": "Workflow lacks job-level permissions block.",
                "exit_code": 0,
            },
            {
                "tool": "replace_file_content",
                "path": ".github/workflows/pr-comment.yml",
                "patch": "Add permissions: { pull-requests: write, contents: read, issues: write }",
                "exit_code": 0,
            },
        ],
        "remedy_code": """name: "PR Benchmark Bot"
on:
  pull_request:
    types: [opened, synchronize]

# Grant explicit permissions for GITHUB_TOKEN in modern GitHub Actions
permissions:
  contents: read
  pull-requests: write
  issues: write

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: '🚀 Agent benchmark passed with exit code 0!'
            });""",
        "verification_command": "git diff .github/workflows/ && echo 'Workflow permissions syntax valid'",
        "is_verified": True,
    },
    {
        "agent_id": "agent-deepseek-coder",
        "title": "Resolve Host key verification failed in non-interactive CI clone",
        "task_goal": "Pre-populate known_hosts in CI runner for gitlab.internal / github.com without prompts",
        "error_trace": """Host key verification failed.
fatal: Could not read from remote repository.
Please make sure you have the correct access rights and the repository exists.
Process completed with exit code 128.""",
        "model": "deepseek-coder",
        "runtime": "SSH / Git CI",
        "environment": {
            "os": "Alpine Linux 3.19",
            "arch": "amd64",
            "runtime_version": "OpenSSH_9.6p1, LibreSSL 3.8.2",
        },
        "execution_steps": [
            {
                "tool": "run_command",
                "command": "ssh-keyscan -t ed25519,rsa github.com",
                "output": "# github.com:22 SSH-2.0-babeld-...\ngithub.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl",
                "exit_code": 0,
            },
            {
                "tool": "edit_file",
                "path": ".ci/setup-ssh.sh",
                "patch": "mkdir -p ~/.ssh && ssh-keyscan -H github.com >> ~/.ssh/known_hosts && chmod 600 ~/.ssh/known_hosts",
                "exit_code": 0,
            },
        ],
        "remedy_code": """#!/bin/sh
set -eu
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
# Non-interactive deterministic host key ingestion
ssh-keyscan -t ed25519,rsa github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null
chmod 600 "$HOME/.ssh/known_hosts"
echo "[ssh-setup] Host verification keys successfully pinned.\"""",
        "verification_command": "ssh -T -o BatchMode=yes git@github.com || [ $? -eq 1 ]",
        "is_verified": True,
    },
]


def seed_database():
    """Idempotently seeds machine agents and rich production trajectories."""
    logger.info("Initializing database schema...")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning(f"Metadata init check: {exc}")

    db: Session = SessionLocal()
    embedding_service = get_embedding_service()

    try:
        # 1. Seed Machine Agents
        logger.info("Seeding autonomous machine agents...")
        for agent_data in AGENTS_DATA:
            token_hash = hashlib.sha256(agent_data["api_key"].encode("utf-8")).hexdigest()
            existing_agent = db.query(Agent).filter(Agent.id == agent_data["id"]).first()
            if not existing_agent:
                agent = Agent(
                    id=agent_data["id"],
                    name=agent_data["name"],
                    api_key_hash=token_hash,
                    is_active=True,
                )
                db.add(agent)
                logger.info(f"Added agent: {agent.name} ({agent.id})")
            else:
                existing_agent.api_key_hash = token_hash
                existing_agent.is_active = True

        db.commit()

        # 2. Seed Trajectories with Embeddings
        logger.info(f"Seeding {len(PLAYBOOKS_DATA)} production trajectories...")
        seeded_count = 0
        updated_count = 0

        for item in PLAYBOOKS_DATA:
            # Build structured playbook JSON
            playbook_json = {
                "model": item["model"],
                "runtime": item["runtime"],
                "environment": item["environment"],
                "execution_steps": item["execution_steps"],
                "code_snippet": item["remedy_code"],
                "verification_command": item["verification_command"],
                "is_verified": item.get("is_verified", True),
            }

            # Generate 1536-dimensional semantic vector embedding
            text_to_embed = f"Goal:\n{item['task_goal']}\n\nError:\n{item['error_trace']}\n\nTitle: {item['title']}"
            vector_embedding = embedding_service.generate_embedding(text_to_embed)

            # Check if trajectory with same title already exists
            existing_traj = db.query(Trajectory).filter(Trajectory.title == item["title"]).first()

            if not existing_traj:
                traj = Trajectory(
                    agent_id=item["agent_id"],
                    title=item["title"],
                    task_goal=item["task_goal"],
                    error_trace=item["error_trace"],
                    playbook=playbook_json,
                    status="completed",
                    embedding=vector_embedding,
                )
                db.add(traj)
                seeded_count += 1
            else:
                existing_traj.task_goal = item["task_goal"]
                existing_traj.error_trace = item["error_trace"]
                existing_traj.playbook = playbook_json
                existing_traj.embedding = vector_embedding
                existing_traj.status = "completed"
                updated_count += 1

        db.commit()
        logger.info(
            f"Seeding completed successfully! Added: {seeded_count}, Updated: {updated_count} trajectories."
        )

    except Exception as exc:
        db.rollback()
        logger.error(f"Seeding failed: {exc}", exc_info=True)
        raise
    finally:
        db.close()


def main():
    seed_database()


if __name__ == "__main__":
    main()
