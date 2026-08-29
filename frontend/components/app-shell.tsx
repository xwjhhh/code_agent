"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BrainCircuit, ChevronRight, Clock3, LayoutDashboard, Plus, TerminalSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { ACTIVE_RUN_STORAGE_KEY, checkApi } from "@/lib/api";

export function AppShell({ children, breadcrumb = "控制台" }: { children: React.ReactNode; breadcrumb?: string }) {
  const pathname = usePathname();
  const [connected, setConnected] = useState(false);
  const [rememberedRunId, setRememberedRunId] = useState<string | null>(null);
  const runMatch = pathname.match(/^\/(?:run|history)\/([^/]+)/);
  const routeRunId = runMatch?.[1];
  const currentRunId = routeRunId ?? rememberedRunId;

  useEffect(() => {
    let storedRunId: string | null = null;
    try {
      storedRunId = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    } catch {
      storedRunId = null;
    }
    if (storedRunId) setRememberedRunId(storedRunId);
    if (routeRunId) {
      try {
        window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, routeRunId);
      } catch {
        // Storage can be unavailable in privacy-restricted browser contexts.
      }
      setRememberedRunId(routeRunId);
    }
  }, [routeRunId]);

  useEffect(() => {
    let active = true;
    void checkApi().then((result) => {
      if (active) setConnected(result);
    });
    return () => {
      active = false;
    };
  }, [pathname]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">CA</span>
          <span className="brand-copy"><span className="brand-name">Code Agent</span><span className="brand-sub">LOCAL AI WORKSPACE</span></span>
        </Link>
        <div className="nav-label">工作区</div>
        <nav className="nav-list">
          <Link href="/" className={"nav-item " + (pathname === "/" ? "active" : "")}><LayoutDashboard /><span>控制台</span></Link>
          <Link href="/task/new" className={"nav-item " + (pathname.startsWith("/task/new") ? "active" : "")}><Plus /><span>新建任务</span></Link>
          <Link href="/history" className={"nav-item " + (pathname.startsWith("/history") ? "active" : "")}><Clock3 /><span>历史运行</span></Link>
          <Link href="/memory" className={"nav-item " + (pathname.startsWith("/memory") ? "active" : "")}><BrainCircuit /><span>记忆图谱</span></Link>
        </nav>
        <div className="nav-label" style={{ marginTop: 25 }}>运行时</div>
        <nav className="nav-list">
          <Link href={currentRunId ? "/run/" + currentRunId : "/task/new"} className={"nav-item " + (pathname.startsWith("/run") ? "active" : "")}><TerminalSquare /><span>{currentRunId ? "当前运行" : "启动任务"}</span></Link>
        </nav>
        <div className="sidebar-spacer" />
        <div className="runtime-card">
          <div className="runtime-row"><span className={"status-dot " + (connected ? "" : "red")} /> FastAPI {connected ? "在线" : "未连接"}</div>
          <div className="runtime-meta">Git Bash / Python</div>
        </div>
        <div className="profile"><div className="avatar">CA</div><div><div className="profile-name">本地工作区</div><div className="profile-role">真实执行环境</div></div><ChevronRight style={{ marginLeft: "auto", width: 13, color: "var(--dim)" }} /></div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Code Agent</span><ChevronRight /><strong>{breadcrumb}</strong></div>
          <div className="top-actions">
            <div className="connection"><span className={"status-dot " + (connected ? "" : "red")} /> 接口{connected ? "已连接" : "未连接"}</div>
            <Link className="icon-button" href="/history" title="运行活动"><Activity /></Link>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
