"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { CircleStop, GitBranch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { CodeEditor } from "@/components/code-editor";
import { ProblemPanel } from "@/components/problem-panel";
import { ReviewerCard } from "@/components/reviewer-card";
import { MemoryGraph } from "@/components/memory-graph";
import { StatusBadge } from "@/components/status-badge";
import { TerminalPanel } from "@/components/terminal-panel";
import { TestPanel } from "@/components/test-panel";
import { TraceTimeline } from "@/components/trace-timeline";
import { getRun, getRunFiles, runEventsUrl, type ApiRun, type RunEvent, type TestCase } from "@/lib/api";
import type { RunStatus } from "@/lib/data";
import { RUN_EVENT_TYPES, terminalLines, toTraceEvent } from "@/lib/trace";

type WorkspaceFile = "solution.py" | "test_solution.py" | "test_cases.json";
type WorkspaceFiles = Record<WorkspaceFile, string>;

const emptyFiles: WorkspaceFiles = {
  "solution.py": "",
  "test_solution.py": "",
  "test_cases.json": "",
};

function statusFromRun(run: ApiRun): RunStatus {
  if (run.status === "error" || (run.done && !run.result?.verified)) return "failed";
  const reviewStarted = run.events.some((event) => event.type === "review_started");
  const reviewFinished = run.events.some((event) => event.type === "review_finished");
  if (reviewStarted && !reviewFinished) return "reviewing";
  return run.done && run.result?.verified ? "passed" : "running";
}

