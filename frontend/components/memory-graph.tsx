"use client";

import {
  ChevronDown,
  Compass,
  GitBranch,
  Lightbulb,
  RotateCcw,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { MemoryCategory, MemoryNode, RunEvent, RunMemory } from "@/lib/api";

type GraphMemory = MemoryNode & { phase: "task" | "recovery" | "learned" };
type Point = { x: number; y: number };

const GRAPH_WIDTH = 340;
const GRAPH_HEIGHT = 330;
const CENTER: Point = { x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 };

const categoryMeta: Record<MemoryCategory, { label: string; Icon: typeof Compass }> = {
  strategy: { label: "策略经验", Icon: Compass },
  recovery: { label: "恢复经验", Icon: Wrench },
  optimization: { label: "优化经验", Icon: Zap },
};

function asMemory(value: unknown, phase: GraphMemory["phase"]): GraphMemory | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Partial<MemoryNode>;
  if (typeof item.id !== "string" || !item.id || !isCategory(item.category)) return null;
  if (item.granularity !== "task" && item.granularity !== "subtask") return null;
  return { ...item, category: item.category, granularity: item.granularity, phase } as GraphMemory;
}

function isCategory(value: unknown): value is MemoryCategory {
  return value === "strategy" || value === "recovery" || value === "optimization";
}

function eventSelected(event: RunEvent, phase: GraphMemory["phase"]): GraphMemory[] {
  const selected = event.data.selected;
  if (!Array.isArray(selected)) return [];
  return selected.map((item) => asMemory(item, phase)).filter((item): item is GraphMemory => item !== null);
}

function eventLearned(event: RunEvent): GraphMemory[] {
  const memories = event.data.memories;
  if (!Array.isArray(memories)) return [];
  return memories.map((item) => asMemory(item, "learned")).filter((item): item is GraphMemory => item !== null);
}

function latestSequence(events: RunEvent[], types: string[]): number {
  return events.reduce((latest, event, index) => {
    if (!types.includes(event.type)) return latest;
    return Math.max(latest, event.sequence ?? index);
  }, -1);
}

function buildGraphData(memory: RunMemory | undefined, events: RunEvent[]) {
  const byId = new Map<string, GraphMemory>();
  const add = (item: GraphMemory | null) => {
    if (!item) return;
    const previous = byId.get(item.id);
    byId.set(item.id, previous ? { ...previous, ...item } : item);
  };

  memory?.task_retrieval?.selected?.forEach((item) => add({ ...item, phase: "task" }));
  memory?.recovery_retrievals?.forEach((retrieval) => retrieval.selected?.forEach((item) => add({ ...item, phase: "recovery" })));
  memory?.learned?.forEach((item) => add({ ...item, phase: "learned" }));
  events.forEach((event) => {
    if (event.type === "memory_retrieval_finished") {
      eventSelected(event, event.data.phase === "recovery" ? "recovery" : "task").forEach(add);
    }
    if (event.type === "memory_learning_finished") eventLearned(event).forEach(add);
  });

  const retrievalStart = latestSequence(events, ["memory_retrieval_started"]);
  const retrievalFinish = latestSequence(events, ["memory_retrieval_finished"]);
  const learningStart = latestSequence(events, ["memory_learning_started"]);
  const learningFinish = latestSequence(events, ["memory_learning_finished"]);
  const recoveryStart = events.reduce((latest, event, index) => {
    if (event.type === "test_failed" || (event.type === "memory_retrieval_started" && event.data.phase === "recovery")) {
      return Math.max(latest, event.sequence ?? index);
    }
    return latest;
  }, -1);
  const recoveryFinish = events.reduce((latest, event, index) => {
    if (event.type === "memory_retrieval_finished" && event.data.phase === "recovery") {
      return Math.max(latest, event.sequence ?? index);
    }
    return latest;
  }, -1);
  const recoveryVisible = events.some((event) => event.type === "memory_retrieval_finished" && event.data.phase === "recovery")
    || (recoveryStart >= 0 && recoveryStart >= recoveryFinish);

  return {
    memories: Array.from(byId.values()).slice(0, 8),
    retrievalActive: retrievalStart > retrievalFinish,
    learningActive: learningStart > learningFinish,
    recoveryVisible,
    hasLearning: learningFinish >= 0,
  };
}

function memoryLabel(memory: GraphMemory): string {
  const text = memory.trigger || memory.content || memory.purpose || "未命名经验";
  return text.replace(/\s+/g, " ").trim().slice(0, 26) || "未命名经验";
}

function nodePoint(index: number, total: number): Point {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(total, 1);
  return {
    x: CENTER.x + Math.cos(angle) * 112,
    y: CENTER.y + Math.sin(angle) * 112,
  };
}

function categoryIcon(category: MemoryCategory) {
  return categoryMeta[category].Icon;
}

