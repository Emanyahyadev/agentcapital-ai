import { RunDetail } from "@/lib/api";
import { deriveStates, StageState } from "@/lib/pipeline";

// Fixed layout mirroring the real LangGraph topology in orchestrator.py:
// a spine with two conditional branches (the human gates) and a failure edge.
type Node = { key: string; x: number; y: number; label: string; col: "main" | "side" };

const NODES: Node[] = [
  { key: "document_ingest", x: 110, y: 45, label: "Ingest", col: "main" },
  { key: "input_guard", x: 110, y: 110, label: "Guard", col: "main" },
  { key: "error_handler", x: 300, y: 110, label: "Error handler", col: "side" },
  { key: "notice_parser", x: 110, y: 175, label: "Parse", col: "main" },
  { key: "entity_resolver", x: 110, y: 240, label: "Resolve", col: "main" },
  { key: "entity_gate", x: 300, y: 240, label: "Entity gate", col: "side" },
  { key: "data_validator", x: 110, y: 325, label: "Validate", col: "main" },
  { key: "exception_gate", x: 300, y: 325, label: "Exception gate", col: "side" },
  { key: "portfolio_analyst", x: 110, y: 410, label: "Analyze", col: "main" },
  { key: "risk_monitor", x: 110, y: 475, label: "Risk", col: "main" },
  { key: "report_generator", x: 110, y: 540, label: "Report", col: "main" },
];

type Edge = { from: string; to: string; label?: string; dashed?: boolean };

const EDGES: Edge[] = [
  { from: "document_ingest", to: "input_guard" },
  { from: "input_guard", to: "notice_parser" },
  { from: "input_guard", to: "error_handler", label: "on failure", dashed: true },
  { from: "notice_parser", to: "entity_resolver" },
  { from: "entity_resolver", to: "data_validator", label: "clear" },
  { from: "entity_resolver", to: "entity_gate", label: "ambiguous" },
  { from: "entity_gate", to: "data_validator" },
  { from: "data_validator", to: "portfolio_analyst", label: "passed" },
  { from: "data_validator", to: "exception_gate", label: "critical" },
  { from: "exception_gate", to: "portfolio_analyst" },
  { from: "portfolio_analyst", to: "risk_monitor" },
  { from: "risk_monitor", to: "report_generator" },
];

const FILL: Record<StageState, string> = {
  done: "#47725a",
  active: "#ffffff",
  waiting: "#f7edd8",
  failed: "#9c3f3a",
  skipped: "#f0eeec",
  pending: "#ffffff",
};
const STROKE: Record<StageState, string> = {
  done: "#47725a",
  active: "#292524",
  waiting: "#96690a",
  failed: "#9c3f3a",
  skipped: "#d6d3cf",
  pending: "#d6d3cf",
};
const GLYPH: Record<StageState, string> = {
  done: "✓", active: "●", waiting: "⏸", failed: "✕", skipped: "–", pending: "",
};

const byKey = Object.fromEntries(NODES.map((n) => [n.key, n]));

export default function GraphView({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail | null;
  selected: string | null;
  onSelect: (key: string) => void;
}) {
  const states: Record<string, StageState> = run
    ? deriveStates(run)
    : Object.fromEntries(NODES.map((n) => [n.key, "pending" as StageState]));

  return (
    <svg viewBox="0 0 440 590" className="graph" role="img" aria-label="orchestration graph">
      {EDGES.map((e, i) => {
        const a = byKey[e.from];
        const b = byKey[e.to];
        const targetDone = states[e.to] === "done";
        const color = e.dashed ? "#d6d3cf" : targetDone ? "#8fb3a0" : "#d6d3cf";
        const midx = (a.x + b.x) / 2;
        const midy = (a.y + b.y) / 2;
        return (
          <g key={i}>
            <line
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={color} strokeWidth={2}
              strokeDasharray={e.dashed ? "4 4" : undefined}
            />
            {e.label && (
              <text x={midx + 6} y={midy - 3} className="graph-edge-label">
                {e.label}
              </text>
            )}
          </g>
        );
      })}

      {NODES.map((n) => {
        const st = states[n.key] ?? "pending";
        const isSel = selected === n.key;
        const labelX = n.x + 22;
        return (
          <g
            key={n.key}
            className="graph-node"
            onClick={() => onSelect(n.key)}
            style={{ cursor: "pointer" }}
          >
            {isSel && (
              <circle cx={n.x} cy={n.y} r={19} fill="none" stroke="#292524" strokeWidth={1.5} />
            )}
            <circle
              cx={n.x} cy={n.y} r={15}
              fill={FILL[st]} stroke={STROKE[st]} strokeWidth={2}
              strokeDasharray={st === "skipped" ? "3 3" : undefined}
            />
            <text
              x={n.x} y={n.y + 4} textAnchor="middle"
              fontSize={12} fontWeight={700}
              fill={st === "done" || st === "failed" ? "#fff" : STROKE[st]}
            >
              {GLYPH[st]}
            </text>
            <text x={labelX} y={n.y + 4} className="graph-node-label">
              {n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
