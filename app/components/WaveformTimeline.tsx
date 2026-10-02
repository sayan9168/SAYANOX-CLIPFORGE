"use client";
import { useEffect, useState } from "react";
import { requestJson } from "../../lib/api";
import type { Trim } from "../../lib/types";

export function WaveformTimeline({ jobId, duration, marks = [] }: { jobId?: string; duration?: number; marks?: Trim[] }) {
  const [curve, setCurve] = useState<number[]>([]);
  useEffect(() => {
    setCurve([]);
    if (!jobId) return;
    const controller = new AbortController();
    requestJson<unknown>(`/api/jobs/files?job=${jobId}&path=energy.json`, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted || !Array.isArray(data)) return;
        const step = Math.max(1, Math.ceil(data.length / 400));
        const buckets = [];
        // Downsample the entire video, not just its first 200 seconds.
        for (let index = 0; index < data.length; index += step) {
          const values = data.slice(index, index + step).map((value: unknown) => typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(1, (value + 60) / 60)) : 0);
          buckets.push(Math.max(...values));
        }
        setCurve(buckets);
      }).catch(() => { if (!controller.signal.aborted) setCurve([]); });
    return () => controller.abort();
  }, [jobId]);
  if (!curve.length) return null;
  const w = 640, h = 64, step = w / Math.max(1, curve.length - 1);
  const path = curve.map((value, index) => `${index ? "L" : "M"} ${index * step} ${h - value * (h - 4)}`).join(" ");
  return <div className="waveWrap"><svg viewBox={`0 0 ${w} ${h}`} className="wave" role="img" aria-label="Full video audio energy and selected trim windows">
    <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
    {marks.map((mark, index) => <rect key={index} x={mark.start / (duration || 1) * w} y={2} width={Math.max(2, (mark.end - mark.start) / (duration || 1) * w)} height={h - 4} fill="currentColor" opacity={0.18} />)}
  </svg><small>Full-video energy · {curve.length} display bins</small></div>;
}
