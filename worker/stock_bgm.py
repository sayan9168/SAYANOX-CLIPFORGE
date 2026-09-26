"""Generate tiny royalty-free beds with ffmpeg (no third-party audio files)."""
from __future__ import annotations

from pathlib import Path

import media

PRESETS = {
    "soft": "sine=frequency=220:sample_rate=44100,volume=0.08",
    "warm": "sine=frequency=174:sample_rate=44100,volume=0.07",
    "pulse": "sine=frequency=110:sample_rate=44100,aecho=0.6:0.6:40:0.3,volume=0.06",
}


def ensure_stock(root: Path) -> dict[str, Path]:
    dest = Path(root) / "stock"
    dest.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, filt in PRESETS.items():
        wav = dest / f"{name}.wav"
        if not wav.is_file() and media.have_tool("ffmpeg"):
            try:
                media.run_ffmpeg(
                    "-f", "lavfi", "-i", filt, "-t", "30", "-c:a", "pcm_s16le", str(wav),
                    timeout=30,
                )
            except Exception:
                continue
        if wav.is_file():
            out[name] = wav
    return out


def resolve_track(root: Path, name: str | None) -> Path | None:
    tracks = ensure_stock(root)
    if name and name in tracks:
        return tracks[name]
    return tracks.get("soft")
