export type ManualCase = { name?: string; input: string; expected_output: string };
export type TestCase = ManualCase & { name: string; source?: string };
export type RunEvent = { sequence?: number; type: string; data: Record<string, unknown>; timestamp: string };
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
  result?: { verified?: boolean; model_calls?: number; solution_path?: string; test_path?: string; test_cases_path?: string; last_test_output?: string };
  review?: { content?: string; local_verification?: string };
};

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
