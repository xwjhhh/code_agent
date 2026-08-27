"use client";

import { Check, ChevronDown, CircleAlert, FileCode2, FlaskConical, LoaderCircle, MessageSquareText, Search, TerminalSquare } from "lucide-react";
import { useState } from "react";
import type { TraceEvent } from "@/lib/data";

function TraceIcon({ item }: { item: TraceEvent }) {
  if (item.kind === "failed") return <CircleAlert />;
  if (item.label.toLowerCase().includes("test")) return <FlaskConical />;
  if (item.label.toLowerCase().includes("write") || item.label.toLowerCase().includes("edit")) return <FileCode2 />;
  if (item.label.toLowerCase().includes("review")) return <Search />;
  if (item.label.toLowerCase().includes("run")) return <TerminalSquare />;
  if (item.kind === "active") return <LoaderCircle className="spin" />;
  return <MessageSquareText />;
}

export function TraceTimeline({ items }: { items: TraceEvent[] }) {
  const [expanded, setExpanded] = useState<number | null>(items[items.length - 1]?.id ?? null);
  return <div className="workspace-right"><div className="trace-header"><div className="trace-title-row"><span className="trace-title">Agent trace</span><span className="trace-count">STEP 6 / 20</span></div><div className="progress-bar"><span /></div></div><div className="trace-list">{items.map((item) => { const isOpen = expanded === item.id; return <div className={`trace-item ${item.kind}`} key={item.id}><div className="trace-node"><TraceIcon item={item} /></div><div className="trace-content"><div className="trace-item-head"><span className="trace-event">{item.label}</span><span className="trace-time">{item.time}</span></div><div className="trace-summary">{item.summary}<button className={`trace-expand ${isOpen ? "open" : ""}`} type="button" title="Toggle step details" onClick={() => setExpanded(isOpen ? null : item.id)}><ChevronDown /></button></div>{isOpen && item.detail && <div className="trace-detail">{item.detail}</div>}</div></div>; })}</div></div>;
}
