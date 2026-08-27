"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false, loading: () => <div className="editor-fallback">Loading editor...</div> });

export function CodeEditor({ value, language = "python" }: { value: string; language?: string }) {
  const [code, setCode] = useState(value);
  return <div className="editor-wrap"><MonacoEditor height="100%" language={language} theme="vs-dark" value={code} onChange={(next) => setCode(next ?? "")} options={{ fontFamily: "JetBrains Mono, Consolas, monospace", fontSize: 12, lineHeight: 21, minimap: { enabled: false }, padding: { top: 15, bottom: 15 }, scrollBeyondLastLine: false, automaticLayout: true, renderLineHighlight: "line", overviewRulerLanes: 0, hideCursorInOverviewRuler: true, scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 } }} /></div>;
}
