import { RunDetail } from "@/lib/api";

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
};

// Mirrors the LangGraph topology in backend/src/core/orchestrator.py.
export const STAGES: Stage[] = [
  { key: "document_ingest", label: "Ingest", desc: "PDF → text · dedup", gate: false },
  { key: "input_guard", label: "Guard", desc: "injection screen", gate: false },
  { key: "notice_parser", label: "Parse", desc: "LLM extraction", gate: false },
  { key: "entity_resolver", label: "Resolve", desc: "entity match", gate: false },
  { key: "entity_gate", label: "Entity gate", desc: "human decision", gate: true },
  { key: "data_validator", label: "Validate", desc: "reconciliation", gate: false },
  { key: "exception_gate", label: "Exception gate", desc: "human override", gate: true },
  { key: "portfolio_analyst", label: "Analyze", desc: "NAV compute", gate: false },
  { key: "risk_monitor", label: "Risk", desc: "look-through", gate: false },
  { key: "report_generator", label: "Report", desc: "briefing", gate: false },
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
      states[stage.key] = "pending"; // refined below
      continue;
    }
    if (!activeAssigned && run.status === "running") {
      states[stage.key] = "active";
      activeAssigned = true;
      continue;
    }
    states[stage.key] = "pending";
  }

  // A gate the run flowed past without pausing was auto-skipped.
  STAGES.forEach((stage, i) => {
    if (!stage.gate || states[stage.key] !== "pending") return;
    const laterDone = STAGES.slice(i + 1).some((s) => states[s.key] === "done");
    if (laterDone || run.status === "completed") states[stage.key] = "skipped";
  });

  return states;
}
