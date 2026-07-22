"use client";

import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, RunDetail } from "@/lib/api";
import AgentDrawer from "@/components/AgentDrawer";
import AgentRail from "@/components/AgentRail";
import GraphView from "@/components/GraphView";

/** Live agent activity: every agent inline, the running one ticking each
 *  second — no clicking needed to see what's happening. */
export function ActivityCard({
  run,
  inspecting,
  onSelect,
}: {
  run: RunDetail | null;
  inspecting: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="card">
      <h2>
        Agent activity
        {run ? (
          <>
            <span className="hint">live · updates every second</span>
            <span className={`chip ${run.status}`} style={{ marginLeft: "auto" }}>
              {run.status.replace("_", " ")}
            </span>
          </>
        ) : (
          <span className="hint">process a notice to watch the agents work</span>
        )}
      </h2>
      <AgentRail run={run} selected={inspecting} onSelect={onSelect} />
      {run?.error && (
        <div className="error-box" style={{ marginTop: 14 }}>
          <b>{run.error.agent ?? "error"}:</b> {run.error.message}
        </div>
      )}
    </div>
  );
}

/** The human-in-the-loop approval card; renders nothing unless a run is
 *  parked at a gate. */
export function GatePanel({
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
    <div className="card gate">
      <h2>⏸ Human approval required — {gate.gate.replace("_", " ")}</h2>
      <p className="reason">{gate.reason ?? gate.question}</p>

      {gate.gate === "entity_gate" &&
        (gate.candidates ?? []).map((c) => (
          <div
            key={c.entity_id}
            className={`candidate ${selectedCand === c.entity_id ? "selected" : ""}`}
            onClick={() => setSelectedCand(c.entity_id)}
          >
            <input type="radio" readOnly checked={selectedCand === c.entity_id} />
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
          disabled={deciding || (gate.gate === "entity_gate" && !selectedCand)}
          onClick={() => decide("approve")}
        >
          {gate.gate === "entity_gate" ? "Approve selection" : "Override & continue"}
        </button>
        <button className="btn danger" disabled={deciding} onClick={() => decide("reject")}>
          Reject
        </button>
      </div>
    </div>
  );
}

/** Optional deep dive: the real orchestration graph beside a per-agent
 *  inspector (duration, tokens, confidence, activity). */
export function InspectRow({
  run,
  inspecting,
  onSelect,
}: {
  run: RunDetail | null;
  inspecting: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="grid2">
      <div className="card">
        <h2>
          Orchestration graph
          <span className="hint">real LangGraph topology · click a node</span>
        </h2>
        <GraphView run={run} selected={inspecting} onSelect={onSelect} />
      </div>
      <AgentDrawer run={run} stageKey={inspecting} />
    </div>
  );
}

/** Briefing with download/print actions; audit trail tucked behind a
 *  disclosure — it's forensic detail, not the headline. */
export function BriefingPanel({
  run,
  auditOpen = false,
}: {
  run: RunDetail | null;
  auditOpen?: boolean;
}) {
  const reportRef = useRef<HTMLDivElement>(null);
  if (!run || (!run.report && run.timeline.length === 0)) {
    return (
      <div className="card">
        <h2>Intelligence briefing</h2>
        <div className="empty">
          Process a notice from the inbox — the briefing appears here once the
          pipeline completes.
        </div>
      </div>
    );
  }

  function downloadMarkdown() {
    if (!run || !run.report) return;
    const blob = new Blob([run.report.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `polaris-briefing-${run.run_id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function printReport() {
    const node = reportRef.current;
    if (!node || !run) return;
    const w = window.open("", "_blank", "width=820,height=940");
    if (!w) return;
    w.document.write(`<!doctype html><html><head><title>Polaris — Intelligence Briefing</title>
<style>
  body { font-family: Georgia, "Times New Roman", serif; max-width: 700px;
         margin: 48px auto; padding: 0 28px; color: #201d1a; line-height: 1.65; font-size: 14px; }
  h1, h2, h3 { font-family: ui-sans-serif, system-ui, sans-serif; margin: 18px 0 8px; }
  h1 { font-size: 20px; } h2 { font-size: 16px; } h3 { font-size: 14px; }
  table { border-collapse: collapse; } th, td { border: 1px solid #bbb; padding: 4px 10px; }
  ul, ol { padding-left: 22px; }
  .footer { margin-top: 36px; color: #8a857e; font-size: 11px;
            border-top: 1px solid #ddd; padding-top: 10px; }
</style></head><body>${node.innerHTML}
<div class="footer">Generated by Polaris · run ${run.run_id} · ${new Date().toLocaleString()}</div>
</body></html>`);
    w.document.close();
    w.focus();
    w.print();
  }

  return (
    <div className="card">
      <h2>
        Intelligence briefing
        {run.report && (
          <span className="report-actions">
            <button className="btn secondary small" onClick={downloadMarkdown}>
              ↓ Download .md
            </button>
            <button className="btn secondary small" onClick={printReport}>
              Print / PDF
            </button>
          </span>
        )}
      </h2>

      {run.report ? (
        <>
          <div className="report" ref={reportRef}>
            <ReactMarkdown>{run.report.markdown}</ReactMarkdown>
          </div>
          <p className="muted" style={{ marginTop: 10 }}>
            {run.report.citations.length} citation(s) · grounded in validated facts
          </p>
        </>
      ) : (
        <div className="empty">
          {run.status === "running" || run.status === "awaiting_approval"
            ? "Generated after the pipeline completes…"
            : "No report for this run."}
        </div>
      )}

      <details className="audit" open={auditOpen}>
        <summary>Audit trail · {run.timeline.length} event(s)</summary>
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
      </details>
    </div>
  );
}
