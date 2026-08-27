"use client";

import Link from "next/link";
import { ArrowLeft, Download, FileCode2, GitBranch, Play, Share2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CodeEditor } from "@/components/code-editor";
import { ReviewerCard } from "@/components/reviewer-card";
import { TestPanel } from "@/components/test-panel";
import { StatusBadge } from "@/components/status-badge";
import { solutionCode, testCode, trace } from "@/lib/data";
import { TraceTimeline } from "@/components/trace-timeline";

export function RunDetail() {
  return <AppShell breadcrumb="Run detail"><main className="page"><div className="page-header"><div><Link href="/" className="muted-link"><ArrowLeft style={{ width: 12, verticalAlign: "middle", marginRight: 5 }} /> All runs</Link><h1 className="page-title" style={{ marginTop: 15 }}>Longest Substring Without Repeating Characters</h1><div style={{ display: "flex", alignItems: "center", gap: 10 }}><StatusBadge status="passed" /><span className="table-cell mono">run_01HZX2</span><span className="table-cell">Completed 2 min ago</span></div></div><div style={{ display: "flex", gap: 8 }}><button className="secondary-button" type="button" title="Share run"><Share2 /><span>Share</span></button><button className="secondary-button" type="button" title="Download files"><Download /><span>Export</span></button><Link href="/run/run_01HZX2" className="primary-button"><Play /> Replay run</Link></div></div><div className="metric-row"><div className="metric"><div className="metric-name">Agent steps</div><div className="metric-value">6</div></div><div className="metric"><div className="metric-name">Duration</div><div className="metric-value">16.4s</div></div><div className="metric"><div className="metric-name">Tokens</div><div className="metric-value">8,420</div></div><div className="metric"><div className="metric-name">Cost</div><div className="metric-value">$0.09</div></div></div><div className="detail-grid" style={{ marginTop: 19 }}><div className="detail-main"><section className="panel"><div className="panel-header"><div style={{ display: "flex", alignItems: "center", gap: 7 }}><FileCode2 style={{ width: 14, color: "var(--blue)" }} /><span className="panel-title">solution.py</span></div><span className="table-cell mono">18 lines</span></div><div style={{ height: 410 }}><CodeEditor value={solutionCode} /></div><div className="replay-bar"><span>Replay position</span><div className="replay-track"><span /></div><span className="table-cell mono">6 / 6</span></div></section><TestPanel /></div><div className="detail-side"><ReviewerCard detailed /><section className="panel"><div className="panel-header"><span className="panel-title">Run trace</span><span className="table-cell mono">6 events</span></div><div style={{ maxHeight: 480, overflow: "auto" }}><TraceTimeline items={trace} /></div></section></div></div></main></AppShell>;
}
