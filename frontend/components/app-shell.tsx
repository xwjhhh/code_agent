"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, ChevronRight, Clock3, LayoutDashboard, Plus, TerminalSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { checkApi } from "@/lib/api";

export function AppShell({ children, breadcrumb = "控制台" }: { children: React.ReactNode; breadcrumb?: string }) {
  const pathname = usePathname();
  const [connected, setConnected] = useState(false);
  const runMatch = pathname.match(/^\/(?:run|history)\/([^/]+)/);
  const currentRunId = runMatch?.[1];

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
          <span className="brand-mark">&gt;_</span>
          <span className="brand-copy"><span className="brand-name">Code Agent</span><span className="brand-sub">local runtime / v0.1</span></span>
        </Link>
        <div className="nav-label">工作区</div>
        <nav className="nav-list">
          <Link href="/" className={"nav-item " + (pathname === "/" ? "active" : "")}><LayoutDashboard /><span>控制台</span></Link>
          <Link href="/task/new" className={"nav-item " + (pathname.startsWith("/task/new") ? "active" : "")}><Plus /><span>新建任务</span></Link>
          <Link href="/" className={"nav-item " + (pathname.startsWith("/history") ? "active" : "")}><Clock3 /><span>历史运行</span></Link>
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
        <div className="profile"><div className="avatar">XW</div><div><div className="profile-name">xwjhhh</div><div className="profile-role">开发者</div></div><ChevronRight style={{ marginLeft: "auto", width: 13, color: "var(--dim)" }} /></div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Code Agent</span><ChevronRight /><strong>{breadcrumb}</strong></div>
          <div className="top-actions">
            <div className="connection"><span className={"status-dot " + (connected ? "" : "red")} /> 接口{connected ? "已连接" : "未连接"}</div>
            <Link className="icon-button" href="/" title="运行活动"><Activity /></Link>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