export function MemoryGraph({ task, memory, events }: { task: string; memory?: RunMemory; events: RunEvent[] }) {
  const graph = useMemo(() => buildGraphData(memory, events), [memory, events]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = graph.memories.find((item) => item.id === selectedId) ?? null;
  const title = task.split("\n")[0].trim().slice(0, 24) || "当前任务";
  const taskMemories = graph.memories.filter((item) => item.granularity === "task");
  const status = graph.learningActive ? "learning" : graph.recoveryVisible ? "recovery" : graph.retrievalActive ? "retrieval" : "idle";
  const points = graph.memories.map((_, index) => nodePoint(index, graph.memories.length));

  return <div className="memory-view">
    <div className="memory-header">
      <div className="trace-title-row"><span className="trace-title">记忆图谱</span><span className="trace-count">{graph.memories.length} 条经验</span></div>
      <div className="memory-status-line">
        {status === "retrieval" && <><Sparkles className="spin" /> 正在回忆相关经验</>}
        {status === "recovery" && <><Wrench /> 失败恢复经验已聚焦</>}
        {status === "learning" && <><Lightbulb /> 正在长出新经验</>}
        {status === "idle" && <><GitBranch /> 当前问题的局部记忆</>}
      </div>
    </div>

    <div className="memory-legend" aria-label="记忆图例">
      {(Object.keys(categoryMeta) as MemoryCategory[]).map((category) => {
        const Icon = categoryMeta[category].Icon;
        return <span key={category}><Icon /> {categoryMeta[category].label}</span>;
      })}
      <span><i className="memory-line solid" /> 同一运行经验</span>
      <span><i className="memory-line dotted" /> 相似关系</span>
    </div>

    {memory?.enabled === false && !graph.memories.length ? <div className="memory-empty">
      <GitBranch />
      <strong>记忆服务未启用</strong>
      <span>当前运行仍会正常完成，记忆只作为辅助上下文。</span>
    </div> : !graph.memories.length ? <div className="memory-empty">
      <Lightbulb />
      <strong>还没有召回经验</strong>
      <span>完成一次本地验证和代码评审后，系统会留下第一条长期经验。</span>
    </div> : <>
      <div className={`memory-canvas ${status}`}>
        <svg className="memory-edges" viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} role="presentation">
          {points.map((point, index) => <line key={`center-${graph.memories[index].id}`} x1={CENTER.x} y1={CENTER.y} x2={point.x} y2={point.y} className="memory-edge solid" />)}
          {taskMemories.slice(1, 4).map((memoryItem, index) => {
            const fromIndex = graph.memories.findIndex((item) => item.id === taskMemories[index]?.id);
            const toIndex = graph.memories.findIndex((item) => item.id === memoryItem.id);
            if (fromIndex < 0 || toIndex < 0) return null;
            return <line key={`similar-${memoryItem.id}`} x1={points[fromIndex].x} y1={points[fromIndex].y} x2={points[toIndex].x} y2={points[toIndex].y} className="memory-edge dotted" />;
          })}
        </svg>
        <div className="memory-current-node" title="当前题目">
          <span className="memory-node-icon"><Compass /></span>
          <span>{title}</span>
        </div>
        {graph.memories.map((item, index) => {
          const Icon = categoryIcon(item.category);
          const isRecovery = item.category === "recovery" || item.phase === "recovery";
          const isNew = item.phase === "learned";
          return <button
            key={item.id}
            type="button"
            title={`${categoryMeta[item.category].label} · ${item.granularity === "task" ? "任务级" : "子任务级"}`}
            className={`memory-node ${item.granularity === "task" ? "task-level" : "subtask-level"} ${isRecovery ? "recovery-node" : ""} ${isNew ? "learning-node" : ""} ${selectedId === item.id ? "selected" : ""} ${graph.retrievalActive ? "retrieval-node" : ""} ${graph.recoveryVisible && !isRecovery ? "memory-faded" : ""}`}
            style={{ left: `${(points[index].x / GRAPH_WIDTH) * 100}%`, top: `${(points[index].y / GRAPH_HEIGHT) * 100}%` }}
            onClick={() => setSelectedId(item.id)}
          >
            <Icon className="memory-category-icon" />
          <span>{memoryLabel(item)}</span>
          </button>;
        })}
      </div>
      {selected && <MemoryInspection memory={selected} onClose={() => setSelectedId(null)} />}
    </>}

    <div className="memory-footer">
      <span><i className="memory-size-sample large" /> 任务级</span>
      <span><i className="memory-size-sample small" /> 子任务级</span>
      {graph.hasLearning && <span className="memory-learned-note"><Lightbulb /> 已记录新经验</span>}
    </div>
  </div>;
}

function MemoryInspection({ memory, onClose }: { memory: GraphMemory; onClose: () => void }) {
  const [showSteps, setShowSteps] = useState(true);
  const detailRef = useRef<HTMLDivElement>(null);
  const Icon = categoryIcon(memory.category);
  useEffect(() => {
    if (!showSteps) return;
    requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }, [showSteps]);
  return <div className="memory-inspection">
    <div className="memory-inspection-head">
      <div className="memory-inspection-title"><Icon /><span>{categoryMeta[memory.category].label} · {memory.granularity === "task" ? "任务级" : "子任务级"}</span></div>
      <button type="button" className="memory-close" onClick={onClose} title="关闭详情">×</button>
    </div>
    <strong>{memory.content || memory.trigger || "未命名经验"}</strong>
    <div className="memory-inspection-meta">
      {typeof memory.similarity === "number" && <span>相似度 {(memory.similarity * 100).toFixed(0)}%</span>}
      {memory.source_run_id && <span>来源 {memory.source_run_id.slice(-10)}</span>}
    </div>
    <button type="button" className="memory-detail-toggle" aria-expanded={showSteps} onClick={() => setShowSteps((value) => !value)}>
      {showSteps ? "收起详情" : "查看详情"}<ChevronDown className={showSteps ? "open" : ""} />
    </button>
    {showSteps && <div className="memory-detail-body" ref={detailRef}>
      {memory.trigger && <p><b>适用条件</b>{memory.trigger}</p>}
      {memory.purpose && <p><b>目的</b>{memory.purpose}</p>}
      {!!memory.steps?.length && <p><b>行动步骤</b>{memory.steps.join("；")}</p>}
      {memory.negative_example && <p><b>避免</b>{memory.negative_example}</p>}
    </div>}
  </div>;
}
