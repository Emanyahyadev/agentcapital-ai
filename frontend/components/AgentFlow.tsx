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

// 21st.dev style sleek vector icons for stage states
function RenderStatusIcon({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (state === "failed") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  }
  if (state === "waiting") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="6" y="4" width="4" height="16" rx="1" />
        <rect x="14" y="4" width="4" height="16" rx="1" />
      </svg>
    );
  }
  if (state === "skipped") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
    );
  }
  return null;
}

const BRANCH: Record<string, string> = {
  entity_gate: "branches here if resolution is ambiguous",
  exception_gate: "branches here if validation finds a critical issue",
};

type Node =
  | { kind: "agent" | "gate"; key: string; last: boolean }
  | { kind: "error" };

function sequence(): Node[] {
  const seq: Node[] = [];
  STAGES.forEach((s, i) => {
    seq.push({ kind: s.gate ? "gate" : "agent", key: s.key, last: i === STAGES.length - 1 });
    if (s.key === "input_guard") seq.push({ kind: "error" });
  });
  return seq;
}

export default function AgentFlow({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail | null;
  selected?: string | null;
  onSelect?: (key: string) => void;
}) {
  const [nowMs, setNowMs] = useState<number>(0);
  useEffect(() => {
    setNowMs(Date.now());
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const states = run ? deriveStates(run) : null;
  const liveStart = run ? activeStartTs(run) : 0;
  const stageByKey = Object.fromEntries(STAGES.map((s) => [s.key, s]));

  function timeFor(key: string, st: StageState) {
    const m = run ? stageMetrics(run, key) : null;
    if ((st === "done" || st === "failed") && m) {
      return {
        text: `${(m.duration_ms / 1000).toFixed(2)}s`,
        cls: "",
        tok: st === "done" && stageByKey[key]?.llm ? m.tokens.input + m.tokens.output : null,
      };
    }
    if (st === "active") {
      return { text: `${Math.max(0, Math.floor((nowMs - liveStart) / 1000))}s`, cls: "live", tok: null };
    }
    if (st === "waiting") return { text: "waiting", cls: "waitc", tok: null };
    return { text: "—", cls: "idle", tok: null };
  }

  return (
    <div className="flow">
      {sequence().map((node) => {
        if (node.kind === "error") {
          const st: StageState = run?.status === "failed" ? "failed" : "pending";
          return (
            <div className="flow-row branch" key="error">
              <div className="flow-track branchtrack">
                <span className={`flow-dot ${st === "failed" ? "failed" : "idle"}`}>
                  {st === "failed" ? (
                    <RenderStatusIcon state="failed" />
                  ) : (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                  )}
                </span>
              </div>
              <div className={`flow-card branchcard ${st === "failed" ? "failed" : "muted"}`}>
                <div className="flow-card-top">
                  <span className="flow-name">Error handler</span>
                  <span className="flow-branch-cond">failure route · retries exhausted</span>
                </div>
              </div>
            </div>
          );
        }

        const stage = stageByKey[node.key];
        const st: StageState = states ? states[node.key] : "pending";
        const t = timeFor(node.key, st);
        const isGate = node.kind === "gate";
        const desc =
          st === "active"
            ? stage.llm ? "thinking…" : "working…"
            : st === "waiting"
              ? "awaiting your decision"
              : st === "skipped"
                ? "not triggered — flow continued"
                : isGate
                  ? BRANCH[node.key]
                  : stage.desc;

        return (
          <div
            className={`flow-row ${isGate ? "branch" : ""}`}
            key={node.key}
            onClick={() => onSelect?.(node.key)}
            style={onSelect ? { cursor: "pointer" } : undefined}
          >
            <div className={`flow-track ${isGate ? "branchtrack" : ""}`}>
              <span className={`flow-dot ${st}`}>
                {st === "active" ? <span className="spinner" /> : <RenderStatusIcon state={st} />}
              </span>
              {!node.last && !isGate && (
                <span className={`flow-line ${st === "done" ? "filled" : ""}`} />
              )}
            </div>

            <div className={`flow-card ${isGate ? "branchcard" : ""} ${st} ${selected === node.key ? "sel" : ""}`}>
              <div className="flow-card-top">
                <span className="flow-name">{stage.label}</span>
                <span className="flow-mode">{stage.llm ? "LLM" : "deterministic"}</span>
                {isGate && <span className="flow-human">HUMAN</span>}
                <span className={`flow-time ${t.cls}`}>{t.text}</span>
              </div>
              <div className="flow-desc">{desc}</div>
              {t.tok !== null && <span className="flow-tok">{t.tok} tokens</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
