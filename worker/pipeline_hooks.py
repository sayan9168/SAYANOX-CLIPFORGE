"""Small helpers for locked trim windows, hook text and thumbnails."""
from __future__ import annotations

from pathlib import Path

import media


def window_for(highlight: dict, durations: list[int], duration: float, pad: float) -> tuple[float, float, int]:
    start = float(highlight.get("start", 0))
    end = float(highlight.get("end", start + 15))
    if highlight.get("locked"):
        if duration:
            end = min(end, duration)
            start = max(0.0, min(start, end - 0.5))
        target = max(1, int(round(end - start)))
        return round(start, 2), round(end, 2), target
    hl_len = end - start
    target = min(durations, key=lambda d: abs(d - hl_len)) if durations else max(1, int(round(hl_len)))
    start = max(0.0, start - pad)
    end = start + target
    if duration:
        end = min(end, duration)
        start = max(0.0, end - target)
    return round(start, 2), round(end, 2), target


def grab_thumbnail(src: Path, dest: Path, t: float) -> Path | None:
    try:
        media.run_ffmpeg(
            "-ss", str(max(0.0, t)),
            "-i", str(src),
            "-frames:v", "1",
            "-q:v", "3",
            str(dest),
            timeout=60,
        )
    except Exception:
        return None
    return dest if dest.is_file() else None
