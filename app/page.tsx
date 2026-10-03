"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, Download, Film, Link2, Loader2, Play, RotateCcw, Save, ShieldCheck, Sparkles, Square, Trash2, Upload, X, Zap } from "lucide-react";
import { ApiError, requestJson, uploadMedia } from "../lib/api";
import { analysisOptions, DEFAULT_ANALYSIS, validateUpload, youtubeUrls, type AnalysisOptions } from "../lib/validation";
import { DEFAULT_RENDER, TERMINAL_STATES, type EditorState, type Highlight, type JobResult, type JobStatus, type Project, type RenderClip, type RenderSettings, type Trim, type WorkerHealth } from "../lib/types";
import { DRAFT_KEY, HISTORY_KEY, SETTINGS_KEY, VALID_ID, WORKSPACE_KEY, editorState, formatTime, historyItems, loadWorkspace, readStorage, renderSettings, writeStorage, type Draft, type HistoryItem } from "../lib/storage";
import { ClipPicker } from "./components/ClipPicker";
import { Phase2Toolbar } from "./components/Phase2Toolbar";
import { SiteNav } from "./components/SiteNav";
import { WorkerStatus } from "./components/WorkerStatus";
import { useJobPolling } from "./components/useJobPolling";

type Phase = "idle" | "uploading" | "analyzing" | "ready" | "rendering" | "done";
type CreatedJob = { job_id: string; jobs?: { url: string; job_id?: string; error?: string }[] };

