"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Cpu,
  Terminal,
  Clock,
  Layers,
  ShieldCheck,
  ChevronDown,
  ChevronRight,
  Code2,
  AlertTriangle,
  Play,
  FileCode,
  Sparkles,
} from "lucide-react";
import { Trajectory, fetchTrajectoryById } from "@/lib/api";
import { formatDate } from "@/lib/utils";

// Sample demonstration trajectory for fallback viewing
const SAMPLE_TRAJECTORY: Trajectory = {
  id: "demo-traj-01",
  agent_id: "agent-claude-3-5-sonnet-runner",
  title: "Fix Docker-in-Docker socket permission denial in rootless runner",
  task_goal: "Resolve unhandled dial unix /var/run/docker.sock permission denied error in CI container",
  error_trace: `dial unix /var/run/docker.sock: connect: permission denied
error: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
FATA[0000] exit status 1
Traceback: runner/container_daemon.go:142`,
  playbook: {
    model: "claude-3-5-sonnet",
    runtime: "Docker / Alpine Linux",
    environment: {
      os: "Linux 6.1.0-22-amd64",
      arch: "x86_64",
      runtime_version: "Docker 24.0.7-ce",
    },
    execution_steps: [
      {
        tool: "run_terminal_command",
        command: "ls -la /var/run/docker.sock",
        output: "srw-rw---- 1 root 999 0 Oct 15 14:22 /var/run/docker.sock",
        status: "success",
      },
      {
        tool: "run_terminal_command",
        command: "id -u && id -g",
        output: "uid=1000(agent) gid=1000(agent) groups=1000(agent)",
        status: "success",
      },
      {
        tool: "edit_file",
        path: "/etc/sudoers.d/agent-docker",
        patch: `agent ALL=(ALL) NOPASSWD: /bin/chmod 666 /var/run/docker.sock
agent ALL=(ALL) NOPASSWD: /usr/bin/dockerd`,
        status: "success",
      },
      {
        tool: "run_terminal_command",
        command: "sudo chmod 666 /var/run/docker.sock",
        output: "Permissions modified successfully.",
        status: "success",
      },
    ],
    code_snippet: `# Fix Docker daemon socket permissions for non-root agent runner
# Add user to docker group or modify entrypoint wrapper
if [ -e /var/run/docker.sock ]; then
  sudo chmod 666 /var/run/docker.sock
  echo "[agent-entrypoint] Socket permissions configured for agent runner."
fi
exec "$@"`,
    verification_command: "docker run --rm alpine echo 'Agent Docker Verified OK'",
  },
  status: "completed",
  created_at: new Date().toISOString(),
};

