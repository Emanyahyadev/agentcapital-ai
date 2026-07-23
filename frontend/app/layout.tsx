import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgentCapital AI — Multi-Agent Financial Intelligence",
  description:
    "Production-grade multi-agent financial intelligence: document ingestion, reconciliation, risk monitoring, and human-in-the-loop review",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="topbar">
          <Link href="/" className="brand">◆ AgentCapital&nbsp;AI</Link>
          <span className="sub">
            production-grade multi-agent financial intelligence · The Whitmore Family Office
          </span>
        </div>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