export default function Home() {
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"url" | "upload">("url");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [analysisJobId, setAnalysisJobId] = useState("");
  const [analysisResult, setAnalysisResult] = useState<JobResult | null>(null);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [selected, setSelected] = useState<boolean[]>([]);
  const [trims, setTrims] = useState<Trim[]>([]);
  const [rendered, setRendered] = useState<RenderClip[]>([]);
  const [renderJobId, setRenderJobId] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [currentJob, setCurrentJob] = useState<JobStatus | null>(null);
  const [settings, setSettings] = useState<RenderSettings>({ ...DEFAULT_RENDER, durations: [30] });
  const [analysis, setAnalysis] = useState<AnalysisOptions>({ ...DEFAULT_ANALYSIS });
  const [health, setHealth] = useState<WorkerHealth | null>(null);
  const [fileName, setFileName] = useState("");
  const [sidecar, setSidecar] = useState<File | null>(null);
  const [bgmFile, setBgmFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("My clip project");
  const [projectNotes, setProjectNotes] = useState("");
  const [workspace, setWorkspace] = useState("local");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const submitLock = useRef(false);
  const uploadController = useRef<AbortController | null>(null);
  const youtubeUnavailable = health?.reachable && (health.youtube_enabled === false || health.yt_dlp === false);
  const busy = restoring || actionBusy || ["uploading", "analyzing", "rendering"].includes(phase);

  const pushHistory = useCallback((item: HistoryItem) => {
    setHistory((previous) => {
      const next = [item, ...previous.filter((entry) => entry.id !== item.id)].slice(0, 30);
      writeStorage(HISTORY_KEY, next);
      return next;
    });
  }, []);
  const remember = useCallback((job: JobStatus) => pushHistory({ id: job.job_id, kind: job.kind, label: job.label || `${job.kind} ${job.job_id.slice(0, 8)}`, status: job.status, at: Date.now(), parent: job.parent_job }), [pushHistory]);
  const applyAnalysis = useCallback((job: JobStatus, editor?: EditorState) => {
    const clips = (job.result?.clips || []) as Highlight[];
    const saved = editorState(editor, clips.length);
    const duration = job.result?.duration || Infinity;
    const validSaved = saved?.trims.every((trim) => trim.end <= duration + 0.1) ? saved : undefined;
    setAnalysisJobId(job.job_id);
    setAnalysisResult(job.result);
    setHighlights(clips);
    setSelected(validSaved?.selected || clips.map(() => true));
    setTrims(validSaved?.trims || clips.map((clip) => ({ start: clip.start, end: clip.end })));
  }, []);

  const handleUpdate = useCallback((job: JobStatus) => {
    setCurrentJob(job);
    setProgress(job.progress || 0);
    setStage(job.stage || job.status);
    if (!TERMINAL_STATES.includes(job.status)) return;
    setActiveId(null);
    remember(job);
    if (job.status === "completed") {
      setError("");
      if (job.kind === "analyze") { applyAnalysis(job); setPhase("ready"); }
      else { setRenderJobId(job.job_id); setRendered((job.result?.clips || []) as RenderClip[]); setPhase("done"); }
    } else if (job.status === "failed") {
      setPhase("ready");
      setError(job.error || "Worker job failed. Review its status and retry.");
    } else {
      setPhase("ready");
      setMessage("Job cancelled safely. You can retry it or start a new one.");
    }
  }, [applyAnalysis, remember]);
  const fatal = useCallback((text: string) => { setActiveId(null); setPhase("ready"); setError(text); }, []);
  const polling = useJobPolling(activeId, handleUpdate, fatal);

  const openJob = useCallback(async (id: string, editor?: EditorState, signal?: AbortSignal) => {
    if (!VALID_ID.test(id)) throw new Error("Invalid job ID.");
    setActiveId(null);
    setRestoring(true);
    setError("");
    try {
      const job = await requestJson<JobStatus>(`/api/jobs/status?job=${id}`, { signal });
      if (signal?.aborted) return;
      if (job.kind === "render") {
        if (job.parent_job) {
          try {
            const parent = await requestJson<JobStatus>(`/api/jobs/status?job=${job.parent_job}`, { signal });
            if (signal?.aborted) return;
            applyAnalysis(parent, editor);
          } catch (failure) {
            if (signal?.aborted) return;
            setAnalysisJobId(""); setAnalysisResult(null); setHighlights([]); setSelected([]); setTrims([]);
            setMessage(failure instanceof Error ? `Source analysis unavailable: ${failure.message} Render outputs can still be opened.` : "Source analysis is unavailable.");
          }
        } else { setAnalysisJobId(""); setAnalysisResult(null); setHighlights([]); setSelected([]); setTrims([]); }
        setRenderJobId(id);
        setRendered(job.status === "completed" ? (job.result?.clips || []) as RenderClip[] : []);
      } else {
        applyAnalysis(job, editor);
        setRenderJobId(""); setRendered([]);
      }
      setCurrentJob(job); setProgress(job.progress || 0); setStage(job.stage || job.status); remember(job);
      if (TERMINAL_STATES.includes(job.status)) {
        setPhase(job.status === "completed" ? job.kind === "render" ? "done" : "ready" : "ready");
        if (job.status === "failed") setError(job.error || "This job failed. You can retry it.");
        if (job.status === "cancelled") setMessage("This job was cancelled. Retry it when ready.");
      } else { setPhase(job.kind === "render" ? "rendering" : "analyzing"); setActiveId(id); }
    } finally { if (!signal?.aborted) setRestoring(false); }
  }, [applyAnalysis, remember]);

  useEffect(() => {
    const controller = new AbortController();
    async function restore() {
      setHistory(historyItems(readStorage(HISTORY_KEY)));
      const saved = readStorage(SETTINGS_KEY) as { render?: unknown; analysis?: Record<string, unknown> } | null;
      setSettings(renderSettings(saved?.render));
      try { setAnalysis(analysisOptions(saved?.analysis || {})); } catch { setAnalysis({ ...DEFAULT_ANALYSIS }); }
      const key = loadWorkspace();
      setWorkspace(key);
      const query = new URLSearchParams(window.location.search);
      try {
        if (query.has("project")) {
          const id = query.get("project") || "";
          if (!VALID_ID.test(id)) throw new Error("Invalid project ID.");
          const project = await requestJson<Project>(`/api/projects?id=${id}`, { headers: { "x-clipforge-user": key }, signal: controller.signal });
          if (controller.signal.aborted) return;
          setProjectId(project.id); setProjectName(project.name); setProjectNotes(project.notes || ""); setUrl(project.url || "");
          setSettings(renderSettings(project.settings));
          try { setAnalysis(analysisOptions({ ...project.analysis })); } catch { setAnalysis({ ...DEFAULT_ANALYSIS }); }
          const job = project.render_job_id || project.job_id;
          if (job) await openJob(job, project.editor, controller.signal);
          else setMessage("Project opened. Add a source video to begin.");
        } else if (query.has("job")) {
          await openJob(query.get("job") || "", undefined, controller.signal);
        } else {
          const draft = readStorage(DRAFT_KEY) as Draft | null;
          if (draft?.version === 2 && typeof draft.jobId === "string" && VALID_ID.test(draft.jobId)) {
            if (typeof draft.projectId === "string" && VALID_ID.test(draft.projectId)) setProjectId(draft.projectId);
            if (typeof draft.projectName === "string") setProjectName(draft.projectName.slice(0, 80));
            if (typeof draft.projectNotes === "string") setProjectNotes(draft.projectNotes.slice(0, 4000));
            if (typeof draft.workspace === "string" && VALID_ID.test(draft.workspace)) setWorkspace(draft.workspace);
            if (typeof draft.url === "string") setUrl(draft.url.slice(0, 10496));
            if (typeof draft.fileName === "string") setFileName(draft.fileName.slice(0, 255));
            if (draft.mode === "url" || draft.mode === "upload") setMode(draft.mode);
            await openJob(draft.jobId, draft, controller.signal);
          }
        }
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Could not restore the studio.");
      } finally {
        if (!controller.signal.aborted) { setRestoring(false); setInitialized(true); }
      }
    }
    void restore();
    return () => { controller.abort(); uploadController.current?.abort(); };
  }, [openJob]);

  useEffect(() => {
    if (!initialized) return;
    writeStorage(SETTINGS_KEY, { render: settings, analysis });
    if (VALID_ID.test(workspace)) writeStorage(WORKSPACE_KEY, workspace);
  }, [initialized, settings, analysis, workspace]);
  useEffect(() => {
    if (!initialized || restoring || !currentJob) return;
    writeStorage(DRAFT_KEY, { version: 2, jobId: currentJob.job_id, analysisJobId, renderJobId, selected, trims, projectId, projectName, projectNotes, workspace, url, mode, fileName } satisfies Draft);
  }, [initialized, restoring, currentJob, analysisJobId, renderJobId, selected, trims, projectId, projectName, projectNotes, workspace, url, mode, fileName]);

  function resetSource() {
    setError(""); setMessage(""); setActiveId(null); setCurrentJob(null); setAnalysisJobId(""); setAnalysisResult(null);
    setHighlights([]); setSelected([]); setTrims([]); setRendered([]); setRenderJobId(""); setProjectId(""); setProgress(0);
  }
  async function analyze() {
    if (busy || submitLock.current) return;
    if (youtubeUnavailable) { setError("YouTube ingestion is unavailable on this worker. Upload a video instead, or enable yt-dlp in the worker settings."); return; }
    let urls: string[], options: AnalysisOptions;
    try { urls = youtubeUrls(url); options = analysisOptions({ ...analysis }); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Check the analysis settings."); return; }
    submitLock.current = true;
    resetSource(); setPhase("analyzing"); setStage("Submitting video URLs");
    try {
      const data = await requestJson<CreatedJob>("/api/analyze", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ urls, ...options }) }, 180_000);
      if (!VALID_ID.test(data.job_id)) throw new Error("Worker did not return a valid job ID.");
      for (const job of data.jobs || []) if (job.job_id) pushHistory({ id: job.job_id, kind: "analyze", label: job.url, status: "queued", at: Date.now() });
      if ((data.jobs?.length || 0) > 1) setMessage(`${data.jobs!.filter((job) => job.job_id).length} videos queued. This studio opens the first; track all of them on the Jobs page.${data.jobs!.some((job) => job.error) ? " Some URLs were rejected; review the worker status." : ""}`);
      setActiveId(data.job_id);
      setCurrentJob({ job_id: data.job_id, kind: "analyze", status: "queued", progress: 0, attempts: 0, max_attempts: 3, error: null, result: null, label: urls[0] });
    } catch (failure) { setPhase("idle"); setError(failure instanceof Error ? failure.message : "Analysis request failed."); }
    finally { submitLock.current = false; }
  }
  async function uploadFile(file: File) {
    if (busy || submitLock.current) return;
    if (health?.reachable && health.ready === false) { setError(health.error || "Worker is not ready. Open its diagnostics and install FFmpeg/FFprobe."); return; }
    let options: AnalysisOptions;
    try {
      validateUpload(file, health?.max_upload_mb ?? 2048);
      options = analysisOptions({ ...analysis });
      if (sidecar && (!/\.srt$/i.test(sidecar.name) || !sidecar.size || sidecar.size > 20 * 1024 ** 2)) throw new Error("Choose a non-empty SRT file under 20 MB.");
      if (bgmFile && (!/\.(mp3|wav|m4a|aac|ogg)$/i.test(bgmFile.name) || !bgmFile.size || bgmFile.size > 50 * 1024 ** 2)) throw new Error("Choose a background audio file under 50 MB.");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Check the upload."); return; }
    submitLock.current = true;
    resetSource(); setFileName(file.name); setProjectName(file.name.replace(/\.[^.]+$/, "")); setPhase("uploading"); setStage("Uploading source file");
    const controller = new AbortController(); uploadController.current = controller;
    const form = new FormData(); form.append("video", file);
    for (const [key, value] of Object.entries(options)) form.append(key, String(value));
    if (sidecar) form.append("captions", sidecar);
    if (bgmFile) form.append("bgm", bgmFile);
    try {
      const data = await uploadMedia<CreatedJob>(form, setProgress, controller.signal);
      if (!VALID_ID.test(data.job_id)) throw new Error("Worker did not return a valid job ID.");
      setProgress(0); setStage("Waiting for worker"); setPhase("analyzing"); setActiveId(data.job_id);
      setCurrentJob({ job_id: data.job_id, kind: "analyze", status: "queued", progress: 0, attempts: 0, max_attempts: 3, error: null, result: null, label: file.name });
      pushHistory({ id: data.job_id, kind: "upload", label: file.name, status: "queued", at: Date.now() });
    } catch (failure) {
      setPhase("idle");
      if (failure instanceof Error && failure.name === "AbortError") setMessage("Upload stopped. No local results were generated.");
      else setError(failure instanceof Error ? failure.message : "Upload failed.");
    } finally { submitLock.current = false; uploadController.current = null; if (fileRef.current) fileRef.current.value = ""; }
  }
  async function render() {
    if (busy || submitLock.current) return;
    const picks = highlights.map((highlight, index) => ({ ...highlight, ...(trims[index] || highlight), locked: settings.render_mode === "exact", selected: selected[index] !== false })).filter((highlight) => highlight.selected);
    if (!picks.length || !analysisJobId) { setError("Select at least one analyzed clip."); return; }
    if (!settings.durations.length || settings.durations.some((value) => !Number.isInteger(value) || value < 5 || value > 180)) { setError("Target length must be a whole number from 5 to 180 seconds."); return; }
    submitLock.current = true;
    setError(""); setMessage(""); setRendered([]); setRenderJobId(""); setPhase("rendering"); setProgress(0); setStage("Preparing selected clips");
    try {
      const data = await requestJson<CreatedJob>("/api/jobs/render", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ parent_job: analysisJobId, highlights: picks, ...settings }) }, 180_000);
      if (!VALID_ID.test(data.job_id)) throw new Error("Worker did not return a valid job ID.");
      setRenderJobId(data.job_id); setActiveId(data.job_id);
      setCurrentJob({ job_id: data.job_id, kind: "render", status: "queued", progress: 0, attempts: 0, max_attempts: 3, error: null, result: null, label: `Render ${picks.length} clips`, parent_job: analysisJobId });
      pushHistory({ id: data.job_id, kind: "render", label: `Render ${picks.length} clips`, status: "queued", at: Date.now(), parent: analysisJobId });
    } catch (failure) { setPhase("ready"); setError(failure instanceof Error ? failure.message : "Could not start rendering."); }
    finally { submitLock.current = false; }
  }
  async function retryJob(id: string) {
    setActionBusy(true); setError("");
    try { await requestJson(`/api/jobs/retry?job=${id}`, { method: "POST" }); await openJob(id, { selected, trims }); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Retry failed."); }
    finally { setActionBusy(false); }
  }
  async function cancelJob() {
    if (!activeId) return;
    setActionBusy(true); setError("");
    try { await requestJson(`/api/jobs/cancel?job=${activeId}`, { method: "POST" }); setStage("Stopping safely; speech inference may need to finish its current stage"); polling.reconnect(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Cancellation failed."); }
    finally { setActionBusy(false); }
  }
  async function deleteJob(id: string) {
    if (!window.confirm("Delete this worker job and its media files? Saved project metadata is kept, but its media link may expire.")) return;
    setError("");
    try {
      await requestJson(`/api/jobs/delete?job=${id}`, { method: "DELETE" });
    } catch (failure) {
      if (!(failure instanceof ApiError && failure.status === 404)) { setError(failure instanceof Error ? failure.message : "Delete failed."); return; }
    }
    setHistory((previous) => { const next = previous.filter((item) => item.id !== id); writeStorage(HISTORY_KEY, next); return next; });
    if (currentJob?.job_id === id) { resetSource(); setPhase("idle"); try { localStorage.removeItem(DRAFT_KEY); } catch {} }
  }
  async function saveProject() {
    if (!projectName.trim() || !VALID_ID.test(workspace)) { setError("Enter a project name and a valid workspace key (letters, numbers, _ or -)."); return; }
    setActionBusy(true); setError("");
    try {
      const project = await requestJson<Project>("/api/projects", { method: "POST", headers: { "content-type": "application/json", "x-clipforge-user": workspace }, body: JSON.stringify({ id: projectId || undefined, name: projectName.trim(), notes: projectNotes, job_id: analysisJobId || undefined, render_job_id: renderJobId || undefined, url: url.split(/[\n,]+/)[0].trim().slice(0, 2048), settings, analysis, editor: { selected, trims } }) });
      setProjectId(project.id); setMessage(`Project “${project.name}” saved with your trims and export settings.`);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not save project."); }
    finally { setActionBusy(false); }
  }
  const selectedCount = selected.filter(Boolean).length;
  const artifact = (path: string, download = false) => `/api/jobs/files?job=${renderJobId}&path=${encodeURIComponent(`clips/${path}`)}${download ? "&download=1" : ""}`;
  const working = ["uploading", "analyzing", "rendering"].includes(phase);
  return <main>
    <SiteNav onHistory={() => setShowHistory((value) => !value)} />
    <WorkerStatus onHealth={setHealth} />
    {showHistory && <section className="historyPanel" aria-label="Recent jobs">
      <div className="resultHead"><h2>Recent jobs</h2><button type="button" className="chip" onClick={() => setShowHistory(false)}><X size={12} /> Close</button></div>
      {!history.length && <p className="hint">No jobs yet. History stays in this browser.</p>}
      <ul className="historyList">{history.map((item) => <li key={item.id}>
        <div><b>{item.label}</b><small>{item.kind} · {item.status} · {new Date(item.at).toLocaleString()}</small></div>
        <div className="historyActions">
          <button type="button" className="chip" disabled={busy} onClick={() => { void openJob(item.id).catch((failure: Error) => setError(failure.message)); }}>Open</button>
          {["failed", "cancelled"].includes(item.status) && <button type="button" className="chip" disabled={busy} onClick={() => retryJob(item.id)}><RotateCcw size={12} /> Retry</button>}
          <button type="button" className="chip" disabled={busy} onClick={() => deleteJob(item.id)} aria-label={`Delete job ${item.id}`}><Trash2 size={12} /></button>
        </div>
      </li>)}</ul>
    </section>}
    <section className="hero">
      <div className="eyebrow"><Sparkles size={14} /> YOUR VIDEO. MORE POSSIBILITIES.</div>
      <h1>Turn long videos into<br /><em>great clips.</em></h1>
      <p className="sub">Find the moments that matter. Fine-tune your trims, add captions, and export ready-to-share videos—all from one studio.</p>
      <div className="workflow" aria-label="Workflow"><span className="on">01 Source</span><span className={analysisJobId ? "on" : ""}>02 Analyze</span><span className={highlights.length ? "on" : ""}>03 Fine-tune</span><span className={rendered.length ? "on" : ""}>04 Export</span></div>
      <section className="panel" aria-label="Video source and analysis">
        <div className="tabs"><button type="button" className={`tab${mode === "url" ? " on" : ""}`} onClick={() => setMode("url")} disabled={busy}><Link2 size={13} /> YouTube URLs</button><button type="button" className={`tab${mode === "upload" ? " on" : ""}`} onClick={() => setMode("upload")} disabled={busy}><Upload size={13} /> Upload file</button></div>
        {mode === "url" ? <>
          <div className="inputRow sourceInput"><Link2 size={16} /><textarea aria-label="YouTube video URLs" value={url} onChange={(event) => setUrl(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void analyze(); } }} placeholder="Paste YouTube video URLs, one per line…" disabled={busy} rows={2} />
            <button type="button" onClick={analyze} disabled={busy || Boolean(youtubeUnavailable)}>{working ? <><Loader2 className="spin" size={14} /> Working</> : <><Play size={14} /> Find clips</>}</button></div>
          {youtubeUnavailable && <p className="warning">YouTube ingestion is disabled or yt-dlp is missing. <button type="button" className="chip" disabled={busy} onClick={() => setMode("upload")}>Upload a file instead</button></p>}
          <p className="inputHelp">Up to 5 videos per batch · Ctrl/⌘ + Enter to start · uploads work without YouTube support</p>
        </> : <>
          <div className={`dropzone${dragOver ? " over" : ""}${busy ? " disabled" : ""}`} role="button" aria-label="Choose video file" aria-disabled={busy} tabIndex={busy ? -1 : 0}
            onDragOver={(event) => { event.preventDefault(); if (!busy) setDragOver(true); }} onDragLeave={() => setDragOver(false)}
            onDrop={(event) => { event.preventDefault(); setDragOver(false); const file = event.dataTransfer.files[0]; if (file && !busy) void uploadFile(file); }}
            onClick={() => { if (!busy) fileRef.current?.click(); }} onKeyDown={(event) => { if (!busy && ["Enter", " "].includes(event.key)) { event.preventDefault(); fileRef.current?.click(); } }}>
            <Upload size={24} /><div><b>{fileName || "Drop a video here or browse files"}</b><small>MP4 · MOV · MKV · WebM · audio transcription · up to {health?.max_upload_mb ?? 2048} MB</small></div>
            <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.avi,.m4v,.mts,.mp3,.wav,.m4a,.aac,.flac,.ogg" hidden disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadFile(file); }} />
          </div>
          <p className="inputHelp">Add optional files first, then choose or drop your source video.</p>
          <div className="sidecarFields"><label>SRT captions <small>Optional · used instead of Whisper</small><input aria-label="SRT sidecar" type="file" accept=".srt" disabled={busy} onChange={(event) => setSidecar(event.target.files?.[0] || null)} /></label>
            <label>Background track <small>Optional · MP3/WAV, up to 50 MB</small><input aria-label="Background track" type="file" accept=".mp3,.wav,.m4a,.aac,.ogg" disabled={busy} onChange={(event) => { const file = event.target.files?.[0] || null; setBgmFile(file); if (file) setSettings((value) => ({ ...value, bgm: true })); }} /></label></div>
        </>}
        <details className="analysisControls"><summary>Analysis controls <span>{analysis.min_seconds}–{analysis.max_seconds}s · up to {analysis.limit} highlights</span></summary><div className="analysisFields">
          <label>Minimum seconds<input type="number" min={5} max={180} value={analysis.min_seconds} disabled={busy} onChange={(event) => setAnalysis((value) => ({ ...value, min_seconds: Number(event.target.value) }))} /></label>
          <label>Maximum seconds<input type="number" min={5} max={180} value={analysis.max_seconds} disabled={busy} onChange={(event) => setAnalysis((value) => ({ ...value, max_seconds: Number(event.target.value) }))} /></label>
          <label>Highlight count<input type="number" min={1} max={20} value={analysis.limit} disabled={busy} onChange={(event) => setAnalysis((value) => ({ ...value, limit: Number(event.target.value) }))} /></label>
        </div></details>
        {restoring && <p className="hint"><Loader2 className="spin" size={13} /> Restoring your studio…</p>}
        {error && <div className="error" role="alert">{error}{currentJob && ["failed", "cancelled"].includes(currentJob.status) && <button type="button" className="chip" disabled={busy} onClick={() => retryJob(currentJob.job_id)}><RotateCcw size={12} /> Retry this job</button>}</div>}
        {message && <div className="note" role="status">{message}</div>}
        {working && <div className="jobProgress" aria-live="polite">
          <div className="progressWrap" role="progressbar" aria-label={phase === "uploading" ? "Upload progress" : "Job progress"} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><div className="progressBar" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /><span>{phase === "uploading" && progress === 100 ? "Saving on worker…" : stage || phase} · {progress}%</span></div>
          <div className="progressActions"><small>{currentJob ? `Job ${currentJob.job_id.slice(0, 8)} · attempt ${currentJob.attempts}/${currentJob.max_attempts} · safe to reload` : "Keep this page open until the worker returns a job ID."}</small>
            {phase === "uploading" ? <button type="button" className="chip danger" onClick={() => uploadController.current?.abort()}><Square size={11} /> Stop upload</button> : activeId && <button type="button" className="chip danger" disabled={actionBusy || currentJob?.status === "cancelling"} onClick={cancelJob}><Square size={11} /> {currentJob?.status === "cancelling" ? "Stopping…" : "Cancel job"}</button>}</div>
        </div>}
        {polling.connection && <div className="warning" role="status">{polling.connection} <button type="button" className="chip" onClick={polling.reconnect}>Reconnect now</button></div>}
        <div className="hint"><ShieldCheck size={13} /> Only process videos you own or have permission to use.</div>
      </section>
      <div className="features"><div><Zap size={18} /><b>Smart picks, precise trims</b><small>Audio + scene signals, exact windows and platform presets</small></div><div><Save size={18} /><b>Pick up where you left off</b><small>Restorable jobs, autosaved settings and project snapshots</small></div><div><Film size={18} /><b>Everything in one export</b><small>MP4, cover images and real SRT/VTT subtitles in a ZIP</small></div></div>
      {analysisJobId && analysisResult && <section className="results" aria-label="Analysis results">
        <div className="resultHead"><div><span className="eyebrow">YOUR HIGHLIGHTS</span><h2>Fine-tune your clips</h2></div><span>{selectedCount}/{highlights.length} selected</span></div>
        <div className="note">{formatTime(analysisResult.duration || 0)} · {analysisResult.engine || "Unknown engine"} · {analysisResult.transcript_segments || 0} segments</div>
        {analysisResult.warnings?.map((warning) => <p className="warning" key={warning}>{warning}</p>)}
        {analysisResult.has_transcript && <div className="toolbar transcriptExports"><span className="optLabel">Full transcript</span>{["srt", "vtt", "txt", "json"].map((format) => <a key={format} className="chip" href={`/api/jobs/transcript?job=${analysisJobId}&format=${format}`} download><Download size={12} /> {format.toUpperCase()}</a>)}</div>}
        {!highlights.length && <p className="warning">No clips matched your length settings. Try a lower minimum, or upload a real SRT transcript.</p>}
        <Phase2Toolbar settings={settings} setSettings={setSettings} busy={busy} onRender={render} highlightCount={selectedCount} canRender={analysisResult.has_video !== false} />
        <ClipPicker key={analysisJobId} clips={highlights} selected={selected} setSelected={setSelected} trims={trims} setTrims={setTrims} platform={settings.platform} busy={busy} jobId={analysisJobId} sourceFile={analysisResult.source_file || "source.mp4"} duration={analysisResult.duration || 0} hasVideo={analysisResult.has_video !== false} />
        <section className="projectSave" aria-label="Save project"><div><span className="eyebrow">SAVE YOUR WORKSPACE</span><h3>Keep this edit for later</h3><p>Stores picks, trims and export settings on the worker. Media files still follow the worker retention policy.</p></div>
          <div className="projectFields"><label>Project name<input value={projectName} maxLength={80} disabled={busy} onChange={(event) => setProjectName(event.target.value)} /></label><label>Workspace key<input value={workspace} maxLength={64} disabled={busy} onChange={(event) => setWorkspace(event.target.value)} /></label>
            <label className="wide">Notes<textarea aria-label="Project notes" rows={2} value={projectNotes} maxLength={4000} disabled={busy} onChange={(event) => setProjectNotes(event.target.value)} /></label>
            <button type="button" className="renderBtn" disabled={busy} onClick={saveProject}><Save size={13} /> {projectId ? "Update project" : "Save project"}</button><a className="chip" href="/projects">Open projects</a>
            <small className="wide timingHint">Workspace keys organize projects; they are not authentication. Use a private deployment for sensitive media.</small>
          </div>
        </section>
      </section>}
      {rendered.length > 0 && <section className="results generatedResults" aria-label="Generated clips">
        <div className="resultHead"><div><span className="eyebrow">EXPORT COMPLETE</span><h2>Ready for your next post.</h2></div><a href={`/api/jobs/zip?job=${renderJobId}`} className="dl" download><Archive size={13} /> Download ZIP</a></div>
        {currentJob?.kind === "render" && currentJob.result?.warnings?.map((warning) => <p key={warning} className="warning">{warning}</p>)}
        <div className="grid">{rendered.map((clip) => <article className="genClip" key={`${renderJobId}-${clip.file}`}>
          <video controls preload="metadata" playsInline style={{ aspectRatio: (clip.aspect || (clip.vertical ? "9:16" : "16:9")).replace(":", "/") }} poster={clip.thumbnail ? artifact(clip.thumbnail) : undefined} src={artifact(clip.file)} onError={() => setError("The browser could not load this MP4. Try downloading it, or check whether the worker job has expired.")}>
            {clip.subtitles?.vtt && <track kind="captions" label="Transcript" srcLang={analysisResult?.language && analysisResult.language !== "unknown" ? analysisResult.language : "en"} src={artifact(clip.subtitles.vtt)} default={!clip.captions} />}
          </video>
          <div className="genMeta"><b>{clip.file.replace(".mp4", "")}</b><small>{formatTime(clip.start)} → {formatTime(clip.end)} · {clip.duration}s · {(clip.bytes / 1048576).toFixed(1)} MB</small>
            <div className="genActions"><a href={artifact(clip.file, true)} download={clip.file} className="dl"><Download size={13} /> MP4</a>{clip.thumbnail && <a href={artifact(clip.thumbnail, true)} download className="dl ghost">Cover</a>}{Object.entries(clip.subtitles || {}).map(([format, file]) => file && <a key={format} href={artifact(file, true)} download className="dl ghost">{format.toUpperCase()}</a>)}</div>
          </div>
        </article>)}</div>
      </section>}
    </section>
    <footer>SAYANOX CLIPFORGE · v1.0 · built for your real workflow</footer>
  </main>;
}
