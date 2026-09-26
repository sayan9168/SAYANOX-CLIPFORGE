"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Scissors, Sparkles, Upload, Clock3, Play, ShieldCheck, Zap,
  Download, Loader2, Link2, Ratio, Type, Film, History, Trash2,
  RotateCcw, Archive, X, Music2, ScanFace,
} from "lucide-react";
import { Phase2Toolbar, type Aspect, type CaptionStyle } from "./components/Phase2Toolbar";
import { SocialCaption } from "./components/SocialCaption";

type DemoClip = { id: number; start: number; end: number; score: number; title: string; reason: string };
type Highlight = {
  start: number; end: number; score: number;
  title?: string; reason?: string; text?: string;
  caption?: string; hashtags?: string[]; hashtag_line?: string; post?: string;
  signals?: { hook?: number; speech?: number; emotion?: number; audio?: number; visual?: number };
};
type RenderClip = {
  file: string; start: number; end: number; duration: number; target: number;
  score: number | null; vertical: boolean; captions: boolean; bytes: number; download: string;
};
type JobStatus = {
  job_id: string; kind: string; status: "queued" | "processing" | "completed" | "failed";
  progress: number; attempts: number; max_attempts: number; error: string | null;
  result: {
    duration?: number; engine?: string; language?: string;
    transcript_segments?: number; scene_changes?: number; clips?: Highlight[] | RenderClip[];
  } | null;
};
type Phase = "idle" | "analyzing" | "ready" | "rendering" | "done" | "error";
type HistoryItem = {
  id: string; kind: "analyze" | "render" | "upload"; label: string; status: string; at: number; parent?: string;
};

