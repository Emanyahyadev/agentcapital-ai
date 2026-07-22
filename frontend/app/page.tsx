"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE, RunDetail, RunSummary, Sample } from "@/lib/api";
import RunConsole from "@/components/RunConsole";

const TERMINAL = new Set(["completed", "failed", "rejected"]);

export default function Home() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [nav, setNav] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const list = await api<RunSummary[]>("/runs");
      setRuns(list);
      setErr(null);
      setSelectedId((cur) => cur ?? list[0]?.run_id ?? null);
    } catch (e) {
      setErr(`Backend unreachable: ${e}`);
    }
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
    api<Sample[]>("/documents/samples").then(setSamples).catch(() => {});
    api<{ position_value_usd: number }[]>("/custodian/feed")
      .then((rows) => setNav(rows.reduce((s, r) => s + r.position_value_usd, 0)))
      .catch(() => {});
    refreshRuns();
    const t = setInterval(refreshRuns, 5000);
    return () => clearInterval(t);
  }, [refreshRuns]);

  useEffect(() => {
    refreshDetail();
    const t = setInterval(() => {
      if (detail && TERMINAL.has(detail.status) && detail.run_id === selectedId) return;
      refreshDetail();
    }, 2500);
    return () => clearInterval(t);
  }, [refreshDetail, selectedId, detail]);

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

  const completed = runs.filter((r) => r.status === "completed").length;
  const awaiting = runs.filter((r) => r.status === "awaiting_approval").length;

  return (
    <>
      {err && <div className="error-box" style={{ marginBottom: 18 }}>{err}</div>}

      <div className="stats">
        <div className="stat">
          <div className="k">Portfolio NAV</div>
          <div className="v">{nav === null ? "—" : `$${(nav / 1e6).toFixed(1)}M`}</div>
        </div>
        <div className="stat">
          <div className="k">Runs completed</div>
          <div className="v">{completed}</div>
        </div>
        <div className="stat">
          <div className="k">Awaiting approval</div>
          <div className="v" style={awaiting ? { color: "var(--warn)" } : undefined}>
            {awaiting}
          </div>
        </div>
        <div className="stat">
          <div className="k">Agents</div>
          <div className="v">6 + 2 gates</div>
        </div>
      </div>

      <RunConsole
        run={detail}
        onChanged={() => {
          refreshDetail();
          refreshRuns();
        }}
      />

      <div className="grid">
        <div>
          <div className="card">
            <h2>
              Inbox<span className="hint">synthetic notices — click to process</span>
            </h2>
            {samples.length === 0 && (
              <div className="empty">No samples — run scripts/generate_pdfs.py</div>
            )}
            {samples.map((s) => (
              <div
                className="row"
                key={s.name}
                onClick={() => !starting && startRun(s.storage_path)}
              >
                <div>
                  <div className="name">{s.name}</div>
                </div>
                <button className="btn small" disabled={starting !== null}>
                  {starting === s.storage_path ? "Starting…" : "Process"}
                </button>
              </div>
            ))}
            <div
              style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}
            >
              <input type="file" ref={fileRef} accept="application/pdf" />
              <button className="btn secondary small" onClick={upload}>
                Upload &amp; run
              </button>
            </div>
          </div>

          <div className="card">
            <h2>
              Ask the book<span className="hint">hybrid RAG + live positions</span>
            </h2>
            <textarea
              rows={2}
              placeholder='e.g. "What is our total exposure to NeuroAI Inc across funds?"'
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <div style={{ marginTop: 10 }}>
              <button className="btn" onClick={ask} disabled={asking}>
                {asking ? "Thinking…" : "Ask"}
              </button>
            </div>
            {answer && <div className="answer">{answer}</div>}
          </div>
        </div>

        <div className="card">
          <h2>
            Workflow runs<span className="hint">click to inspect</span>
            <button
              className="btn secondary small"
              style={{ marginLeft: "auto" }}
              title="Clear processed documents & runs so demo scenarios can be re-run"
              onClick={async (e) => {
                e.stopPropagation();
                if (!window.confirm("Reset demo data? All runs, documents and reports will be cleared."))
                  return;
                await api("/demo/reset", { method: "POST" });
                setSelectedId(null);
                setDetail(null);
                await refreshRuns();
              }}
            >
              Reset demo
            </button>
          </h2>
          {runs.length === 0 && (
            <div className="empty">No runs yet — process a notice from the inbox.</div>
          )}
          {runs.map((r) => (
            <div
              className={`row ${r.run_id === selectedId ? "selected" : ""}`}
              key={r.run_id}
              onClick={() => {
                setSelectedId(r.run_id);
                setDetail(null);
              }}
            >
              <div>
                <div className="name">
                  {r.document?.split(/[\\/]/).pop() ?? r.run_id.slice(0, 8)}
                </div>
                <div className="meta">
                  {r.current_node ?? "—"} · {new Date(r.started_at).toLocaleTimeString()}
                </div>
              </div>
              <span className={`chip ${r.status}`}>{r.status.replace("_", " ")}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
