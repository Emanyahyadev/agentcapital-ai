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

export default function Pipeline({ run }: { run: RunDetail | null }) {
  const states = run ? deriveStates(run) : null;

  return (
    <div className="pipeline">
      {STAGES.map((stage, i) => {
        const state: StageState = states ? states[stage.key] : "pending";
        return (
          <div className={`stage ${state}`} key={stage.key}>
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
