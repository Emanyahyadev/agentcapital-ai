import { Metrics } from "@/lib/api";

function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function MetricsStrip({
  metrics,
  nav,
}: {
  metrics: Metrics | null;
  nav: number | null;
}) {
  const items = [
    {
      k: "Portfolio NAV",
      v: nav === null ? "—" : `$${(nav / 1e6).toFixed(1)}M`,
    },
    {
      k: "Runs",
      v: metrics ? String(metrics.total_runs) : "—",
    },
    {
      k: "Success Rate",
      v:
        metrics && metrics.success_rate != null
          ? `${(metrics.success_rate * 100).toFixed(0)}%`
          : "—",
    },
    {
      k: "Avg Runtime",
      v: metrics?.avg_runtime_s ? `${metrics.avg_runtime_s.toFixed(1)}s` : "—",
    },
    {
      k: "LLM Tokens",
      v: metrics?.tokens_total ? fmtTokens(metrics.tokens_total) : "—",
    },
    {
      k: "Est. LLM Cost",
      v: metrics?.est_cost_usd ? `$${metrics.est_cost_usd.toFixed(4)}` : "—",
    },
  ];

  return (
    <div className="stats">
      {items.map((it) => (
        <div className="stat" key={it.k}>
          <div className="k">{it.k}</div>
          <div className="v">{it.v}</div>
        </div>
      ))}
    </div>
  );
}
