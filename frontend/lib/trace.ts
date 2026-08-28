import type { RunEvent } from "@/lib/api";
import type { TraceEvent } from "@/lib/data";

export const RUN_EVENT_TYPES = [
  "test_cases_ready",
  "agent_started",
  "model_thinking",
  "model_response",
  "command_started",
  "command_finished",
  "file_changed",
  "test_started",
  "test_failed",
  "test_passed",
  "agent_submitted",
  "agent_finished",
  "review_started",
  "review_finished",
  "model_error",
  "run_error",
] as const;

const eventLabels: Record<string, string> = {
  test_cases_ready: "测试用例已准备",
  agent_started: "智能体开始运行",
  model_thinking: "模型分析中",
  model_response: "模型给出下一步",
  command_started: "开始执行命令",
  command_finished: "命令执行完成",
  file_changed: "文件已更新",
  test_started: "开始本地测试",
  test_failed: "本地测试失败",
  test_passed: "本地测试通过",
  agent_submitted: "智能体提交结果",
  agent_finished: "智能体循环结束",
  review_started: "开始代码评审",
  review_finished: "代码评审完成",
  model_error: "模型调用错误",
  run_error: "运行错误",
};

export function toTraceEvent(event: RunEvent, index: number): TraceEvent {
  const { type, data } = event;
  const rawOutput = data.output ?? data.error ?? data.command ?? data.content ?? "";
  const output = typeof rawOutput === "string" ? rawOutput : JSON.stringify(rawOutput, null, 2);
  const failed = type === "test_failed" || type === "model_error" || type === "run_error";
  const done = ["test_cases_ready", "file_changed", "test_passed", "agent_submitted", "agent_finished", "review_finished"].includes(type);

  let summary = output.split("\n")[0].slice(0, 80);
  if (type === "test_cases_ready") {
    const cases = Array.isArray(data.cases) ? data.cases.length : 0;
    summary = `${data.source === "generated" ? "AI 生成" : "人工输入"}，共 ${cases} 个用例`;
  } else if (type === "file_changed") {
    summary = String(data.filename ?? "工作区文件");
  } else if (type === "model_thinking") {
    summary = `第 ${data.step ?? index + 1} 次模型调用`;
  } else if (type === "model_response") {
    summary = `解析到 ${data.action_count ?? 0} 个 Bash 动作`;
  } else if (type === "test_started") {
    summary = "执行 python -m pytest -q";
  } else if (type === "test_passed") {
    summary = "权威输入输出用例全部通过";
  } else if (type === "test_failed") {
    summary = "失败信息已反馈给编程模型";
  } else if (type === "review_started") {
    summary = "本地测试通过，进入独立评审";
  } else if (type === "review_finished") {
    summary = "评审意见已保存";
  } else if (!summary) {
    summary = eventLabels[type] ?? type;
  }

  return {
    id: index + 1,
    label: eventLabels[type] ?? type,
    summary,
    time: new Date(event.timestamp).toLocaleTimeString("zh-CN", { hour12: false }),
    kind: failed ? "failed" : done ? "done" : "active",
    detail: output || undefined,
  };
}

export function terminalLines(events: RunEvent[]): string[] {
  const lines: string[] = [];
  for (const event of events) {
    if (event.type === "command_started" && typeof event.data.command === "string") {
      lines.push(`$ ${event.data.command}`);
    }
    if (event.type === "command_finished" && typeof event.data.output === "string" && event.data.output) {
      lines.push(event.data.output);
    }
    if ((event.type === "model_error" || event.type === "run_error") && typeof event.data.error === "string") {
      lines.push(event.data.error);
    }
  }
  return lines;
}
