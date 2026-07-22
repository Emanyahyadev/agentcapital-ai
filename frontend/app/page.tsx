"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE, RunSummary, Sample } from "@/lib/api";

export default function Home() {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [starting, setStarting] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setRuns(await api<RunSummary[]>("/runs"));
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    api<Sample[]>("/documents/samples").then(setSamples).catch(() => {});
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  async function startRun(storage_path: string) {
    setStarting(storage_path);
    try {
      await api("/runs", {
        method: "POST",
        body: JSON.stringify({ storage_path }),
      });
      await refresh();
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
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      setErr(await res.text());
      return;
    }
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

  return (
    <>
      {err && <div className="error-box" style={{ marginBottom: 18 }}>{err}</div>}
      <div className="grid">
        <div>
          <div className="card">
            <h2>
              Inbox<span className="hint">synthetic notices — click to process</span>
            </h2>
            {samples.length === 0 && (
              <p className="muted">
                No samples found — run <code>scripts/generate_pdfs.py</code> on the backend.
              </p>
            )}
            {samples.map((s) => (
              <div className="row" key={s.name}>
                <span className="name">{s.name}</span>
                <button
                  className="btn"
                  disabled={starting !== null}
                  onClick={() => startRun(s.storage_path)}
                >
                  {starting === s.storage_path ? "Starting…" : "Process"}
                </button>
              </div>
            ))}
            <div className="row" style={{ marginTop: 6 }}>
              <input type="file" ref={fileRef} accept="application/pdf" />
              <button className="btn secondary" onClick={upload}>Upload &amp; run</button>
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
            Workflow runs<span className="hint">auto-refreshes</span>
          </h2>
          {runs.length === 0 && <p className="muted">No runs yet.</p>}
          {runs.map((r) => (
            <Link href={`/runs/${r.run_id}`} key={r.run_id} style={{ color: "inherit" }}>
              <div className="row">
                <div>
                  <div className="name">
                    {r.document?.split(/[\\/]/).pop() ?? r.run_id.slice(0, 8)}
                  </div>
                  <div className="muted">
                    {r.current_node ?? "—"} · {new Date(r.started_at).toLocaleTimeString()}
                  </div>
                </div>
                <span className={`chip ${r.status}`}>{r.status.replace("_", " ")}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
