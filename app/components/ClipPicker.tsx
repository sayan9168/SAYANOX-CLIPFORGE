"use client";
import { useRef, useState } from "react";
import { Play, RotateCcw } from "lucide-react";
import { formatTime } from "../../lib/storage";
import type { Highlight, Trim } from "../../lib/types";
import { SocialCaption } from "./SocialCaption";
import { WaveformTimeline } from "./WaveformTimeline";
export type { Highlight } from "../../lib/types";

export function ClipPicker({ clips, selected, setSelected, trims, setTrims, platform, busy, jobId, sourceFile, duration, hasVideo = true }: {
  clips: Highlight[]; selected: boolean[]; setSelected: (value: boolean[]) => void;
  trims: Trim[]; setTrims: (value: Trim[]) => void; platform: string; busy: boolean;
  jobId: string; sourceFile: string; duration: number; hasVideo?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const [previewError, setPreviewError] = useState("");
  const video = useRef<HTMLVideoElement | null>(null);
  const marks = clips.map((clip, index) => trims[index] || { start: clip.start, end: clip.end });
  const maximum = duration || marks.reduce((value, mark) => Math.max(value, mark.end), 1);
  function patch(index: number, field: "start" | "end", n: number) {
    if (!Number.isFinite(n)) return;
    const next = marks.map((trim) => ({ ...trim }));
    const trim = next[index];
    if (field === "start") {
      trim.start = Math.max(0, Math.min(maximum - 0.1, n));
      trim.end = Math.min(maximum, Math.max(trim.end, trim.start + 0.1));
      if (trim.end - trim.start > 180) trim.end = trim.start + 180;
    } else {
      trim.end = Math.max(0.1, Math.min(maximum, n));
      trim.start = Math.max(0, Math.min(trim.start, trim.end - 0.1));
      if (trim.end - trim.start > 180) trim.start = trim.end - 180;
    }
    setTrims(next);
  }
  function preview(index: number) {
    setPreviewError("");
    if (open === index && video.current) {
      video.current.currentTime = marks[index].start;
      void video.current.play().catch(() => setPreviewError("Press the video play button to start preview."));
    } else setOpen(index);
  }
  return <>
    <div className="toolbar pickerActions">
      <button type="button" className="chip" disabled={busy} onClick={() => setSelected(clips.map(() => true))}>Select all</button>
      <button type="button" className="chip" disabled={busy} onClick={() => setSelected(clips.map(() => false))}>Select none</button>
      <button type="button" className="chip" disabled={busy} onClick={() => setTrims(clips.map((clip) => ({ start: clip.start, end: clip.end })))}><RotateCcw size={12} /> Reset trims</button>
    </div>
    <WaveformTimeline jobId={jobId} duration={maximum} marks={marks} />
    {clips.map((clip, index) => {
      const { start, end } = marks[index];
      const low = Math.max(0, Math.min(clip.start, start) - 8);
      const high = Math.min(maximum, Math.max(clip.end, end) + 8);
      const span = Math.max(0.1, high - low);
      return <article className={`clip${selected[index] === false ? " dim" : ""}`} key={`${jobId}-${index}`}>
        <div className="thumb"><Play size={22} /><small>{formatTime(start)} — {formatTime(end)}</small></div>
        <div className="clipBody">
          <div className="clipTitle"><label className="pickLabel">
            <input type="checkbox" checked={selected[index] !== false} disabled={busy} onChange={() => setSelected(selected.map((value, i) => i === index ? !value : value))} aria-label={`Select clip ${index + 1}`} />
            <h3>{clip.title || `Highlight #${index + 1}`}</h3>
          </label><strong>{Math.round(clip.score)}/100</strong></div>
          <p>{clip.reason || clip.text || ""}</p>
          <div className="timeline">
            <div className="rail"><i style={{ left: `${(start - low) / span * 100}%`, width: `${(end - start) / span * 100}%` }} /></div>
            <div className="trimRow">
              <span>In</span><input aria-label={`Clip ${index + 1} in slider`} type="range" min={low} max={high} step={0.1} disabled={busy} value={start} onChange={(event) => patch(index, "start", Number(event.target.value))} />
              <input aria-label={`Clip ${index + 1} in seconds`} type="number" step={0.1} min={0} max={maximum} disabled={busy} value={Number(start.toFixed(1))} onChange={(event) => patch(index, "start", Number(event.target.value))} />
              <span>Out</span><input aria-label={`Clip ${index + 1} out slider`} type="range" min={low} max={high} step={0.1} disabled={busy} value={end} onChange={(event) => patch(index, "end", Number(event.target.value))} />
              <input aria-label={`Clip ${index + 1} out seconds`} type="number" step={0.1} min={0.1} max={maximum} disabled={busy} value={Number(end.toFixed(1))} onChange={(event) => patch(index, "end", Number(event.target.value))} />
              <code>{(end - start).toFixed(1)}s</code>
            </div>
          </div>
          {jobId && sourceFile && hasVideo && <div className="previewBox">
            <button type="button" className="chip" onClick={() => preview(index)}><Play size={12} /> Preview trim</button>
            {open === index && <>
              <video ref={video} controls playsInline preload="metadata"
                src={`/api/jobs/files?job=${jobId}&path=${encodeURIComponent(sourceFile)}`}
                onLoadedMetadata={(event) => { event.currentTarget.currentTime = start; void event.currentTarget.play().catch(() => {}); }}
                onTimeUpdate={(event) => { if (event.currentTarget.currentTime >= end) event.currentTarget.pause(); }}
                onError={() => setPreviewError("This source codec cannot play in your browser. Render an MP4 clip to preview it.")} />
              {previewError && <small className="warning">{previewError}</small>}
            </>}
          </div>}
          {clip.signals && <div className="signals">{Object.entries(clip.signals).map(([key, value]) =>
            value != null ? <span className="sig" key={key}>{key}<strong>{Math.round(value * 100)}</strong></span> : null)}</div>}
          <SocialCaption pack={clip} packs={clip.packs} languages={clip.languages} title={clip.title} text={clip.text} platform={platform} />
        </div>
      </article>;
    })}
  </>;
}
