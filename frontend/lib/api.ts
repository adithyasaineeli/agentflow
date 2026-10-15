export interface Trajectory {
  id: string;
  agent_id: string;
  title: string;
  task_goal: string;
  error_trace?: string | null;
  playbook: {
    execution_steps?: Array<{
      tool?: string;
      action?: string;
      name?: string;
      command?: string;
      params?: any;
      input?: any;
      output?: any;
      result?: any;
      status?: string;
      [key: string]: any;
    }>;
    code_snippet?: string;
    patch?: string;
    verification_command?: string;
    runtime?: string;
    model?: string;
    environment?: {
      os?: string;
      arch?: string;
      runtime_version?: string;
    };
    [key: string]: any;
  };
  status: string;
  created_at?: string | null;
  similarity_score?: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export async function fetchTrajectories(limit = 20, offset = 0): Promise<Trajectory[]> {
  try {
    const res = await fetch(`${API_BASE}/trajectories?limit=${limit}&offset=${offset}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`Failed to fetch trajectories: ${res.statusText}`);
    }
    return await res.json();
  } catch (error) {
    console.warn("Could not reach backend API, using fallback data:", error);
    return [];
  }
}

export async function fetchTrajectoryById(id: string): Promise<Trajectory | null> {
  try {
    const list = await fetchTrajectories(100, 0);
    const found = list.find((t) => t.id === id);
    if (found) return found;

    // Fallback direct fetch if route is added
    const res = await fetch(`${API_BASE}/trajectories/${id}`, { cache: "no-store" });
    if (res.ok) {
      return await res.json();
    }
    return null;
  } catch (error) {
    console.error("Error fetching trajectory by id:", error);
    return null;
  }
}

export async function searchTrajectories(
  queryEmbedding: number[],
  limit = 5
): Promise<Trajectory[]> {
  try {
    const res = await fetch(`${API_BASE}/trajectories/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query_embedding: queryEmbedding,
        limit,
      }),
    });
    if (!res.ok) throw new Error("Search failed");
    return await res.json();
  } catch (error) {
    console.error("Error searching trajectories:", error);
    return [];
  }
}
