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
  "memory_retrieval_started",
  "memory_retrieval_finished",
  "memory_route_decided",
  "memory_relevance_graded",
  "memory_query_rewritten",
  "memory_context_injected",
  "memory_learning_started",
  "memory_dedup_judged",
  "memory_learning_finished",
  "memory_error",
  "run_finished",
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
  memory_retrieval_started: "开始记忆检索",
  memory_retrieval_finished: "记忆检索完成",
  memory_route_decided: "记忆路由决策",
  memory_relevance_graded: "记忆相关性评估",
  memory_query_rewritten: "重写记忆查询",
  memory_context_injected: "经验已注入模型",
  memory_learning_started: "开始提炼经验",
  memory_dedup_judged: "记忆去重判断",
  memory_learning_finished: "经验已持久化",
  memory_error: "记忆服务错误",
  run_finished: "本次运行结束",
  model_error: "模型调用错误",
  run_error: "运行错误",
};

export function toTraceEvent(event: RunEvent, index: number): TraceEvent {
  const { type, data } = event;
  const rawOutput = data.output || data.error || data.exception_info || data.command || data.content || "";
  const output = typeof rawOutput === "string" ? rawOutput : JSON.stringify(rawOutput, null, 2);
  const failed = type === "test_failed" || type === "model_error" || type === "run_error";
  const done = ["test_cases_ready", "file_changed", "test_passed", "agent_submitted", "agent_finished", "review_finished", "run_finished"].includes(type);

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
  } else if (type === "memory_retrieval_started") {
    summary = `${data.phase === "recovery" ? "失败恢复" : "任务"}记忆检索中`;
  } else if (type === "memory_retrieval_finished") {
    summary = `召回 ${data.candidate_count ?? 0} 条候选，选中 ${Array.isArray(data.selected) ? data.selected.length : 0} 条`;
  } else if (type === "memory_route_decided") {
    summary = `${data.action === "skip" ? "跳过" : "开始检索"}：${String(data.reason ?? "")}`;
  } else if (type === "memory_relevance_graded") {
    summary = `${data.relevant ? "经验可使用" : "经验不适用"}：${String(data.reason ?? "")}`;
  } else if (type === "memory_query_rewritten") {
    summary = `第 ${data.attempt ?? 1} 次重写查询`;
  } else if (type === "memory_context_injected") {
    summary = `${data.phase === "recovery" ? "恢复" : "任务"}经验已加入模型上下文`;
  } else if (type === "memory_learning_started") {
    summary = "从已验证运行中提炼可复用经验";
  } else if (type === "memory_dedup_judged") {
    summary = `${data.duplicate ? "发现重复经验" : "保留新经验"}${data.reason ? `：${String(data.reason)}` : ""}`;
  } else if (type === "memory_learning_finished") {
    summary = `提炼 ${data.extracted_count ?? 0} 条，新增 ${data.stored_count ?? 0} 条记忆`;
  } else if (type === "memory_error") {
    summary = String(data.error ?? "记忆服务不可用");
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
    if (event.type === "command_finished" && typeof event.data.exception_info === "string" && event.data.exception_info) {
      lines.push(`[error] ${event.data.exception_info}`);
    }
    if ((event.type === "model_error" || event.type === "run_error") && typeof event.data.error === "string") {
      lines.push(event.data.error);
    }
  }
  return lines;
}
