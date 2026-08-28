"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, FileCode2, FolderOpen } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { CodeEditor } from "@/components/code-editor";
import { ReviewerCard } from "@/components/reviewer-card";
import { StatusBadge } from "@/components/status-badge";
import { TestPanel } from "@/components/test-panel";
import { TraceTimeline } from "@/components/trace-timeline";
import { getRun, getRunFiles, type ApiRun } from "@/lib/api";
import type { RunStatus } from "@/lib/data";
import { toTraceEvent } from "@/lib/trace";

type DetailFile = "solution.py" | "test_solution.py" | "test_cases.json";
type DetailFiles = Record<DetailFile, string>;

const emptyFiles: DetailFiles = { "solution.py": "", "test_solution.py": "", "test_cases.json": "" };

function displayStatus(run: ApiRun): RunStatus {
  if (run.status === "error" || (run.done && !run.result?.verified)) return "failed";
  const reviewing = run.events.some((event) => event.type === "review_started") && !run.events.some((event) => event.type === "review_finished");
  if (reviewing) return "reviewing";
  return run.done && run.result?.verified ? "passed" : "running";
}

export function RunDetail() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const [run, setRun] = useState<ApiRun | null>(null);
  const [files, setFiles] = useState<DetailFiles>(emptyFiles);
  const [activeFile, setActiveFile] = useState<DetailFile>("solution.py");
  const [error, setError] = useState("");

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const [nextRun, nextFiles] = await Promise.all([getRun(runId), getRunFiles(runId)]);
        if (stopped) return;
        setRun(nextRun);
        setFiles(nextFiles);
        if (!nextRun.done) timer = setTimeout(load, 1500);
      } catch (loadError) {
        if (!stopped) setError(loadError instanceof Error ? loadError.message : "无法读取运行记录。");
      }
    };

    void load();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  const status = run ? displayStatus(run) : "running";
  const lastTestEvent = [...(run?.events ?? [])].reverse().find((event) => event.type === "test_passed" || event.type === "test_failed");
  const testStatus: RunStatus = run?.result?.verified || lastTestEvent?.type === "test_passed"
    ? "passed"
    : lastTestEvent?.type === "test_failed"
      ? "failed"
      : "running";
  const trace = useMemo(() => (run?.events ?? []).map(toTraceEvent), [run?.events]);
  const title = run?.task.split("\n")[0].slice(0, 80) || "运行 " + runId;
  const language = activeFile === "test_cases.json" ? "json" : "python";

  return <AppShell breadcrumb="运行详情">
    <main className="page">
      {error && <div className="callout" style={{ marginBottom: 17, borderColor: "var(--red)", background: "var(--red-soft)", color: "#efabab" }}>{error}</div>}
      <div className="page-header">
        <div>
          <Link href="/" className="muted-link"><ArrowLeft style={{ width: 12, verticalAlign: "middle", marginRight: 5 }} /> 全部运行</Link>
          <h1 className="page-title" style={{ marginTop: 15 }}>{title}</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <StatusBadge status={status} />
            <span className="table-cell mono">{runId}</span>
            <span className="table-cell">{run?.done ? "运行已结束" : "运行中，页面自动刷新"}</span>
          </div>
        </div>
        <Link href={"/run/" + runId} className="primary-button"><FolderOpen /> 查看工作区</Link>
      </div>
      <div className="metric-row">
        <div className="metric"><div className="metric-name">模型调用</div><div className="metric-value">{run?.result?.model_calls ?? "-"}</div></div>
        <div className="metric"><div className="metric-name">模型</div><div className="metric-value" style={{ fontSize: 12, letterSpacing: 0 }}>{run?.model ?? "-"}</div></div>
        <div className="metric"><div className="metric-name">本地测试</div><div className="metric-value">{testStatus === "passed" ? "通过" : testStatus === "failed" ? "未通过" : "等待中"}</div></div>
        <div className="metric"><div className="metric-name">测试用例</div><div className="metric-value">{run?.test_cases.length ?? 0} <span style={{ color: "var(--dim)", fontSize: 10 }}>{run?.test_case_source === "generated" ? "AI 生成" : "人工输入"}</span></div></div>
      </div>
      <div className="detail-grid" style={{ marginTop: 19 }}>
        <div className="detail-main">
          <section className="panel">
            <div className="panel-header">
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}><FileCode2 style={{ width: 14, color: "var(--blue)" }} /><span className="panel-title">运行文件</span></div>
              <span className="table-cell mono">{trace.length} 个事件</span>
            </div>
            <div className="file-tabs">
              {(["solution.py", "test_solution.py", "test_cases.json"] as DetailFile[]).map((filename) =>
                <button className={"file-tab " + (activeFile === filename ? "active" : "")} type="button" onClick={() => setActiveFile(filename)} key={filename}>{filename}</button>
              )}
            </div>
            <div style={{ height: 410 }}><CodeEditor value={files[activeFile] || "文件尚未生成。"} language={language} /></div>
          </section>
          <TestPanel cases={run?.test_cases ?? []} status={testStatus} output={run?.result?.last_test_output ?? ""} source={run?.test_case_source ?? "manual"} />
        </div>
        <div className="detail-side">
          <ReviewerCard content={run?.review?.content} verified={Boolean(run?.result?.verified)} loading={status === "reviewing"} />
          <section className="panel">
            <div className="panel-header"><span className="panel-title">运行轨迹</span><span className="table-cell mono">{trace.length} 个事件</span></div>
            <div style={{ maxHeight: 560, overflow: "auto" }}><TraceTimeline items={trace} /></div>
          </section>
        </div>
      </div>
    </main>
  </AppShell>;
}
