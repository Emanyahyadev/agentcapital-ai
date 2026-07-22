import { RunDetail, TimelineEvent } from "@/lib/api";

export type StageState =
  | "pending"
  | "active"
  | "done"
  | "waiting"
  | "failed"
  | "skipped";

export type Stage = {
  key: string;      // audit-log agent name
  label: string;
  desc: string;
  gate: boolean;
  llm: boolean;     // does this agent call the LLM?
  detail: string;   // one-line "what it does" for the drawer
};

// Mirrors the LangGraph topology in backend/src/core/orchestrator.py.
export const STAGES: Stage[] = [
  { key: "document_ingest", label: "Ingest", desc: "PDF → text · dedup", gate: false, llm: false,
    detail: "Extracts the PDF text layer and fingerprints it (sha256) so the same notice is never processed twice." },
  { key: "input_guard", label: "Guard", desc: "injection screen", gate: false, llm: false,
    detail: "Redacts instruction-shaped spans before any LLM sees the text. Deterministic regex — you can't ask a model to referee text designed to manipulate models." },
  { key: "notice_parser", label: "Parse", desc: "LLM extraction", gate: false, llm: true,
    detail: "Gemini structured extraction into a typed contract, then a grounding check: the amount and fund name must literally appear in the source or the extraction is rejected." },
  { key: "entity_resolver", label: "Resolve", desc: "entity match", gate: false, llm: false,
    detail: "Deterministic exact → alias → fuzzy matching with calibrated confidence. Refuses to guess on ambiguity, low confidence, or parent-vs-sub-fund notices." },
  { key: "entity_gate", label: "Entity gate", desc: "human decision", gate: true, llm: false,
    detail: "The run parks here when resolution is ambiguous — a human picks the destination entity. Parked state in the checkpointer, not a blocked process." },
  { key: "data_validator", label: "Validate", desc: "reconciliation", gate: false, llm: false,
    detail: "Duplicate guard, deadline checks, and custodian reconciliation — identifies which other fund's position moved when a distribution is mis-attributed." },
  { key: "exception_gate", label: "Exception gate", desc: "human override", gate: true, llm: false,
    detail: "The run parks here on a critical validation issue — a human overrides or rejects. Transactions stay pending_review until then." },
  { key: "portfolio_analyst", label: "Analyze", desc: "NAV compute", gate: false, llm: false,
    detail: "Recomputes NAV as pure arithmetic over sourced numbers. Zero LLM — figures an LLM 'computed' cannot be audited." },
  { key: "risk_monitor", label: "Risk", desc: "look-through", gate: false, llm: false,
    detail: "Look-through concentration across funds — the exposure no single fund report reveals — plus escalation of unreconciled variances." },
  { key: "report_generator", label: "Report", desc: "briefing", gate: false, llm: true,
    detail: "Narrates a briefing over already-validated facts. The LLM writes; it never computes. Citations are assembled in code." },
];

export function deriveStates(run: RunDetail): Record<string, StageState> {
  const seen = new Set(run.timeline.map((t) => t.agent));
  const failedAgent = run.status === "failed" ? run.error?.agent : undefined;
  const pendingGate = run.pending_gate?.gate;
  const states: Record<string, StageState> = {};
  let activeAssigned = false;

  for (const stage of STAGES) {
    if (seen.has(stage.key)) {
      states[stage.key] = "done";
      continue;
    }
    if (failedAgent === stage.key) {
      states[stage.key] = "failed";
      activeAssigned = true;
      continue;
    }
    if (pendingGate === stage.key) {
      states[stage.key] = "waiting";
      activeAssigned = true;
      continue;
    }
    if (stage.gate) {
      states[stage.key] = "pending";
      continue;
    }
    if (!activeAssigned && run.status === "running") {
      states[stage.key] = "active";
      activeAssigned = true;
      continue;
    }
    states[stage.key] = "pending";
  }

  STAGES.forEach((stage, i) => {
    if (!stage.gate || states[stage.key] !== "pending") return;
    const laterDone = STAGES.slice(i + 1).some((s) => states[s.key] === "done");
    if (laterDone || run.status === "completed") states[stage.key] = "skipped";
  });

  return states;
}

/** All audit events attributed to one agent, oldest first. */
export function stageEvents(run: RunDetail, key: string): TimelineEvent[] {
  return run.timeline.filter((t) => t.agent === key);
}

/** Real duration + token telemetry for an agent, from its agent_completed row. */
export function stageMetrics(
  run: RunDetail,
  key: string,
): { duration_ms: number; tokens: { input: number; output: number } } | null {
  const row = run.timeline.find(
    (t) => t.agent === key && t.event === "agent_completed",
  );
  if (!row) return null;
  const p = row.payload as {
    duration_ms?: number;
    tokens?: { input?: number; output?: number };
  };
  return {
    duration_ms: p.duration_ms ?? 0,
    tokens: { input: p.tokens?.input ?? 0, output: p.tokens?.output ?? 0 },
  };
}
