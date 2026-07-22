import { RunDetail } from "@/lib/api";
import { deriveStates, STAGES, StageState } from "@/lib/pipeline";

const GLYPH: Record<StageState, (i: number) => string> = {
  done: () => "✓",
  failed: () => "✕",
  waiting: () => "⏸",
  active: () => "●",
  skipped: () => "–",
  pending: (i) => String(i + 1),
};

export default function Pipeline({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail | null;
  selected?: string | null;
  onSelect?: (key: string) => void;
}) {
  const states = run ? deriveStates(run) : null;

  return (
    <div className="pipeline">
      {STAGES.map((stage, i) => {
        const state: StageState = states ? states[stage.key] : "pending";
        return (
          <div
            className={`stage ${state} ${selected === stage.key ? "sel" : ""}`}
            key={stage.key}
            onClick={() => onSelect?.(stage.key)}
            style={onSelect ? { cursor: "pointer" } : undefined}
          >
            {i > 0 && (
              <div className={`connector ${state === "done" ? "filled" : ""}`} />
            )}
            <div className="body">
              <div className="node">{GLYPH[state](i)}</div>
              <div className="label">{stage.label}</div>
              <div className="desc">{stage.desc}</div>
              {stage.gate && <div className="gate-tag">HUMAN</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
