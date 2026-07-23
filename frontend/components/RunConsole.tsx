"use client";

import { useEffect, useState } from "react";
import { api, RunDetail } from "@/lib/api";
import AgentDrawer from "@/components/AgentDrawer";
import AgentFlow from "@/components/AgentFlow";
import { currentStage } from "@/lib/pipeline";

/** Human-in-the-loop approval gate card */
function GatePanel({
  run,
  onChanged,
}: {
  run: RunDetail | null;
  onChanged: () => void;
}) {
  const [deciding, setDeciding] = useState(false);
  const [selectedCand, setSelectedCand] = useState<string | null>(null);
  const gate = run?.pending_gate ?? null;
  if (!run || !gate) return null;

  async function decide(action: "approve" | "reject") {
    if (!run) return;
    setDeciding(true);
    try {
      await api(`/runs/${run.run_id}/${action}`, {
        method: "POST",
        body: JSON.stringify(
          action === "approve" ? { selected_entity_id: selectedCand } : {},
        ),
      });
      onChanged();
    } finally {
      setDeciding(false);
    }
  }

  return (
    <div className="gate-card warning">
      <div className="gate-header">
        <span className="gate-icon">⏸</span>
        <h2>Human Approval Required — {gate.gate.replace("_", " ")}</h2>
      </div>
      <p className="gate-reason">{gate.reason ?? gate.question}</p>

      {gate.gate === "entity_gate" &&
        (gate.candidates ?? []).map((c) => (
          <div
            key={c.entity_id}
            className={`candidate-tile ${selectedCand === c.entity_id ? "selected" : ""}`}
            onClick={() => setSelectedCand(c.entity_id)}
          >
            <input type="radio" readOnly checked={selectedCand === c.entity_id} />
            <span className="c-name">{c.name} <span className="muted">({c.kind})</span></span>
            <span className="c-conf">{c.method} · {(c.confidence * 100).toFixed(0)}%</span>
          </div>
        ))}

      {gate.gate === "exception_gate" &&
        (gate.issues ?? []).map((issue, i) => (
          <div className="issue-chip" key={i}>
            <span className="code">{issue.code}</span>
            {issue.message}
          </div>
        ))}

      <div className="gate-actions">
        <button
          className="btn-ent approve"
          disabled={deciding || (gate.gate === "entity_gate" && !selectedCand)}
          onClick={() => decide("approve")}
        >
          {gate.gate === "entity_gate" ? "Approve Selection" : "Override & Continue"}
        </button>
        <button className="btn-ent danger" disabled={deciding} onClick={() => decide("reject")}>
          Reject Notice
        </button>
      </div>
    </div>
  );
}

/** Multi-Agent Execution Cockpit Pipeline View (GitHub Actions Style) */
export function ExecutionPanel({
  run,
  onChanged,
}: {
  run: RunDetail | null;
  onChanged: () => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const runId = run?.run_id;
  useEffect(() => setPicked(null), [runId]);
  const inspecting = picked ?? currentStage(run);

  return (
    <div className="execution-cockpit-wrapper">
      <GatePanel run={run} onChanged={onChanged} />

      <div className="cockpit-grid">
        {/* Left: GitHub Actions inspired workflow pipeline */}
        <div className="ent-card">
          <div className="ent-card-header">
            <h2>Multi-Agent Workflow Pipeline</h2>
            {run ? (
              <span className={`chip ${run.status}`}>
                {run.status.replace("_", " ")}
              </span>
            ) : (
              <span className="subtle-badge">Select a notice to run</span>
            )}
          </div>

          <div className="pipeline-nodes-flow">
            <AgentFlow run={run} selected={inspecting} onSelect={setPicked} />
          </div>

          {run?.error && (
            <div className="error-banner">
              <strong>{run.error.agent ?? "Error"}:</strong> {run.error.message}
            </div>
          )}
        </div>

        {/* Right: Agent Inspector Drawer */}
        <AgentDrawer run={run} stageKey={inspecting} />
      </div>
    </div>
  );
}
