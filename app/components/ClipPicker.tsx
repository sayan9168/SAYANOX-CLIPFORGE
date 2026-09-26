"use client";
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
  clips,
  selected,
  setSelected,
  trims,
  setTrims,
  platform,
  busy,
}: {
  clips: Highlight[];
  selected: boolean[];
  setSelected: (v: boolean[]) => void;
  trims: { start: number; end: number }[];
  setTrims: (v: { start: number; end: number }[]) => void;
  platform: string;
  busy: boolean;
}) {
  function toggle(i: number) {
    const next = selected.slice();
    next[i] = !next[i];
    setSelected(next);
  }
  function patch(i: number, field: "start" | "end", raw: string) {
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    const next = trims.map((t) => ({ ...t }));
    next[i] = { ...next[i], [field]: Math.max(0, n) };
    if (next[i].end <= next[i].start) next[i].end = next[i].start + 1;
    setTrims(next);
  }
  return (
    <>
      {clips.map((c, i) => (
        <article className={`clip${selected[i] === false ? " dim" : ""}`} key={i}>
          <div className="thumb"><Play size={22} /><small>{fmt(trims[i]?.start ?? c.start)} — {fmt(trims[i]?.end ?? c.end)}</small></div>
          <div className="clipBody">
            <div className="clipTitle">
              <label className="pickLabel">
                <input type="checkbox" checked={selected[i] !== false} disabled={busy} onChange={() => toggle(i)} />
                <h3>{c.title || `Highlight #${i + 1}`}</h3>
              </label>
              <strong>{Math.round(c.score)}/100</strong>
            </div>
            <p>{c.reason || c.text || ""}</p>
            <div className="trimRow">
              <span>Trim</span>
              <input type="number" step="0.1" min={0} disabled={busy} value={Number((trims[i]?.start ?? c.start).toFixed(1))} onChange={(e) => patch(i, "start", e.target.value)} />
              <span>→</span>
              <input type="number" step="0.1" min={0} disabled={busy} value={Number((trims[i]?.end ?? c.end).toFixed(1))} onChange={(e) => patch(i, "end", e.target.value)} />
              <code>{fmt((trims[i]?.end ?? c.end) - (trims[i]?.start ?? c.start))}</code>
            </div>
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
      ))}
    </>
  );
}
