"use client";

import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Compass,
  GitBranch,
  Lightbulb,
  RotateCcw,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { getMemoryGraph, type MemoryCategory, type MemoryExperienceType, type MemoryNode, type RunEvent, type RunMemory } from "@/lib/api";

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
const experienceMeta: Record<MemoryExperienceType, { label: string; Icon: typeof Compass }> = {
  success: { label: "成功经验", Icon: CheckCircle2 },
  failure: { label: "失败经验", Icon: CircleAlert },
};

function experienceTypeFor(memory: MemoryNode): MemoryExperienceType {
  if (memory.experience_type === "failure" || memory.experience_type === "success") return memory.experience_type;
  return memory.category === "recovery" ? "failure" : "success";
}

function asMemory(value: unknown, phase: GraphMemory["phase"]): GraphMemory | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Partial<MemoryNode>;
  if (typeof item.id !== "string" || !item.id || !isCategory(item.category)) return null;
  return { ...item, category: item.category, phase } as GraphMemory;
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

function experienceIcon(memory: MemoryNode) {
  return experienceMeta[experienceTypeFor(memory)].Icon;
}

export function MemoryGraph({ task, memory, events }: { task: string; memory?: RunMemory; events: RunEvent[] }) {
  const graph = useMemo(() => buildGraphData(memory, events), [memory, events]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [globalMemoryCount, setGlobalMemoryCount] = useState<number | null>(null);
  const selected = graph.memories.find((item) => item.id === selectedId) ?? null;
  const title = task.split("\n")[0].trim().slice(0, 24) || "当前任务";
  const status = graph.learningActive ? "learning" : graph.recoveryVisible ? "recovery" : graph.retrievalActive ? "retrieval" : "idle";
  const points = graph.memories.map((_, index) => nodePoint(index, graph.memories.length));

  useEffect(() => {
    if (graph.memories.length || memory?.enabled === false) return;
    let active = true;
    void getMemoryGraph(1).then((payload) => {
      if (active) setGlobalMemoryCount(payload.count);
    }).catch(() => {
      if (active) setGlobalMemoryCount(null);
    });
    return () => { active = false; };
  }, [graph.memories.length, memory?.enabled]);

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
      {(Object.keys(experienceMeta) as MemoryExperienceType[]).map((type) => {
        const Icon = experienceMeta[type].Icon;
        return <span key={type}><Icon /> {experienceMeta[type].label}</span>;
      })}
      <span><i className="memory-line solid" /> 同一运行经验</span>
      <span><i className="memory-line dotted" /> 相似关系</span>
    </div>

    {memory?.enabled === false && !graph.memories.length ? <div className="memory-empty">
      <GitBranch />
      <strong>记忆服务未启用</strong>
      <span>当前运行仍会正常完成，记忆只作为辅助上下文。</span>
      <Link href="/memory" className="memory-empty-link">查看全部经验 <ChevronDown /></Link>
    </div> : !graph.memories.length ? <div className="memory-empty">
      <Lightbulb />
      {globalMemoryCount !== null && <span className="memory-empty-context">经验库中已有 {globalMemoryCount} 条长期经验。</span>}
      {memory?.retrieval_skipped && <span className="memory-empty-context">本次运行跳过了运行前检索，已积累的经验可在记忆图谱中查看。</span>}
      {!memory?.retrieval_skipped && <span className="memory-empty-context">当前运行没有匹配的历史经验，已积累的经验可在记忆图谱中查看。</span>}
      <strong>还没有召回经验</strong>
      <span>完成一次本地验证和代码评审后，系统会留下第一条长期经验。</span>
      <Link href="/memory" className="memory-empty-link">查看全部经验 <ChevronDown /></Link>
    </div> : <>
      <div className={`memory-canvas ${status}`}>
        <svg className="memory-edges" viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} role="presentation">
          {points.map((point, index) => <line key={`center-${graph.memories[index].id}`} x1={CENTER.x} y1={CENTER.y} x2={point.x} y2={point.y} className="memory-edge solid" />)}
          {graph.memories.slice(1, 4).map((memoryItem, index) => {
            const fromIndex = graph.memories.findIndex((item) => item.id === graph.memories[index]?.id);
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
          const type = experienceTypeFor(item);
          const Icon = experienceIcon(item);
          const isRecovery = type === "failure" || item.phase === "recovery";
          const isNew = item.phase === "learned";
          return <button
            key={item.id}
            type="button"
            title={`${experienceMeta[type].label} · ${categoryMeta[item.category].label}`}
            className={`memory-node ${type} ${item.category} ${isRecovery ? "recovery-node" : ""} ${isNew ? "learning-node" : ""} ${selectedId === item.id ? "selected" : ""} ${graph.retrievalActive ? "retrieval-node" : ""} ${graph.recoveryVisible && !isRecovery ? "memory-faded" : ""}`}
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
      {graph.hasLearning && <span className="memory-learned-note"><Lightbulb /> 已记录新经验</span>}
    </div>
  </div>;
}

function MemoryInspection({ memory, onClose }: { memory: GraphMemory; onClose: () => void }) {
  const [showSteps, setShowSteps] = useState(true);
  const detailRef = useRef<HTMLDivElement>(null);
  const type = experienceTypeFor(memory);
  const Icon = experienceIcon(memory);
  useEffect(() => {
    if (!showSteps) return;
    requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }, [showSteps]);
  return <div className="memory-inspection">
    <div className="memory-inspection-head">
      <div className="memory-inspection-title"><Icon /><span>{experienceMeta[type].label} · {categoryMeta[memory.category].label}</span></div>
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
      {memory.failure && <p><b>实际失败</b>{memory.failure}</p>}
      {memory.fix && <p><b>修复</b>{memory.fix}</p>}
      {memory.verification && <p><b>验证</b>{memory.verification}</p>}
    </div>}
  </div>;
}
