"use client";

import { useEffect, useState } from "react";

export default function LoadingScreen({ onComplete }: { onComplete: () => void }) {
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("Initializing Financial Intelligence Engine…");

  useEffect(() => {
    const stages = [
      { p: 20, text: "Loading institutional design system & workspace tokens…" },
      { p: 45, text: "Connecting to custodian position feeds & SEC RAG database…" },
      { p: 75, text: "Initializing multi-agent execution pipeline & deterministic gates…" },
      { p: 100, text: "Preparing Executive Dashboard…" },
    ];

    let step = 0;
    const interval = setInterval(() => {
      if (step < stages.length) {
        setProgress(stages[step].p);
        setStage(stages[step].text);
        step++;
      } else {
        clearInterval(interval);
        setTimeout(onComplete, 400);
      }
    }, 450);

    return () => clearInterval(interval);
  }, [onComplete]);

  return (
    <div className="skeleton-loading-overlay">
      <div className="loading-card">
        <div className="loading-logo-row">
          <span className="diamond-logo">◆</span>
          <span className="brand-name">AgentCapital AI</span>
        </div>

        <div className="loading-stage-text">{stage}</div>

        <div className="shimmer-progress-bar">
          <div className="shimmer-fill" style={{ width: `${progress}%` }}></div>
        </div>

        <div className="loading-sub-info">
          <span>Estimated setup time: &lt; 2s</span>
          <span className="mono">{progress}% Complete</span>
        </div>
      </div>
    </div>
  );
}
