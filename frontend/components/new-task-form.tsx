"use client";

import Link from "next/link";
import { ArrowRight, Bot, Check, FileCode2, FlaskConical, Info, Play, Plus, Settings2, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { createRun, generateTestCases, type ManualCase } from "@/lib/api";

export function NewTaskForm() {
  const router = useRouter();
  const [problem, setProblem] = useState("输入一个字符串，将其中的数字字符移动到非数字字符之后，并保持数字字符和非数字字符输入时的顺序。\n\n输入：一行字符串，长度小于 100。\n输出：移动后的字符串。\n\n例如：输入 ab4f35gr#a6，输出 abfgr#a4356。");
  const [notes, setNotes] = useState("");
  const [cases, setCases] = useState<ManualCase[]>([
    { input: "ab4f35gr#a6", expected_output: "abfgr#a4356" },
    { input: "a1b2", expected_output: "ab12" },
  ]);
  const [model, setModel] = useState("demo");
  const [maxSteps, setMaxSteps] = useState(20);
  const [timeout, setTimeoutValue] = useState(120);
  const [submitting, setSubmitting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [testSource, setTestSource] = useState<"manual" | "generated">("manual");
  const [error, setError] = useState("");
  const task = notes.trim() ? `${problem.trim()}\n\n补充要求：\n${notes.trim()}` : problem.trim();
  const addCase = () => { setTestSource("manual"); setCases((items) => [...items, { input: "", expected_output: "" }]); };
  const updateCase = (index: number, key: keyof ManualCase, value: string) => { setTestSource("manual"); setCases((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item)); };
  const removeCase = (index: number) => { setTestSource("manual"); setCases((items) => items.filter((_, itemIndex) => itemIndex !== index)); };
  const generateCases = async () => {
    if (!problem.trim()) { setError("请先输入题目，再生成测试用例。"); return; }
    setGenerating(true); setError("");
    try {
      const result = await generateTestCases({ task, model, count: 6 });
      setCases(result.cases);
      setTestSource("generated");
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "生成测试用例失败。");
    } finally {
      setGenerating(false);
    }
  };
  const startRun = async () => {
    if (!problem.trim()) return;
    setSubmitting(true); setError("");
    try {
      const result = await createRun({ task, model, max_steps: maxSteps, timeout, test_cases: cases, test_case_source: testSource });
      router.push(`/run/${result.run_id}`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "创建运行失败，请确认后端已启动。");
      setSubmitting(false);
    }
  };
  return <AppShell breadcrumb="新建任务">
    <main className="page">
      <div className="page-header"><div><div className="eyebrow">创建运行</div><h1 className="page-title">给智能体一道题</h1><p className="page-description">描述算法题目，智能体会自动编写代码、生成测试、运行验证并完成评审。</p></div><div className="badge blue"><span className="badge-dot" /> Python 工作区</div></div>
      {error && <div className="callout" style={{ marginTop: -10, marginBottom: 18, borderColor: "var(--red)", background: "var(--red-soft)", color: "var(--red)" }}>{error}</div>}
      <div className="form-layout">
        <section className="panel"><div className="panel-header"><span className="panel-title">题目描述</span><span style={{ color: "var(--dim)", fontSize: 10, fontFamily: "var(--mono)" }}>题目文本</span></div><div className="panel-body"><div className="field"><label className="field-label" htmlFor="problem">你希望智能体解决什么问题？</label><textarea id="problem" className="textarea" value={problem} onChange={(event) => { setProblem(event.target.value); if (testSource === "generated") { setCases([]); setTestSource("manual"); } }} placeholder="粘贴题目、约束条件和样例..." /></div><div className="field"><label className="field-label" htmlFor="notes">补充要求 <span style={{ color: "var(--dim)", fontWeight: 400 }}>（可选）</span></label><input id="notes" className="input" value={notes} onChange={(event) => { setNotes(event.target.value); if (testSource === "generated") { setCases([]); setTestSource("manual"); } }} placeholder="例如：优先使用线性时间复杂度" /></div><div className="field"><div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}><div style={{ display: "flex", alignItems: "center", gap: 8 }}><label className="field-label">测试输入与期望输出</label><span className={`badge ${testSource === "generated" ? "purple" : "blue"}`}>{testSource === "generated" ? "AI 生成" : "人工输入"}</span></div><div style={{ display: "flex", gap: 6 }}><button className="secondary-button" type="button" onClick={generateCases} disabled={generating} style={{ height: 28, padding: "0 9px" }}><Sparkles /> {generating ? "生成中..." : "AI 生成"}</button><button className="secondary-button" type="button" onClick={addCase} style={{ height: 28, padding: "0 9px" }}><Plus /> 添加</button></div></div><div className="field-hint">每项都是完整的标准输入和标准输出文本，支持多行。运行时保存为 test_cases.json，同时提供给编程模型和 pytest。</div><div style={{ display: "grid", gap: 10 }}>{cases.map((item, index) => <div className="test-case-editor" key={`${item.name ?? "case"}-${index}`}><div className="test-case-editor-head"><span>{item.name || `用例 ${index + 1}`}</span><button className="icon-button" type="button" title="删除测试用例" onClick={() => removeCase(index)}><Trash2 /></button></div><div className="test-case-editor-grid"><div><label className="field-label" htmlFor={`case-input-${index}`}>输入</label><textarea id={`case-input-${index}`} className="case-textarea" placeholder="完整标准输入" value={item.input} onChange={(event) => updateCase(index, "input", event.target.value)} /></div><div><label className="field-label" htmlFor={`case-output-${index}`}>期望输出</label><textarea id={`case-output-${index}`} className="case-textarea" placeholder="完整标准输出" value={item.expected_output} onChange={(event) => updateCase(index, "expected_output", event.target.value)} /></div></div></div>)}</div></div><div className="form-footer"><Link href="/" className="secondary-button">取消</Link><button className="primary-button" type="button" onClick={startRun} disabled={submitting || generating}>{submitting ? "正在创建..." : <><Play /> 运行智能体 <ArrowRight /></>}</button></div></div></section>
        <aside style={{ display: "grid", gap: 16 }}>
          <section className="panel"><div className="panel-header"><span className="panel-title">运行配置</span><Settings2 style={{ width: 14, color: "var(--dim)" }} /></div><div className="panel-body"><div className="field"><label className="field-label" htmlFor="model">模型</label><select id="model" className="select" value={model} onChange={(event) => setModel(event.target.value)}><option value="demo">演示模型（本地，无需 Key）</option><option value="claude-sonnet-4">Claude Sonnet 4（LiteLLM）</option><option value="openai/gpt-4o-mini">GPT-4o mini（LiteLLM）</option><option value="deepseek/deepseek-chat">DeepSeek Chat（LiteLLM）</option></select></div><div className="setting-grid"><div className="field"><label className="field-label" htmlFor="steps">最大步骤</label><input id="steps" className="input" value={maxSteps} onChange={(event) => setMaxSteps(Number(event.target.value))} type="number" min="1" max="100" /></div><div className="field"><label className="field-label" htmlFor="timeout">命令超时（秒）</label><input id="timeout" className="input" value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} type="number" min="1" max="600" /></div></div><div className="field"><label className="field-label">输出语言</label><div className="badge blue" style={{ height: 36, width: "100%", justifyContent: "flex-start", paddingLeft: 11 }}><FileCode2 /> Python 3.11</div></div></div></section>
          <section className="panel"><div className="panel-header"><span className="panel-title">接下来会发生什么</span><Sparkles style={{ width: 14, color: "var(--purple)" }} /></div><div className="panel-body"><div className="pipeline"><div className="pipeline-step done"><div className="pipeline-node"><Check /></div><div className="pipeline-copy"><div className="pipeline-name">准备测试用例</div><div className="pipeline-detail">保存人工填写或 AI 生成的输入输出</div></div></div><div className="pipeline-step active"><div className="pipeline-node"><Bot /></div><div className="pipeline-copy"><div className="pipeline-name">编写并测试</div><div className="pipeline-detail">模型读取用例、写题解并运行 pytest</div></div></div><div className="pipeline-step"><div className="pipeline-node"><FlaskConical /></div><div className="pipeline-copy"><div className="pipeline-name">代码评审</div><div className="pipeline-detail">检查复杂度、边界情况和覆盖率</div></div></div></div><div className="callout"><Info style={{ width: 13, verticalAlign: "middle", marginRight: 5 }} /> 权威测试文件由系统保护，编程模型不能修改。</div></div></section>
        </aside>
      </div>
    </main>
  </AppShell>;
}
