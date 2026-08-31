export type ManualCase = { name?: string; input: string; expected_output: string };
export type TestCase = ManualCase & { name: string; source?: string };
export type RunEvent = { sequence?: number; type: string; data: Record<string, unknown>; timestamp: string };
export type MemoryCategory = "strategy" | "recovery" | "optimization";
export type MemoryGranularity = "task" | "subtask";
export type MemoryNode = {
  id: string;
  category: MemoryCategory;
  granularity: MemoryGranularity;
  trigger: string;
  content: string;
  purpose?: string;
  steps?: string[];
  negative_example?: string | null;
  problem_family?: string[];
  algorithm_tags?: string[];
  constraints?: string[];
  priority?: number;
  quality_score?: number;
  source_run_id?: string;
  source_verified?: boolean;
  embedding_model?: string;
  created_at?: string;
  retrieval_count?: number;
  similarity?: number;
  matched_query?: string;
};
export type MemoryRetrieval = {
  phase: "task" | "recovery";
  queries: { granularity: MemoryGranularity; category?: MemoryCategory | null; text: string }[];
  candidate_count: number;
  selected: MemoryNode[];
  route_action?: "retrieve" | "skip" | null;
  route_reason?: string;
  grade_relevant?: boolean | null;
  grade_reason?: string;
  grade_score?: number | null;
  rewrite_count?: number;
};
export type RunMemory = {
  enabled?: boolean;
  retrieval_skipped?: boolean;
  task_retrieval?: MemoryRetrieval;
  recovery_retrievals?: MemoryRetrieval[];
  learned?: MemoryNode[];
  initialization_error?: string;
  task_retrieval_error?: string;
  learning_error?: string;
};
export type MemoryGraphEdge = { source: string; target: string; kind: "solid" | "dotted"; similarity?: number };
export type MemoryGraphPayload = {
  enabled: boolean;
  count: number;
  embedding_model?: string;
  nodes: MemoryNode[];
  edges: MemoryGraphEdge[];
};
export type ApiRun = {
  run_id: string;
  task: string;
  model: string;
  status: "running" | "completed" | "error";
  done: boolean;
  error?: string | null;
  created_at: string;
  test_cases: TestCase[];
  test_case_source: "manual" | "generated";
  events: RunEvent[];
  memory?: RunMemory;
  result?: { verified?: boolean; model_calls?: number; solution_path?: string; test_path?: string; test_cases_path?: string; last_test_output?: string };
  review?: { content?: string; local_verification?: string };
};

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
export const ACTIVE_RUN_STORAGE_KEY = "code-agent:active-run";

export function rememberActiveRun(runId: string) {
  if (typeof window === "undefined" || !runId) return;
  try {
    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, runId);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}

export async function createRun(payload: { task: string; model: string; max_steps: number; timeout: number; test_cases: ManualCase[]; test_case_source: "manual" | "generated" }) {
  const response = await fetch(`${API_BASE}/api/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{ run_id: string }>;
}

export async function getRunFiles(runId: string) {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/files`, { cache: "no-store" });
  if (!response.ok) throw new Error("读取运行文件失败");
  return response.json() as Promise<{ "solution.py": string; "test_solution.py": string; "test_cases.json": string }>;
}

export async function getRun(runId: string) {
  const response = await fetch(`${API_BASE}/api/runs/${runId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("读取运行状态失败");
  return response.json() as Promise<ApiRun>;
}

export async function listRuns() {
  const response = await fetch(`${API_BASE}/api/runs`, { cache: "no-store" });
  if (!response.ok) throw new Error("读取运行列表失败");
  return response.json() as Promise<ApiRun[]>;
}

export async function getMemoryGraph(limit = 200) {
  const response = await fetch(`${API_BASE}/api/memories/graph?limit=${limit}`, { cache: "no-store" });
  if (!response.ok) throw new Error("读取记忆图谱失败");
  return response.json() as Promise<MemoryGraphPayload>;
}

export async function generateTestCases(payload: { task: string; model: string; count?: number }) {
  const response = await fetch(`${API_BASE}/api/test-cases/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{ source: "generated"; cases: TestCase[] }>;
}

export function runEventsUrl(runId: string, cursor = 0) {
  return `${API_BASE}/api/runs/${runId}/events?cursor=${cursor}`;
}

export async function checkApi() {
  try { return (await fetch(`${API_BASE}/api/health`, { cache: "no-store" })).ok; } catch { return false; }
}
