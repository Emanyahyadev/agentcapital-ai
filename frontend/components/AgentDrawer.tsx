import { RunDetail } from "@/lib/api";
import { deriveStates, STAGES, stageEvents, stageMetrics, StageState } from "@/lib/pipeline";

const STATE_LABEL: Record<StageState, string> = {
  done: "completed",
  active: "running",
  waiting: "awaiting human",
  failed: "failed",
  skipped: "skipped (not needed)",
  pending: "pending",
};

/** Confidence + issue detail, surfaced only where the agent genuinely
 *  produces it — never fabricated for agents that don't. */
function Signals({ run, stageKey }: { run: RunDetail; stageKey: string }) {
  const events = stageEvents(run, stageKey);

  if (stageKey === "entity_resolver") {
    const ev = events.find((e) => e.event === "entities_resolved");
    const cands = (ev?.payload?.candidates as [string, number][]) ?? [];
    if (!cands.length) return null;
    return (
      <div className="signals">
        <div className="signals-h">Match confidence</div>
        {cands.slice(0, 4).map(([name, conf], i) => (
          <div className="confbar" key={i}>
            <span className="confbar-name">{name}</span>
            <span className="confbar-track">
              <span className="confbar-fill" style={{ width: `${conf * 100}%` }} />
            </span>
            <span className="confbar-val">{(conf * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    );
  }

  if (stageKey === "data_validator") {
    const ev = events.find((e) => e.event === "validation_complete");
    if (!ev) return null;
    const passed = ev.payload?.passed as boolean;
    const issues = (ev.payload?.issues as [string, string][]) ?? [];
    return (
      <div className="signals">
        <div className="signals-h">Reconciliation</div>
        <div className={`verdict ${passed ? "ok" : "bad"}`}>
          {passed ? "✓ Passed — no critical issues" : "✕ Critical issue — routed to human"}
        </div>
        {issues.map(([code, sev], i) => (
          <div className="issue" key={i}>
            <span className="code">{code}</span>
            <span className="muted">{sev}</span>
          </div>
        ))}
      </div>
    );
  }

  if (stageKey === "risk_monitor") {
    const ev = events.find((e) => e.event === "risk_assessed");
    const findings = (ev?.payload?.findings as Array<{
      kind: string; severity: string; message: string;
      exposure_pct?: number; entities?: string[];
    }>) ?? [];
    if (!findings.length) return null;
    return (
      <div className="signals">
        <div className="signals-h">Why flagged</div>
        {findings.map((f, i) => (
          <div key={i} className={`finding ${f.severity}`}>
            <div className="finding-msg">
              {f.severity === "critical" ? "⚠ " : ""}
              {f.message}
            </div>
            {f.entities && f.entities.length > 0 && (
              <div className="finding-entities">
                across {f.entities.join(" · ")}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  return null;
}

export default function AgentDrawer({
  run,
  stageKey,
}: {
  run: RunDetail | null;
  stageKey: string | null;
}) {
  const stage = STAGES.find((s) => s.key === stageKey);
  if (!stage) {
    return (
      <div className="card">
        <h2>Agent detail</h2>
        <div className="empty">Select an agent in the graph to inspect it.</div>
      </div>
    );
  }

  const state: StageState = run ? deriveStates(run)[stage.key] : "pending";
  const metrics = run ? stageMetrics(run, stage.key) : null;
  const reasoning = run
    ? stageEvents(run, stage.key).filter((e) => e.event !== "agent_completed")
    : [];

  return (
    <div className="card">
      <h2>
        {stage.label} agent
        <span className={`chip ${state === "done" ? "completed" : state === "failed" ? "failed" : state === "waiting" ? "awaiting_approval" : "running"}`}
              style={{ marginLeft: "auto" }}>
          {STATE_LABEL[state]}
        </span>
      </h2>

      <p className="agent-detail">{stage.detail}</p>

      <div className="agent-metrics">
        <div className="am">
          <div className="am-k">Duration</div>
          <div className="am-v">{metrics ? `${(metrics.duration_ms / 1000).toFixed(2)}s` : "—"}</div>
        </div>
        <div className="am">
          <div className="am-k">LLM tokens</div>
          <div className="am-v">
            {!metrics ? "—" : stage.llm
              ? `${metrics.tokens.input + metrics.tokens.output}`
              : "0"}
          </div>
        </div>
        <div className="am">
          <div className="am-k">Mode</div>
          <div className="am-v" style={{ fontSize: 13 }}>
            {stage.llm ? "LLM" : "deterministic"}
          </div>
        </div>
      </div>
      {metrics && stage.llm && (
        <div className="muted" style={{ marginTop: -4, marginBottom: 10 }}>
          {metrics.tokens.input} in · {metrics.tokens.output} out
        </div>
      )}
      {metrics && !stage.llm && (
        <div className="muted" style={{ marginTop: -4, marginBottom: 10 }}>
          No LLM call — fully reproducible, nothing to hallucinate.
        </div>
      )}

      {run && <Signals run={run} stageKey={stage.key} />}

      {reasoning.length > 0 && (
        <div className="reasoning">
          <div className="signals-h">Activity</div>
          <ul className="timeline">
            {reasoning.map((e, i) => (
              <li key={i}>
                <span className="ts">{new Date(e.ts).toLocaleTimeString()}</span>
                <span className={e.level}>
                  {e.event}
                  {Object.keys(e.payload ?? {}).length > 0 && (
                    <span className="payload"> · {JSON.stringify(e.payload).slice(0, 90)}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
