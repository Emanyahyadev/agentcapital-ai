export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Fallback Demo Dataset when HTTP fetch to localhost is blocked by HTTPS browser policies on Vercel
const MOCK_RUN_ID = "run-demo-northgate-001";

const MOCK_SAMPLES = [
  { name: "Northgate Capital Call ($1.25M)", label: "Northgate Capital Call ($1.25M)", path: "notices/capital_call_northgate.pdf", storage_path: "notices/capital_call_northgate.pdf" },
  { name: "TechVantage Distribution ($1.20M)", label: "TechVantage Distribution ($1.20M)", path: "notices/distribution_techvantage.pdf", storage_path: "notices/distribution_techvantage.pdf" },
  { name: "Meridian Growth IV Call ($850K)", label: "Meridian Growth IV Call ($850K)", path: "notices/capital_call_meridian_iv.pdf", storage_path: "notices/capital_call_meridian_iv.pdf" },
  { name: "Injection Test Notice", label: "Injection Test Notice", path: "notices/capital_call_injection.pdf", storage_path: "notices/capital_call_injection.pdf" },
];

const MOCK_CUSTODIAN = [
  { account_ref: "ACC-101", entity_name: "Northgate Ventures IX", position_value_usd: 12450000, as_of: "2026-07-24" },
  { account_ref: "ACC-102", entity_name: "Crestline Real Estate Partners VIII", position_value_usd: 11800000, as_of: "2026-07-24" },
  { account_ref: "ACC-103", entity_name: "Meridian Growth Fund IV-A", position_value_usd: 9800000, as_of: "2026-07-24" },
  { account_ref: "ACC-104", entity_name: "Halcyon Growth Equity III", position_value_usd: 8950000, as_of: "2026-07-24" },
  { account_ref: "ACC-105", entity_name: "Meridian Growth Fund IV-B", position_value_usd: 6400000, as_of: "2026-07-24" },
  { account_ref: "ACC-106", entity_name: "Auren Ventures V", position_value_usd: 6100000, as_of: "2026-07-24" },
  { account_ref: "ACC-107", entity_name: "TechVantage Opportunities LP", position_value_usd: 5200000, as_of: "2026-07-24" },
  { account_ref: "ACC-108", entity_name: "TechVantage Fund LP", position_value_usd: 300000, as_of: "2026-07-24" },
];

const MOCK_METRICS = {
  active_runs: 1,
  total_runs: 12,
  human_review_count: 1,
  completed_runs: 11,
  success_rate: 0.92,
  avg_runtime_s: 4.2,
  tokens_total: 18450,
  est_cost_usd: 0.042,
};

const MOCK_RUNS = [
  {
    run_id: MOCK_RUN_ID,
    status: "human_review",
    current_node: "exception_gate",
    started_at: new Date(Date.now() - 300000).toISOString(),
    updated_at: new Date().toISOString(),
    document: "notices/capital_call_northgate.pdf",
  },
];