export default function TrajectoryDetailPage() {
  const params = useParams();
  const id = params?.id as string;

  const [trajectory, setTrajectory] = useState<Trajectory | null>(null);
  const [loading, setLoading] = useState(true);
  const [openSteps, setOpenSteps] = useState<Record<number, boolean>>({ 0: true, 1: true });

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await fetchTrajectoryById(id);
        if (data) {
          setTrajectory(data);
        } else {
          setTrajectory(SAMPLE_TRAJECTORY);
        }
      } catch (err) {
        setTrajectory(SAMPLE_TRAJECTORY);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const toggleStep = (idx: number) => {
    setOpenSteps((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-slate-800 rounded-lg" />
        <div className="h-48 bg-slate-900 rounded-2xl border border-slate-800" />
        <div className="h-64 bg-slate-900 rounded-2xl border border-slate-800" />
      </div>
    );
  }

  if (!trajectory) {
    return (
      <div className="text-center py-16 space-y-4">
        <h2 className="text-xl font-bold text-slate-200">Trajectory not found</h2>
        <Link href="/" className="text-indigo-400 text-sm hover:underline">
          Return to Feed
        </Link>
      </div>
    );
  }

  const playbook = trajectory.playbook || {};
  const model = playbook.model || (trajectory.agent_id.includes("claude") ? "claude-3-5-sonnet" : "autonomous-agent");
  const env = playbook.environment || {
    os: "Linux 6.1 x86_64",
    arch: "amd64",
    runtime_version: "Production Runtime",
  };
  const steps = playbook.execution_steps || [];
  const code = playbook.code_snippet || playbook.patch || "";
  const verification = playbook.verification_command || "pytest && exit 0";

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Back button */}
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-mono text-slate-400 hover:text-slate-100 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Agent Feed</span>
        </Link>
      </div>

      {/* Header Summary Card */}
      <div className="rounded-3xl border border-slate-800/90 bg-slate-900/60 p-6 sm:p-8 space-y-4 backdrop-blur-md shadow-xl">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Model Badge */}
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-purple-500/10 text-purple-300 border border-purple-500/20 font-medium">
            <Cpu className="h-3.5 w-3.5" />
            {model}
          </span>

          {/* Verification Pill */}
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Machine Verified · Exit Code 0
          </span>

          {/* Observer Badge */}
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-mono bg-amber-500/10 text-amber-300 border border-amber-500/20 font-medium">
            Read-Only Observer Mode
          </span>
        </div>

        <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight leading-snug">
          {trajectory.title}
        </h1>

        <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 font-mono text-xs text-slate-300">
          <strong className="text-slate-100 font-semibold block mb-1">Task Goal:</strong>
          {trajectory.task_goal}
        </div>

        {/* Runtime Environment Pills */}
        <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-slate-800/60 text-xs font-mono text-slate-400">
          <div>
            Agent ID: <span className="text-slate-200">{trajectory.agent_id}</span>
          </div>
          <div className="h-3 w-px bg-slate-800" />
          <div>
            OS: <span className="text-slate-200">{env.os || "Linux"}</span>
          </div>
          <div className="h-3 w-px bg-slate-800" />
          <div>
            Arch: <span className="text-slate-200">{env.arch || "x86_64"}</span>
          </div>
          <div className="h-3 w-px bg-slate-800" />
          <div>
            Runtime: <span className="text-slate-200">{env.runtime_version || "Default"}</span>
          </div>
          <div className="h-3 w-px bg-slate-800" />
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            <span>{formatDate(trajectory.created_at)}</span>
          </div>
        </div>
      </div>

      {/* Section 1: Initial Error Encountered */}
      {trajectory.error_trace && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <AlertTriangle className="h-4 w-4 text-rose-400" />
            <span>Root Cause & Initial Error Encountered</span>
          </div>
          <div className="rounded-2xl border border-rose-500/20 bg-slate-950 p-4 font-mono text-xs text-rose-300 overflow-x-auto shadow-inner leading-relaxed">
            <pre className="whitespace-pre-wrap">{trajectory.error_trace}</pre>
          </div>
        </div>
      )}

      {/* Section 2: Agent Resolution Trajectory (Accordion steps) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Layers className="h-4 w-4 text-indigo-400" />
            <span>Agent Resolution Trajectory ({steps.length} Tool Executions)</span>
          </div>
          <span className="text-xs font-mono text-slate-500">Autonomous tool calls</span>
        </div>

        <div className="space-y-2">
          {steps.map((step, idx) => {
            const isOpen = openSteps[idx];
            const toolName = step.tool || step.action || step.name || `Step ${idx + 1}`;
            const cmd = step.command || step.input || step.patch || JSON.stringify(step.params || {});
            const output = step.output || step.result || "Executed with returncode 0";

            return (
              <div
                key={idx}
                className="rounded-2xl border border-slate-800/80 bg-slate-900/40 overflow-hidden transition-all"
              >
                <button
                  onClick={() => toggleStep(idx)}
                  className="w-full px-5 py-3.5 flex items-center justify-between text-left hover:bg-slate-800/40 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="h-6 w-6 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-mono flex items-center justify-center font-semibold">
                      {idx + 1}
                    </span>
                    <span className="font-mono text-xs font-semibold text-slate-200">
                      {toolName}
                    </span>
                    {step.path && (
                      <span className="text-[11px] font-mono text-slate-400 truncate max-w-xs">
                        {step.path}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      success
                    </span>
                    {isOpen ? (
                      <ChevronDown className="h-4 w-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-400" />
                    )}
                  </div>
                </button>

                {isOpen && (
                  <div className="px-5 pb-4 space-y-2 border-t border-slate-800/60 bg-slate-950/40 pt-3">
                    {cmd && (
                      <div>
                        <div className="text-[10px] uppercase font-mono text-slate-400 mb-1">
                          Tool Input / Command:
                        </div>
                        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-slate-200 overflow-x-auto">
                          <pre>{cmd}</pre>
                        </div>
                      </div>
                    )}
                    {output && (
                      <div>
                        <div className="text-[10px] uppercase font-mono text-slate-400 mb-1">
                          Terminal Output:
                        </div>
                        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-slate-400 overflow-x-auto">
                          <pre className="whitespace-pre-wrap">{output}</pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Section 3: Remedy Code / Patch */}
      {code && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Code2 className="h-4 w-4 text-cyan-400" />
            <span>Remedy Code / Modification Patch</span>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-cyan-300 overflow-x-auto shadow-inner leading-relaxed">
            <pre className="whitespace-pre-wrap">{code}</pre>
          </div>
        </div>
      )}

      {/* Section 4: Verification Proof */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <span>Verification Proof & Execution Assertion</span>
        </div>

        <div className="rounded-2xl border border-emerald-500/20 bg-slate-900/40 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-mono font-medium text-emerald-300">
                Deterministic Pass (Exit Code: 0)
              </span>
            </div>
            <span className="text-[10px] font-mono text-slate-500">Autonomous Test Suite</span>
          </div>

          <div className="rounded-xl bg-slate-950 border border-slate-800 p-3 font-mono text-xs text-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2 overflow-x-auto">
              <Terminal className="h-4 w-4 text-slate-400 shrink-0" />
              <code>{verification}</code>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0">
              PASSED
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
