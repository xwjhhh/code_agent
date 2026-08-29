"use client";

import Link from "next/link";
import {
  BrainCircuit,
  ChevronDown,
  CircleAlert,
  Compass,
  RefreshCw,
  RotateCcw,
  Wrench,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { getMemoryGraph, type MemoryCategory, type MemoryGraphEdge, type MemoryGraphPayload, type MemoryNode } from "@/lib/api";

type FilterCategory = "all" | MemoryCategory;
type FilterLevel = "all" | "task" | "subtask";
type Point = { x: number; y: number };

const GRAPH_WIDTH = 820;
const GRAPH_HEIGHT = 560;
const categoryMeta: Record<MemoryCategory, { label: string; Icon: typeof Compass }> = {
  strategy: { label: "策略经验", Icon: Compass },
  recovery: { label: "恢复经验", Icon: Wrench },
  optimization: { label: "优化经验", Icon: Zap },
};

function labelFor(node: MemoryNode): string {
  const text = node.trigger || node.content || node.purpose || "未命名经验";
  return text.replace(/\s+/g, " ").trim().slice(0, 30) || "未命名经验";
}

function layoutNodes(nodes: MemoryNode[]): Map<string, Point> {
  const positions = new Map<string, Point>();
  const taskNodes = nodes.filter((node) => node.granularity === "task");
  const subtaskNodes = nodes.filter((node) => node.granularity === "subtask");
  const anchors = new Map<string, Point>();
  const taskRadius = Math.min(215, 100 + taskNodes.length * 10);

  taskNodes.forEach((node, index) => {
    const angle = taskNodes.length === 1 ? -Math.PI / 2 : -Math.PI / 2 + (Math.PI * 2 * index) / taskNodes.length;
    const point = { x: GRAPH_WIDTH / 2 + Math.cos(angle) * taskRadius, y: GRAPH_HEIGHT / 2 + Math.sin(angle) * 205 };
    positions.set(node.id, point);
    if (node.source_run_id) anchors.set(node.source_run_id, point);
  });

  const orphanAnchor = { x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 };
  const grouped = new Map<string, MemoryNode[]>();
  subtaskNodes.forEach((node) => {
    const key = node.source_run_id || "orphan";
    grouped.set(key, [...(grouped.get(key) ?? []), node]);
  });
  grouped.forEach((group, sourceRun) => {
    const anchor = anchors.get(sourceRun) ?? orphanAnchor;
    group.forEach((node, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(group.length, 1);
      positions.set(node.id, { x: anchor.x + Math.cos(angle) * 82, y: anchor.y + Math.sin(angle) * 66 });
    });
  });
  return positions;
}

function nodeIcon(category: MemoryCategory) {
  return categoryMeta[category].Icon;
}

function formatDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "-" : date.toLocaleDateString("zh-CN");
}

