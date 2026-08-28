"use client";

import Link from "next/link";
import { Check, ChevronRight, Clock3, Cpu, FileCheck2, Plus, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { checkApi, listRuns, type ApiRun } from "@/lib/api";
import type { RunStatus } from "@/lib/data";

function runStatus(run: ApiRun): RunStatus {
  if (run.status === "error" || (run.done && !run.result?.verified)) return "failed";
  const reviewing = run.events.some((event) => event.type === "review_started")
    && !run.events.some((event) => event.type === "review_finished");
  if (reviewing) return "reviewing";
  return run.done && run.result?.verified ? "passed" : "running";
}

export function Dashboard() {
  const [runs, setRuns] = useState<ApiRun[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([listRuns(), checkApi()])
      .then(([items, health]) => {
        setRuns(items);
        setConnected(health);
      })
      .catch(() => setConnected(false))
      .finally(() => setLoading(false));
  }, []);

  const metrics = useMemo(() => {
    const passed = runs.filter((run) => runStatus(run) === "passed").length;
    const calls = runs.reduce((sum, run) => sum + (run.result?.model_calls ?? 0), 0);
    return {
      rate: runs.length ? Math.round((passed / runs.length) * 100) : 0,
      averageSteps: runs.length ? (calls / runs.length).toFixed(1) : "0.0",
    };
  }, [runs]);

  return (
    <AppShell>
      <main className="page">
        <div className="page-header">
          <div>
            <div className="eyebrow">实时数据 / FastAPI</div>
            <h1 className="page-title">智能体工作台</h1>
            <p className="page-description">这里显示当前后端进程中的真实运行任务。</p>
          </div>
          <Link className="primary-button" href="/task/new"><Plus /> 新建任务</Link>
        </div>

        <div className="stats-grid">
          <Metric label="运行总数" value={runs.length} />
          <Metric label="通过率" value={`${metrics.rate}%`} />
          <Metric label="平均模型调用" value={metrics.averageSteps} />
          <Metric label="后端连接" value={connected ? "正常" : "断开"} color={connected ? "var(--green)" : "var(--red)"} />
        </div>

        <div className="section-heading">
          <div className="section-title">最近运行</div>
          <span className="muted-link">{loading ? "加载中..." : `${runs.length} 条记录`}</span>
        </div>
        <div className="runs-table">
          <div className="run-row table-header"><div>题目</div><div>状态</div><div>模型</div><div>调用</div><div>测试</div><div /></div>
          {runs.map((run) => <RunRow key={run.run_id} run={run} />)}
          {!loading && !runs.length && (
            <div style={{ padding: 30, textAlign: "center", color: "var(--muted)" }}>
              还没有运行记录。<Link href="/task/new" style={{ color: "var(--blue)", marginLeft: 6 }}>创建第一条任务</Link>
            </div>
          )}
        </div>

        <div className="dashboard-secondary-grid">
          <section className="panel">
            <div className="panel-header"><span className="panel-title">最近活动</span><Clock3 style={{ width: 14, color: "var(--dim)" }} /></div>
            <div className="panel-body" style={{ paddingTop: 5, paddingBottom: 5 }}>
              {runs.slice(0, 3).map((run) => (
                <div className="meta-row" key={run.run_id}>
                  <span>{run.task.split("\n")[0].slice(0, 36)}</span>
                  <span>{new Date(run.created_at).toLocaleTimeString("zh-CN", { hour12: false })}</span>
                </div>
              ))}
              {!runs.length && <div style={{ padding: 12, color: "var(--dim)" }}>暂无活动</div>}
            </div>
          </section>
          <section className="panel">
            <div className="panel-header"><span className="panel-title">运行环境</span><FileCheck2 style={{ width: 14, color: connected ? "var(--green)" : "var(--red)" }} /></div>
            <div className="panel-body" style={{ display: "grid", gap: 10 }}>
              <div className="runtime-row"><span className={`status-dot ${connected ? "" : "yellow"}`} /> FastAPI {connected ? "已连接" : "未连接"}</div>
              <div className="runtime-row"><span className={`status-dot ${connected ? "" : "yellow"}`} /> Agent 事件流 {connected ? "可用" : "不可用"}</div>
              <div style={{ color: "var(--dim)", fontSize: 10, fontFamily: "var(--mono)" }}>http://127.0.0.1:8000</div>
            </div>
          </section>
        </div>
      </main>
    </AppShell>
  );
}

function Metric({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return <div className="stat-block"><div className="stat-label">{label}</div><div className="stat-value" style={color ? { color, fontSize: 16 } : undefined}>{value}</div></div>;
}

function RunRow({ run }: { run: ApiRun }) {
  const status = runStatus(run);
  const icon = status === "passed" ? <Check /> : status === "reviewing" ? <Sparkles /> : <Cpu />;
  const color = status === "passed" ? "green" : status === "failed" ? "red" : status === "reviewing" ? "yellow" : "";
  return (
    <Link href={`/history/${run.run_id}`} className="run-row">
      <div className="run-problem"><span className={`run-glyph ${color}`}>{icon}</span><span><span className="run-name">{run.task.split("\n")[0].slice(0, 52)}</span><span className="run-id">{run.run_id}</span></span></div>
      <div><StatusBadge status={status} /></div>
      <div className="table-cell">{run.model}</div>
      <div className="table-cell mono">{run.result?.model_calls ?? "-"}</div>
      <div className="table-cell mono">{run.test_cases?.length ?? 0}</div>
      <span className="row-chevron"><ChevronRight /></span>
    </Link>
  );
}
