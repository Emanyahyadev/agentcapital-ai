"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, RunDetail } from "@/lib/api";

const TERMINAL = new Set(["completed", "failed", "rejected"]);

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const detail = await api<RunDetail>(`/runs/${id}`);
      setRun(detail);
      setErr(null);
      return detail;
    } catch (e) {
      setErr(String(e));
      return null;
    }
  }, [id]);

  useEffect(() => {
    refresh();
    const t = setInterval(async () => {
      const d = await refresh();
      if (d && TERMINAL.has(d.status)) clearInterval(t);
    }, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  async function decide(action: "approve" | "reject") {
    setDeciding(true);
    try {
      await api(`/runs/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify(
          action === "approve" ? { selected_entity_id: selected } : {},
        ),
      });
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setDeciding(false);
    }
  }

  if (!run) {
    return <p className="muted">{err ?? "Loading run…"}</p>;
  }

  const gate = run.pending_gate;

  return (
    <>
      <p style={{ marginBottom: 14 }}>
        <Link href="/">← back</Link>
      </p>

      <div className="card">
        <h2>
          Run {run.run_id.slice(0, 8)}
          <span className={`chip ${run.status}`} style={{ marginLeft: 12 }}>
            {run.status.replace("_", " ")}
          </span>
        </h2>
        <p className="muted">
          {run.document ?? "—"} · started {new Date(run.started_at).toLocaleString()}
        </p>
        {run.error && (
          <div className="error-box" style={{ marginTop: 10 }}>
            <b>{run.error.agent ?? "error"}:</b> {run.error.message}
          </div>
        )}
      </div>

      {gate && (
        <div className="gate">
          <h2>⏸ Human approval required — {gate.gate.replace("_", " ")}</h2>
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
              className="btn success"
              disabled={deciding || (gate.gate === "entity_gate" && !selected)}
              onClick={() => decide("approve")}
            >
              {gate.gate === "entity_gate" ? "Approve selection" : "Override & continue"}
            </button>
            <button
              className="btn danger"
              disabled={deciding}
              onClick={() => decide("reject")}
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {run.report && (
        <div className="card">
          <h2>Intelligence briefing</h2>
          <div className="report">
            <ReactMarkdown>{run.report.markdown}</ReactMarkdown>
          </div>
          <p className="muted" style={{ marginTop: 10 }}>
            {run.report.citations.length} citation(s) — grounded in the audit trail
          </p>
        </div>
      )}

      <div className="card">
        <h2>Agent timeline<span className="hint">from the audit log</span></h2>
        {run.timeline.length === 0 && <p className="muted">No events yet…</p>}
        <ul className="timeline">
          {run.timeline.map((t, i) => (
            <li key={i}>
              <span className="ts">{new Date(t.ts).toLocaleTimeString()}</span>
              <span className={`agent ${t.level}`}>{t.agent}</span>
              <span className={t.level}>
                {t.event}
                {Object.keys(t.payload ?? {}).length > 0 && (
                  <span className="muted">
                    {" "}
                    · {JSON.stringify(t.payload).slice(0, 140)}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
