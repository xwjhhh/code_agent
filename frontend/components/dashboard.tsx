"use client";

import Link from "next/link";
import { ArrowUpRight, Check, ChevronRight, CircleDollarSign, Clock3, Cpu, FileCheck2, Plus, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { runs } from "@/lib/data";
import { StatusBadge } from "@/components/status-badge";

export function Dashboard() {
  return <AppShell>
    <main className="page">
      <div className="page-header"><div><div className="eyebrow">Overview / 27 Aug 2026</div><h1 className="page-title">Your agent workspace</h1><p className="page-description">Watch your coding agent reason, build, test, and review.</p></div><Link className="primary-button" href="/task/new"><Plus /> New task</Link></div>
      <div className="stats-grid">
        <div className="stat-block"><div className="stat-label">Total runs</div><div className="stat-value">24 <span className="stat-trend">+4 this week</span></div></div>
        <div className="stat-block"><div className="stat-label">Pass rate</div><div className="stat-value">87.5<span style={{ fontSize: 13 }}>%</span> <span className="stat-trend">+6.2%</span></div></div>
        <div className="stat-block"><div className="stat-label">Avg. steps</div><div className="stat-value">7.8 <span className="stat-trend" style={{ color: "var(--muted)" }}>per run</span></div></div>
        <div className="stat-block"><div className="stat-label">Model spend</div><div className="stat-value">$2.84 <span className="stat-trend" style={{ color: "var(--muted)" }}>this month</span></div></div>
      </div>
      <div className="section-heading"><div className="section-title">Recent runs</div><Link href="/history/run_01HZX2" className="muted-link">View all <ArrowUpRight style={{ width: 12, verticalAlign: "middle" }} /></Link></div>
      <div className="runs-table">
        <div className="run-row" style={{ minHeight: 39, background: "#111415", color: "var(--dim)", fontSize: 10 }}><div>Problem</div><div>Status</div><div>Model</div><div>Steps</div><div>Tests</div><div /></div>
        {runs.map((run) => <Link href={`/history/${run.id}`} className="run-row" key={run.id}><div className="run-problem"><span className={`run-glyph ${run.status === "passed" ? "green" : run.status === "failed" ? "red" : run.status === "reviewing" ? "yellow" : ""}`}>{run.status === "passed" ? <Check /> : run.status === "failed" ? <CircleDollarSign /> : run.status === "reviewing" ? <Sparkles /> : <Cpu />}</span><span><span className="run-name">{run.title}</span><span className="run-id">{run.id}</span></span></div><div><StatusBadge status={run.status} /></div><div className="table-cell">{run.model}</div><div className="table-cell mono">{run.steps}</div><div className="table-cell mono">{run.tests}</div><span className="row-chevron"><ChevronRight /></span></Link>)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 25 }}>
        <div className="panel"><div className="panel-header"><span className="panel-title">Recent activity</span><Clock3 style={{ width: 14, color: "var(--dim)" }} /></div><div className="panel-body" style={{ paddingTop: 5, paddingBottom: 5 }}><div className="meta-row"><span>Agent completed Two Sum</span><span>2 min ago</span></div><div className="meta-row"><span>Reviewer scored Merge Intervals</span><span>1 hr ago</span></div><div className="meta-row"><span>New run started for Dijkstra</span><span>3 hr ago</span></div></div></div>
        <div className="panel"><div className="panel-header"><span className="panel-title">Runtime health</span><FileCheck2 style={{ width: 14, color: "var(--green)" }} /></div><div className="panel-body" style={{ display: "grid", gap: 10 }}><div className="runtime-row"><span className="status-dot" /> Local executor ready</div><div className="runtime-row"><span className="status-dot" /> Python test runner ready</div><div style={{ color: "var(--dim)", fontSize: 10, fontFamily: "var(--mono)" }}>Last health check 14:03:08</div></div></div>
      </div>
    </main>
  </AppShell>;
}
