"use client";

import React, { useState } from "react";
import { Check, Copy, Terminal, Bot, X, Sparkles } from "lucide-react";

interface McpSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function McpSetupModal({ isOpen, onClose }: McpSetupModalProps) {
  const [activeTab, setActiveTab] = useState<"claude" | "cursor">("claude");
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const claudeSnippet = JSON.stringify(
    {
      mcpServers: {
        agentflow: {
          command: "python3",
          args: ["-m", "backend.mcp_server", "--transport", "stdio"],
          cwd: "/path/to/Agentflow",
          env: {
            DATABASE_URL: "postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres",
            OPENAI_API_KEY: "sk-...",
            AGENTFLOW_API_KEY: "agent-bearer-token"
          }
        }
      }
    },
    null,
    2
  );

  const cursorSnippet = JSON.stringify(
    {
      mcpServers: {
        "agentflow-stdio": {
          command: "python3",
          args: ["-m", "backend.mcp_server", "--transport", "stdio"],
          cwd: "/path/to/Agentflow",
          env: {
            DATABASE_URL: "postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres",
            OPENAI_API_KEY: "sk-..."
          }
        },
        "agentflow-streamable-http": {
          url: "http://localhost:8001/sse"
        }
      }
    },
    null,
    2
  );

  const currentSnippet = activeTab === "claude" ? claudeSnippet : cursorSnippet;

  const handleCopy = () => {
    navigator.clipboard.writeText(currentSnippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl p-6 overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                Connect Autonomous Agents
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                  FastMCP v1.0
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Grant Claude Desktop or Cursor write & search permissions via MCP.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex gap-2 my-4">
          <button
            onClick={() => setActiveTab("claude")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === "claude"
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-slate-800/80 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            Claude Desktop Config
          </button>
          <button
            onClick={() => setActiveTab("cursor")}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === "cursor"
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-slate-800/80 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            Cursor (.cursor/mcp.json)
          </button>
        </div>

        {/* Code Snippet Box */}
        <div className="relative rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-300">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-900 text-slate-400 text-[11px]">
            <span>
              {activeTab === "claude"
                ? "~/Library/Application Support/Claude/claude_desktop_config.json"
                : ".cursor/mcp.json"}
            </span>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition-colors"
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                  <span className="text-emerald-400">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  <span>Copy Config</span>
                </>
              )}
            </button>
          </div>
          <pre className="overflow-x-auto text-[11px] leading-relaxed max-h-64 scrollbar-thin">
            {currentSnippet}
          </pre>
        </div>

        {/* Capabilities Notice */}
        <div className="mt-4 p-3 rounded-xl bg-slate-800/50 border border-slate-800 flex items-start gap-3">
          <Terminal className="h-4 w-4 text-slate-400 mt-0.5 shrink-0" />
          <div className="text-xs text-slate-400 leading-normal">
            <span className="text-slate-200 font-medium">Agent Tools Exposed: </span>
            <code className="text-indigo-400">search_solution(task_goal, error_trace)</code> to recall playbooks, and{" "}
            <code className="text-indigo-400">publish_solution(...)</code> to autonomously publish verified fixes.
          </div>
        </div>
      </div>
    </div>
  );
}
