"use client";
import { useEffect, useState } from "react";

export function WaveformTimeline({
  jobId, duration, marks,
}: {
  jobId?: string;
  duration?: number;
  marks?: { start: number; end: number }[];
}) {
  const [curve, setCurve] = useState<number[]>([]);
  useEffect(() => {
    if (!jobId) return;
    fetch(`/api/jobs/files?job=${jobId}&path=${encodeURIComponent("energy.json")}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        const arr = Array.isArray(data) ? data : [];
        const nums = arr.map((x: number) => {
          const n = Number(x);
          if (!Number.isFinite(n) || n === Number.NEGATIVE_INFINITY) return 0;
          return Math.max(0, Math.min(1, (n + 60) / 60));
        });
        setCurve(nums.slice(0, 400));
      })
      .catch(() => setCurve([]));
  }, [jobId]);
  if (!curve.length) return null;
  const w = 640, h = 64;
  const step = w / Math.max(1, curve.length - 1);
  const d = curve.map((v, i) => `${i === 0 ? "M" : "L"} ${i * step} ${h - v * (h - 4)}`).join(" ");
  return (
    <div className="waveWrap">
      <svg viewBox={`0 0 ${w} ${h}`} className="wave">
        <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
        {(marks || []).map((m, i) => {
          const dur = duration || curve.length * 0.5;
          const x = (m.start / dur) * w;
          const width = Math.max(2, ((m.end - m.start) / dur) * w);
          return <rect key={i} x={x} y={2} width={width} height={h - 4} fill="currentColor" opacity={0.18} />;
        })}
      </svg>
      <small>Full-video energy · {curve.length} bins</small>
    </div>
  );
}
