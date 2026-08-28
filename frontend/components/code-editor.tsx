"use client";

import dynamic from "next/dynamic";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false, loading: () => <div className="editor-fallback">正在加载编辑器...</div> });

export function CodeEditor({ value, language = "python" }: { value: string; language?: string }) {
  return <div className="editor-wrap"><MonacoEditor height="100%" language={language} theme="vs-dark" value={value} options={{ readOnly: true, domReadOnly: true, fontFamily: "JetBrains Mono, Consolas, monospace", fontSize: 12, lineHeight: 21, minimap: { enabled: false }, padding: { top: 15, bottom: 15 }, scrollBeyondLastLine: false, automaticLayout: true, renderLineHighlight: "line", overviewRulerLanes: 0, hideCursorInOverviewRuler: true, scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 } }} /></div>;
}