export function MemoryWorkspace() {
  const [graph, setGraph] = useState<MemoryGraphPayload | null>(null);
  const [category, setCategory] = useState<FilterCategory>("all");
  const [level, setLevel] = useState<FilterLevel>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showSteps, setShowSteps] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setGraph(await getMemoryGraph());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "读取记忆图谱失败。");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const visibleNodes = useMemo(() => (graph?.nodes ?? []).filter((node) => {
    return (category === "all" || node.category === category) && (level === "all" || node.granularity === level);
  }), [category, graph?.nodes, level]);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const positions = useMemo(() => layoutNodes(visibleNodes), [visibleNodes]);
  const visibleEdges = useMemo(() => (graph?.edges ?? []).filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)), [graph?.edges, visibleIds]);
  const selected = visibleNodes.find((node) => node.id === selectedId) ?? null;
  const stats = useMemo(() => ({
    task: graph?.nodes.filter((node) => node.granularity === "task").length ?? 0,
    subtask: graph?.nodes.filter((node) => node.granularity === "subtask").length ?? 0,
    strategy: graph?.nodes.filter((node) => node.category === "strategy").length ?? 0,
    recovery: graph?.nodes.filter((node) => node.category === "recovery").length ?? 0,
    optimization: graph?.nodes.filter((node) => node.category === "optimization").length ?? 0,
  }), [graph?.nodes]);

  return <AppShell breadcrumb="记忆图谱">
    <main className="page memory-page">
      <div className="page-header">
        <div>
          <div className="eyebrow">全局图谱 / 持久记忆</div>
          <h1 className="page-title">全局记忆图谱</h1>
          <p className="page-description">查看 Agent 在历次验证成功的任务中积累的可复用经验。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? "spin" : ""} /> 刷新图谱</button>
      </div>

      {error && <div className="callout memory-error"><CircleAlert style={{ width: 14, verticalAlign: "middle", marginRight: 6 }} />{error}</div>}
      <div className="memory-global-toolbar">
        <div className="memory-filter-group" role="group" aria-label="按经验类型筛选">
          <span className="memory-filter-label">类型</span>
          {(["all", "strategy", "recovery", "optimization"] as FilterCategory[]).map((value) => <button key={value} type="button" className={category === value ? "active" : ""} onClick={() => { setCategory(value); setSelectedId(null); }}>
            {value === "all" ? "全部" : categoryMeta[value].label}
          </button>)}
        </div>
        <div className="memory-filter-group" role="group" aria-label="按记忆层级筛选">
          <span className="memory-filter-label">层级</span>
          {(["all", "task", "subtask"] as FilterLevel[]).map((value) => <button key={value} type="button" className={level === value ? "active" : ""} onClick={() => { setLevel(value); setSelectedId(null); }}>
            {value === "all" ? "全部" : value === "task" ? "任务级" : "子任务级"}
          </button>)}
        </div>
        <span className="memory-global-count">{loading ? "读取中..." : `${visibleNodes.length} / ${graph?.count ?? 0} 条经验`}</span>
      </div>

      <div className="memory-stats-row">
        <div><span>任务级经验</span><strong>{stats.task}</strong></div>
        <div><span>子任务级经验</span><strong>{stats.subtask}</strong></div>
        <div><span>策略经验</span><strong>{stats.strategy}</strong></div>
        <div><span>恢复经验</span><strong>{stats.recovery}</strong></div>
        <div><span>优化经验</span><strong>{stats.optimization}</strong></div>
        <div className="memory-embedding-meta"><span>向量模型</span><strong>{graph?.embedding_model ?? "Qwen/Qwen3-Embedding-8B"}</strong></div>
      </div>

      <div className="memory-global-layout">
        <section className="panel memory-global-panel">
          <div className="panel-header"><div className="memory-panel-title"><BrainCircuit /> <span>记忆演进</span></div><span className="muted-link">点击节点查看详情</span></div>
          <div className="memory-global-canvas-wrap">
            {loading ? <div className="memory-global-empty"><RefreshCw className="spin" /><span>正在读取记忆网络...</span></div> : !graph?.enabled ? <div className="memory-global-empty"><BrainCircuit /><strong>记忆服务未启用</strong><span>配置 Embedding Key 后，验证成功的运行才会写入长期经验。</span></div> : !visibleNodes.length ? <div className="memory-global-empty"><BrainCircuit /><strong>当前筛选没有记忆</strong><span>完成本地验证和 Reviewer 后，经验会自动进入这里。</span></div> : <svg className="memory-global-canvas" viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} role="img" aria-label="全局 Memory Graph">
              {visibleEdges.map((edge) => <GraphEdge edge={edge} positions={positions} key={`${edge.source}-${edge.target}`} />)}
              {visibleNodes.map((node) => <GraphNode key={node.id} node={node} point={positions.get(node.id) ?? { x: 0, y: 0 }} selected={node.id === selectedId} onSelect={() => { setSelectedId(node.id); setShowSteps(true); }} />)}
            </svg>}
          </div>
          <div className="memory-global-legend">
            {(Object.keys(categoryMeta) as MemoryCategory[]).map((value) => { const Icon = categoryMeta[value].Icon; return <span key={value}><Icon /> {categoryMeta[value].label}</span>; })}
            <span><i className="memory-line solid" /> 同一运行经验</span><span><i className="memory-line dotted" /> 相似度关系</span>
          </div>
        </section>

        <aside className="memory-global-side">
          {selected ? <MemoryDetail node={selected} showSteps={showSteps} onToggle={() => setShowSteps((value) => !value)} /> : <div className="panel memory-select-hint"><BrainCircuit /><strong>选择一条记忆</strong><span>图谱只展示关系，完整内容在这里查看。</span></div>}
          <div className="panel memory-source-list"><div className="panel-header"><span className="panel-title">经验来源</span><span className="muted-link">来源运行 ID</span></div><div className="panel-body source-list-body">
            {Array.from(new Set(visibleNodes.map((node) => node.source_run_id).filter(Boolean))).slice(0, 8).map((source) => <Link href={`/history/${source}`} key={source} className="source-run-row"><RotateCcw /><span>{source?.slice(-18)}</span><ChevronDown /></Link>)}
            {!visibleNodes.some((node) => node.source_run_id) && <span className="muted-link">暂无来源运行</span>}
          </div></div>
        </aside>
      </div>
    </main>
  </AppShell>;
}