export function RunWorkspace() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const [activeFile, setActiveFile] = useState<WorkspaceFile>("solution.py");
  const [status, setStatus] = useState<RunStatus>("running");
  const [testStatus, setTestStatus] = useState<RunStatus>("running");
  const [task, setTask] = useState("正在读取题目...");
  const [model, setModel] = useState("模型连接中...");
  const [files, setFiles] = useState<WorkspaceFiles>(emptyFiles);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [testSource, setTestSource] = useState<"manual" | "generated">("manual");
  const [lastTestOutput, setLastTestOutput] = useState("");
  const [review, setReview] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [error, setError] = useState("");
  const [inspectorTab, setInspectorTab] = useState<"memory" | "trace">("memory");
  const [memory, setMemory] = useState<ApiRun["memory"]>();

  useEffect(() => {
    let source: EventSource | undefined;
    let stopped = false;

    const refreshFiles = async () => {
      const nextFiles = await getRunFiles(runId);
      if (!stopped) setFiles(nextFiles);
    };

    const applyRun = (run: ApiRun) => {
      setTask(run.task);
      setModel(run.model);
      setStatus(statusFromRun(run));
      setTestCases(run.test_cases ?? []);
      setTestSource(run.test_case_source ?? "manual");
      setEvents(run.events ?? []);
      setLastTestOutput(run.result?.last_test_output ?? "");
      setReview(run.review?.content ?? "");
      setMemory(run.memory);
      setReviewLoading(run.events.some((event) => event.type === "review_started") && !run.review);
      if (run.result?.verified) {
        setTestStatus("passed");
      } else if (run.events.some((event) => event.type === "test_failed")) {
        setTestStatus("failed");
      }
    };

    const handleEvent = (type: string, data: Record<string, unknown>) => {
      const timestamp = typeof data._timestamp === "string" ? data._timestamp : new Date().toISOString();
      const sequence = typeof data._sequence === "number" ? data._sequence : undefined;
      const event: RunEvent = { sequence, type, data, timestamp };
      setEvents((items) => {
        if (sequence !== undefined && items.some((item) => item.sequence === sequence)) return items;
        return [...items, event];
      });

      if (type === "test_cases_ready") {
        setTestCases((Array.isArray(data.cases) ? data.cases : []) as TestCase[]);
        setTestSource(data.source === "generated" ? "generated" : "manual");
        void refreshFiles();
      }
      if (type === "file_changed") void refreshFiles();
      if (type === "test_failed") {
        setTestStatus("failed");
        setLastTestOutput(String(data.output ?? ""));
      }
      if (type === "test_passed") {
        setTestStatus("passed");
        setLastTestOutput(String(data.output ?? ""));
      }
      if (type === "agent_finished") {
        setStatus(data.verified ? "passed" : "failed");
        void refreshFiles();
      }
      if (type === "review_started") {
        setStatus("reviewing");
        setReviewLoading(true);
      }
      if (type === "review_finished") {
        const nextReview = data.review as { content?: string } | undefined;
        setReview(nextReview?.content ?? "");
        setReviewLoading(false);
        setStatus("passed");
      }
      if (type === "run_finished") {
        source?.close();
        setStatus(data.verified ? "passed" : "failed");
        void refreshFiles();
      }
      if (type === "model_error" || type === "run_error") {
        setStatus("failed");
        setError(String(data.error ?? "运行失败"));
      }
    };

    const load = async () => {
      try {
        const run = await getRun(runId);
        if (stopped) return;
        applyRun(run);
        await refreshFiles();
        if (run.done) return;

        source = new EventSource(runEventsUrl(runId, run.events.length));
        for (const type of RUN_EVENT_TYPES) {
          source.addEventListener(type, (message) => {
            try {
              handleEvent(type, JSON.parse((message as MessageEvent<string>).data) as Record<string, unknown>);
            } catch {
              setError("收到无法解析的运行事件。");
            }
          });
        }
      } catch (loadError) {
        if (!stopped) {
          setError(loadError instanceof Error ? loadError.message : "无法连接 FastAPI 后端。");
          setStatus("failed");
        }
      }
    };

    void load();
    return () => {
      stopped = true;
      source?.close();
    };
  }, [runId]);

  const traceItems = useMemo(() => events.map(toTraceEvent), [events]);
  const outputs = useMemo(() => terminalLines(events), [events]);
  const title = task && task !== "正在读取题目..." ? task.split("\n")[0].slice(0, 72) : "运行 " + runId;
  const language = activeFile === "test_cases.json" ? "json" : "python";

  return <AppShell breadcrumb={status === "running" ? "当前运行" : "运行结果"}>
    <div className="run-header">
      <div className="run-heading">
        <div className="run-title"><StatusBadge status={status} /><span>{title}</span></div>
        <div className="run-subtitle"><span>{runId}</span><span>{model}</span><span>FastAPI / SSE 实时数据</span></div>
      </div>
      <div className="run-actions">
        <Link className="secondary-button" href={"/history/" + runId}><CircleStop /><span>查看运行详情</span></Link>
      </div>
    </div>
    {error && <div className="callout" style={{ margin: 16, borderColor: "var(--red)", background: "var(--red-soft)", color: "var(--red)" }}>{error}</div>}
    <div className="workspace-grid">
      <ProblemPanel task={task} model={model} cases={testCases} source={testSource} />
      <section className="workspace-center">
        <div className="file-tabs">
          {(["solution.py", "test_solution.py", "test_cases.json"] as WorkspaceFile[]).map((filename) =>
            <button className={"file-tab " + (activeFile === filename ? "active" : "")} type="button" onClick={() => setActiveFile(filename)} key={filename}>
              <span className="file-dot" style={{ background: filename === "solution.py" ? "var(--blue)" : filename === "test_cases.json" ? "var(--purple)" : "var(--yellow)" }} />{filename}
            </button>
          )}
          <span style={{ marginLeft: "auto", padding: "0 10px 10px 0", color: "var(--dim)", fontSize: 10 }}><GitBranch style={{ width: 11, verticalAlign: "middle", marginRight: 4 }} /> 本地工作区</span>
        </div>
        <CodeEditor value={files[activeFile] || "等待文件生成..."} language={language} />
        <TerminalPanel outputs={outputs} />
        <div style={{ padding: 14, borderTop: "1px solid var(--line-soft)", display: "grid", gap: 14 }}>
          <TestPanel compact cases={testCases} status={testStatus} output={lastTestOutput} source={testSource} />
          {(reviewLoading || review) && <ReviewerCard content={review} verified={testStatus === "passed"} loading={reviewLoading} />}
        </div>
      </section>
      <div className="workspace-right workspace-inspector">
        <div className="inspector-tabs" role="tablist" aria-label="运行信息">
          <button type="button" role="tab" aria-selected={inspectorTab === "memory"} className={inspectorTab === "memory" ? "active" : ""} onClick={() => setInspectorTab("memory")}>
            Memory
          </button>
          <button type="button" role="tab" aria-selected={inspectorTab === "trace"} className={inspectorTab === "trace" ? "active" : ""} onClick={() => setInspectorTab("trace")}>
            Trace
          </button>
        </div>
        <div className="inspector-content">
          {inspectorTab === "memory" ? <MemoryGraph task={task} memory={memory} events={events} /> : <TraceTimeline items={traceItems} embedded />}
        </div>
      </div>
    </div>
  </AppShell>;
}
