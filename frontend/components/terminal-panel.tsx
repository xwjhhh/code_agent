"use client";

import { useEffect, useRef } from "react";
import "@xterm/xterm/css/xterm.css";
import { CircleStop, TerminalSquare } from "lucide-react";

type TerminalLike = { writeln: (value: string) => void; clear: () => void; dispose: () => void };

export function TerminalPanel({ outputs = [] }: { outputs?: string[] }) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const terminalInstance = useRef<TerminalLike | null>(null);
  const outputCount = useRef(0);
  const latestOutputs = useRef(outputs);
  latestOutputs.current = outputs;

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    void Promise.all([import("@xterm/xterm"), import("@xterm/addon-fit")]).then(([xterm, fitModule]) => {
      if (!terminalRef.current || disposed) return;
      const terminal = new xterm.Terminal({
        convertEol: true,
        cursorBlink: false,
        disableStdin: true,
        fontFamily: "JetBrains Mono, Consolas, monospace",
        fontSize: 11,
        theme: { background: "#0d1117", foreground: "#a7b2c1", green: "#4fd39a", red: "#ff7b7b" },
      });
      const fit = new fitModule.FitAddon();
      terminal.loadAddon(fit);
      terminal.open(terminalRef.current);
      fit.fit();
      terminalInstance.current = terminal;
      latestOutputs.current.forEach((output) => output.split("\n").forEach((line) => terminal.writeln(line)));
      outputCount.current = latestOutputs.current.length;
      const observer = new ResizeObserver(() => fit.fit());
      observer.observe(terminalRef.current);
      cleanup = () => {
        observer.disconnect();
        terminal.dispose();
        terminalInstance.current = null;
      };
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  useEffect(() => {
    if (!terminalInstance.current || outputs.length <= outputCount.current) return;
    outputs.slice(outputCount.current).forEach((output) => output.split("\n").forEach((line) => terminalInstance.current?.writeln(line)));
    outputCount.current = outputs.length;
  }, [outputs]);

  return <section className="terminal-section">
    <div className="terminal-header">
      <div className="terminal-label"><TerminalSquare /> 真实命令输出 <span className="badge green" style={{ marginLeft: 3, height: 18 }}>只读</span></div>
      <button className="icon-button" type="button" title="清空当前显示" onClick={() => terminalInstance.current?.clear()}><CircleStop /></button>
    </div>
    <div ref={terminalRef} style={{ flex: 1, minHeight: 0, padding: "10px 15px" }} />
  </section>;
}
