"use client";

import { Check, ChevronDown, CircleAlert, FileCode2, FlaskConical, LoaderCircle, MessageSquareText, Search, TerminalSquare } from "lucide-react";
import { useState } from "react";
import type { TraceEvent } from "@/lib/data";

function TraceIcon({ item }: { item: TraceEvent }) {
  if (item.kind === "failed") return <CircleAlert />;
  if (item.label.toLowerCase().includes("test") || item.label.includes("测试")) return <FlaskConical />;
  if (item.label.toLowerCase().includes("write") || item.label.toLowerCase().includes("edit") || item.label.includes("文件")) return <FileCode2 />;
  if (item.label.toLowerCase().includes("review") || item.label.includes("评审")) return <Search />;
  if (item.label.toLowerCase().includes("run") || item.label.includes("命令")) return <TerminalSquare />;
  if (item.kind === "active") return <LoaderCircle className="spin" />;
  return <MessageSquareText />;
}

export function TraceTimeline({ items }: { items: TraceEvent[] }) {
  const [expanded, setExpanded] = useState<number | null>(items[items.length - 1]?.id ?? null);
  return <div className="workspace-right"><div className="trace-header"><div className="trace-title-row"><span className="trace-title">智能体轨迹</span><span className="trace-count">第 {items.length} 步</span></div><div className="progress-bar"><span style={{ width: `${Math.min(100, Math.max(4, items.length * 15))}%` }} /></div></div><div className="trace-list">{items.map((item) => { const isOpen = expanded === item.id; return <div className={`trace-item ${item.kind}`} key={item.id}><div className="trace-node"><TraceIcon item={item} /></div><div className="trace-content"><div className="trace-item-head"><span className="trace-event">{item.label}</span><span className="trace-time">{item.time}</span></div><div className="trace-summary">{item.summary}<button className={`trace-expand ${isOpen ? "open" : ""}`} type="button" title="展开步骤详情" onClick={() => setExpanded(isOpen ? null : item.id)}><ChevronDown /></button></div>{isOpen && item.detail && <div className="trace-detail">{item.detail}</div>}</div></div>; })}</div></div>;
}
