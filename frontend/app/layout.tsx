import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Code Agent",
  description: "Observe an autonomous coding agent solve algorithm problems.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