const HISTORY_KEY = "clipforge-history-v1";
const MAX_HISTORY = 20;

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryItem[]) : [];
  } catch {
    return [];
  }
}
function saveHistory(items: HistoryItem[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)));
  } catch {}
}
function fmt(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.round(s % 60);
  return h > 0
    ? String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0")
    : String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [rendered, setRendered] = useState<RenderClip[]>([]);
  const [renderJob, setRenderJob] = useState("");
  const [durations, setDurations] = useState<number[]>([30]);
  const [customDur, setCustomDur] = useState("");
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>("default");
  const [aspect, setAspect] = useState<Aspect>("9:16");
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [useBgm, setUseBgm] = useState(false);
  const [faceCrop, setFaceCrop] = useState(true);
  const [platform, setPlatform] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"url" | "upload">("url");
  const [fileName, setFileName] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const analyzeJob = useRef("");
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const renderTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setHistory(loadHistory());
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
      if (renderTimer.current) clearInterval(renderTimer.current);
    };
  }, []);

  const pushHistory = useCallback((item: HistoryItem) => {
    setHistory((prev) => {
      const next = [item, ...prev.filter((h) => h.id !== item.id)].slice(0, MAX_HISTORY);
      saveHistory(next);
      return next;
    });
  }, []);

  function stopPoll(kind: "analyze" | "render") {
    const t = kind === "analyze" ? pollTimer : renderTimer;
    if (t.current) { clearInterval(t.current); t.current = null; }
  }

  function pollAnalyze(jobId: string) {
    analyzeJob.current = jobId;
    pollTimer.current = setInterval(async () => {
      try {
        const s = await fetch(`/api/jobs/status?job=${jobId}`, { cache: "no-store" });
        const j: JobStatus = await s.json();
        if (!s.ok) throw new Error((j as any)?.error || "Job lookup failed.");
        setProgress(j.progress ?? 0);
        if (j.status === "completed") {
          stopPoll("analyze");
          const clips = (j.result?.clips || []) as Highlight[];
          setHighlights(clips);
          setRendered([]);
          setNote(`Analyzed ${j.result?.duration ? fmt(j.result.duration) : "video"} • engine: ${j.result?.engine || "?"} • ${j.result?.transcript_segments ?? 0} segments`);
          setPhase(clips.length ? "ready" : "error");
          if (!clips.length) setError("No highlights found in this video.");
          pushHistory({ id: jobId, kind: "analyze", label: url || fileName || jobId.slice(0, 8), status: "completed", at: Date.now() });
        } else if (j.status === "failed") {
          stopPoll("analyze");
          setPhase("error");
          setError(j.error || "Worker job failed.");
          pushHistory({ id: jobId, kind: "analyze", label: url || fileName || jobId.slice(0, 8), status: "failed", at: Date.now() });
        }
      } catch (e) {
        stopPoll("analyze");
        setPhase("error");
        setError(e instanceof Error ? e.message : "Lost contact with the worker.");
      }
    }, 1500);
  }

  async function analyze() {
    setError(""); stopPoll("analyze"); stopPoll("render");
    setHighlights([]); setRendered([]); setNote(""); setRenderJob("");
    if (!url.trim()) { setError("Paste a YouTube URL first."); return; }
    setPhase("analyzing"); setProgress(0);
    try {
      const r = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url, min_seconds: 15, max_seconds: 90, limit: 8 }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Analysis failed.");
      if (d.mode === "demo") {
        setHighlights(d.clips.map((c: DemoClip) => ({
          start: c.start, end: c.end, score: c.score, title: c.title, reason: c.reason,
          signals: { hook: 0.8, speech: 0.75, emotion: 0.7, audio: 0.65, visual: 0.55 },
        })));
        setNote("DEMO MODE — WORKER_API_URL is not configured.");
        setPhase("ready");
        return;
      }
      pollAnalyze(d.job_id);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Analysis failed.");
    }
  }

  async function uploadFile(file: File) {
    setError(""); stopPoll("analyze"); stopPoll("render");
    setHighlights([]); setRendered([]); setNote(""); setRenderJob("");
    setFileName(file.name); setPhase("analyzing"); setProgress(0);
    try {
      const fd = new FormData();
      fd.append("video", file);
      fd.append("min_seconds", "15"); fd.append("max_seconds", "90"); fd.append("limit", "8");
      const r = await fetch("/api/jobs/upload", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || d.detail || "Upload failed.");
      pollAnalyze(d.job_id);
      pushHistory({ id: d.job_id, kind: "upload", label: file.name, status: "queued", at: Date.now() });
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Upload failed.");
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) uploadFile(f);
  }

  async function render() {
    setError(""); stopPoll("render"); setRendered([]); setPhase("rendering"); setProgress(0);
    try {
      const picks = highlights.slice(0, Math.min(4, Math.max(1, durations.length)));
      const r = await fetch("/api/jobs/render", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          parent_job: analyzeJob.current,
          highlights: picks,
          durations: durations.slice(0, picks.length),
          vertical: aspect === "9:16",
          aspect,
          captions: burnCaptions,
          caption_style: captionStyle,
          bgm: useBgm,
          duck: true,
          face_crop: faceCrop,
          platform,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || d.detail || "Render request failed.");
      setRenderJob(d.job_id);
      renderTimer.current = setInterval(async () => {
        try {
          const s = await fetch(`/api/jobs/status?job=${d.job_id}`, { cache: "no-store" });
          const j: JobStatus = await s.json();
          if (!s.ok) throw new Error((j as any)?.error || "Job lookup failed.");
          setProgress(j.progress ?? 0);
          if (j.status === "completed") {
            stopPoll("render");
            setRendered((j.result?.clips || []) as RenderClip[]);
            setPhase("done");
            pushHistory({ id: d.job_id, kind: "render", label: `Render ${picks.length} clip(s)`, status: "completed", at: Date.now(), parent: analyzeJob.current });
          } else if (j.status === "failed") {
            stopPoll("render"); setPhase("error"); setError(j.error || "Render job failed.");
          }
        } catch (e) {
          stopPoll("render"); setPhase("error");
          setError(e instanceof Error ? e.message : "Lost contact with the worker.");
        }
      }, 1500);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Render failed.");
    }
  }

  async function retryJob(id: string) {
    setError("");
    try {
      const r = await fetch(`/api/jobs/retry?job=${id}`, { method: "POST" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Retry failed.");
      setPhase("analyzing"); setProgress(0); pollAnalyze(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry failed.");
    }
  }

  async function deleteJob(id: string) {
    try {
      await fetch(`/api/jobs/delete?job=${id}`, { method: "DELETE" });
      setHistory((prev) => {
        const next = prev.filter((h) => h.id !== id);
        saveHistory(next);
        return next;
      });
    } catch {}
  }

  function addCustomDuration() {
    const n = parseInt(customDur, 10);
    if (!Number.isFinite(n) || n < 5 || n > 180) {
      setError("Custom duration must be 5–180 seconds.");
      return;
    }
    setError("");
    setDurations((v) => (v.includes(n) ? v : [...v, n].sort((a, b) => a - b)));
    setCustomDur("");
  }

  const busy = phase === "analyzing" || phase === "rendering";
  const clipSrc = (c: RenderClip) => `/api/jobs/files?job=${renderJob}&path=${encodeURIComponent("clips/" + c.file)}`;
  const zipHref = renderJob ? `/api/jobs/zip?job=${renderJob}` : "";

  return (
    <main>
      <nav>
        <div className="brand"><Scissors size={18} /> SAYANOX <span>CLIPFORGE</span></div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button type="button" className="tab" onClick={() => setShowHistory((v) => !v)}><History size={13} /> History</button>
          <div className="status"><i /> v0.8 • Phase 2</div>
        </div>
      </nav>

      {showHistory && (
        <div className="historyPanel">
          <div className="resultHead">
            <h2 style={{ fontSize: 18, margin: 0 }}>Recent jobs</h2>
            <button type="button" className="chip" onClick={() => setShowHistory(false)}><X size={12} /> Close</button>
          </div>
          {history.length === 0 && <p className="hint">No jobs yet.</p>}
          <ul className="historyList">
            {history.map((h) => (
              <li key={h.id + h.at}>
                <div><b>{h.label}</b><small>{h.kind} · {h.status} · {new Date(h.at).toLocaleString()}</small></div>
                <div className="historyActions">
                  {(h.status === "failed" || h.status === "queued") && (
                    <button type="button" className="chip" onClick={() => retryJob(h.id)} disabled={busy}><RotateCcw size={12} /> Retry</button>
                  )}
                  <button type="button" className="chip" onClick={() => deleteJob(h.id)}><Trash2 size={12} /> Delete</button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <section className="hero">
        <div className="eyebrow"><Sparkles size={14} /> AI VIDEO HIGHLIGHT ENGINE</div>
        <h1>Turn long videos into<br /><em>great clips.</em></h1>
        <p className="sub">Paste a URL or drop a file. Transcribe → score → render with platform presets, captions &amp; optional BGM.</p>

        <div className="panel">
          <div className="tabs">
            <button type="button" className={mode === "url" ? "tab on" : "tab"} onClick={() => setMode("url")} disabled={busy}><Link2 size={13} /> YouTube URL</button>
            <button type="button" className={mode === "upload" ? "tab on" : "tab"} onClick={() => setMode("upload")} disabled={busy}><Upload size={13} /> Upload file</button>
          </div>
          {mode === "url" ? (
            <div className="inputRow">
              <Link2 size={16} />
              <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !busy && analyze()} placeholder="Paste a YouTube video URL…" disabled={busy} />
              <button onClick={analyze} disabled={busy}>{busy ? <><Loader2 className="spin" size={14} /> Working</> : <><Play size={14} /> Find clips</>}</button>
            </div>
          ) : (
            <div className={`dropzone${dragOver ? " over" : ""}`} onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={onDrop} onClick={() => fileRef.current?.click()}>
              <Upload size={22} />
              <div><b>{fileName || "Drop video here or click to browse"}</b><small>MP4, MOV, MKV, WebM · requires WORKER_API_URL</small></div>
              <input ref={fileRef} type="file" accept="video/*,audio/*" hidden disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f); }} />
            </div>
          )}
          {error && <div className="error">{error}</div>}
          {busy && (
            <div className="progressWrap">
              <div className="progressBar" style={{ width: `${progress}%` }} />
              <span>{phase === "analyzing" ? "Analyzing" : "Rendering"}… {progress}%</span>
            </div>
          )}
          <div className="hint"><ShieldCheck size={13} /> Only process videos you own or have permission to use.</div>
        </div>

        <div className="features">
          <div><Zap size={18} /><b>Smart scoring</b><small>Hook, density, speech, emotion, audio &amp; scene signals</small></div>
          <div><Clock3 size={18} /><b>Platform presets</b><small>TikTok · Reels · Shorts · Square + custom 5–180s</small></div>
          <div><Film size={18} /><b>EN caption + tags</b><small>Copy-ready English post with hashtags</small></div>
        </div>

        {(phase === "ready" || phase === "rendering" || phase === "done") && highlights.length > 0 && (
          <div className="results">
            <div className="resultHead">
              <div><span className="eyebrow">RESULTS</span><h2>Suggested clips</h2></div>
              <span>{highlights.length} highlights</span>
            </div>
            {note && <div className="note">{note}</div>}
            <Phase2Toolbar
              busy={busy}
              platform={platform}
              setPlatform={setPlatform}
              aspect={aspect}
              setAspect={setAspect}
              durations={durations}
              setDurations={setDurations}
              customDur={customDur}
              setCustomDur={setCustomDur}
              addCustomDuration={addCustomDuration}
              captionStyle={captionStyle}
              setCaptionStyle={setCaptionStyle}
              burnCaptions={burnCaptions}
              setBurnCaptions={setBurnCaptions}
              useBgm={useBgm}
              setUseBgm={setUseBgm}
              faceCrop={faceCrop}
              setFaceCrop={setFaceCrop}
              onRender={render}
              highlightCount={highlights.length}
            />
            {highlights.map((c, i) => (
              <article className="clip" key={i}>
                <div className="thumb"><Play size={22} /><small>{fmt(c.start)} — {fmt(c.end)}</small></div>
                <div className="clipBody">
                  <div className="clipTitle"><h3>{c.title || `Highlight #${i + 1}`}</h3><strong>{Math.round(c.score)}/100</strong></div>
                  <p>{c.reason || c.text || ""}</p>
                  <code>{fmt(c.start)} → {fmt(c.end)} ({fmt(c.end - c.start)})</code>
                  {c.signals && (
                    <div className="signals">
                      {Object.entries(c.signals).map(([k, v]) =>
                        v != null ? <span className="sig" key={k}>{k}<strong>{Math.round(Number(v) * 100)}</strong></span> : null,
                      )}
                    </div>
                  )}
                  <SocialCaption pack={c} title={c.title} text={c.text} platform={platform} />
                </div>
              </article>
            ))}
          </div>
        )}

        {rendered.length > 0 && (
          <div className="results">
            <div className="resultHead">
              <div><span className="eyebrow">GENERATED CLIPS</span><h2>Ready to preview &amp; download</h2></div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span>{rendered.length} MP4s</span>
                {zipHref && <a href={zipHref} className="dl" download><Archive size={13} /> Download ZIP</a>}
              </div>
            </div>
            <div className="grid">
              {rendered.map((c) => (
                <article className="genClip" key={c.file}>
                  <video controls preload="metadata" playsInline src={clipSrc(c)} />
                  <div className="genMeta">
                    <b>{c.file.replace(".mp4", "")}</b>
                    <small>{fmt(c.start)} → {fmt(c.end)} · {c.duration}s · {(c.bytes / 1048576).toFixed(1)} MB</small>
                    <div className="genActions">
                      <a href={clipSrc(c)} download={c.file} className="dl"><Download size={13} /> Download</a>
                      <a href={clipSrc(c)} target="_blank" rel="noreferrer" className="dl ghost">Open</a>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
      <footer>SAYANOX CLIPFORGE · Built for creators · v0.8.0 Phase 2</footer>
    </main>
  );
}
