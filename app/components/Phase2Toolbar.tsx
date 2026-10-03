"use client";
import type { Dispatch, SetStateAction } from "react";
import { Clock3, Music2, ScanFace, SlidersHorizontal } from "lucide-react";
import { DEFAULT_RENDER, type Aspect, type CaptionStyle, type RenderSettings } from "../../lib/types";
export type { Aspect, CaptionStyle } from "../../lib/types";

export function Phase2Toolbar({ settings, setSettings, busy, onRender, highlightCount, canRender = true }: {
  settings: RenderSettings; setSettings: Dispatch<SetStateAction<RenderSettings>>;
  busy: boolean; onRender: () => void; highlightCount: number; canRender?: boolean;
}) {
  function patch<K extends keyof RenderSettings>(key: K, value: RenderSettings[K]) {
    setSettings((previous) => ({ ...previous, [key]: value }));
  }
  const exact = settings.render_mode === "exact";
  return <section className="exportSettings" aria-label="Export settings">
    <div className="toolbar">
      <span className="optLabel"><SlidersHorizontal size={14} /> Quick preset</span>
      {[
        { id: "tiktok", label: "TikTok", aspect: "9:16" as Aspect, seconds: 30 },
        { id: "reels", label: "Reels", aspect: "9:16" as Aspect, seconds: 30 },
        { id: "shorts", label: "Shorts", aspect: "9:16" as Aspect, seconds: 60 },
        { id: "square", label: "Square", aspect: "1:1" as Aspect, seconds: 30 },
      ].map((preset) => <button key={preset.id} type="button" className={`chip${settings.platform === preset.id ? " on" : ""}`} disabled={busy}
        onClick={() => setSettings((value) => ({ ...value, platform: preset.id, aspect: preset.aspect, durations: [preset.seconds], render_mode: "target" }))}>
        {preset.label}
      </button>)}
      <button type="button" className="chip" disabled={busy} onClick={() => setSettings({ ...DEFAULT_RENDER, durations: [30] })}>Reset settings</button>
    </div>
    <div className="toolbar">
      <span className="optLabel"><Clock3 size={13} /> Timing</span>
      <button type="button" className={`chip${exact ? " on" : ""}`} aria-pressed={exact} disabled={busy} onClick={() => patch("render_mode", "exact")}>Exact trims</button>
      <button type="button" className={`chip${!exact ? " on" : ""}`} aria-pressed={!exact} disabled={busy} onClick={() => patch("render_mode", "target")}>Smart length</button>
      {!exact && <>
        <select aria-label="Target clip length" disabled={busy} value={settings.durations[0]} onChange={(event) => patch("durations", [Number(event.target.value)])}>
          {[...new Set([15, 30, 60, 90, ...settings.durations])].sort((a, b) => a - b).map((value) => <option value={value} key={value}>{value}s</option>)}
        </select>
        <label className="optLabel">Custom seconds <input className="customDur" aria-label="Custom target length" type="number" min={5} max={180} disabled={busy}
          value={settings.durations[0]} onChange={(event) => patch("durations", [Number(event.target.value)])} /></label>
      </>}
      <small className="timingHint">{exact ? "Your in/out points are preserved." : "One clip per pick, fitted to the chosen length and clamped to the video."}</small>
    </div>
    <div className="toolbar">
      <span className="optLabel">Aspect</span>
      {(["9:16", "1:1", "16:9"] as Aspect[]).map((aspect) => <button key={aspect} type="button" className={`chip${settings.aspect === aspect ? " on" : ""}`} disabled={busy} onClick={() => patch("aspect", aspect)}>{aspect}</button>)}
      <label className="optLabel">Caption style <select disabled={busy} value={settings.caption_style} onChange={(event) => patch("caption_style", event.target.value as CaptionStyle)}>
        {(["default", "karaoke", "clean", "bold", "bengali", "hindi"] as CaptionStyle[]).map((style) => <option key={style} value={style}>{style}</option>)}
      </select></label>
      <button type="button" className={`chip${settings.captions ? " on" : ""}`} aria-pressed={settings.captions} disabled={busy} onClick={() => patch("captions", !settings.captions)}>Burn captions {settings.captions ? "on" : "off"}</button>
      <button type="button" className={`chip${settings.face_crop ? " on" : ""}`} aria-pressed={settings.face_crop} disabled={busy} onClick={() => patch("face_crop", !settings.face_crop)}><ScanFace size={12} /> Face crop</button>
      <button type="button" className={`chip${settings.grade ? " on" : ""}`} aria-pressed={settings.grade} disabled={busy} onClick={() => patch("grade", !settings.grade)}>Color grade</button>
      <button type="button" className={`chip${settings.hook_zoom ? " on" : ""}`} aria-pressed={settings.hook_zoom} disabled={busy} onClick={() => patch("hook_zoom", !settings.hook_zoom)}>2s hook zoom</button>
      <button type="button" className={`chip${settings.bgm ? " on" : ""}`} aria-pressed={settings.bgm} disabled={busy} onClick={() => patch("bgm", !settings.bgm)}><Music2 size={12} /> Background audio</button>
    </div>
    {settings.bgm && <div className="toolbar">
      <label className="optLabel">BGM volume <input aria-label="Background audio volume" type="range" min={0} max={1} step={0.01} disabled={busy} value={settings.bgm_volume} onChange={(event) => patch("bgm_volume", Number(event.target.value))} /> {Math.round(settings.bgm_volume * 100)}%</label>
      <button type="button" className={`chip${settings.duck ? " on" : ""}`} aria-pressed={settings.duck} disabled={busy} onClick={() => patch("duck", !settings.duck)}>Duck under speech</button>
      <small className="timingHint">Uses your uploaded track, otherwise a synthesized soft tone bed.</small>
    </div>}
    <div className="toolbar renderRow">
      <small className="timingHint">Settings autosave in this browser. SRT/VTT exports are generated when a real transcript is available.</small>
      <button type="button" className="renderBtn" onClick={onRender} disabled={busy || !highlightCount || !canRender}>
        Render {highlightCount} clip{highlightCount === 1 ? "" : "s"}
      </button>
    </div>
    {!canRender && <p className="warning">This source is audio-only. Transcript downloads are available; MP4 rendering needs a video.</p>}
  </section>;
}
