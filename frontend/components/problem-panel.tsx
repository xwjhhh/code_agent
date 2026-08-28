import { BookOpen, Check, Clock3, Cpu, FileCode2 } from "lucide-react";
import type { TestCase } from "@/lib/api";

export function ProblemPanel({
  task,
  model,
  timeout = 120,
  cases = [],
  source = "manual",
}: {
  task?: string;
  model?: string;
  timeout?: number;
  cases?: TestCase[];
  source?: "manual" | "generated";
}) {
  return <aside className="workspace-left">
    <div className="eyebrow">题目</div>
    <h2 className="problem-title">算法题目</h2>
    <div className="problem-copy" style={{ whiteSpace: "pre-wrap" }}>{task || "正在读取题目..."}</div>
    <div className="problem-examples">
      {cases.slice(0, 2).map((item, index) =>
        <div className="example" key={item.name + "-" + index}><strong>输入</strong> {item.input || "（空输入）"}<br /><strong>输出</strong> {item.expected_output || "（空输出）"}</div>
      )}
      {!cases.length && <div className="example">等待后端准备输入输出用例...</div>}
    </div>
    <div className="problem-meta">
      <div className="meta-row"><span><BookOpen style={{ width: 11, verticalAlign: "middle", marginRight: 5 }} /> 用例来源</span><span style={{ color: source === "generated" ? "var(--purple)" : "var(--blue)" }}>{source === "generated" ? "AI 生成" : "人工输入"}</span></div>
      <div className="meta-row"><span><Cpu style={{ width: 11, verticalAlign: "middle", marginRight: 5 }} /> 模型</span><span>{model || "-"}</span></div>
      <div className="meta-row"><span><Clock3 style={{ width: 11, verticalAlign: "middle", marginRight: 5 }} /> 超时</span><span>{timeout}s</span></div>
      <div className="meta-row"><span><FileCode2 style={{ width: 11, verticalAlign: "middle", marginRight: 5 }} /> 语言</span><span>Python 3.11</span></div>
    </div>
    <div className="callout" style={{ marginTop: 18 }}><Check style={{ width: 12, verticalAlign: "middle", marginRight: 5 }} /> test_cases.json 同时提供给编程模型和 pytest。</div>
  </aside>;
}
