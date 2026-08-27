"use client";

import Link from "next/link";
import { Check, ChevronRight, CircleStop, FileCode2, FlaskConical, GitBranch, Pause, Play, SquareTerminal } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { CodeEditor } from "@/components/code-editor";
import { ProblemPanel } from "@/components/problem-panel";
import { ReviewerCard } from "@/components/reviewer-card";
import { StatusBadge } from "@/components/status-badge";
import { TerminalPanel } from "@/components/terminal-panel";
import { TestPanel } from "@/components/test-panel";
import { trace, solutionCode, testCode } from "@/lib/data";
import { TraceTimeline } from "@/components/trace-timeline";

export function RunWorkspace() {
  const [file, setFile] = useState<"solution" | "tests">("solution");
  const [paused, setPaused] = useState(false);
  return <AppShell breadcrumb="Active run"><div className="run-header"><div className="run-heading"><div className="run-title"><StatusBadge status="running" /> <span>Longest Substring Without Repeating Characters</span></div><div className="run-subtitle"><span>run_01HZX2</span><span>Claude Sonnet 4</span><span>Started 14:02:11</span></div></div><div className="run-actions"><button className="secondary-button" type="button" onClick={() => setPaused(!paused)}>{paused ? <Play /> : <Pause />} <span>{paused ? "Resume" : "Pause"}</span></button><Link className="secondary-button" href="/history/run_01HZX2"><CircleStop /> <span>Stop run</span></Link></div></div><div className="workspace-grid"><ProblemPanel /><section className="workspace-center"><div className="file-tabs"><button className={`file-tab ${file === "solution" ? "active" : ""}`} type="button" onClick={() => setFile("solution")}><span className="file-dot" style={{ background: "var(--blue)" }} />solution.py</button><button className={`file-tab ${file === "tests" ? "active" : ""}`} type="button" onClick={() => setFile("tests")}><span className="file-dot" />test_solution.py</button><span style={{ marginLeft: "auto", padding: "0 10px 10px 0", color: "var(--dim)", fontSize: 10 }}><GitBranch style={{ width: 11, verticalAlign: "middle", marginRight: 4 }} /> agent/editing</span></div><CodeEditor value={file === "solution" ? solutionCode : testCode} /><TerminalPanel /><div style={{ padding: 14, borderTop: "1px solid var(--line-soft)" }}><TestPanel compact /></div></section><TraceTimeline items={trace} /></div></AppShell>;
}
