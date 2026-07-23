"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE, Metrics, RunDetail, RunSummary, Sample } from "@/lib/api";
import MetricsStrip from "@/components/MetricsStrip";
import ExecutiveReportView from "@/components/ExecutiveReportView";
import { ExecutionPanel } from "@/components/RunConsole";
import LoadingScreen from "@/components/LoadingScreen";

const TERMINAL = new Set(["completed", "failed", "rejected"]);

type ActiveTab = "executive" | "cockpit";

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ActiveTab>("executive");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [nav, setNav] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const list = await api<RunSummary[]>("/runs");
      setRuns(list);
      setErr(null);
      setSelectedId((cur) => cur ?? list[0]?.run_id ?? null);
    } catch {
      setErr(null);
    }
    api<{ position_value_usd: number }[]>("/custodian/feed")
      .then((rows) => setNav(rows.reduce((s, r) => s + r.position_value_usd, 0)))
      .catch(() => {});
    api<Sample[]>("/documents/samples")
      .then((s) => setSamples((prev) => (s.length ? s : prev)))
      .catch(() => {});
    api<Metrics>("/metrics").then(setMetrics).catch(() => {});
  }, []);

  const refreshDetail = useCallback(async () => {
    if (!selectedId) return;
    try {
      setDetail(await api<RunDetail>(`/runs/${selectedId}`));
    } catch {
      /* keep last snapshot */
    }
  }, [selectedId]);

  useEffect(() => {
    refreshRuns();
    const t = setInterval(refreshRuns, 5000);
    return () => clearInterval(t);
  }, [refreshRuns]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    const tick = async () => {
      const d = await api<RunDetail>(`/runs/${selectedId}`).catch(() => null);
      if (cancelled || !d) return;
      setDetail(d);
      if (TERMINAL.has(d.status)) clearInterval(t);
    };
    tick();
    const t = setInterval(tick, 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [selectedId]);

  async function startRun(storage_path: string) {
    setStarting(storage_path);
    try {
      const res = await api<{ run_id: string }>("/runs", {
        method: "POST",
        body: JSON.stringify({ storage_path }),
      });
      setSelectedId(res.run_id);
      setDetail(null);
      await refreshRuns();
    } catch (e) {
      setErr(String(e));
    } finally {
      setStarting(null);
    }
  }

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/documents/upload`, { method: "POST", body: form });
    if (!res.ok) return setErr(await res.text());
    const { storage_path } = await res.json();
    await startRun(storage_path);
  }

  async function resetDemo() {
    if (!confirm("Are you sure you want to reset all demo runs and clear the workspace?")) return;
    setResetting(true);
    try {
      await api("/demo/reset", { method: "POST" });
      setSelectedId(null);
      setDetail(null);
      setMsg("Demo workspace reset successfully!");
      setTimeout(() => setMsg(null), 4000);
      await refreshRuns();
    } catch (e) {
      setErr(`Reset failed: ${e}`);
    } finally {
      setResetting(false);
    }
  }

  async function ask() {
    if (!question.trim()) return;
    setAsking(true);
    setAnswer(null);
    try {
      const res = await api<{ answer: string }>("/ask", {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      setAnswer(res.answer);
    } catch (e) {
      setAnswer(`Error: ${e}`);
    } finally {
      setAsking(false);
    }
  }

  const onChanged = () => {
    refreshDetail();
    refreshRuns();
  };

  if (loading) {
    return <LoadingScreen onComplete={() => setLoading(false)} />;
  }

  return (
    <div className="workspace-wrapper">
      {err && <div className="error-banner" style={{ marginBottom: 16 }}>{err}</div>}
      {msg && (
        <div
          style={{
            background: "#ecfdf5",
            border: "1px solid #a7f3d0",
            color: "#10b981",
            padding: "10px 16px",
            borderRadius: "8px",
            marginBottom: 16,
            fontSize: "13.5px",
            fontWeight: 700,
          }}
        >
          ✓ {msg}
        </div>
      )}

      {/* ── Document Ingestion Bar & Reset Demo Controls ── */}
      <div className="ingestion-control-bar">
        <div className="ent-card compact-card">
          <div className="card-header-flex">
            <h3>Document Notice Inbox &amp; Controls</h3>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span className="subtle-badge">Select sample notice or reset workspace</span>
              <button
                className="btn-ent secondary small"
                onClick={resetDemo}
                disabled={resetting}
                style={{ color: "#dc2626", borderColor: "#fecaca", background: "#fef2f2" }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M23 4v6h-6" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                {resetting ? "Resetting…" : "Reset Demo"}
              </button>
            </div>
          </div>
          <div className="samples-flex-row">
            {samples.map((s) => (
              <button
                key={s.name}
                className={`sample-pill ${starting === s.storage_path ? "starting" : ""}`}
                disabled={starting !== null}
                onClick={() => startRun(s.storage_path)}
              >
                <span>{s.name}</span>
                <span className="pill-action">{starting === s.storage_path ? "Processing…" : "Run Notice"}</span>
              </button>
            ))}
            <div className="upload-inline-wrap">
              <input type="file" ref={fileRef} accept="application/pdf" style={{ display: "none" }} onChange={upload} />
              <button className="btn-ent secondary small" onClick={() => fileRef.current?.click()}>
                Upload PDF Notice
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── System Performance Metrics Strip (6 Columns) ────────────── */}
      <MetricsStrip metrics={metrics} nav={nav} />

      {/* ── Main Module Switcher (Executive Dashboard vs Multi-Agent Cockpit) ── */}
      <div className="tab-navigation-bar">
        <div className="nav-tabs">
          <button
            className={`nav-tab-item ${activeTab === "executive" ? "active" : ""}`}
            onClick={() => setActiveTab("executive")}
          >
            Executive Intelligence Dashboard
          </button>
          <button
            className={`nav-tab-item ${activeTab === "cockpit" ? "active" : ""}`}
            onClick={() => setActiveTab("cockpit")}
          >
            Multi-Agent Execution Cockpit
          </button>
        </div>

        {selectedId && detail && (
          <div className="active-run-indicator">
            <span>Active Run:</span>
            <code className="mono">{selectedId.slice(0, 8)}</code>
            <span className={`chip ${detail.status}`} style={{ marginLeft: 6 }}>
              {detail.status.replace("_", " ")}
            </span>
          </div>
        )}
      </div>

      {/* ── MODULE 1: EXECUTIVE INTELLIGENCE DASHBOARD ──────────────────── */}
      {activeTab === "executive" && (
        <div className="module-content animate-in">
          <ExecutiveReportView run={detail} />

          {/* RAG Query Assistant Footer */}
          <div className="ent-card" style={{ marginTop: 24 }}>
            <div className="ent-card-header">
              <h2>Hybrid RAG Query &amp; Portfolio Search</h2>
              <span className="subtle-badge">Grounded RAG Intelligence</span>
            </div>
            <p className="muted" style={{ marginBottom: 12 }}>
              Ask any question across ingested capital calls, custodian feeds, LP master agreements, or risk disclosures.
            </p>
            <div style={{ display: "flex", gap: 12 }}>
              <input
                type="text"
                className="input-ent"
                placeholder='e.g. "What is our total look-through exposure to NeuroAI Inc across all funds?"'
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button className="btn-ent primary" onClick={ask} disabled={asking} style={{ minWidth: 160 }}>
                {asking ? "Searching…" : "Query RAG"}
              </button>
            </div>
            {answer && <div className="answer-box">{answer}</div>}
          </div>
        </div>
      )}

      {/* ── MODULE 2: MULTI-AGENT EXECUTION COCKPIT ─────────────────────── */}
      {activeTab === "cockpit" && (
        <div className="module-content animate-in">
          <ExecutionPanel run={detail} onChanged={onChanged} />
        </div>
      )}
    </div>
  );
}
