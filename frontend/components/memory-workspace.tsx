"use client";

import Link from "next/link";
import {
  BrainCircuit,
  CheckCircle2,
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
import { getMemoryGraph, type MemoryCategory, type MemoryExperienceType, type MemoryGraphEdge, type MemoryGraphPayload, type MemoryNode } from "@/lib/api";

type GraphFilter = "all" | MemoryExperienceType;
type Point = { x: number; y: number };

const GRAPH_WIDTH = 980;
const GRAPH_MIN_HEIGHT = 520;
const categoryMeta: Record<MemoryCategory, { label: string; Icon: typeof Compass }> = {
  strategy: { label: "策略经验", Icon: Compass },
  recovery: { label: "恢复经验", Icon: Wrench },
  optimization: { label: "优化经验", Icon: Zap },
};
const experienceMeta: Record<MemoryExperienceType, { label: string; Icon: typeof Compass }> = {
  success: { label: "成功经验", Icon: CheckCircle2 },
  failure: { label: "失败经验", Icon: CircleAlert },
};

function experienceTypeFor(node: MemoryNode): MemoryExperienceType {
  if (node.experience_type === "failure" || node.experience_type === "success") return node.experience_type;
  return node.category === "recovery" ? "failure" : "success";
}

function labelFor(node: MemoryNode): string {
  const text = node.trigger || node.content || node.purpose || "未命名经验";
  return text.replace(/\s+/g, " ").trim().slice(0, 30) || "未命名经验";
}

function layoutNodes(nodes: MemoryNode[], compact: boolean) {
  const positions = new Map<string, Point>();
  const groups = (["success", "failure"] as MemoryExperienceType[]).filter((type) => nodes.some((node) => experienceTypeFor(node) === type));
  const centers = groups.length > 1 ? groups.map((_, index) => 180 + index * 310) : [GRAPH_WIDTH / 2];
  const rowGap = compact ? 58 : 102;
  const top = compact ? 70 : 88;
  let maxRows = 1;

  groups.forEach((type, column) => {
    const group = nodes.filter((node) => experienceTypeFor(node) === type).slice().sort((left, right) => Number(right.quality_score ?? 0) - Number(left.quality_score ?? 0));
    const columns = compact || group.length > 6 ? 2 : 1;
    const rows = Math.ceil(group.length / columns);
    maxRows = Math.max(maxRows, rows);
    group.forEach((node, index) => {
      const row = Math.floor(index / columns);
      const subColumn = index % columns;
      positions.set(node.id, { x: centers[column] + (columns === 2 ? (subColumn ? 76 : -76) : 0), y: top + row * rowGap });
    });
  });

  return { positions, groups, centers, width: groups.length > 1 ? GRAPH_WIDTH : 760, height: Math.max(GRAPH_MIN_HEIGHT, top + maxRows * rowGap + 100) };
}

function nodeIcon(node: MemoryNode) {
  return experienceMeta[experienceTypeFor(node)].Icon;
}

function formatDate(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "-" : date.toLocaleDateString("zh-CN");
}

export function MemoryWorkspace() {
  const [graph, setGraph] = useState<MemoryGraphPayload | null>(null);
  const [filter, setFilter] = useState<GraphFilter>("all");
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
    if (filter === "all") return true;
    return experienceTypeFor(node) === filter;
  }), [filter, graph?.nodes]);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const compact = filter === "all";
  const layout = useMemo(() => layoutNodes(visibleNodes, compact), [compact, visibleNodes]);
  const positions = layout.positions;
  const visibleEdges = useMemo(() => (graph?.edges ?? []).filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)), [graph?.edges, visibleIds]);
  const selected = visibleNodes.find((node) => node.id === selectedId) ?? null;
  const stats = useMemo(() => ({
    success: graph?.nodes.filter((node) => experienceTypeFor(node) === "success").length ?? 0,
    failure: graph?.nodes.filter((node) => experienceTypeFor(node) === "failure").length ?? 0,
  }), [graph?.nodes]);

  return <AppShell breadcrumb="记忆图谱">
    <main className="page memory-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">中文知识图谱</h1>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? "spin" : ""} /> 刷新图谱</button>
      </div>

      {error && <div className="callout memory-error"><CircleAlert style={{ width: 14, verticalAlign: "middle", marginRight: 6 }} />{error}</div>}
      <div className="memory-global-toolbar">
        <div className="memory-filter-group" role="group" aria-label="图谱视图">
          {(["all", "success", "failure"] as GraphFilter[]).map((value) => <button key={value} type="button" className={filter === value ? "active" : ""} onClick={() => { setFilter(value); setSelectedId(null); }}>
            {value === "all" ? "全部经验" : experienceMeta[value].label}
          </button>)}
        </div>
        <span className="memory-global-count">{loading ? "读取中..." : `${visibleNodes.length} / ${graph?.count ?? 0} 条经验 · ${filter === "all" ? "全部经验" : experienceMeta[filter].label}`}</span>
      </div>

      <div className="memory-stats-row">
        <div><span>成功经验</span><strong>{stats.success}</strong></div>
        <div><span>失败经验</span><strong>{stats.failure}</strong></div>
        <div className="memory-embedding-meta"><span>向量模型</span><strong>{graph?.embedding_model ?? "Qwen/Qwen3-Embedding-8B"}</strong></div>
      </div>

      <div className="memory-global-layout">
        <section className="panel memory-global-panel">
          <div className="panel-header"><div className="memory-panel-title"><BrainCircuit /> <span>经验演进关系</span></div><span className="muted-link">点击节点查看详情</span></div>
          <div className="memory-global-canvas-wrap">
            {loading ? <div className="memory-global-empty"><RefreshCw className="spin" /><span>正在读取记忆网络...</span></div> : !graph?.enabled ? <div className="memory-global-empty"><BrainCircuit /><strong>记忆服务未启用</strong><span>配置 Embedding Key 后，验证成功的运行才会写入长期经验。</span></div> : !visibleNodes.length ? <div className="memory-global-empty"><BrainCircuit /><strong>当前筛选没有记忆</strong><span>完成本地验证和 Reviewer 后，经验会自动进入这里。</span></div> : <svg className="memory-global-canvas" viewBox={`0 0 ${layout.width} ${layout.height}`} role="img" aria-label="全局 Memory Graph">
              {layout.groups.map((type, index) => <text className="memory-graph-column-title" x={layout.centers[index]} y="28" textAnchor="middle" key={type}>{experienceMeta[type].label} · {visibleNodes.filter((node) => experienceTypeFor(node) === type).length}</text>)}
              {visibleEdges.map((edge) => <GraphEdge edge={edge} positions={positions} key={`${edge.source}-${edge.target}`} />)}
              {visibleNodes.map((node) => <GraphNode key={node.id} node={node} point={positions.get(node.id) ?? { x: 0, y: 0 }} selected={node.id === selectedId} compact={compact} onSelect={() => { setSelectedId(node.id); setShowSteps(true); }} />)}
            </svg>}
          </div>
          <div className="memory-global-legend">
            {(Object.keys(experienceMeta) as MemoryExperienceType[]).map((value) => { const Icon = experienceMeta[value].Icon; return <span key={value}><Icon /> {experienceMeta[value].label}</span>; })}
            <span><i className="memory-line solid" /> 同一运行经验</span><span><i className="memory-line dotted" /> 相似度关系</span>
          </div>
        </section>

        <aside className="memory-global-side">
          {selected ? <MemoryDetail node={selected} showSteps={showSteps} onToggle={() => setShowSteps((value) => !value)} /> : <div className="panel memory-select-hint"><BrainCircuit /><strong>选择一条记忆</strong><span>图谱只展示关系，完整内容在这里查看。</span></div>}
          <div className="panel memory-source-list"><div className="panel-header"><span className="panel-title">经验来源</span><span className="muted-link">来源运行 ID</span></div><div className="panel-body source-list-body">
            {Array.from(new Set(visibleNodes.map((node) => node.source_run_id).filter(Boolean))).slice(0, 8).map((source) => <Link href={`/run/${source}`} key={source} className="source-run-row"><RotateCcw /><span>{source?.slice(-18)}</span><ChevronDown /></Link>)}
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

