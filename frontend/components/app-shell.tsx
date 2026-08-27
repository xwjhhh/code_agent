"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, ChevronRight, Clock3, FileCode2, LayoutDashboard, Plus, Settings2, TerminalSquare } from "lucide-react";

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/task/new", label: "New task", icon: Plus },
];

export function AppShell({ children, breadcrumb = "Dashboard" }: { children: React.ReactNode; breadcrumb?: string }) {
  const pathname = usePathname();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">&gt;_</span>
          <span className="brand-copy"><span className="brand-name">Code Agent</span><span className="brand-sub">local runtime / v0.1</span></span>
        </Link>
        <div className="nav-label">Workspace</div>
        <nav className="nav-list">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return <Link href={item.href} className={`nav-item ${active ? "active" : ""}`} key={item.href}><Icon /><span>{item.label}</span>{item.href === "/task/new" && <span className="nav-count">N</span>}</Link>;
          })}
          <Link href="/history/run_01HZX2" className={`nav-item ${pathname.startsWith("/history") ? "active" : ""}`}><Clock3 /><span>History</span><span className="nav-count">12</span></Link>
        </nav>
        <div className="nav-label" style={{ marginTop: 25 }}>Runtime</div>
        <nav className="nav-list">
          <Link href="/run/run_01HZX2" className={`nav-item ${pathname.startsWith("/run") ? "active" : ""}`}><TerminalSquare /><span>Active run</span><span className="nav-count">1</span></Link>
          <button className="nav-item" type="button"><Settings2 /><span>Settings</span></button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="runtime-card"><div className="runtime-row"><span className="status-dot" /> Local runtime online</div><div className="runtime-meta">Git Bash / Python 3.11.9</div></div>
        <div className="profile"><div className="avatar">XW</div><div><div className="profile-name">xwjhhh</div><div className="profile-role">Developer</div></div><ChevronRight style={{ marginLeft: "auto", width: 13, color: "var(--dim)" }} /></div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Code Agent</span><ChevronRight /><strong>{breadcrumb}</strong></div>
          <div className="top-actions"><div className="connection"><span className="status-dot" /> API connected</div><button className="icon-button" type="button" title="Activity log"><Activity /></button></div>
        </header>
        {children}
      </div>
    </div>
  );
}
