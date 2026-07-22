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
  const tiles = [
    { k: "Portfolio NAV", v: nav === null ? "—" : `$${(nav / 1e6).toFixed(1)}M` },
    { k: "Runs", v: metrics ? String(metrics.total_runs) : "—" },
    {
      k: "Success rate",
      v:
        metrics && metrics.success_rate !== null
          ? `${(metrics.success_rate * 100).toFixed(0)}%`
          : "—",
    },
    {
      k: "Avg runtime",
      v: metrics && metrics.avg_runtime_s ? `${metrics.avg_runtime_s}s` : "—",
    },
    { k: "LLM tokens", v: metrics ? fmtTokens(metrics.tokens_total) : "—" },
    {
      k: "Est. LLM cost",
      v: metrics ? `$${metrics.est_cost_usd.toFixed(4)}` : "—",
    },
  ];

  return (
    <div className="stats">
      {tiles.map((t) => (
        <div className="stat" key={t.k}>
          <div className="k">{t.k}</div>
          <div className="v">{t.v}</div>
        </div>
      ))}
    </div>
  );
}
