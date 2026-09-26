"use client";
import { Clock3, Music2, ScanFace } from "lucide-react";

export type Aspect = "9:16" | "1:1" | "16:9";
export type CaptionStyle =
  | "default"
  | "karaoke"
  | "clean"
  | "bold"
  | "bengali"
  | "hindi";

type Props = {
  busy: boolean;
  platform: string;
  setPlatform: (v: string) => void;
  aspect: Aspect;
  setAspect: (a: Aspect) => void;
  durations: number[];
  setDurations: (d: number[] | ((v: number[]) => number[])) => void;
  customDur: string;
  setCustomDur: (v: string) => void;
  addCustomDuration: () => void;
  captionStyle: CaptionStyle;
  setCaptionStyle: (s: CaptionStyle) => void;
  burnCaptions: boolean;
  setBurnCaptions: (v: boolean) => void;
  useBgm: boolean;
  setUseBgm: (v: boolean | ((x: boolean) => boolean)) => void;
  faceCrop: boolean;
  setFaceCrop: (v: boolean | ((x: boolean) => boolean)) => void;
  grade?: boolean;
  setGrade?: (v: boolean | ((x: boolean) => boolean)) => void;
  hookZoom?: boolean;
  setHookZoom?: (v: boolean | ((x: boolean) => boolean)) => void;
  onRender: () => void;
  highlightCount: number;
};

export function Phase2Toolbar(p: Props) {
  return (
    <>
      <div className="toolbar">
        <span className="optLabel">Platform</span>
        {[
          { id: "tiktok", label: "TikTok", aspect: "9:16" as Aspect, dur: 30 },
          { id: "reels", label: "Reels", aspect: "9:16" as Aspect, dur: 30 },
          { id: "shorts", label: "Shorts", aspect: "9:16" as Aspect, dur: 60 },
          { id: "square", label: "Square", aspect: "1:1" as Aspect, dur: 30 },
        ].map((pr) => (
          <button
            key={pr.id}
            type="button"
            className={p.platform === pr.id ? "chip on" : "chip"}
            disabled={p.busy}
            onClick={() => {
              p.setPlatform(pr.id);
              p.setAspect(pr.aspect);
              p.setDurations([pr.dur]);
            }}
          >
            {pr.label}
          </button>
        ))}
      </div>
      <div className="toolbar">
        <span className="durPick">
          <Clock3 size={13} /> Length
        </span>
        {[15, 30, 60, 90].map((d) => (
          <button
            key={d}
            type="button"
            className={p.durations.includes(d) ? "chip on" : "chip"}
            disabled={p.busy}
            onClick={() =>
              p.setDurations((v) =>
                v.includes(d) ? v.filter((x) => x !== d) : [...v, d].sort((a, b) => a - b),
              )
            }
          >
            {d}s
          </button>
        ))}
        <input
          className="customDur"
          type="number"
          min={5}
          max={180}
          placeholder="custom"
          value={p.customDur}
          disabled={p.busy}
          onChange={(e) => p.setCustomDur(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && p.addCustomDuration()}
        />
        <button type="button" className="chip" disabled={p.busy} onClick={p.addCustomDuration}>
          Add
        </button>
        <span className="optLabel" style={{ marginLeft: 8 }}>
          Aspect
        </span>
        {(["9:16", "1:1", "16:9"] as Aspect[]).map((a) => (
          <button
            key={a}
            type="button"
            className={p.aspect === a ? "chip on" : "chip"}
            disabled={p.busy}
            onClick={() => p.setAspect(a)}
          >
            {a}
          </button>
        ))}
        <span className="optLabel" style={{ marginLeft: 8 }}>
          Captions
        </span>
        {(["default", "karaoke", "clean", "bold", "bengali", "hindi"] as CaptionStyle[]).map(
          (s) => (
            <button
              key={s}
              type="button"
              className={p.captionStyle === s && p.burnCaptions ? "chip on" : "chip"}
              disabled={p.busy}
              onClick={() => {
                p.setBurnCaptions(true);
                p.setCaptionStyle(s);
              }}
            >
              {s}
            </button>
          ),
        )}
        <button
          type="button"
          className={!p.burnCaptions ? "chip on" : "chip"}
          disabled={p.busy}
          onClick={() => p.setBurnCaptions(false)}
        >
          off
        </button>
        <button type="button" className={p.useBgm ? "chip on" : "chip"} disabled={p.busy} onClick={() => p.setUseBgm((v) => !v)}>
          <Music2 size={12} /> BGM
        </button>
        <button type="button" className={p.faceCrop ? "chip on" : "chip"} disabled={p.busy} onClick={() => p.setFaceCrop((v) => !v)}>
          <ScanFace size={12} /> Face crop
        </button>
        {p.setGrade && (
          <button type="button" className={p.grade ? "chip on" : "chip"} disabled={p.busy} onClick={() => p.setGrade((v) => !v)}>
            Grade
          </button>
        )}
        {p.setHookZoom && (
          <button type="button" className={p.hookZoom ? "chip on" : "chip"} disabled={p.busy} onClick={() => p.setHookZoom((v) => !v)}>
            Hook zoom
          </button>
        )}
        <button className="renderBtn" onClick={p.onRender} disabled={p.busy || !p.durations.length} style={{ marginLeft: "auto" }}>
          Render {Math.max(1, Math.min(p.highlightCount, p.durations.length || 1))} clip(s)
        </button>
      </div>
    </>
  );
}
