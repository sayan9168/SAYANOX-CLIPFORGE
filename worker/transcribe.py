"""Transcription adapters: faster-whisper, openai-whisper, energy-chunk fallback.

Normalised shape:
    {"language": str, "segments": [{"start","end","text"}], "engine": str}
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

_LOCK = threading.Lock()
_MODEL = None
_MODEL_NAME = ""


def _ffprobe_duration(path: Path) -> float:
    try:
        p = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if p.returncode == 0:
            return float(json.loads(p.stdout).get("format", {}).get("duration") or 0)
    except Exception:
        pass
    return 0.0


def energy_chunk_transcript(audio_path: Path, chunk: float = 25.0) -> dict:
    """No-ML fallback for Termux / devices without Whisper wheels.

    Splits the timeline into fixed windows so highlight scoring still runs
    on energy + scenes. Captions will be generic placeholders.
    """
    duration = _ffprobe_duration(audio_path)
    if duration <= 0:
        duration = 60.0
    chunk = max(8.0, float(chunk))
    segs = []
    t = 0.0
    idx = 1
    while t < duration - 0.5:
        end = min(t + chunk, duration)
        segs.append({
            "start": round(t, 3),
            "end": round(end, 3),
            "text": f"Highlight window {idx} ({int(t)}s–{int(end)}s)",
        })
        t = end
        idx += 1
    if not segs:
        segs = [{"start": 0.0, "end": round(duration, 3), "text": "Full clip"}]
    return {"language": "unknown", "segments": segs, "engine": "energy-fallback"}


def transcribe(audio_path: Path, model_name: str = "base",
               device: str = "cpu", compute_type: str = "int8") -> dict:
    """Timestamped transcript. Falls back to energy chunks if no Whisper."""
    global _MODEL, _MODEL_NAME
    fw_err = ow_err = None

    # 1) faster-whisper
    try:
        from faster_whisper import WhisperModel  # type: ignore
        with _LOCK:
            if _MODEL is None or _MODEL_NAME != f"fw:{model_name}":
                _MODEL = WhisperModel(model_name, device=device, compute_type=compute_type)
                _MODEL_NAME = f"fw:{model_name}"
            raw, info = _MODEL.transcribe(str(audio_path), vad_filter=True)
            segs = [
                {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()}
                for s in raw
            ]
            return {"language": info.language, "segments": segs, "engine": "faster-whisper"}
    except Exception as e:
        fw_err = e

    # 2) openai-whisper
    try:
        import whisper  # type: ignore
        with _LOCK:
            if _MODEL is None or _MODEL_NAME != f"ow:{model_name}":
                _MODEL = whisper.load_model(model_name, device="cpu" if device == "cpu" else device)
                _MODEL_NAME = f"ow:{model_name}"
            result = _MODEL.transcribe(str(audio_path))
            segs = [
                {
                    "start": round(float(s["start"]), 3),
                    "end": round(float(s["end"]), 3),
                    "text": s["text"].strip(),
                }
                for s in result.get("segments", [])
            ]
            return {
                "language": result.get("language", "unknown"),
                "segments": segs,
                "engine": "openai-whisper",
            }
    except Exception as e:
        ow_err = e

    # 3) Termux / no-ML fallback — never hard-fail for missing wheels
    return energy_chunk_transcript(audio_path)


def available_engine() -> str:
    try:
        import faster_whisper  # noqa: F401
        return "faster-whisper"
    except Exception:
        pass
    try:
        import whisper  # noqa: F401
        return "openai-whisper"
    except Exception:
        return "energy-fallback"
