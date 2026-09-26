"use client";
import { useRef, useState } from "react";
import { Play } from "lucide-react";
import { SocialCaption } from "./SocialCaption";

export type Highlight = {
  start: number; end: number; score: number;
  title?: string; reason?: string; text?: string;
  caption?: string; hashtags?: string[]; hashtag_line?: string; post?: string;
  packs?: Record<string, { post?: string }>;
  languages?: Record<string, Record<string, { post?: string }>>;
  signals?: Record<string, number | undefined>;
};

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
}

export function ClipPicker({
  clips, selected, setSelected, trims, setTrims, platform, busy, jobId,
}: {
  clips: Highlight[];
  selected: boolean[];
  setSelected: (v: boolean[]) => void;
  trims: { start: number; end: number }[];
  setTrims: (v: { start: number; end: number }[]) => void;
  platform: string;
  busy: boolean;
  jobId?: string;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const vids = useRef<Record<number, HTMLVideoElement | null>>({});

  function toggle(i: number) {
    const next = selected.slice();
    next[i] = !next[i];
    setSelected(next);
  }
  function patch(i: number, field: "start" | "end", n: number) {
    if (!Number.isFinite(n)) return;
    const next = trims.map((t) => ({ ...t }));
    next[i] = { ...next[i], [field]: Math.max(0, n) };
    if (next[i].end <= next[i].start) next[i].end = next[i].start + 1;
    setTrims(next);
  }
  function playPreview(i: number) {
    setOpen(i);
    const el = vids.current[i];
    const t = trims[i]?.start ?? clips[i].start;
    if (el) {
      el.currentTime = Math.max(0, t);
      el.play().catch(() => {});
    }
  }
  return (
    <>
      {clips.map((c, i) => {
        const t0 = trims[i]?.start ?? c.start;
        const t1 = trims[i]?.end ?? c.end;
        const rail0 = Math.max(0, Math.min(c.start, t0) - 8);
        const rail1 = Math.max(c.end, t1) + 8;
        const span = Math.max(1, rail1 - rail0);
        const left = ((t0 - rail0) / span) * 100;
        const width = ((t1 - t0) / span) * 100;
        return (
          <article className={`clip${selected[i] === false ? " dim" : ""}`} key={i}>
            <div className="thumb">
              <Play size={22} />
              <small>{fmt(t0)} — {fmt(t1)}</small>
            </div>
            <div className="clipBody">
              <div className="clipTitle">
                <label className="pickLabel">
                  <input type="checkbox" checked={selected[i] !== false} disabled={busy} onChange={() => toggle(i)} />
                  <h3>{c.title || `Highlight #${i + 1}`}</h3>
                </label>
                <strong>{Math.round(c.score)}/100</strong>
              </div>
              <p>{c.reason || c.text || ""}</p>
              <div className="timeline">
                <div className="rail"><i style={{ left: `${left}%`, width: `${width}%` }} /></div>
                <div className="trimRow">
                  <span>In</span>
                  <input type="range" min={rail0} max={rail1} step={0.1} disabled={busy}
                    value={t0} onChange={(e) => patch(i, "start", Number(e.target.value))} />
                  <input type="number" step={0.1} min={0} disabled={busy} value={Number(t0.toFixed(1))}
                    onChange={(e) => patch(i, "start", Number(e.target.value))} />
                  <span>Out</span>
                  <input type="range" min={rail0} max={rail1} step={0.1} disabled={busy}
                    value={t1} onChange={(e) => patch(i, "end", Number(e.target.value))} />
                  <input type="number" step={0.1} min={0} disabled={busy} value={Number(t1.toFixed(1))}
                    onChange={(e) => patch(i, "end", Number(e.target.value))} />
                  <code>{fmt(t1 - t0)}</code>
                </div>
              </div>
              {jobId && (
                <div className="previewBox">
                  <button type="button" className="chip" disabled={busy} onClick={() => playPreview(i)}>
                    Preview trim
                  </button>
                  {open === i && (
                    <video
                      ref={(el) => { vids.current[i] = el; }}
                      src={`/api/jobs/files?job=${jobId}&path=${encodeURIComponent("source.mp4")}`}
                      controls
                      onLoadedMetadata={(e) => {
                        const el = e.currentTarget;
                        el.currentTime = t0;
                      }}
                      onTimeUpdate={(e) => {
                        if (e.currentTarget.currentTime >= t1) {
                          e.currentTarget.pause();
                        }
                      }}
                    />
                  )}
                </div>
              )}
              {c.signals && (
                <div className="signals">
                  {Object.entries(c.signals).map(([k, v]) =>
                    v != null ? <span className="sig" key={k}>{k}<strong>{Math.round(Number(v) * 100)}</strong></span> : null,
                  )}
                </div>
              )}
              <SocialCaption pack={c} packs={c.packs} languages={c.languages} title={c.title} text={c.text} platform={platform} />
            </div>
          </article>
        );
      })}
    </>
  );
}
