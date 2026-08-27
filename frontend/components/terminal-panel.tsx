"use client";

import { useEffect, useRef, useState } from "react";
import "@xterm/xterm/css/xterm.css";
import { ChevronDown, CircleStop, Play, TerminalSquare } from "lucide-react";

export function TerminalPanel() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const [command, setCommand] = useState("");
  const [running, setRunning] = useState(false);
  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    void Promise.all([import("@xterm/xterm"), import("@xterm/addon-fit")]).then(([xterm, fitModule]) => {
      if (!terminalRef.current || disposed) return;
      const terminal = new xterm.Terminal({ convertEol: true, cursorBlink: false, disableStdin: true, fontFamily: "JetBrains Mono, Consolas, monospace", fontSize: 11, theme: { background: "#0b0d0e", foreground: "#8da19a", green: "#62d39a", red: "#f07c7c" } });
      const fit = new fitModule.FitAddon();
      terminal.loadAddon(fit);
      terminal.open(terminalRef.current);
      fit.fit();
      terminal.writeln("\x1b[32m$\x1b[0m python -m pytest -q");
      terminal.writeln("........................................");
      terminal.writeln("\x1b[32m8 passed\x1b[0m in 0.03s");
      const observer = new ResizeObserver(() => fit.fit());
      observer.observe(terminalRef.current);
      cleanup = () => { observer.disconnect(); terminal.dispose(); };
    });
    return () => { disposed = true; cleanup(); };
  }, []);
  const send = () => { if (!command.trim()) return; setRunning(true); window.setTimeout(() => setRunning(false), 650); setCommand(""); };
  return <section className="terminal-section"><div className="terminal-header"><div className="terminal-label"><TerminalSquare /> Terminal <span className="badge green" style={{ marginLeft: 3, height: 18 }}>local</span></div><div style={{ display: "flex", gap: 3 }}><button className="icon-button" type="button" title="Clear terminal"><CircleStop /></button><button className="icon-button" type="button" title="Terminal settings"><ChevronDown /></button></div></div><div ref={terminalRef} style={{ flex: 1, minHeight: 0, padding: "10px 15px" }} /><div className="terminal-input"><span>$</span><input value={command} onChange={(event) => setCommand(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") send(); }} placeholder={running ? "Running..." : "Type a command"} disabled={running} /><button className="icon-button" type="button" title="Run command" onClick={send} disabled={running} style={{ width: 24, height: 24, border: 0 }}><Play /></button></div></section>;
}
