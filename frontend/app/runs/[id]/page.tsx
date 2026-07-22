"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, RunDetail } from "@/lib/api";
import {
  ActivityCard,
  BriefingPanel,
  GatePanel,
  InspectRow,
} from "@/components/RunConsole";
import { currentStage } from "@/lib/pipeline";

const TERMINAL = new Set(["completed", "failed", "rejected"]);

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
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

  const inspecting = picked ?? currentStage(run);

  return (
    <>
      <p style={{ marginBottom: 14 }}>
        <Link href="/" style={{ color: "var(--muted)" }}>← back to console</Link>
      </p>
      {err && <div className="error-box" style={{ marginBottom: 18 }}>{err}</div>}
      <ActivityCard run={run} inspecting={inspecting} onSelect={setPicked} />
      <GatePanel run={run} onChanged={refresh} />
      <InspectRow run={run} inspecting={inspecting} onSelect={setPicked} />
      <BriefingPanel run={run} auditOpen />
    </>
  );
}
