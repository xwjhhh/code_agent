import { CircleCheck, CircleX, LoaderCircle, ScanSearch } from "lucide-react";
import type { RunStatus } from "@/lib/data";

const config = {
  passed: { label: "Passed", className: "green", icon: CircleCheck },
  failed: { label: "Failed", className: "red", icon: CircleX },
  running: { label: "Running", className: "yellow", icon: LoaderCircle },
  reviewing: { label: "Reviewing", className: "purple", icon: ScanSearch },
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const item = config[status];
  const Icon = item.icon;
  return <span className={`badge ${item.className}`}><Icon className={status === "running" ? "spin" : ""} style={{ width: 11, height: 11 }} />{item.label}</span>;
}
