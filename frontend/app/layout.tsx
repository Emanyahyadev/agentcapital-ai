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
        <div className="container">
          <div className="header">
            <h1>
              <Link href="/" style={{ color: "inherit" }}>✦ Polaris</Link>
            </h1>
            <span className="sub">
              autonomous capital-call processing · The Whitmore Family Office
            </span>
          </div>
          {children}
        </div>
      </body>
    </html>
  );
}
