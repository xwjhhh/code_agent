import { CircleCheck, CircleX, LoaderCircle, ScanSearch } from "lucide-react";
import type { RunStatus } from "@/lib/data";

const config = {
  passed: { label: "通过", className: "green", icon: CircleCheck },
  failed: { label: "失败", className: "red", icon: CircleX },
  running: { label: "运行中", className: "yellow", icon: LoaderCircle },
  reviewing: { label: "评审中", className: "purple", icon: ScanSearch },
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const item = config[status];
  const Icon = item.icon;
  return <span className={`badge ${item.className}`}><Icon className={status === "running" ? "spin" : ""} style={{ width: 11, height: 11 }} />{item.label}</span>;
}
