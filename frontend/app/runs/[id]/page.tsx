"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, RunDetail } from "@/lib/api";
import RunConsole from "@/components/RunConsole";

const TERMINAL = new Set(["completed", "failed", "rejected"]);

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<RunDetail | null>(null);
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
    }, 2500);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <>
      <p style={{ marginBottom: 14 }}>
        <Link href="/" style={{ color: "var(--muted)" }}>← back to console</Link>
      </p>
      {err && <div className="error-box" style={{ marginBottom: 18 }}>{err}</div>}
      <RunConsole run={run} onChanged={refresh} />
    </>
  );
}
