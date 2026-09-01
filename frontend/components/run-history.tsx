"use client";

import Link from "next/link";
import { Check, ChevronRight, CircleAlert, Clock3, Cpu, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { listRuns, type ApiRun } from "@/lib/api";
import type { RunStatus } from "@/lib/data";

function runStatus(run: ApiRun): RunStatus {
  if (run.status === "error" || (run.done && !run.result?.verified)) return "failed";
  const reviewStarted = run.events.some((event) => event.type === "review_started");
  const reviewFinished = run.events.some((event) => event.type === "review_finished");
  if (reviewStarted && !reviewFinished) return "reviewing";
  return run.done && run.result?.verified ? "passed" : "running";
}

function formatCreated(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export function RunHistory() {
  const [runs, setRuns] = useState<ApiRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRuns(await listRuns());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "读取历史运行失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return <AppShell breadcrumb="历史运行">
    <main className="page">
      <div className="page-header">
        <div>
          <div className="eyebrow">运行记录</div>
          <h1 className="page-title">历史运行</h1>
          <p className="page-description">查看当前 FastAPI 进程中的任务、测试结果和代码评审。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? "spin" : ""} /> 刷新</button>
      </div>
      {error && <div className="callout" style={{ marginBottom: 18, borderColor: "var(--red)", background: "var(--red-soft)", color: "var(--red)" }}><CircleAlert style={{ width: 13, verticalAlign: "middle", marginRight: 6 }} />{error}</div>}
      <div className="section-heading"><div className="section-title">全部运行</div><span className="muted-link">{loading ? "加载中..." : `${runs.length} 条记录`}</span></div>
      <div className="runs-table history-runs-table">
        <div className="run-row table-header"><div>题目</div><div>状态</div><div>模型</div><div>调用</div><div>创建时间</div><div /></div>
        {runs.map((run) => {
          const status = runStatus(run);
          return <Link href={`/run/${run.run_id}`} className="run-row" key={run.run_id}>
            <div className="run-problem">
              <span className={`run-glyph ${status === "passed" ? "green" : status === "failed" ? "red" : status === "reviewing" ? "yellow" : ""}`}>{status === "passed" ? <Check /> : status === "reviewing" ? <Sparkles /> : <Cpu />}</span>
              <span><span className="run-name">{run.task.split("\n")[0].slice(0, 52)}</span><span className="run-id">{run.run_id}</span></span>
            </div>
            <div><StatusBadge status={status} /></div>
            <div className="table-cell">{run.model}</div>
            <div className="table-cell mono">{run.result?.model_calls ?? "-"}</div>
            <div className="table-cell">{formatCreated(run.created_at)}</div>
            <span className="row-chevron"><ChevronRight /></span>
          </Link>;
        })}
        {!loading && !runs.length && <div style={{ padding: 36, textAlign: "center", color: "var(--muted)" }}><Clock3 style={{ width: 16, verticalAlign: "middle", marginRight: 7 }} />暂无运行记录。<Link href="/task/new" style={{ color: "var(--blue)", marginLeft: 6 }}>创建任务</Link></div>}
      </div>
    </main>
  </AppShell>;
}
