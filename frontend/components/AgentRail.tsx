"use client";

import { useEffect, useState } from "react";
import { RunDetail } from "@/lib/api";
import {
  activeStartTs,
  deriveStates,
  STAGES,
  StageState,
  stageMetrics,
} from "@/lib/pipeline";

const ICON: Record<StageState, string> = {
  done: "✓",
  failed: "✕",
  waiting: "⏸",
  active: "",
  skipped: "–",
  pending: "",
};

/** Live agent rail: every agent inline, the running one ticking each second,
 *  completed ones showing their real recorded duration and token count. */
export default function AgentRail({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail | null;
  selected?: string | null;
  onSelect?: (key: string) => void;
}) {
  // Re-render every second so the active agent's timer counts up.
  const [nowMs, setNowMs] = useState<number>(0);
  useEffect(() => {
    setNowMs(Date.now());
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const states = run ? deriveStates(run) : null;
  const liveStart = run ? activeStartTs(run) : 0;

  return (
    <div className="rail">
      {STAGES.map((stage, i) => {
        const st: StageState = states ? states[stage.key] : "pending";
        const m = run ? stageMetrics(run, stage.key) : null;

        let time = "—";
        let timeCls = "";
        if ((st === "done" || st === "failed") && m) {
          time = `${(m.duration_ms / 1000).toFixed(2)}s`;
        } else if (st === "active") {
          const secs = Math.max(0, Math.floor((nowMs - liveStart) / 1000));
          time = `${secs}s`;
          timeCls = "live";
        } else if (st === "waiting") {
          time = "waiting";
          timeCls = "waitc";
        }
        const tok =
          st === "done" && m && stage.llm ? m.tokens.input + m.tokens.output : null;

        const desc =
          st === "active"
            ? stage.llm
              ? "thinking…"
              : "working…"
            : st === "waiting"
              ? "awaiting your decision"
              : st === "skipped"
                ? "skipped — not needed"
                : stage.desc;

        return (
          <div
            key={stage.key}
            className={`rail-row ${st} ${selected === stage.key ? "sel" : ""}`}
            onClick={() => onSelect?.(stage.key)}
            style={onSelect ? { cursor: "pointer" } : undefined}
          >
            <div className="rail-track">
              <span className="rail-node">
                {st === "active" ? <span className="spinner" /> : ICON[st]}
              </span>
              {i < STAGES.length - 1 && (
                <span className={`rail-line ${st === "done" ? "filled" : ""}`} />
              )}
            </div>

            <div className="rail-main">
              <div className="rail-name">
                {stage.label}
                <span className="rail-mode">{stage.llm ? "LLM" : "deterministic"}</span>
                {stage.gate && <span className="rail-gate">HUMAN</span>}
              </div>
              <div className="rail-desc">{desc}</div>
            </div>

            <div className="rail-right">
              <span className={`rail-time ${timeCls}`}>{time}</span>
              {tok !== null && <span className="rail-tok">{tok} tok</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
