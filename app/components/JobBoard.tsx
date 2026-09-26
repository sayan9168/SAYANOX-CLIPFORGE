"use client";
import { useEffect, useState } from "react";

type Job = { id: string; kind: string; status: string; progress?: number; error?: string | null };

export function JobBoard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState("");
  async function load() {
    setErr("");
    try {
      const r = await fetch("/api/jobs/list", { cache: "no-store" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || d.detail || "Worker job list unavailable.");
      setJobs(d.jobs || d || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not sync jobs.");
    }
  }
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  return (
    <div className="historyPanel">
      <div className="resultHead">
        <h2 style={{ fontSize: 18, margin: 0 }}>Worker jobs</h2>
        <button type="button" className="chip" onClick={load}>Refresh</button>
      </div>
      {err && <p className="hint">{err}</p>}
      {!err && jobs.length === 0 && <p className="hint">No jobs on the worker yet.</p>}
      <ul className="historyList">
        {jobs.map((j) => (
          <li key={j.id}>
            <div><b>{j.kind} · {j.id.slice(0, 8)}</b><small>{j.status} · {j.progress ?? 0}%</small></div>
            {j.error && <small>{j.error}</small>}
          </li>
        ))}
      </ul>
    </div>
  );
}