function GraphEdge({ edge, positions }: { edge: MemoryGraphEdge; positions: Map<string, Point> }) {
  const source = positions.get(edge.source);
  const target = positions.get(edge.target);
  if (!source || !target) return null;
  return <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} className={`memory-global-edge ${edge.kind}`} />;
}

function GraphNode({ node, point, selected, onSelect }: { node: MemoryNode; point: Point; selected: boolean; onSelect: () => void }) {
  const Icon = nodeIcon(node.category);
  return <g className={`memory-global-node ${node.category} ${node.granularity === "task" ? "task-level" : "subtask-level"} ${selected ? "selected" : ""}`} transform={`translate(${point.x} ${point.y})`} onClick={onSelect} role="button" tabIndex={0} aria-label={labelFor(node)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(); }}>
    <circle className="memory-global-node-ring" r={node.granularity === "task" ? 38 : 25} />
    <foreignObject x={node.granularity === "task" ? -35 : -23} y={node.granularity === "task" ? -35 : -22} width={node.granularity === "task" ? 70 : 46} height={node.granularity === "task" ? 70 : 44}>
      <div className="memory-global-node-content"><Icon /><span>{labelFor(node)}</span></div>
    </foreignObject>
  </g>;
}

function MemoryDetail({ node, showSteps, onToggle }: { node: MemoryNode; showSteps: boolean; onToggle: () => void }) {
  const Icon = nodeIcon(node.category);
  return <section className="panel memory-detail-panel"><div className="panel-header"><div className="memory-panel-title"><Icon /> <span>{categoryMeta[node.category].label} · {node.granularity === "task" ? "任务级" : "子任务级"}</span></div><span className="badge blue">已选中</span></div><div className="memory-detail-content"><strong>{node.content || node.trigger || "未命名经验"}</strong><div className="memory-detail-meta"><span>来源 {node.source_run_id?.slice(-12) || "-"}</span><span>{formatDate(node.created_at)}</span></div><button type="button" className="memory-detail-toggle" onClick={onToggle}>{showSteps ? "收起详情" : "查看详情"}<ChevronDown className={showSteps ? "open" : ""} /></button>{showSteps && <div className="memory-detail-body">{node.trigger && <p><b>适用条件</b>{node.trigger}</p>}{node.purpose && <p><b>目的</b>{node.purpose}</p>}{!!node.steps?.length && <p><b>行动步骤</b>{node.steps.join("；")}</p>}{node.negative_example && <p><b>避免</b>{node.negative_example}</p>}</div>}</div></section>;
}
