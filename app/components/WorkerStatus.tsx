"use client";
import { useEffect, useRef, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { requestJson } from "../../lib/api";
import type { WorkerHealth } from "../../lib/types";

export function WorkerStatus({ onHealth }: { onHealth?: (health: WorkerHealth) => void }) {
  const [health, setHealth] = useState<WorkerHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const callback = useRef(onHealth);
  useEffect(() => { callback.current = onHealth; });
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      setLoading(true);
      try {
        const data = await requestJson<{ worker: WorkerHealth }>("/api/health", { signal: controller.signal }, 10_000);
        if (controller.signal.aborted) return;
        setHealth(data.worker);
        callback.current?.(data.worker);
      } catch (error) {
        if (controller.signal.aborted) return;
        const offline = { configured: true, reachable: false, error: error instanceof Error ? error.message : "Health check failed." };
        setHealth(offline);
        callback.current?.(offline);
      } finally { if (!controller.signal.aborted) setLoading(false); }
      if (!controller.signal.aborted) timer = setTimeout(load, 30_000);
    }
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [revision]);
  const ready = health?.reachable && health.ready;
  const label = !health ? "Checking worker" : !health.configured ? "Worker not configured" : !health.reachable ? "Worker offline" : !health.ready ? health.error ? "Worker needs attention" : "Media tools missing" : "Worker online";
  return <div className="workerPanel">
    <details>
      <summary><span className={`healthDot${ready ? " healthy" : ""}`} /><b>{label}</b>
        <span className="healthSummary">{ready ? `${health.queue_jobs ?? 0} active · ${health.whisper_engine || "unknown engine"}` : "Setup & diagnostics"}</span>
        <Activity size={14} />
      </summary>
      <div className="healthDetails">
        {!health?.configured && <p>Set <code>WORKER_API_URL</code> on the web server and start the FastAPI worker. No demo results are generated.</p>}
        {health?.error && <p className="error" role="alert">{health.error}</p>}
        {health?.reachable && <>
          <div className="diagnosticGrid">
            <span>FFmpeg <b>{health.ffmpeg ? "Available" : "Missing"}</b></span>
            <span>FFprobe <b>{health.ffprobe ? "Available" : "Missing"}</b></span>
            <span>YouTube <b>{health.youtube_enabled && health.yt_dlp ? "Enabled" : "Disabled / unavailable"}</b></span>
            <span>Upload limit <b>{health.max_upload_mb ?? "—"} MB</b></span>
            <span>Storage <b>{((health.storage_bytes ?? 0) / 1024 ** 3).toFixed(2)} / {((health.max_storage_bytes ?? 0) / 1024 ** 3).toFixed(0)} GB</b></span>
            <span>Version <b>{health.version || "—"}</b></span>
          </div>
          {health.whisper_engine === "energy-fallback" && <p className="warning">Whisper is not installed. Attach an SRT file for real captions, or use timeline-based highlights without speech subtitles.</p>}
        </>}
      </div>
    </details>
    <button type="button" className="chip" disabled={loading} onClick={() => setRevision((value) => value + 1)} aria-label="Refresh worker status"><RefreshCw size={13} className={loading ? "spin" : ""} /></button>
  </div>;
}
