"use client";
import { useEffect, useRef, useState } from "react";
import {
  Scissors, Sparkles, Upload, Clock3, Play, ShieldCheck, Zap,
  Download, Loader2, Link2, Ratio, Type, Film,
} from "lucide-react";

type DemoClip = { id: number; start: number; end: number; score: number; title: string; reason: string };
type Highlight = {
  start: number; end: number; score: number;
  title?: string; reason?: string; text?: string;
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
type CaptionStyle = "default" | "karaoke" | "clean" | "bold";
type Aspect = "9:16" | "1:1" | "16:9";

const demo: DemoClip[] = [
  { id: 1, start: 873, end: 907, score: 92, title: "The strongest moment", reason: "Clear hook, complete thought and high information density." },
  { id: 2, start: 1142, end: 1175, score: 88, title: "Key insight", reason: "Self-contained statement with a natural ending." },
  { id: 3, start: 1540, end: 1571, score: 84, title: "Best reaction", reason: "Strong emotional/audio peak and clean context." },
];

function fmt(s: number) {
  const h = Math.floor(s / 3600),
    m = Math.floor((s % 3600) / 60),
    sec = Math.round(s % 60);
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
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>("default");
  const [aspect, setAspect] = useState<Aspect>("9:16");
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"url" | "upload">("url");
  const analyzeJob = useRef("");
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const renderTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
      if (renderTimer.current) clearInterval(renderTimer.current);
    },
    [],
  );

  function stopPoll(kind: "analyze" | "render") {
    const t = kind === "analyze" ? pollTimer : renderTimer;
    if (t.current) {
      clearInterval(t.current);
      t.current = null;
    }
  }

  async function analyze() {
    setError("");
    stopPoll("analyze");
    stopPoll("render");
    setHighlights([]);
    setRendered([]);
    setNote("");
    setRenderJob("");
    if (!url.trim()) {
      setError("Paste a YouTube URL first.");
      return;
    }
    setPhase("analyzing");
    setProgress(0);
    try {
      const r = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url, min_seconds: 15, max_seconds: 90, limit: 8 }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Analysis failed.");
      if (d.mode === "demo") {
        setHighlights(
          d.clips.map((c: DemoClip) => ({
            start: c.start,
            end: c.end,
            score: c.score,
            title: c.title,
            reason: c.reason,
            signals: { hook: 0.8, speech: 0.75, emotion: 0.7, audio: 0.65, visual: 0.55 },
          })),
        );
        setNote("DEMO MODE — WORKER_API_URL is not configured. Results below are sample data, not real analysis.");
        setPhase("ready");
        return;
      }
      analyzeJob.current = d.job_id;
      pollTimer.current = setInterval(async () => {
        try {
          const s = await fetch(`/api/jobs/status?job=${analyzeJob.current}`, { cache: "no-store" });
          const j: JobStatus = await s.json();
          if (!s.ok) throw new Error((j as any)?.error || "Job lookup failed.");
          setProgress(j.progress ?? 0);
          if (j.status === "completed") {
            stopPoll("analyze");
            const clips = (j.result?.clips || []) as Highlight[];
            setHighlights(clips);
            setRendered([]);
            setNote(
              `Analyzed ${j.result?.duration ? fmt(j.result.duration) : "video"} • engine: ${j.result?.engine || "?"} • ${j.result?.transcript_segments ?? 0} transcript segments • ${j.result?.scene_changes ?? 0} scene changes`,
            );
            setPhase(clips.length ? "ready" : "error");
            if (!clips.length) setError("No highlights found in this video.");
          } else if (j.status === "failed") {
            stopPoll("analyze");
            setPhase("error");
            setError(j.error || "Worker job failed.");
          }
        } catch (e) {
          stopPoll("analyze");
          setPhase("error");
          setError(e instanceof Error ? e.message : "Lost contact with the worker.");
        }
      }, 1500);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Analysis failed.");
    }
  }

  async function render() {
    setError("");
    stopPoll("render");
    setRendered([]);
    setPhase("rendering");
    setProgress(0);
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
          } else if (j.status === "failed") {
            stopPoll("render");
            setPhase("error");
            setError(j.error || "Render job failed.");
          }
        } catch (e) {
          stopPoll("render");
          setPhase("error");
          setError(e instanceof Error ? e.message : "Lost contact with the worker.");
        }
      }, 1500);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Render failed.");
    }
  }

  const busy = phase === "analyzing" || phase === "rendering";
  const clipSrc = (c: RenderClip) =>
    `/api/jobs/files?job=${renderJob}&path=${encodeURIComponent("clips/" + c.file)}`;

  return (
    <main>
      <nav>
        <div className="brand">
          <Scissors size={18} />
          SAYANOX <span>CLIPFORGE</span>
        </div>
        <div className="status">
          <i />
          v0.6 • Whisper + FFmpeg • Real pipeline
        </div>
      </nav>

      <section className="hero">
        <div className="eyebrow">
          <Sparkles size={14} /> AI VIDEO HIGHLIGHT ENGINE
        </div>
        <h1>
          Turn long videos into
          <br />
          <em>great clips.</em>
        </h1>
        <p className="sub">
          Paste a video URL. ClipForge queues a real worker job: download → Whisper transcription →
          audio &amp; scene analysis → highlight scoring → rendered clips you can preview and download.
        </p>

        <div className="panel">
          <div className="tabs">
            <button type="button" className={mode === "url" ? "tab on" : "tab"} onClick={() => setMode("url")} disabled={busy}>
              <Link2 size={13} /> YouTube URL
            </button>
            <button type="button" className={mode === "upload" ? "tab on" : "tab"} onClick={() => setMode("upload")} disabled={busy}>
              <Upload size={13} /> Upload file
            </button>
          </div>

          {mode === "url" ? (
            <div className="inputRow">
              <Link2 size={16} />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !busy && analyze()}
                placeholder="Paste a YouTube video URL…"
                disabled={busy}
              />
              <button onClick={analyze} disabled={busy}>
                {busy ? (
                  <>
                    <Loader2 className="spin" size={14} /> Working
                  </>
                ) : (
                  <>
                    <Play size={14} /> Find clips
                  </>
                )}
              </button>
            </div>
          ) : (
            <div className="inputRow">
              <Upload size={16} />
              <input
                type="text"
                readOnly
                value="File upload via worker /jobs/upload — connect WORKER_API_URL and use API or future drag-drop"
                disabled
              />
              <button disabled title="Use worker upload endpoint for now">
                Coming soon
              </button>
            </div>
          )}

          {error && <div className="error">{error}</div>}
          {busy && (
            <div className="progressWrap">
              <div className="progressBar" style={{ width: `${progress}%` }} />
              <span>
                {phase === "analyzing" ? "Analyzing" : "Rendering"}… {progress}%
              </span>
            </div>
          )}
          <div className="hint">
            <ShieldCheck size={13} /> Only process videos you own or have permission to use.
          </div>
        </div>

        <div className="features">
          <div>
            <Zap size={18} />
            <b>Smart scoring</b>
            <small>Hook, density, speech, emotion, audio &amp; scene signals + auto titles</small>
          </div>
          <div>
            <Clock3 size={18} />
            <b>15–90 sec</b>
            <small>Pick lengths that fit Shorts, Reels, TikTok or YouTube</small>
          </div>
          <div>
            <Film size={18} />
            <b>Real MP4 clips</b>
            <small>FFmpeg render · vertical crop · burned captions · download</small>
          </div>
        </div>

        {(phase === "ready" || phase === "rendering" || phase === "done") && highlights.length > 0 && (
          <div className="results">
            <div className="resultHead">
              <div>
                <span className="eyebrow">RESULTS</span>
                <h2>Suggested clips</h2>
              </div>
              <span>{highlights.length} highlights</span>
            </div>
            {note && <div className="note">{note}</div>}

            <div className="toolbar">
              <span className="durPick">
                <Clock3 size={13} /> Length
              </span>
              {[15, 30, 60, 90].map((d) => (
                <button
                  key={d}
                  type="button"
                  className={durations.includes(d) ? "chip on" : "chip"}
                  disabled={busy}
                  onClick={() =>
                    setDurations((v) =>
                      v.includes(d) ? v.filter((x) => x !== d) : [...v, d].sort((a, b) => a - b),
                    )
                  }
                >
                  {d}s
                </button>
              ))}

              <span className="optLabel" style={{ marginLeft: 8 }}>
                <Ratio size={13} /> Aspect
              </span>
              {(["9:16", "1:1", "16:9"] as Aspect[]).map((a) => (
                <button
                  key={a}
                  type="button"
                  className={aspect === a ? "chip on" : "chip"}
                  disabled={busy}
                  onClick={() => setAspect(a)}
                >
                  {a}
                </button>
              ))}

              <span className="optLabel" style={{ marginLeft: 8 }}>
                <Type size={13} /> Captions
              </span>
              {(["default", "karaoke", "clean", "bold"] as CaptionStyle[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={captionStyle === s && burnCaptions ? "chip on" : "chip"}
                  disabled={busy}
                  onClick={() => {
                    setBurnCaptions(true);
                    setCaptionStyle(s);
                  }}
                >
                  {s}
                </button>
              ))}
              <button
                type="button"
                className={!burnCaptions ? "chip on" : "chip"}
                disabled={busy}
                onClick={() => setBurnCaptions(false)}
              >
                off
              </button>

              <button
                className="renderBtn"
                onClick={render}
                disabled={busy || !durations.length}
                style={{ marginLeft: "auto" }}
              >
                <Play size={13} /> Render {Math.max(1, Math.min(highlights.length, durations.length || 1))} clip(s)
              </button>
            </div>

            {highlights.map((c, i) => (
              <article className="clip" key={i}>
                <div className="thumb">
                  <Play size={22} />
                  <small>
                    {fmt(c.start)} — {fmt(c.end)}
                  </small>
                </div>
                <div className="clipBody">
                  <div className="clipTitle">
                    <h3>{c.title || `Highlight #${i + 1}`}</h3>
                    <strong>{Math.round(c.score)}/100</strong>
                  </div>
                  <p>{c.reason || c.text || ""}</p>
                  <code>
                    {fmt(c.start)} → {fmt(c.end)} ({fmt(c.end - c.start)})
                  </code>
                  {c.signals && (
                    <div className="signals">
                      {Object.entries(c.signals).map(([k, v]) =>
                        v != null ? (
                          <span className="sig" key={k}>
                            {k}
                            <strong>{Math.round(Number(v) * 100)}</strong>
                          </span>
                        ) : null,
                      )}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}

        {rendered.length > 0 && (
          <div className="results">
            <div className="resultHead">
              <div>
                <span className="eyebrow">GENERATED CLIPS</span>
                <h2>Ready to preview &amp; download</h2>
              </div>
              <span>{rendered.length} MP4s</span>
            </div>
            <div className="grid">
              {rendered.map((c) => (
                <article className="genClip" key={c.file}>
                  <video controls preload="metadata" playsInline src={clipSrc(c)} />
                  <div className="genMeta">
                    <b>{c.file.replace(".mp4", "")}</b>
                    <small>
                      {fmt(c.start)} → {fmt(c.end)} • {c.duration}s • {c.vertical ? "9:16" : "16:9"} •{" "}
                      {c.captions ? "captions" : "no captions"} • {(c.bytes / 1048576).toFixed(1)} MB
                    </small>
                    <div className="genActions">
                      <a href={clipSrc(c)} download={c.file} className="dl">
                        <Download size={13} /> Download
                      </a>
                      <a href={clipSrc(c)} target="_blank" rel="noreferrer" className="dl ghost">
                        Open
                      </a>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            <div className="hint">Generated clips stay available until the worker storage TTL removes the job.</div>
          </div>
        )}
      </section>

      <footer>SAYANOX CLIPFORGE • Built for creators • v0.6.0</footer>
    </main>
  );
}