function GraphNode({ node, point, selected, compact, onSelect }: { node: MemoryNode; point: Point; selected: boolean; compact: boolean; onSelect: () => void }) {
  const type = experienceTypeFor(node);
  const Icon = nodeIcon(node);
  const radius = compact ? 20 : 26;
  const label = labelFor(node);
  const lines = label.match(/.{1,10}/g)?.slice(0, 2) ?? [label];
  return <g className={`memory-global-node ${type} ${node.category} ${selected ? "selected" : ""}`} transform={`translate(${point.x} ${point.y})`} onClick={onSelect} role="button" tabIndex={0} aria-label={label} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(); }}>
    <circle className="memory-global-node-ring" r={radius} />
    <g className="memory-global-node-icon" transform="translate(-7 -7)"><Icon width={14} height={14} /></g>
    {!compact && <text className="memory-global-node-label" y={radius + 16} textAnchor="middle">{lines.map((line, index) => <tspan x="0" dy={index ? 13 : 0} key={line}>{line}</tspan>)}</text>}
  </g>;
}

function MemoryDetail({ node, showSteps, onToggle }: { node: MemoryNode; showSteps: boolean; onToggle: () => void }) {
  const type = experienceTypeFor(node);
  const Icon = nodeIcon(node);
  return <section className="panel memory-detail-panel"><div className="panel-header"><div className="memory-panel-title"><Icon /> <span>{experienceMeta[type].label} · {categoryMeta[node.category].label}</span></div><span className="badge blue">已选中</span></div><div className="memory-detail-content"><strong>{node.content || node.trigger || "未命名经验"}</strong><div className="memory-detail-meta"><span>来源 {node.source_run_id?.slice(-12) || "-"}</span><span>{formatDate(node.created_at)}</span></div><button type="button" className="memory-detail-toggle" onClick={onToggle}>{showSteps ? "收起详情" : "查看详情"}<ChevronDown className={showSteps ? "open" : ""} /></button>{showSteps && <div className="memory-detail-body">{node.trigger && <p><b>适用条件</b>{node.trigger}</p>}{node.purpose && <p><b>目的</b>{node.purpose}</p>}{!!node.steps?.length && <p><b>行动步骤</b>{node.steps.join("；")}</p>}{node.negative_example && <p><b>避免</b>{node.negative_example}</p>}{node.failure && <p><b>实际失败</b>{node.failure}</p>}{node.fix && <p><b>修复</b>{node.fix}</p>}{node.verification && <p><b>验证</b>{node.verification}</p>}</div>}</div></section>;
}
