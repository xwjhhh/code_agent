"use client";

import Link from "next/link";
import { ArrowRight, Bot, Check, Clock3, FileCode2, FlaskConical, GitBranch, Info, Play, Settings2, Sparkles, TerminalSquare } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";

export function NewTaskForm() {
  const [problem, setProblem] = useState("Given a string s, find the length of the longest substring without repeating characters.\n\nExamples:\nInput: s = \\\"abcabcbb\\\"\nOutput: 3\n\nConstraints: 0 <= s.length <= 5 * 10^4");
  const [submitted, setSubmitted] = useState(false);
  const startRun = () => { if (problem.trim()) setSubmitted(true); };
  return <AppShell breadcrumb="New task">
    <main className="page">
      <div className="page-header"><div><div className="eyebrow">Create a run</div><h1 className="page-title">Give your agent a problem</h1><p className="page-description">Describe the algorithm challenge. The agent will write, test, and review a solution.</p></div><div className="badge blue"><span className="badge-dot" /> Python workspace</div></div>
      {submitted && <div className="callout" style={{ marginTop: -10, marginBottom: 18, borderColor: "var(--green)", background: "var(--green-soft)", color: "#a9e5c2" }}>Run prepared. Connect this action to the FastAPI task endpoint to start a live agent session.</div>}
      <div className="form-layout">
        <section className="panel"><div className="panel-header"><span className="panel-title">Problem statement</span><span style={{ color: "var(--dim)", fontSize: 10, fontFamily: "var(--mono)" }}>MARKDOWN</span></div><div className="panel-body"><div className="field"><label className="field-label" htmlFor="problem">What should the agent solve?</label><textarea id="problem" className="textarea" value={problem} onChange={(event) => setProblem(event.target.value)} placeholder="Paste a coding problem, constraints, and examples..." /></div><div className="field"><label className="field-label" htmlFor="notes">Additional instructions <span style={{ color: "var(--dim)", fontWeight: 400 }}>(optional)</span></label><input id="notes" className="input" placeholder="e.g. Prefer a linear-time solution" /></div><div className="form-footer"><Link href="/" className="secondary-button">Cancel</Link><button className="primary-button" type="button" onClick={startRun}><Play /> Run agent <ArrowRight /></button></div></div></section>
        <aside style={{ display: "grid", gap: 16 }}>
          <section className="panel"><div className="panel-header"><span className="panel-title">Run configuration</span><Settings2 style={{ width: 14, color: "var(--dim)" }} /></div><div className="panel-body"><div className="field"><label className="field-label" htmlFor="model">Model</label><select id="model" className="select" defaultValue="claude"><option value="claude">Claude Sonnet 4</option><option value="gpt">GPT-4o</option><option value="deepseek">DeepSeek Chat</option></select></div><div className="setting-grid"><div className="field"><label className="field-label" htmlFor="steps">Max steps</label><input id="steps" className="input" defaultValue="20" type="number" /></div><div className="field"><label className="field-label" htmlFor="timeout">Timeout</label><input id="timeout" className="input" defaultValue="120" type="number" /></div></div><div className="field"><label className="field-label">Output language</label><div className="badge blue" style={{ height: 36, width: "100%", justifyContent: "flex-start", paddingLeft: 11 }}><FileCode2 /> Python 3.11</div></div></div></section>
          <section className="panel"><div className="panel-header"><span className="panel-title">What happens next</span><Sparkles style={{ width: 14, color: "var(--purple)" }} /></div><div className="panel-body"><div className="pipeline"><div className="pipeline-step done"><div className="pipeline-node"><Check /></div><div className="pipeline-copy"><div className="pipeline-name">Understand</div><div className="pipeline-detail">Parse constraints and plan an approach</div></div></div><div className="pipeline-step active"><div className="pipeline-node"><Bot /></div><div className="pipeline-copy"><div className="pipeline-name">Build and test</div><div className="pipeline-detail">Write code, generate expected outputs, run pytest</div></div></div><div className="pipeline-step"><div className="pipeline-node"><FlaskConical /></div><div className="pipeline-copy"><div className="pipeline-name">Review</div><div className="pipeline-detail">Inspect complexity, edge cases, and coverage</div></div></div></div><div className="callout"><Info style={{ width: 13, verticalAlign: "middle", marginRight: 5 }} /> Tests are generated from the problem and run locally in an isolated workspace.</div></div></section>
        </aside>
      </div>
    </main>
  </AppShell>;
}
