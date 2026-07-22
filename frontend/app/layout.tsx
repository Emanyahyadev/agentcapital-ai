import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polaris — Family Office Intelligence",
  description:
    "Autonomous capital-call processing: multi-agent ingestion, reconciliation, and risk monitoring",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="topbar">
          <Link href="/" className="brand">✦ Polaris</Link>
          <span className="sub">
            autonomous capital-call processing · The Whitmore Family Office
          </span>
        </div>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