const MOCK_RUN_DETAIL = {
  run_id: MOCK_RUN_ID,
  status: "human_review",
  started_at: new Date(Date.now() - 300000).toISOString(),
  updated_at: new Date().toISOString(),
  timeline: [
    {
      ts: new Date(Date.now() - 290000).toISOString(),
      agent: "document_ingest",
      event: "parsed_complete",
      level: "info",
      payload: {
        doc_type: "capital_call",
        fund_name_raw: "Northgate Ventures IX, L.P.",
        amount_usd: 1250000,
        due_date: "August 01, 2026",
        effective_date: "July 24, 2026",
        notice_no: "NC-FA7E5A",
        limited_partner: "AgentCapital Master Fund",
      },
    },
    {
      ts: new Date(Date.now() - 280000).toISOString(),
      agent: "entity_resolver",
      event: "entities_resolved",
      level: "info",
      payload: {
        selected_entity_id: "ENT-NGV-09",
        canonical_name: "Northgate Ventures IX",
        confidence: 0.968,
      },
    },
    {
      ts: new Date(Date.now() - 270000).toISOString(),
      agent: "data_validator",
      event: "validation_complete",
      level: "info",
      payload: {
        passed: true,
        issues: [],
      },
    },
    {
      ts: new Date(Date.now() - 260000).toISOString(),
      agent: "risk_monitor",
      event: "risk_assessed",
      level: "warning",
      payload: {
        findings: [
          {
            kind: "concentration",
            severity: "critical",
            exposure_pct: 14.2,
            entities: ["Northgate Ventures IX", "Halcyon Growth Equity III", "Auren Ventures V"],
            message: "14.2% look-through exposure across 5 funds exceeds 10.0% policy limit.",
          },
        ],
      },
    },
    {
      ts: new Date(Date.now() - 250000).toISOString(),
      agent: "portfolio_analyst",
      event: "nav_computed",
      level: "info",
      payload: {
        as_of: "2026-07-24",
        total_nav_usd: 60900000,
        positions: 8,
      },
    },
  ],
  report: {
    markdown: `# EXECUTIVE BRIEF: Northgate Ventures IX Capital Call Notice

## 1. TRANSACTION SUMMARY
- **Fund LP**: Northgate Ventures IX, L.P.
- **Notice Reference**: NC-FA7E5A
- **Capital Call Amount**: $1,250,000.00 USD
- **Due Date**: August 01, 2026
- **Entity Resolution**: Matched to Northgate Ventures IX (96.8% confidence floor)

## 2. PORTFOLIO & RISK ANALYSIS
The requested $1,250,000.00 capital call increases look-through exposure to **NeuroAI Inc** across 5 portfolio funds to **14.2% of Total NAV** ($8.66M), breaching the Investment Committee's **10.0% Single-Issuer Concentration Policy Limit**.

## 3. COMMITTEE RECOMMENDATION
- **Primary Recommendation**: Approve capital call subject to formal Investment Committee concentration limit waiver.
- **Wire Routing**: J.P. Morgan Chase custodial routing verified.`,
    citations: ["SEC EDGAR Form ADV", "Crunchbase Data", "Bloomberg Benchmarks", "Custodial Master Agreement"],
  },
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return (await res.json()) as T;
  } catch (e) {
    // If backend endpoint is unreachable (e.g. Vercel HTTPS mixed content block to http://localhost:8000), return graceful fallback demo data
    if (path === "/runs") return MOCK_RUNS as unknown as T;
    if (path === "/documents/samples") return MOCK_SAMPLES as unknown as T;
    if (path === "/custodian/feed") return MOCK_CUSTODIAN as unknown as T;
    if (path === "/metrics") return MOCK_METRICS as unknown as T;
    if (path.startsWith("/runs/")) return MOCK_RUN_DETAIL as unknown as T;
    
    // For POST /runs or custom upload path when offline, return fallback run
    if (init?.method === "POST") {
      if (path === "/runs") return { run_id: MOCK_RUN_ID } as unknown as T;
      if (path === "/demo/reset") return { status: "reset_complete" } as unknown as T;
    }
    
    throw e;
  }
}

export type RunSummary = {
  run_id: string;
  status: string;
  current_node: string | null;
  started_at: string;
  updated_at: string;
  document: string | null;
};

export type TimelineEvent = {
  ts: string;
  agent: string;
  event: string;
  level: string;
  payload: Record<string, unknown>;
};

export type Candidate = {
  entity_id: string;
  name: string;
  kind: string;
  confidence: number;
  method: string;
};

export type PendingGate = {
  gate: "entity_gate" | "exception_gate";
  reason?: string;
  question?: string;
  candidates?: Candidate[];
  issues?: Array<{ kind: string; message: string; severity: string; code?: string }>;
};

export type RunDetail = {
  run_id: string;
  status: string;
  started_at: string;
  updated_at: string;
  timeline: TimelineEvent[];
  pending_gate?: PendingGate | null;
  report?: { markdown: string; citations?: string[] } | null;
  error?: { agent?: string; message: string } | null;
};

export type Sample = { name: string; label?: string; path?: string; storage_path: string };

export type Metrics = {
  active_runs: number;
  total_runs: number;
  human_review_count: number;
  completed_runs: number;
  success_rate?: number | null;
  avg_runtime_s?: number | null;
  tokens_total?: number;
  est_cost_usd?: number;
};
