import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Code Agent | 智能编程工作台",
  description: "本地编程智能体运行、测试与评审工作台。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
