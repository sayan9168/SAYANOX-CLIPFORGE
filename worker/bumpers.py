"""Concat optional intro.mp4 / outro.mp4 around a rendered clip."""
from __future__ import annotations

from pathlib import Path

import media


def _find(work: Path, stem: str) -> Path | None:
    for ext in (".mp4", ".mov", ".webm"):
        p = work / f"{stem}{ext}"
        if p.is_file():
            return p
    parent_stock = work.parent / "bumpers" / f"{stem}.mp4"
    if parent_stock.is_file():
        return parent_stock
    return None


def stitch(clip: Path, work: Path) -> Path:
    intro = _find(work, "intro")
    outro = _find(work, "outro")
    if not intro and not outro:
        return clip
    lst = work / f"{clip.stem}-concat.txt"
    lines = []
    if intro:
        lines.append(f"file '{intro.resolve()}'")
    lines.append(f"file '{clip.resolve()}'")
    if outro:
        lines.append(f"file '{outro.resolve()}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = clip.with_name(clip.stem + "-bumper.mp4")
    try:
        media.run_ffmpeg(
            "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", str(dest), timeout=300,
        )
    except Exception:
        try:
            media.run_ffmpeg(
                "-f", "concat", "-safe", "0", "-i", str(lst),
                "-c:v", "libx264", "-c:a", "aac", str(dest), timeout=600,
            )
        except Exception:
            return clip
    if dest.is_file() and dest.stat().st_size > 0:
        dest.replace(clip)
    return clip
