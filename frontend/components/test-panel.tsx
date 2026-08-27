"use client";

import { Check, CircleAlert, RotateCw } from "lucide-react";
import { useState } from "react";
import type { RunStatus } from "@/lib/data";
import { testCases } from "@/lib/data";

export function TestPanel({ compact = false, status = "passed" as RunStatus }: { compact?: boolean; status?: RunStatus }) {
  const [rerunning, setRerunning] = useState(false);
  const [lastRun, setLastRun] = useState("0.03s");
  const rerun = () => { setRerunning(true); window.setTimeout(() => { setRerunning(false); setLastRun("0.04s"); }, 650); };
  const passed = status !== "failed";
  const cases = passed ? testCases : testCases.slice(0, 4).map((item, index) => index === 2 ? { ...item, status: "failed" } : item);
  return <section className="test-panel"><div className="panel-header"><span className="panel-title">Test results</span><div style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="table-cell mono">pytest -q</span><button className="icon-button" type="button" title="Run tests again" onClick={rerun} disabled={rerunning}><RotateCw className={rerunning ? "spin" : ""} /></button></div></div><div className="test-summary"><div className={`test-score ${passed ? "" : "error"}`} style={{ color: passed ? "var(--green)" : "var(--red)" }}>{passed ? "8" : "3"}<small> / {passed ? "8" : "4"}</small></div><div className="test-progress"><div className="test-progress-label"><span>{rerunning ? "Running local tests..." : passed ? "All generated cases passed" : "One case needs attention"}</span><span style={{ fontFamily: "var(--mono)" }}>{lastRun}</span></div><div className="test-progress-track"><span style={{ width: `${passed ? 100 : 75}%`, background: passed ? "var(--green)" : "var(--red)" }} /></div></div></div><div className="test-list">{cases.map((item) => <div className={`test-item ${item.status === "failed" ? "failed" : ""}`} key={item.name}>{item.status === "failed" ? <CircleAlert /> : <Check />}<span>{item.name}</span><span style={{ marginLeft: "auto", color: "var(--dim)", fontFamily: "var(--mono)" }}>{item.expected}</span></div>)}</div>{!compact && !passed && <div className="callout" style={{ margin: "0 16px 16px", borderColor: "var(--red)", background: "var(--red-soft)", color: "#efabab" }}>Input "abba" returned 3, expected 2. The failing observation is available in the Agent trace.</div>}</section>;
}
