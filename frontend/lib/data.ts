export type RunStatus = "passed" | "failed" | "running" | "reviewing";

export type TraceEvent = {
  id: number;
  label: string;
  summary: string;
  time: string;
  kind: "done" | "failed" | "active";
  detail?: string;
};
