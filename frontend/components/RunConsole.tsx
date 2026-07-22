"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, RunDetail } from "@/lib/api";
import Pipeline from "@/components/Pipeline";

export default function RunConsole({
  run,
  onChanged,
}: {
  run: RunDetail | null;
  onChanged: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);

  async function decide(action: "approve" | "reject") {
    if (!run) return;
    setDeciding(true);
    try {
      await api(`/runs/${run.run_id}/${action}`, {
        method: "POST",
        body: JSON.stringify(
          action === "approve" ? { selected_entity_id: selected } : {},
        ),
      });
      onChanged();
    } finally {
      setDeciding(false);
    }
  }

  const gate = run?.pending_gate ?? null;

  return (
    <>
      <div className="card">
        <h2>
          Agent pipeline
          {run ? (
            <>
              <span className="hint">
                {run.document?.split(/[\\/]/).pop() ?? run.run_id.slice(0, 8)}
              </span>
              <span className={`chip ${run.status}`} style={{ marginLeft: "auto" }}>
                {run.status.replace("_", " ")}
              </span>
            </>
          ) : (
            <span className="hint">process a notice to watch the agents work</span>
          )}
        </h2>
        <Pipeline run={run} />
        {run?.error && (
          <div className="error-box" style={{ marginTop: 16 }}>
            <b>{run.error.agent ?? "error"}:</b> {run.error.message}
          </div>
        )}
      </div>

      {gate && (
        <div className="card gate">
          <h2>Human approval required — {gate.gate.replace("_", " ")}</h2>
          <p className="reason">{gate.reason ?? gate.question}</p>

          {gate.gate === "entity_gate" &&
            (gate.candidates ?? []).map((c) => (
              <div
                key={c.entity_id}
                className={`candidate ${selected === c.entity_id ? "selected" : ""}`}
                onClick={() => setSelected(c.entity_id)}
              >
                <input type="radio" readOnly checked={selected === c.entity_id} />
                <span>
                  {c.name} <span className="muted">({c.kind})</span>
                </span>
                <span className="conf">
                  {c.method} · {(c.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}

          {gate.gate === "exception_gate" &&
            (gate.issues ?? []).map((issue, i) => (
              <div className="issue" key={i}>
                <span className="code">{issue.code}</span>
                {issue.message}
              </div>
            ))}

          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button
              className="btn approve"
              disabled={deciding || (gate.gate === "entity_gate" && !selected)}
              onClick={() => decide("approve")}
            >
              {gate.gate === "entity_gate" ? "Approve selection" : "Override & continue"}
            </button>
            <button className="btn danger" disabled={deciding} onClick={() => decide("reject")}>
              Reject
            </button>
          </div>
        </div>
      )}

      {run && (run.report || run.timeline.length > 0) && (
        <div className="grid2">
          {run.report ? (
            <div className="card">
              <h2>Intelligence briefing</h2>
              <div className="report">
                <ReactMarkdown>{run.report.markdown}</ReactMarkdown>
              </div>
              <p className="muted" style={{ marginTop: 10 }}>
                {run.report.citations.length} citation(s) · grounded in validated facts
              </p>
            </div>
          ) : (
            <div className="card">
              <h2>Intelligence briefing</h2>
              <div className="empty">
                {run.status === "running" || run.status === "awaiting_approval"
                  ? "Generated after the pipeline completes…"
                  : "No report for this run."}
              </div>
            </div>
          )}

          <div className="card">
            <h2>Audit trail</h2>
            {run.timeline.length === 0 && <div className="empty">No events yet…</div>}
            <ul className="timeline">
              {run.timeline.map((t, i) => (
                <li key={i}>
                  <span className="ts">{new Date(t.ts).toLocaleTimeString()}</span>
                  <span className={`agent ${t.level}`}>{t.agent}</span>
                  <span className={t.level}>
                    {t.event}
                    {Object.keys(t.payload ?? {}).length > 0 && (
                      <span className="payload">
                        {" "}· {JSON.stringify(t.payload).slice(0, 110)}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
