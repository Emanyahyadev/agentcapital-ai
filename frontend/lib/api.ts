export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
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
  question: string;
  reason?: string;
  candidates?: Candidate[];
  issues?: { code: string; severity: string; message: string }[];
  notice?: Record<string, unknown>;
};

export type RunDetail = RunSummary & {
  error: { agent?: string; message?: string } | null;
  timeline: TimelineEvent[];
  pending_gate: PendingGate | null;
  report: { markdown: string; citations: unknown[] } | null;
};

export type Sample = { name: string; storage_path: string };

export type Metrics = {
  total_runs: number;
  by_status: Record<string, number>;
  completed: number;
  success_rate: number | null;
  avg_runtime_s: number | null;
  tokens_input: number;
  tokens_output: number;
  tokens_total: number;
  est_cost_usd: number;
};
